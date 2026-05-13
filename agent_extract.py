"""
Layer 1: Source extraction agent (schema-driven).

For each source in sources.json:
  - look up handling rules from roles.json by `role`
  - skip if rules.do_not_extract  (style references)
  - fetch the URL (cached to outputs/raw/)
  - send content + source metadata + role rules to Claude
  - return claims tagged with source URL, role, vendor, dimensions_covered,
    editorial_signal, claim_handling, and disputed_claims_ref
  - opportunistically capture a published_date if visible on the page

The agent does NOT branch on hardcoded JSON keys. Source type is inferred
from the source's `role`; behavior comes from roles.json. Adding a new source
type means adding a new role entry, not editing this file.

Input:  sources.json, roles.json
Output: outputs/extractions_<piece-id>.json    (claims, piece-scoped via output_path())
        outputs/raw/{slug}.txt                 (cached fetched text)

CLI:
  python3 agent_extract.py                   # all extractable sources
  python3 agent_extract.py --url <url>       # one specific URL (smoke test)
"""

import argparse
import json
import sys
import time
from pathlib import Path

import anthropic
from anthropic import Anthropic

from models import EXTRACT_MODEL
from prompt_context import build_editorial_context
from utils import RAW_DIR, fetch, output_path, slug

ROOT = Path(__file__).parent
SOURCES_PATH = ROOT / "sources.json"
ROLES_PATH = ROOT / "roles.json"
OUTPUT_PATH = output_path("extractions")

MAX_TOKENS = 8000

# How each claim_handling value should shape the model's output voice.
CLAIM_HANDLING_GUIDANCE = {
    "factual_authoritative": (
        "State as fact. No hedging. The source is authoritative for these claims."
    ),
    "factual_with_attribution": (
        "State as the vendor's claim. Use phrasing like 'Vercel says X' or "
        "'according to Cloudflare's docs'. The reader should know this is the "
        "vendor's own positioning, not an independent assessment."
    ),
    "partisan_critique": (
        "State as the source's argument with explicit attribution baked into the "
        "claim text. Do NOT state as fact. Use phrasing like 'Inngest argues that X' "
        "or 'Per Inngest's blog, Y'. The reader must understand this is the source's "
        "position, not a neutral truth."
    ),
    "category_authority": (
        "State as the framework or definition the source establishes for the broader "
        "category. Useful for vocabulary and taxonomy, not for product-specific facts."
    ),
    "community_signal": (
        "Emit ONLY thematic summaries of what the community is discussing. Do NOT "
        "extract individual commenter quotes or attribute claims to specific users. "
        "Each claim should be a thematic observation like 'Developers expressed "
        "concern about X' or 'The thread surfaces tension between Y and Z'. The "
        "output is evidence that a debate exists, not what specific people said."
    ),
}

# How extraction_depth shapes how aggressive the model should be.
EXTRACTION_DEPTH_GUIDANCE = {
    "shallow":  "Stay top-level: positioning, headline features. Roughly 5-10 claims.",
    "medium":   "Substantive: key facts and design choices. Roughly 10-25 claims.",
    "deep":     "Full extraction: every concrete fact and position. No upper bound.",
    "thematic": "Only thematic summaries: 3-7 high-level themes describing what the source surfaces. No granular facts.",
}

EXTRACTION_RULES = """# Extraction rules

You are extracting claims from a single web source for a competitive comparison article. The editorial context above governs WHY claims matter; these rules govern HOW to extract them.

You will receive:
- The source's metadata (role, vendor, dimensions it covers, optional claim_summary previewing what to look for, optional disputed_claims this source takes positions on)
- Handling rules from `roles.json` (claim_handling, extraction_depth, quotable, always_attribute)
- The fetched page content

Return a JSON object of this exact shape:

{
  "discovered_published_date": "<YYYY-MM-DD if a publication date is visibly stated on the page; otherwise null>",
  "claims": [
    {
      "claim": "<one verifiable fact or position, in plain English, phrased per the claim_handling rule>",
      "verbatim_quote": "<short direct quote supporting the claim, only if quotable=true and a quote is available; otherwise null>",
      "dimensions_covered": ["<subset of the source's dimensions_covered that THIS specific claim addresses; do not just copy the source's full list>"],
      "disputed_claims_ref": ["<from the source's disputed_claims list if this claim addresses one of them; otherwise empty array>"]
    }
  ]
}

Universal rules:
- Only emit what the source actually says. Do NOT invent. Do NOT extrapolate.
- Use claim_summary as a hint about what to look for, but extract from the page CONTENT, not from claim_summary.
- Each claim must be discrete and verifiable from the source content.
- For dimensions_covered on each claim, pick only the dimensions that THIS specific claim speaks to.
- Skip vague developer-marketing phrases unless quantified.
- Output ONLY valid JSON. No prose before or after."""


def build_extract_system_prompt(comparison_id: str) -> str:
    """
    Compose the extract agent's full system prompt:
      [editorial context] -> [precedence note] -> [extraction rules]

    The per-source metadata and source content go in the user prompt
    (built per call by `build_user_prompt`).
    """
    editorial = build_editorial_context(comparison_id)
    return f"{editorial}\n\n{EXTRACTION_RULES}"


def fetch_cached(url: str) -> str:
    """Fetch a URL and cache the cleaned text. Reuses cache if present."""
    raw_path = RAW_DIR / f"{slug(url)}.txt"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if raw_path.exists():
        return raw_path.read_text()
    content = fetch(url)
    raw_path.write_text(content)
    return content


def iter_sources(config: dict):
    """
    Yield (subject_id, category, source_dict) for every source in sources.json.

    Style references and third-party perspectives have subject_id=None and
    category=None — their handling rules come from `role` alone, not position
    in the schema.
    """
    for subject_id in ("subject_a", "subject_b"):
        subject = config.get(subject_id, {})
        for category, sources in subject.get("sources", {}).items():
            for src in sources:
                yield subject_id, category, src
    for src in config.get("third_party_perspectives", []):
        yield None, None, src
    for src in config.get("style_references", []):
        yield None, None, src


def build_user_prompt(source: dict, rules: dict, subject_id, category) -> str:
    """Build the per-source extraction prompt from metadata + rules + content."""
    parts = ["=== SOURCE METADATA ==="]
    parts.append(json.dumps(source, indent=2))

    parts.append("\n=== HANDLING RULES (from roles.json) ===")
    parts.append(json.dumps(rules, indent=2))

    handling = rules.get("claim_handling")
    if handling in CLAIM_HANDLING_GUIDANCE:
        parts.append(f"\nCLAIM_HANDLING = `{handling}`:")
        parts.append(CLAIM_HANDLING_GUIDANCE[handling])

    depth = rules.get("extraction_depth")
    if depth in EXTRACTION_DEPTH_GUIDANCE:
        parts.append(f"\nEXTRACTION_DEPTH = `{depth}`:")
        parts.append(EXTRACTION_DEPTH_GUIDANCE[depth])

    if rules.get("quotable"):
        parts.append("\nQUOTABLE = true: include verbatim_quote where a short direct quote supports the claim.")
    else:
        parts.append("\nQUOTABLE = false: leave verbatim_quote as null for every claim.")

    if rules.get("always_attribute"):
        parts.append(
            "\nALWAYS_ATTRIBUTE = true: every claim MUST include explicit attribution "
            "to the source's vendor in the claim text itself."
        )

    if subject_id:
        parts.append(f"\nSUBJECT BEING DESCRIBED: {subject_id} (category: {category})")

    return "\n".join(parts)


def extract_source(client: Anthropic, source: dict, rules: dict, subject_id, category, system_prompt: str) -> dict:
    """
    Fetch + extract claims from one source.

    Returns:
      {
        "source_url": ...,
        "discovered_published_date": ...,
        "claims": [<each claim enriched with source-level tags>]
      }
    """
    url = source["url"]
    content = fetch_cached(url)

    user_prompt = build_user_prompt(source, rules, subject_id, category)
    user_prompt += "\n\n=== SOURCE CONTENT ===\n\n" + content

    resp = client.messages.create(
        model=EXTRACT_MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = resp.content[0].text
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object in response for {url}:\n{raw[:500]}")
    data = json.loads(raw[start : end + 1])

    # Denormalize source-level metadata onto each claim so the matrix layer
    # can filter/group without re-joining against sources.json.
    enriched = []
    for c in data.get("claims", []):
        enriched.append({
            "claim": c.get("claim"),
            "verbatim_quote": c.get("verbatim_quote"),
            "source_url": url,
            "role": source.get("role"),
            "vendor": source.get("vendor"),
            "subject_id": subject_id,
            "category": category,
            "dimensions_covered": c.get("dimensions_covered", []),
            "editorial_signal": source.get("editorial_signal"),
            "claim_handling": rules.get("claim_handling"),
            "disputed_claims_ref": c.get("disputed_claims_ref", []),
        })

    return {
        "source_url": url,
        "discovered_published_date": data.get("discovered_published_date"),
        "claims": enriched,
    }


def run(url_filter=None) -> dict:
    config = json.loads(SOURCES_PATH.read_text())
    rules_map = json.loads(ROLES_PATH.read_text())
    client = Anthropic()

    # Build the system prompt once per run. Editorial context is static
    # across all sources in this comparison.
    system_prompt = build_extract_system_prompt(config["id"])

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_PATH.exists():
        result = json.loads(OUTPUT_PATH.read_text())
    else:
        result = {"id": config["id"], "topic": config["topic"], "extractions": []}

    by_url = {ext["source_url"]: i for i, ext in enumerate(result["extractions"])}

    for subject_id, category, source in iter_sources(config):
        url = source["url"]
        if url_filter and url != url_filter:
            continue

        role = source.get("role")
        rules = rules_map.get(role)
        if rules is None:
            print(f"  WARN: no rules for role={role!r} on {url}; skipping")
            continue
        if rules.get("do_not_extract"):
            print(f"  SKIP (do_not_extract): {url}")
            continue

        print(f"  EXTRACT [{role}] {url}")
        try:
            extraction = extract_source(client, source, rules, subject_id, category, system_prompt)
        except (anthropic.APIError, ValueError, json.JSONDecodeError) as e:
            print(f"    [error] {e}", file=sys.stderr)
            continue

        print(f"    {len(extraction['claims'])} claims; published_date={extraction['discovered_published_date']}")

        if url in by_url:
            result["extractions"][by_url[url]] = extraction
        else:
            result["extractions"].append(extraction)
            by_url[url] = len(result["extractions"]) - 1

        OUTPUT_PATH.write_text(json.dumps(result, indent=2))
        time.sleep(0.5)

    return result


def _cli() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", help="extract only this URL (smoke test)")
    args = p.parse_args()
    run(url_filter=args.url)


if __name__ == "__main__":
    _cli()

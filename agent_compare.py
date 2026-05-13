"""
Layer 2: Comparison matrix agent.

Reads outputs/extractions.json (claims from all sources), composes a
comparison matrix per the contract in comparison_matrix.schema.md.

Pipeline:
  1. SETUP — Claude call. Given the brief and the extraction's dimension
     universe, return: dimensions in scope, tensions to surface (with type),
     and category-framing voices to acknowledge.
  2. PER-DIMENSION COMPOSITION — one Claude call per in-scope dimension.
     Returns positions, verdict, disagreement_intensity (per rubric),
     reader_decision_impact reasoning.
  3. PER-TENSION COMPOSITION — one Claude call per tension. Returns
     type-specific fields, narrative_payload (3-5 sentences in
     shared_rules.md §4 voice), draft_placement, steelman_quality,
     reader_decision_impact reasoning.
  4. ASYMMETRY QUERY — single Claude call returning detected_asymmetries.
  5. MECHANICAL POST-PROCESSING — compute brief_priority,
     evidence_density, composite_weight. Sort dimensions and tensions by
     composite_weight descending. (Tension's disagreement_intensity is
     derived from steelman_quality.)
  6. RENDER outputs/comparison_brief.md mechanically from the JSON.

Outputs (piece-scoped via output_path() in utils.py; piece-id comes from sources.json):
  outputs/comparison_matrix_<piece-id>.json  (primary, for agent_draft.py)
  outputs/comparison_brief_<piece-id>.md     (secondary, for human review)

Read order is priority signal: dimensions and editorial_tensions are emitted
in composite_weight DESCENDING order. The draft agent treats early entries as
load-bearing and later entries as supporting material.
"""

import json
import math
import re
import sys
import time
from datetime import date
from pathlib import Path

from anthropic import Anthropic

from prompt_context import build_editorial_context
from utils import output_path

ROOT             = Path(__file__).parent
EXTRACTIONS_PATH = output_path("extractions")
SOURCES_PATH     = ROOT / "sources.json"
PIECE_BRIEF_PATH = ROOT / "piece_brief.md"
MATRIX_PATH      = output_path("comparison_matrix")
BRIEF_PATH       = output_path("comparison_brief")

MODEL      = "claude-opus-4-7"      # synthesis layer; Opus per project convention
MAX_TOKENS = 8000

# Keywords used to score brief_priority for each dimension by scanning piece_brief.md.
DIMENSION_KEYWORDS = {
    "programming_model":     ["programming model", "directives", "step API", "step ID", "build-time"],
    "state_persistence":     ["state persistence", "state model", "event log", "Durable Objects", "SQLite"],
    "compute_substrate":     ["compute substrate", "where code runs", "Fluid Compute", "Workers"],
    "pricing":               ["pricing", "billing", "CPU time", "three-resource"],
    "language_support":      ["language support", "TypeScript", "Python"],
    "ai_orientation":        ["AI orientation", "AI SDK", "WorkflowAgent", "Workers AI", "Agents SDK"],
    "lock_in_portability":   ["lock-in", "portability", "Worlds architecture"],
    "observability_testing": ["observability", "testing", "tracing"],
    "limits_and_payloads":   ["limits", "payload", "MB per", "MiB"],
}


# ───────────────────────── utilities ──────────────────────────

def _parse_json_response(raw: str, context: str = "") -> dict:
    """Extract the first complete JSON object from a model response."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object in response{' for ' + context if context else ''}:\n{raw[:500]}")
    return json.loads(raw[start : end + 1])


def _read_brief_section(brief_text: str, header: str) -> str:
    """Extract the body of a section starting with the given `## header`."""
    pattern = rf"##\s+{re.escape(header)}\s*\n(.*?)(?=\n##\s|\Z)"
    m = re.search(pattern, brief_text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


# ───────────────────────── mechanical scoring ──────────────────────────

def compute_brief_priority(keywords: list, brief_text: str) -> int:
    """
    Score how prominently the dimension/tension is named in piece_brief.md.

      3 = appears in §"Editorial tensions to surface" or §Thesis or §The angle
      2 = appears in §Scope (in-scope portion)
      1 = appears anywhere else in the brief
      0 = absent
    """
    tensions  = _read_brief_section(brief_text, "Editorial tensions to surface")
    thesis    = _read_brief_section(brief_text, "Thesis")
    angle     = _read_brief_section(brief_text, "The angle")
    scope_all = _read_brief_section(brief_text, "Scope")
    in_scope  = scope_all.split("**Out of scope:**")[0] if "**Out of scope:**" in scope_all else scope_all

    high_pool = (tensions + "\n" + thesis + "\n" + angle).lower()
    mid_pool  = in_scope.lower()
    low_pool  = brief_text.lower()

    for kw in keywords:
        kwl = kw.lower()
        if kwl in high_pool:
            return 3
    for kw in keywords:
        if kw.lower() in mid_pool:
            return 2
    for kw in keywords:
        if kw.lower() in low_pool:
            return 1
    return 0


def compute_composite_weight(scoring: dict) -> float:
    """
    composite_weight = brief_priority
                     + reader_decision_impact.score
                     + 1.0 * disagreement_intensity
                     + 0.3 * log(evidence_density + 1)
    """
    bp   = scoring.get("brief_priority", 0)
    rdi  = scoring.get("reader_decision_impact", {}).get("score", 0)
    di   = scoring.get("disagreement_intensity", 0)
    ed   = scoring.get("evidence_density", 0)
    return bp + rdi + 1.0 * di + 0.3 * math.log(ed + 1)


# ───────────────────────── claim indexing ──────────────────────────

def collect_claims_for_dimension(extractions: list, dimension: str) -> dict:
    """
    Group claims tagged with this dimension by subject_id.

    Returns: {"subject_a": [<claim>...], "subject_b": [<claim>...], "third_party": [<claim>...]}
    """
    out = {"subject_a": [], "subject_b": [], "third_party": []}
    for ext in extractions:
        for c in ext.get("claims", []):
            if dimension in (c.get("dimensions_covered") or []):
                bucket = c.get("subject_id") or "third_party"
                out[bucket].append(c)
    return out


def collect_claims_for_tension(extractions: list, tension_name: str, brief_disputed_ids: list) -> list:
    """
    Pull claims relevant to a tension.

    Includes:
      - Any claim whose disputed_claims_ref intersects with the tension's
        associated disputed_claims (provided in brief_disputed_ids)
      - Any claim from a subject whose source's `disputed_claims` registers
        a stake in this tension (i.e., subject sources that defend a position
        against the dispute)
    For sub-types where disputed_claims_refs aren't applicable
    (subject_disclosure, category framing tensions), the model is given the
    full claim set in the user prompt and selects from it.
    """
    relevant = []
    for ext in extractions:
        for c in ext.get("claims", []):
            refs = set(c.get("disputed_claims_ref") or [])
            if refs & set(brief_disputed_ids):
                relevant.append(c)
    return relevant


def evidence_urls_from_claims(claims: list) -> list:
    """Distinct source URLs in insertion order."""
    seen, out = set(), []
    for c in claims:
        u = c.get("source_url")
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


# ───────────────────────── Claude calls ──────────────────────────

SETUP_RULES = """# Setup phase

Given the editorial context (shared_rules.md + piece_brief.md) above plus a list of dimensions actually present in the extracted claims, return:

{
  "dimensions_in_scope": ["<dimension_name>", ...],
  "tensions_to_surface": [
    {
      "name": "<snake_case>",
      "type": "design_disagreement_between_subjects" | "subject_disclosure" | "external_critique",
      "summary": "<one-line description>",
      "associated_disputed_claims": ["<disputed_claim ID from sources.json>", ...],
      "disclosing_subject": "subject_a" | "subject_b" | null,
      "external_voice": "<vendor name>" | null
    }
  ],
  "category_framings": [
    {
      "category": "<e.g. durable execution>",
      "canonical_voice": "<vendor name>",
      "evidence_url": "<source URL>"
    }
  ]
}

Rules:
- `dimensions_in_scope` filters the candidate dimension list against piece_brief.md §Scope. Dimensions in §"Out of scope" must be excluded.
- `tensions_to_surface` is parsed from piece_brief.md §"Editorial tensions to surface". Map each bullet to a name (snake_case identifier you choose) and type. For type=subject_disclosure, name `disclosing_subject`. For type=external_critique, name the `external_voice` vendor. Populate `associated_disputed_claims` with relevant IDs from the third_party_perspectives in sources.json (e.g., "build_time_directive_safety", "step_identity_stability").
- `category_framings` lists category authority sources (role=category_authority) with the category they speak to.
- Output ONLY valid JSON."""


def call_setup(client, system_prompt: str, dimension_universe: list, sources_excerpt: str) -> dict:
    user = (
        "Candidate dimensions present in extractions (from per-claim dimensions_covered tags):\n"
        f"{json.dumps(sorted(dimension_universe), indent=2)}\n\n"
        "Relevant excerpt from sources.json (for tension/framing identification):\n"
        f"{sources_excerpt}"
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt + "\n\n" + SETUP_RULES,
        messages=[{"role": "user", "content": user}],
    )
    return _parse_json_response(resp.content[0].text, context="setup")


DIMENSION_RULES = """# Dimension composition

Compose a single dimension entry. Return JSON of this shape:

{
  "subject_a_position": "<concise statement>",
  "subject_b_position": "<concise statement>",
  "verdict": {
    "winner": "subject_a" | "subject_b" | "no_clear_winner" | "depends_on_workload",
    "rationale": "<one sentence>"
  },
  "disagreement_intensity": 0 | 1 | 2 | 3,
  "reader_decision_impact": {
    "score": 0 | 1 | 2 | 3,
    "reasoning": "<one sentence>"
  }
}

Verdict rules (STRICT):
- Default to "depends_on_workload" whenever the dimension has any meaningful workload-conditional split.
- Reserve "subject_a"/"subject_b" for cases where one product is genuinely better across ALL reasonable workloads (rare).
- Use "no_clear_winner" only when the products are truly equivalent.
- When winner=depends_on_workload, the rationale MUST name the workload conditional explicitly. e.g., "Cloudflare wins for I/O-bound workloads; Vercel wins where payload size matters."

Disagreement intensity rubric (apply to the position pair):
  0 = positions are substantively equivalent
  1 = same outcome via different mechanism (e.g., both support X via different APIs)
  2 = different design choices, both internally coherent, no direct conflict
  3 = positions in direct conflict OR contested via active disputed_claims_ref
FLOOR: any dimension with an active disputed_claims_ref in the evidence scores AT LEAST 2.
If unsure between two scores, choose the lower (conservative).

Reader decision impact:
  Articulate in ONE SENTENCE why a reader's choice between the two products would shift based on this dimension.
  If you cannot articulate it concretely, score low (0 or 1).

Output ONLY valid JSON."""


def call_dimension_composition(client, system_prompt: str, dimension: str, claims_by_subject: dict) -> dict:
    user_parts = [
        f"DIMENSION: {dimension}\n",
        f"\n=== subject_a claims ({len(claims_by_subject['subject_a'])}) ===\n",
        json.dumps(claims_by_subject["subject_a"], indent=2),
        f"\n\n=== subject_b claims ({len(claims_by_subject['subject_b'])}) ===\n",
        json.dumps(claims_by_subject["subject_b"], indent=2),
    ]
    if claims_by_subject["third_party"]:
        user_parts += [
            f"\n\n=== third-party claims touching this dimension ({len(claims_by_subject['third_party'])}) ===\n",
            json.dumps(claims_by_subject["third_party"], indent=2),
        ]
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt + "\n\n" + DIMENSION_RULES,
        messages=[{"role": "user", "content": "".join(user_parts)}],
    )
    return _parse_json_response(resp.content[0].text, context=f"dimension={dimension}")


TENSION_RULES = """# Tension composition

Compose a single editorial tension entry. Return JSON of this shape:

{
  "subject_a_position": "<...>" | null,
  "subject_a_steelman": "<charitable case for subject_a's choice>" | null,
  "subject_b_position": "<...>" | null,
  "subject_b_steelman": "<charitable case for subject_b's choice>" | null,
  "disclosing_subject": "subject_a" | "subject_b" | null,
  "disclosure": "<what the subject discloses>" | null,
  "external_voice": "<vendor name>" | null,
  "critique_summary": "<the critique>" | null,
  "narrative_payload": "<3-5 sentence draft-ready paragraph>",
  "draft_placement": "<where this paragraph belongs in the piece>",
  "steelman_quality": "both_strong" | "asymmetric" | "weak",
  "reader_decision_impact": {
    "score": 0 | 1 | 2 | 3,
    "reasoning": "<one sentence>"
  }
}

Type-specific population:
  - design_disagreement_between_subjects: populate the four subject_*/steelman fields. Leave disclosure/external fields null.
  - subject_disclosure: populate disclosing_subject + disclosure. Leave subject_*/external fields null.
  - external_critique: populate external_voice + critique_summary. Leave subject_*/disclosure null.

NARRATIVE_PAYLOAD constraints (CRITICAL):
- 3 to 5 sentences. No more, no less.
- Voice and register per shared_rules.md §4 (in editorial context above) AND piece_brief.md §Voice register.
- This paragraph WILL APPEAR in the final piece. Write it as draft prose, not as analysis ABOUT the tension.
- The draft agent will insert this verbatim or with minimal edits and write only connective tissue around it.
- For two-sided tensions: present both positions with charitable framing. Do not resolve.
- For external_critique: name the external voice explicitly in the prose. Use phrasing like "Inngest argues that..." per shared_rules.md §5.
- For subject_disclosure: name the disclosing subject. Frame the disclosure honestly without minimizing it.
- No marketing adjectives (banned list in shared_rules.md §4). Active voice. Concrete and specific.

draft_placement: name the section where this paragraph fits, referencing piece_brief.md §Structure.
steelman_quality: judge whether both sides have compelling evidence (both_strong), one side dominates (asymmetric), or the tension is weak (weak).

Output ONLY valid JSON."""


def call_tension_composition(client, system_prompt: str, tension_spec: dict, evidence_claims: list) -> dict:
    user = (
        f"TENSION: {tension_spec['name']}\n"
        f"TYPE: {tension_spec['type']}\n"
        f"SUMMARY (from brief): {tension_spec.get('summary', '')}\n"
        f"DISCLOSING_SUBJECT (if applicable): {tension_spec.get('disclosing_subject')}\n"
        f"EXTERNAL_VOICE (if applicable): {tension_spec.get('external_voice')}\n"
        f"ASSOCIATED_DISPUTED_CLAIMS: {tension_spec.get('associated_disputed_claims', [])}\n\n"
        f"=== Evidence claims ({len(evidence_claims)}) ===\n"
        f"{json.dumps(evidence_claims, indent=2)}"
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt + "\n\n" + TENSION_RULES,
        messages=[{"role": "user", "content": user}],
    )
    return _parse_json_response(resp.content[0].text, context=f"tension={tension_spec['name']}")


ASYMMETRY_RULES = """# Asymmetry detection

Identify structural asymmetries between subject_a and subject_b across the corpus. Look for:

  - concept_hierarchy: one subject documents a concept where the other treats it as implicit (or files it under a different category)
  - terminology: divergent vocabulary for the same underlying thing
  - evidence_density_imbalance: dimensions where one subject has much richer documentation than the other
  - feature_framing_difference: same feature framed differently (e.g., one as a primitive, the other as an SDK convenience)

Return JSON:
{
  "detected_asymmetries": [
    {
      "type": "concept_hierarchy" | "terminology" | "evidence_density_imbalance" | "feature_framing_difference",
      "description": "<structured statement>",
      "subject_a_view": "<...>",
      "subject_b_view": "<...>",
      "implication": "<what this asymmetry reveals about the products>",
      "evidence_refs": ["<source URL>", ...],
      "draft_treatment": "<how the draft should surface this — prose, table footnote, structural choice>"
    }
  ]
}

Rules:
- Asymmetries are FINDINGS per shared_rules.md §6, not noise. Surface them.
- Aim for 3-6 asymmetries. Quality over quantity.
- Do NOT include asymmetries that are also editorial_tensions; those live elsewhere.
- Output ONLY valid JSON."""


def call_asymmetry_detection(client, system_prompt: str, sources_summary: str, claim_summary: str) -> list:
    user = (
        "Sources summary (organized by subject and category):\n"
        f"{sources_summary}\n\n"
        "Claim distribution summary (by subject and dimension):\n"
        f"{claim_summary}"
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt + "\n\n" + ASYMMETRY_RULES,
        messages=[{"role": "user", "content": user}],
    )
    parsed = _parse_json_response(resp.content[0].text, context="asymmetry")
    return parsed.get("detected_asymmetries", [])


# ───────────────────────── helpers for setup/asymmetry inputs ──────────────────────────

def dimension_universe(extractions: list) -> list:
    out = set()
    for ext in extractions:
        for c in ext.get("claims", []):
            out.update(c.get("dimensions_covered") or [])
    return sorted(out)


def sources_excerpt(sources: dict) -> str:
    """Compact sources.json excerpt for the setup call's tension/framing identification."""
    return json.dumps({
        "subject_a": sources["subject_a"],
        "subject_b": sources["subject_b"],
        "third_party_perspectives": sources["third_party_perspectives"],
    }, indent=2)


def sources_summary_for_asymmetry(sources: dict) -> str:
    """Subject-by-category view: what each subject documents and how it's structured."""
    lines = []
    for subj_key in ("subject_a", "subject_b"):
        subj = sources[subj_key]
        lines.append(f"{subj_key} = {subj['vendor']} ({subj['name']}):")
        for cat, items in subj["sources"].items():
            urls = [it["url"] if isinstance(it, dict) else it for it in items]
            lines.append(f"  {cat}: {len(urls)} source(s)")
            for u in urls:
                lines.append(f"    - {u}")
    return "\n".join(lines)


def claim_summary_by_subject_dimension(extractions: list) -> str:
    """Subject × dimension claim count grid for the asymmetry detector."""
    counts = {}
    for ext in extractions:
        for c in ext.get("claims", []):
            subj = c.get("subject_id") or "third_party"
            for dim in c.get("dimensions_covered") or []:
                counts.setdefault(dim, {"subject_a": 0, "subject_b": 0, "third_party": 0})
                counts[dim][subj] += 1
    lines = ["dimension                | subject_a | subject_b | third_party"]
    lines.append("-" * 65)
    for dim in sorted(counts):
        c = counts[dim]
        lines.append(f"{dim:<24} | {c['subject_a']:>9} | {c['subject_b']:>9} | {c['third_party']:>11}")
    return "\n".join(lines)


# ───────────────────────── matrix assembly ──────────────────────────

def disputed_claims_active_in(claims_by_subject: dict) -> list:
    refs = set()
    for bucket in claims_by_subject.values():
        for c in bucket:
            refs.update(c.get("disputed_claims_ref") or [])
    return sorted(refs)


def assemble_dimension_entry(dim: str, claims_by_subject: dict, model_output: dict, brief_text: str) -> dict:
    """Stitch model output + mechanical scoring into a full dimension entry."""
    subject_a_urls = evidence_urls_from_claims(claims_by_subject["subject_a"])
    subject_b_urls = evidence_urls_from_claims(claims_by_subject["subject_b"])
    evidence_density = len(subject_a_urls) + len(subject_b_urls)

    # Apply the disputed_claims floor for disagreement_intensity
    di = int(model_output.get("disagreement_intensity", 0))
    if disputed_claims_active_in(claims_by_subject):
        di = max(di, 2)

    bp = compute_brief_priority(DIMENSION_KEYWORDS.get(dim, [dim.replace("_", " ")]), brief_text)

    scoring = {
        "brief_priority":         bp,
        "evidence_density":       evidence_density,
        "disagreement_intensity": di,
        "reader_decision_impact": model_output.get("reader_decision_impact", {"score": 0, "reasoning": ""}),
    }
    scoring["composite_weight"] = round(compute_composite_weight(scoring), 3)

    return {
        "subject_a_position": model_output.get("subject_a_position", ""),
        "subject_b_position": model_output.get("subject_b_position", ""),
        "verdict":            model_output.get("verdict", {"winner": "no_clear_winner", "rationale": ""}),
        "evidence_refs":      {"subject_a": subject_a_urls, "subject_b": subject_b_urls},
        "scoring":            scoring,
    }


def assemble_tension_entry(tension_spec: dict, evidence_claims: list, model_output: dict, brief_text: str) -> dict:
    """Stitch model output + mechanical scoring into a full tension entry."""
    evidence_urls = evidence_urls_from_claims(evidence_claims)

    # disagreement_intensity for tensions derives from steelman_quality
    sq = model_output.get("steelman_quality", "weak")
    di = {"both_strong": 3, "asymmetric": 2, "weak": 1}.get(sq, 1)

    bp = compute_brief_priority([tension_spec["name"].replace("_", " "), tension_spec.get("summary", "")], brief_text)
    # Tensions named in piece_brief.md §"Editorial tensions to surface" should land at 3
    bp = max(bp, 3 if "tension" in tension_spec.get("source", "brief") else bp)

    scoring = {
        "brief_priority":         bp,
        "evidence_density":       len(evidence_urls),
        "disagreement_intensity": di,
        "reader_decision_impact": model_output.get("reader_decision_impact", {"score": 0, "reasoning": ""}),
    }
    scoring["composite_weight"] = round(compute_composite_weight(scoring), 3)

    return {
        "name":                 tension_spec["name"],
        "type":                 tension_spec["type"],
        "summary":              tension_spec.get("summary", ""),
        "subject_a_position":   model_output.get("subject_a_position"),
        "subject_a_steelman":   model_output.get("subject_a_steelman"),
        "subject_b_position":   model_output.get("subject_b_position"),
        "subject_b_steelman":   model_output.get("subject_b_steelman"),
        "disclosing_subject":   model_output.get("disclosing_subject"),
        "disclosure":           model_output.get("disclosure"),
        "external_voice":       model_output.get("external_voice"),
        "critique_summary":     model_output.get("critique_summary"),
        "evidence_refs":        evidence_urls,
        "disputed_claims_refs": tension_spec.get("associated_disputed_claims", []),
        "narrative_payload":    model_output.get("narrative_payload", ""),
        "draft_placement":      model_output.get("draft_placement", ""),
        "steelman_quality":     sq,
        "scoring":              scoring,
    }


# ───────────────────────── brief renderer ──────────────────────────

def render_brief_md(matrix: dict) -> str:
    """Render comparison_brief.md from the matrix JSON. Pure template, no model call."""
    lines = []
    lines.append(f"# Comparison Brief: {matrix['topic']}")
    lines.append(f"\n> Auto-rendered from `comparison_matrix.json`. Edit the matrix, not this file.")
    lines.append(f"> Generated: {matrix['generated_at']}")

    s = matrix["source_summary"]
    lines.append(f"\n**Source summary:** {s['subject_a']['name']} ({s['subject_a']['source_count']} sources, {s['subject_a']['claim_count']} claims) · "
                 f"{s['subject_b']['name']} ({s['subject_b']['source_count']} sources, {s['subject_b']['claim_count']} claims) · "
                 f"third-party {s['third_party_claim_count']} claims · total {s['total_claims']}")

    # Editorial tensions first — most editorially load-bearing
    lines.append("\n## Editorial tensions (in priority order)")
    for t in matrix["editorial_tensions"]:
        lines.append(f"\n### {t['name']}  *(weight {t['scoring']['composite_weight']}, {t['type']})*")
        lines.append(f"\n**Summary:** {t['summary']}")
        if t["type"] == "design_disagreement_between_subjects":
            lines.append(f"\n**{matrix['source_summary']['subject_a']['vendor']}'s position:** {t['subject_a_position']}")
            lines.append(f"\n**Steelman:** {t['subject_a_steelman']}")
            lines.append(f"\n**{matrix['source_summary']['subject_b']['vendor']}'s position:** {t['subject_b_position']}")
            lines.append(f"\n**Steelman:** {t['subject_b_steelman']}")
        elif t["type"] == "subject_disclosure":
            who = matrix['source_summary'][t['disclosing_subject']]['vendor'] if t['disclosing_subject'] else "—"
            lines.append(f"\n**Disclosing subject:** {who}")
            lines.append(f"\n**Disclosure:** {t['disclosure']}")
        elif t["type"] == "external_critique":
            lines.append(f"\n**External voice:** {t['external_voice']}")
            lines.append(f"\n**Critique:** {t['critique_summary']}")
        lines.append(f"\n**Steelman quality:** {t['steelman_quality']}")
        lines.append(f"\n**Draft placement:** {t['draft_placement']}")
        lines.append(f"\n**Narrative payload (draft-ready, insert verbatim or near-verbatim):**\n\n> {t['narrative_payload']}")
        lines.append(f"\n**Reader decision impact:** {t['scoring']['reader_decision_impact']['score']}/3 — {t['scoring']['reader_decision_impact']['reasoning']}")
        if t["evidence_refs"]:
            lines.append(f"\n**Evidence:** {', '.join(t['evidence_refs'])}")

    # Then dimensions in priority order
    lines.append("\n## Dimensions (in priority order)")
    for dim_name, d in matrix["dimensions"].items():
        lines.append(f"\n### {dim_name}  *(weight {d['scoring']['composite_weight']})*")
        lines.append(f"\n**{matrix['source_summary']['subject_a']['vendor']}:** {d['subject_a_position']}")
        lines.append(f"\n**{matrix['source_summary']['subject_b']['vendor']}:** {d['subject_b_position']}")
        lines.append(f"\n**Verdict:** {d['verdict']['winner']} — {d['verdict']['rationale']}")
        lines.append(f"\n**Reader decision impact:** {d['scoring']['reader_decision_impact']['score']}/3 — {d['scoring']['reader_decision_impact']['reasoning']}")
        sc = d['scoring']
        lines.append(f"\n**Scoring:** brief_priority={sc['brief_priority']} · evidence_density={sc['evidence_density']} · disagreement_intensity={sc['disagreement_intensity']}")

    if matrix.get("category_framing"):
        lines.append("\n## Category framing")
        for cf in matrix["category_framing"]:
            lines.append(f"\n- **{cf['canonical_voice']}** on *{cf['category']}*: {cf['framing_summary']}")
            lines.append(f"  Draft placement: {cf['draft_placement']}")

    if matrix.get("detected_asymmetries"):
        lines.append("\n## Detected asymmetries")
        for a in matrix["detected_asymmetries"]:
            lines.append(f"\n### {a['type']}")
            lines.append(f"\n{a['description']}")
            lines.append(f"\n- {matrix['source_summary']['subject_a']['vendor']}: {a['subject_a_view']}")
            lines.append(f"- {matrix['source_summary']['subject_b']['vendor']}: {a['subject_b_view']}")
            lines.append(f"\n**Implication:** {a['implication']}")
            lines.append(f"\n**Draft treatment:** {a['draft_treatment']}")

    return "\n".join(lines) + "\n"


# ───────────────────────── orchestrator ──────────────────────────

def run() -> dict:
    extractions_doc = json.loads(EXTRACTIONS_PATH.read_text())
    sources         = json.loads(SOURCES_PATH.read_text())
    brief_text      = PIECE_BRIEF_PATH.read_text()
    extractions     = extractions_doc["extractions"]

    client = Anthropic()
    system_prompt = build_editorial_context(sources["id"])

    # Source summary (mechanical)
    def _count_for(subject_key):
        urls = set()
        for cat in sources[subject_key]["sources"].values():
            for it in cat:
                urls.add(it["url"] if isinstance(it, dict) else it)
        claim_count = sum(len(ext["claims"]) for ext in extractions if any(c.get("subject_id") == subject_key for c in ext["claims"]))
        return len(urls), claim_count

    sa_src, sa_claims = _count_for("subject_a")
    sb_src, sb_claims = _count_for("subject_b")
    third_party_claims = sum(len(ext["claims"]) for ext in extractions if all(c.get("subject_id") is None for c in ext["claims"]))
    total_claims = sum(len(ext["claims"]) for ext in extractions)

    matrix = {
        "id":           sources["id"],
        "topic":        sources["topic"],
        "generated_at": str(date.today()),
        "source_summary": {
            "subject_a": {"vendor": sources["subject_a"]["vendor"], "name": sources["subject_a"]["name"],
                          "source_count": sa_src, "claim_count": sa_claims},
            "subject_b": {"vendor": sources["subject_b"]["vendor"], "name": sources["subject_b"]["name"],
                          "source_count": sb_src, "claim_count": sb_claims},
            "third_party_claim_count": third_party_claims,
            "total_claims":            total_claims,
        },
        "dimensions":           {},
        "editorial_tensions":   [],
        "category_framing":     [],
        "detected_asymmetries": [],
    }

    # ─── Pass 1: setup ───
    print("[1/4] Setup: identifying in-scope dimensions, tensions, category framings...")
    dim_universe = dimension_universe(extractions)
    setup = call_setup(client, system_prompt, dim_universe, sources_excerpt(sources))
    dimensions_in_scope = setup["dimensions_in_scope"]
    tensions_to_surface = setup["tensions_to_surface"]
    print(f"      {len(dimensions_in_scope)} dimensions, {len(tensions_to_surface)} tensions, {len(setup.get('category_framings', []))} framings")

    # ─── Pass 2a: per-dimension composition ───
    print("[2/4] Per-dimension composition...")
    for dim in dimensions_in_scope:
        claims_by_subject = collect_claims_for_dimension(extractions, dim)
        if not (claims_by_subject["subject_a"] or claims_by_subject["subject_b"]):
            print(f"      SKIP {dim} (no evidence on either side)")
            continue
        print(f"      compose {dim}  (a={len(claims_by_subject['subject_a'])}, b={len(claims_by_subject['subject_b'])})")
        try:
            model_out = call_dimension_composition(client, system_prompt, dim, claims_by_subject)
        except Exception as e:
            print(f"        [error] {e}", file=sys.stderr)
            continue
        matrix["dimensions"][dim] = assemble_dimension_entry(dim, claims_by_subject, model_out, brief_text)
        time.sleep(0.5)

    # ─── Pass 2b: per-tension composition ───
    print("[3/4] Per-tension composition...")
    for spec in tensions_to_surface:
        spec["source"] = "brief"   # for brief_priority floor
        evidence = collect_claims_for_tension(extractions, spec["name"], spec.get("associated_disputed_claims", []))
        # If type=subject_disclosure and no disputed_claims_refs hit, fall back to subject's own claims
        if not evidence and spec["type"] == "subject_disclosure" and spec.get("disclosing_subject"):
            evidence = [c for ext in extractions for c in ext["claims"]
                        if c.get("subject_id") == spec["disclosing_subject"]]
        # Bound the evidence (some tensions sweep widely)
        evidence = evidence[:60]
        print(f"      compose tension '{spec['name']}'  ({len(evidence)} evidence claims)")
        try:
            model_out = call_tension_composition(client, system_prompt, spec, evidence)
        except Exception as e:
            print(f"        [error] {e}", file=sys.stderr)
            continue
        matrix["editorial_tensions"].append(assemble_tension_entry(spec, evidence, model_out, brief_text))
        time.sleep(0.5)

    # ─── Category framing (mechanical from setup) ───
    for cf in setup.get("category_framings", []):
        cf_claims = [c for ext in extractions for c in ext["claims"] if c.get("source_url") == cf.get("evidence_url")]
        framing_summary = "; ".join((c.get("claim") or "") for c in cf_claims[:3])[:300]
        matrix["category_framing"].append({
            "category":         cf["category"],
            "canonical_voice":  cf["canonical_voice"],
            "framing_summary":  framing_summary or "(no claims extracted)",
            "evidence_refs":    [cf["evidence_url"]] if cf.get("evidence_url") else [],
            "draft_placement":  "Lead, parenthetical when defining the category",
        })

    # ─── Pass 3: asymmetry query ───
    print("[4/4] Asymmetry detection...")
    try:
        matrix["detected_asymmetries"] = call_asymmetry_detection(
            client, system_prompt,
            sources_summary_for_asymmetry(sources),
            claim_summary_by_subject_dimension(extractions),
        )
        print(f"      {len(matrix['detected_asymmetries'])} asymmetries detected")
    except Exception as e:
        print(f"        [error] {e}", file=sys.stderr)

    # ─── Sort by composite_weight desc ───
    matrix["dimensions"] = dict(sorted(
        matrix["dimensions"].items(),
        key=lambda kv: kv[1]["scoring"]["composite_weight"], reverse=True,
    ))
    matrix["editorial_tensions"].sort(key=lambda t: t["scoring"]["composite_weight"], reverse=True)

    # ─── Write outputs ───
    MATRIX_PATH.parent.mkdir(parents=True, exist_ok=True)
    MATRIX_PATH.write_text(json.dumps(matrix, indent=2))
    BRIEF_PATH.write_text(render_brief_md(matrix))
    print(f"\nWrote {MATRIX_PATH}")
    print(f"Wrote {BRIEF_PATH}")

    return matrix


if __name__ == "__main__":
    run()

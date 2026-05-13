"""
Editorial context loader.

Single source of truth for assembling the editorial context block injected
into every agent's system prompt.

Two public functions:

  build_editorial_context(comparison_id) -> str
      Used by agent_extract.py and agent_compare.py. Loads shared_rules.md
      and piece_brief.md, resolves ${variable} placeholders against
      sources.json, joins with the precedence note. Does NOT include the
      voice anchor — voice anchor is draft-only.

  build_draft_editorial_context(comparison_id, mode) -> str
      Used by agent_draft.py only. Wraps build_editorial_context() and
      appends a voice anchor block selected per the rules in
      sources.json + piece_brief.md. Mode-specific framing for the
      composition vs. revision pass.

Convention: `subject_a` is the commissioning vendor. ${primary_subject_vendor}
resolves to subject_a.vendor; ${other_subject_vendor} resolves to
subject_b.vendor.
"""

import json
import re
import string
from pathlib import Path

from utils import RAW_DIR, fetch, slug

ROOT = Path(__file__).parent
SOURCES_PATH       = ROOT / "sources.json"
SHARED_RULES_PATH  = ROOT / "shared_rules.md"
PIECE_BRIEF_PATH   = ROOT / "piece_brief.md"

PRECEDENCE_NOTE = (
    "When piece_brief.md and shared_rules.md conflict, piece_brief.md wins at "
    "the rule level: its specifics override but do not replace shared rules "
    "where the brief is silent. roles.json is the lookup table for how to "
    "handle individual sources by role."
)

COMPOSE_ANCHOR_FRAMING = (
    "The following is a published piece from the same content family as the piece you're "
    "writing. Match its cadence, register, and texture — sentence variety, paragraph length, "
    "the way concrete details anchor abstract claims. Don't borrow content, copy structure, "
    "or reuse phrases. The editorial rules above override the anchor when they diverge. "
    "Before writing each major section, re-read the corresponding section of the anchor "
    "article — match its rhythm specifically for that section type."
)

REVISE_ANCHOR_FRAMING = (
    "The voice anchor below was used during composition. Compare your draft against it for "
    "cadence and texture drift; revise where the draft has slipped."
)


def _bindings_from_sources(sources: dict) -> dict:
    """Derive ${variable} bindings. subject_a = commissioning vendor, by convention."""
    return {
        "primary_subject_vendor": sources["subject_a"]["vendor"],
        "other_subject_vendor":   sources["subject_b"]["vendor"],
        "subject_a":              sources["subject_a"]["name"],
        "subject_b":              sources["subject_b"]["name"],
    }


def build_editorial_context(comparison_id: str) -> str:
    """
    Build the editorial context block for a system prompt (no voice anchor).

    Args:
        comparison_id: must match `sources["id"]`. Sanity check that the agent
            and the sources file agree on which comparison is being run.

    Returns:
        A formatted block:
          # Editorial context
          ## shared_rules.md (with ${...} resolved)
          ## piece_brief.md (verbatim)
          # Precedence
    """
    sources = json.loads(SOURCES_PATH.read_text())
    if sources["id"] != comparison_id:
        raise ValueError(
            f"comparison_id mismatch: requested {comparison_id!r}, "
            f"sources.json declares {sources['id']!r}"
        )

    bindings = _bindings_from_sources(sources)
    shared_rules_raw = SHARED_RULES_PATH.read_text()
    shared_rules = string.Template(shared_rules_raw).safe_substitute(bindings)
    piece_brief = PIECE_BRIEF_PATH.read_text()

    return (
        "# Editorial context\n\n"
        "These two documents define the editorial standards for this "
        "comparison piece. They apply to every claim, dimension, and paragraph "
        "this pipeline produces.\n\n"
        "## shared_rules.md (universal across all comparison pieces)\n\n"
        f"{shared_rules}\n\n"
        "## piece_brief.md (specifics for this comparison)\n\n"
        f"{piece_brief}\n\n"
        "# Precedence\n\n"
        f"{PRECEDENCE_NOTE}"
    )


# ───────────────────────── voice anchor (draft only) ──────────────────────────

def _parse_voice_anchor_section(brief_text: str) -> dict:
    """
    Parse the '## Voice anchor' section of piece_brief.md into a dict.
    Returns {} if the section is absent.

    Note: `register` is parsed and returned but not used by selection logic.
    Reserved for future filtering when the corpus contains references with
    divergent registers. Explicit reservation, not a no-op filter.
    """
    pattern = r"##\s+Voice anchor\s*\n(.*?)(?=\n##\s|\Z)"
    m = re.search(pattern, brief_text, re.DOTALL)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip().lower().replace(" ", "_")] = v.strip()
    return out


def _select_voice_anchor(brief_anchor: dict, style_refs: list) -> dict:
    """
    Select the best-matching style_reference per the rules locked in step 1:
      - Exact match on genre AND subject_domain wins.
      - If multiple matches: primary_voice_anchor=true is the tiebreaker;
        otherwise first in array order.
      - If zero matches: fall back to primary_voice_anchor=true (universal
        fallback). Closest-but-weak is worse than the explicit primary.
    """
    primaries = [r for r in style_refs if r.get("primary_voice_anchor") is True]
    if len(primaries) > 1:
        raise ValueError(
            f"Schema violation: {len(primaries)} style_references have "
            "primary_voice_anchor=true; expected exactly one."
        )
    primary = primaries[0] if primaries else None

    genre          = brief_anchor.get("genre")
    subject_domain = brief_anchor.get("subject_domain")

    matches = [
        r for r in style_refs
        if r.get("genre") == genre and r.get("subject_domain") == subject_domain
    ]

    if matches:
        if len(matches) == 1:
            return matches[0]
        primary_in_matches = [r for r in matches if r.get("primary_voice_anchor")]
        return primary_in_matches[0] if primary_in_matches else matches[0]

    # Zero matches → fall back to primary (universal tiebreaker)
    if primary is None:
        raise ValueError(
            f"No style_reference matches genre={genre!r} subject_domain={subject_domain!r}, "
            "and no primary_voice_anchor is set. Cannot select a voice anchor."
        )
    return primary


def _load_anchor_content(url: str) -> str:
    """
    Read cached anchor content; fetch and cache if missing. Style references
    aren't fetched by the extract agent (do_not_extract=true), so the first
    draft run after a sources.json change incurs a one-time fetch (~2-5s).
    """
    cache_path = RAW_DIR / f"{slug(url)}.txt"
    if cache_path.exists():
        return cache_path.read_text()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    content = fetch(url)
    cache_path.write_text(content)
    return content


def _render_voice_anchor_block(anchor: dict, content: str, mode: str) -> str:
    """Compose the voice anchor block with mode-specific framing."""
    if mode == "compose":
        framing = COMPOSE_ANCHOR_FRAMING
    elif mode == "revise":
        framing = REVISE_ANCHOR_FRAMING
    else:
        raise ValueError(f"Unknown voice anchor mode {mode!r}; expected 'compose' or 'revise'.")
    return (
        "# Voice anchor\n\n"
        f"{framing}\n\n"
        f"**Selected:** {anchor['url']} "
        f"(genre={anchor.get('genre', 'unknown')}, "
        f"primary_voice_anchor={anchor.get('primary_voice_anchor', False)})\n\n"
        "---\n\n"
        f"{content}"
    )


def build_draft_editorial_context(comparison_id: str, mode: str = "compose") -> str:
    """
    Editorial context + selected voice anchor with mode-specific framing.
    Draft agent only — extract and compare must continue using
    build_editorial_context() so voice anchor doesn't leak into extraction.

    Args:
        comparison_id: must match sources["id"].
        mode: "compose" — composition framing (re-read each section for rhythm)
              "revise"  — revision framing (compare draft for drift)

    Returns:
        build_editorial_context(comparison_id) output, plus an appended
        voice anchor block.
    """
    base = build_editorial_context(comparison_id)

    sources = json.loads(SOURCES_PATH.read_text())
    if sources["id"] != comparison_id:
        raise ValueError(
            f"comparison_id mismatch: requested {comparison_id!r}, "
            f"sources.json declares {sources['id']!r}"
        )

    brief_anchor = _parse_voice_anchor_section(PIECE_BRIEF_PATH.read_text())
    style_refs   = sources.get("style_references") or []
    if not style_refs:
        raise ValueError("No style_references in sources.json; cannot select voice anchor.")

    selected = _select_voice_anchor(brief_anchor, style_refs)
    content  = _load_anchor_content(selected["url"])
    block    = _render_voice_anchor_block(selected, content, mode)

    return f"{base}\n\n{block}"

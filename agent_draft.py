"""
Layer 3: Draft writer agent.

Architecture: single-pass composition with built-in revision.
  Call 1 — Compose. Loads editorial context + matrix + brief, produces the
           full draft in one composition.
  Call 2 — Revise. Self-reviews against the reader test and anti-patterns,
           produces revision notes and the revised final draft.

The framing is "you have an editorial spec, now write the piece" — not
"render this structure." The matrix is the editorial spec; the brief is the
reading guide; piece_brief.md (in editorial context) is the structural
reference. The agent interprets these inputs into prose, not transcribes
them. Voice is single-sourced: both passes load shared_rules + piece_brief
via the same prompt_context helper the compare agent used.

Outputs (piece-scoped via output_path() in utils.py; piece-id comes from sources.json):
  outputs/agent_draft_<piece-id>.md                  (revised final, for the publishing pipeline)
  outputs/agent_draft_revision_notes_<piece-id>.md   (agent's self-review notes)
"""

import json
import sys
from pathlib import Path

from anthropic import Anthropic

from models import DRAFT_MODEL
from prompt_context import build_draft_editorial_context
from utils import output_path

ROOT            = Path(__file__).parent
MATRIX_PATH     = output_path("comparison_matrix")
BRIEF_PATH      = output_path("comparison_brief")
SOURCES_PATH    = ROOT / "sources.json"
PIECE_BRIEF_PATH = ROOT / "piece_brief.md"

FINAL_PATH      = output_path("agent_draft")
REV_NOTES_PATH  = output_path("agent_draft_revision_notes")

MAX_TOKENS_COMPOSE = 8000
MAX_TOKENS_REVISE  = 16000   # holds revision notes + revised draft


COMPOSITION_RULES = """# Composition

You are composing a complete comparison piece for the Vercel knowledge base. It should read as a sibling to vercel-vs-fastly and vercel-waf-vs-cloudflare-waf — confidently Vercel-leaning, structurally fair, written for developers who are choosing.

You have three inputs:
- The COMPARISON MATRIX (JSON, structured editorial spec)
- The COMPARISON BRIEF (markdown, the matrix rendered for humans — same content, easier to scan)
- The editorial context above (shared_rules.md + piece_brief.md), which gives you universal principles and per-piece specifics

Your job is to interpret these inputs into prose. Not transcription, not rendering — interpretation. The matrix IS the editorial spec; the brief IS the reading guide; piece_brief.md IS the structural reference. Trust them.

## Four constraints that matter — with reasoning

1. **`narrative_payload` fields in the matrix are draft-ready prose.** They were generated under the same voice register as the rest of the piece (shared_rules.md §4 + piece_brief.md voice). When the matrix has a tension with a `narrative_payload`, insert it at the location its `draft_placement` field indicates — verbatim or near-verbatim. They are not rough material to rewrite. They are the editorial passages that need the most care, and the comparison agent already wrote them with the full evidence in working memory.

2. **Tables earn their place.** Use them where they communicate more cleanly than prose: capability comparisons (programming model, state, limits, AI orientation), the pricing comparison, and the "When to choose" decision table. Don't force tables where prose works better. The pricing comparison should be a table because billing axes don't compress well into prose. The lead should NOT be a table because the architectural fork is a paragraph-shaped idea.

3. **Verdicts spine the "When to choose" section.** Each dimension's `verdict.rationale` and `reader_decision_impact.reasoning` is the source for one or more rows in the decision table. Workload rows should be specific — "AI agents passing >1MB of context between steps," not "AI workloads." Use the matrix's `composite_weight` ordering as the natural priority signal: heavier-weighted dimensions warrant more decision rows.

4. **Temporal goes once, in the lead, parenthetically.** The `category_framing` entry for Temporal exists to acknowledge category vocabulary, not to expand into a third subject. One mention. One parenthetical. Not in the body sections.

## Voice — why, not just what

You're writing for developers who read engineering blogs, not marketing pages. They trust voices that name specific tradeoffs over voices that promise everything works seamlessly. Concrete numbers, named mechanics, declarative claims when evidence supports them. The banned adjective list in shared_rules.md §4 is not a stylistic preference — it's a credibility signal. Marketing language tells the reader the writer doesn't trust the evidence to do the work.

When you write about a Cloudflare advantage, name it cleanly without hedging. When you write about a Vercel advantage, name it cleanly without overclaiming. The structure does the work of fairness; the prose can be confident.

## Output

Produce the complete piece in markdown. No preamble, no meta-commentary, no JSON wrapper. Just the article — title through closing CTA."""


REVISION_RULES = """# Revision

You just composed the draft above. Now revise it.

Your job in this pass is editorial self-review, not rewriting from scratch. Read the draft once with the reader test in mind. Read it again with the anti-pattern list in mind. Note what would change and why. Then produce the revised version.

## Reader test (actionable form, from shared_rules.md §9)

A developer reading the piece should come away able to:

1. Make a decision about which product fits their workload.
2. Explain the architectural difference between the products in their own words.
3. Articulate at least one thing the non-commissioning product (Cloudflare) does better than the commissioning one (Vercel).

If your honest read says the draft fails any of these, revise the relevant section before final output.

## Anti-pattern check

Review against the universal anti-patterns enumerated in shared_rules.md §8 (loaded in editorial context above):
- False balance ("both products have tradeoffs")
- Universal winner ("Product X is better")
- Marketing copy with attribution
- Feature inventory disguised as comparison
- Hedging that dissolves real differences
- Burying the architectural fork
- Ignoring the category authority

And the piece-specific anti-patterns in piece_brief.md §"Anti-patterns specific to this piece":
- Don't write a philosophical essay
- Don't bury the architectural fork
- Don't false-balance into mush
- Don't omit the "where each goes deeper" sections
- Don't try to crown a universal winner
- Don't skip the cost section
- Don't try to compare to Temporal in depth

Name violations explicitly in the revision notes. Then revise.

## Output format

Output exactly this two-section format. The delimiters must appear on their own lines, with the exact spelling shown:

=== REVISION_NOTES ===
[Specific notes on what you found in self-review and what you changed. Reference sections and paragraphs concretely: "Section 3, paragraph 2 — softened a 'Vercel wins' claim to acknowledge Cloudflare's edge advantage." If you found nothing material to revise, say so honestly. Do not pad. Do not restate the rules.]

=== FINAL_DRAFT ===
[The revised complete piece in markdown. Title through closing CTA. This is the version that will be published.]

## Reader test (full editorial form, from piece_brief.md §Reader test)

A developer reading this should come away able to make a decision. Specifically: they should know which product fits their workload type, why, and what the meaningful tradeoffs are. They should not feel sold to. They should feel guided.

A weaker version of the piece would summarize feature parity and conclude "both are good choices, depending on your needs." A stronger version names the architectural fork in the lead, walks through dimensions where the two products meaningfully differ, gives both products their due where they go deeper, and closes with specific workload-by-workload recommendations."""


# ───────────────────────── utilities ──────────────────────────

def _parse_revision_response(raw: str) -> tuple:
    """Split the delimited response into (revision_notes, final_draft)."""
    notes_marker = "=== REVISION_NOTES ==="
    draft_marker = "=== FINAL_DRAFT ==="

    notes_idx = raw.find(notes_marker)
    draft_idx = raw.find(draft_marker)

    if notes_idx == -1 or draft_idx == -1 or draft_idx < notes_idx:
        raise ValueError(
            f"Could not parse revision response (notes_marker found: {notes_idx != -1}, "
            f"draft_marker found: {draft_idx != -1}). First 800 chars:\n{raw[:800]}"
        )

    notes = raw[notes_idx + len(notes_marker):draft_idx].strip()
    draft = raw[draft_idx + len(draft_marker):].strip()
    return notes, draft


# ───────────────────────── Claude calls ──────────────────────────

def compose_draft(client: Anthropic, system_prompt: str, matrix: dict, brief_md: str) -> str:
    """Call 1: produce the full draft from matrix + brief."""
    user = (
        "## Inputs\n\n"
        "### Comparison matrix (JSON — structured editorial spec)\n\n"
        f"```json\n{json.dumps(matrix, indent=2)}\n```\n\n"
        "### Comparison brief (markdown — same content, rendered for human review)\n\n"
        f"{brief_md}\n\n"
        "## Task\n\n"
        "Compose the complete comparison piece in markdown per the composition rules above. Output only the markdown."
    )
    resp = client.messages.create(
        model=DRAFT_MODEL,
        max_tokens=MAX_TOKENS_COMPOSE,
        system=system_prompt,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text.strip()


def revise_draft(client: Anthropic, system_prompt: str, draft: str) -> tuple:
    """Call 2: self-review + revise. Returns (revision_notes, final_draft)."""
    user = (
        "## Draft to review and revise\n\n"
        f"{draft}\n\n"
        "## Task\n\n"
        "Apply the revision rules above. Output your revision notes followed by the revised final draft, "
        "using the exact two-section delimiter format."
    )
    resp = client.messages.create(
        model=DRAFT_MODEL,
        max_tokens=MAX_TOKENS_REVISE,
        system=system_prompt,
        messages=[{"role": "user", "content": user}],
    )
    return _parse_revision_response(resp.content[0].text)


# ───────────────────────── orchestrator ──────────────────────────

def write_draft(matrix: dict) -> str:
    """End-to-end: load inputs, compose, revise, write outputs."""
    client = Anthropic()

    brief_md = BRIEF_PATH.read_text()
    sources  = json.loads(SOURCES_PATH.read_text())

    # Voice and editorial standards single-sourced through prompt_context.
    # Composition and revision get mode-specific voice anchor framing.
    composition_editorial = build_draft_editorial_context(sources["id"], mode="compose")
    revision_editorial    = build_draft_editorial_context(sources["id"], mode="revise")
    composition_system = f"{composition_editorial}\n\n{COMPOSITION_RULES}"
    revision_system    = f"{revision_editorial}\n\n{REVISION_RULES}"

    print("[1/2] Composing draft...")
    draft_v1 = compose_draft(client, composition_system, matrix, brief_md)
    print(f"      composed: {len(draft_v1)} chars (~{len(draft_v1.split())} words)")

    print("[2/2] Self-reviewing and revising...")
    try:
        notes, final_draft = revise_draft(client, revision_system, draft_v1)
    except ValueError as e:
        print(f"      [error] {e}", file=sys.stderr)
        # If the delimiter parse fails, write the unrevised draft so we don't lose work.
        FINAL_PATH.write_text(draft_v1 + "\n")
        REV_NOTES_PATH.write_text(f"# Revision pass failed to parse\n\n{e}\n")
        raise
    print(f"      revision notes: {len(notes)} chars")
    print(f"      final draft:    {len(final_draft)} chars (~{len(final_draft.split())} words)")

    REV_NOTES_PATH.write_text(notes + "\n")
    FINAL_PATH.write_text(final_draft + "\n")
    print(f"\nWrote {REV_NOTES_PATH}")
    print(f"Wrote {FINAL_PATH}")

    return final_draft


def run() -> str:
    matrix = json.loads(MATRIX_PATH.read_text())
    return write_draft(matrix)


if __name__ == "__main__":
    run()

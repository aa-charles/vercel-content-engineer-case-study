# comparison_matrix.json — Schema

> Output contract for `agent_compare.py`. Primary consumer: `agent_draft.py`. Secondary artifact: `outputs/comparison_brief_<piece-id>.md` (rendered from this JSON via template, no model call).
>
> Outputs land in `outputs/comparison_matrix_<piece-id>.json` and `outputs/comparison_brief_<piece-id>.md`. Paths are piece-scoped via `output_path()` in `utils.py`; the id comes from `sources.json`.

---

## Full schema

```jsonc
{
  "id":           "vercel-workflows-vs-cloudflare-workflows",
  "topic":        "<from sources.json>",
  "generated_at": "<ISO date>",

  "source_summary": {
    "subject_a": { "vendor": "Vercel",     "name": "Vercel Workflows",     "source_count": 8, "claim_count": 149 },
    "subject_b": { "vendor": "Cloudflare", "name": "Cloudflare Workflows", "source_count": 9, "claim_count": 158 },
    "third_party_claim_count": 34,
    "total_claims": 341
  },

  // ORDERED by composite_weight descending. Read order IS priority signal.
  "dimensions": {
    "<dimension_name>": {
      "subject_a_position": "<concise statement>",
      "subject_b_position": "<concise statement>",
      "verdict": {
        // winner defaults to "depends_on_workload" whenever the dimension has any
        // meaningful workload-conditional split. Reserve "subject_a" or "subject_b"
        // for cases where one product is genuinely better across ALL reasonable
        // workloads (rare). Use "no_clear_winner" when the products are truly
        // equivalent.
        "winner":    "subject_a" | "subject_b" | "no_clear_winner" | "depends_on_workload",
        // Rationale MUST name the workload conditional explicitly when winner=depends_on_workload.
        // E.g., "Cloudflare wins for I/O-bound workloads; Vercel wins where payload size matters."
        "rationale": "<one sentence>"
      },
      "evidence_refs": {
        "subject_a": ["<source URL>", ...],
        "subject_b": ["<source URL>", ...]
      },
      "scoring": {
        "brief_priority":         0 | 1 | 2 | 3,    // mechanical, derived from piece_brief.md
        "evidence_density":       <int>,             // mechanical, count across both subjects
        // Applied by the model in the dimension composition call, against this rubric:
        //   0 = positions are substantively equivalent
        //   1 = same outcome via different mechanism (e.g., both support X via different APIs)
        //   2 = different design choices, both internally coherent, no direct conflict
        //   3 = positions in direct conflict OR contested via active disputed_claims_ref
        // FLOOR: any dimension with an active disputed_claims_ref scores at least 2.
        // If unsure between two scores, choose the lower (conservative).
        "disagreement_intensity": 0 | 1 | 2 | 3,
        "reader_decision_impact": {
          "score":     0 | 1 | 2 | 3,                // model judgment, inline
          "reasoning": "<one sentence>"
        },
        "composite_weight": <float>
      }
    }
  },

  // ORDERED by composite_weight descending.
  "editorial_tensions": [
    {
      "name":    "<snake_case>",
      "type":    "design_disagreement_between_subjects" | "subject_disclosure" | "external_critique",
      "summary": "<one-line structured description>",

      // type=design_disagreement_between_subjects
      "subject_a_position": "<...>" | null,
      "subject_a_steelman": "<charitable case for subject_a>" | null,
      "subject_b_position": "<...>" | null,
      "subject_b_steelman": "<charitable case for subject_b>" | null,

      // type=subject_disclosure
      "disclosing_subject": "subject_a" | "subject_b" | null,
      "disclosure":         "<what the subject discloses>" | null,

      // type=external_critique
      "external_voice":   "<vendor name>" | null,
      "critique_summary": "<the critique>" | null,

      // All types
      "evidence_refs":        ["<source URL>", ...],
      "disputed_claims_refs": ["<disputed_claim ID from sources.json>", ...],

      // Generated under shared_rules.md §4 + piece_brief.md voice register.
      // 3-5 sentences. Treated as a paragraph that will appear in the final
      // piece, not as analysis prose ABOUT the tension. Draft agent inserts
      // verbatim or near-verbatim and writes connective tissue around it.
      "narrative_payload": "<draft-ready prose, 3-5 sentences>",
      "draft_placement":   "<e.g. 'Section 2.1 (Programming model and step identity)' or 'Lead, paragraph 3'>",
      "steelman_quality":  "both_strong" | "asymmetric" | "weak",

      "scoring": {
        "brief_priority":         0 | 1 | 2 | 3,
        "evidence_density":       <int>,
        "disagreement_intensity": 0 | 1 | 2 | 3,    // derived: both_strong=3, asymmetric=2, weak=1
        "reader_decision_impact": {
          "score":     0 | 1 | 2 | 3,
          "reasoning": "<one sentence>"
        },
        "composite_weight": <float>
      }
    }
  ],

  "category_framing": [
    {
      "category":        "<e.g. durable execution>",
      "canonical_voice": "<e.g. Temporal>",
      "framing_summary": "<1-2 sentences of vocabulary/taxonomy>",
      "evidence_refs":   ["<source URL>", ...],
      "draft_placement": "<e.g. 'Lead, parenthetical when defining durable execution'>"
    }
  ],

  "detected_asymmetries": [
    {
      "type":            "concept_hierarchy" | "terminology" | "evidence_density_imbalance" | "feature_framing_difference",
      "description":     "<structured statement of the asymmetry>",
      "subject_a_view":  "<how subject_a structures/names/emphasizes>",
      "subject_b_view":  "<how subject_b structures/names/emphasizes>",
      "implication":     "<what this asymmetry reveals about the products>",
      "evidence_refs":   ["<source URL>", ...],
      "draft_treatment": "<how the draft should surface it: prose, table footnote, structural choice>"
    }
  ]
}
```

---

## Field reference

### `dimensions`

Normalized comparison axes (`programming_model`, `state_persistence`, `pricing`, etc.). Populated only when evidence exists from BOTH subjects. Out-of-scope dimensions per `piece_brief.md` §Scope are filtered before reaching the matrix.

**Ordering:** emitted in `composite_weight` descending order. The draft agent treats the first N as load-bearing for the piece; later entries as supporting material.

### `editorial_tensions`

Points where (a) the subjects meaningfully disagree, (b) a subject discloses a limitation, or (c) an external voice critiques. Type taxonomy is strict: each tension is exactly one type, and only the fields relevant to that type are populated; others are `null`.

The setup pass parses `piece_brief.md` §"Editorial tensions to surface" and assigns each item a snake_case `name` and a `type`. A typical comparison piece produces 3–5 tensions, sorted in the output matrix by `composite_weight` descending. Specific tension names are model judgments per run, not part of the schema contract — the schema fixes the field shape, not the labels.

### `narrative_payload` semantics

The most editorially-sensitive field. Constraints:

- **Voice:** generated under `shared_rules.md` §4 + `piece_brief.md` §Voice register. The compare agent loads both files via `prompt_context.build_editorial_context()` so voice is single-sourced across compare and draft.
- **Length:** 3–5 sentences. Matches `shared_rules.md` §4 paragraph cadence. Constrained at generation time.
- **Register:** draft-ready prose, not analysis. Treat as a paragraph that will appear in the final piece — not as commentary about the tension.
- **Downstream usage:** `agent_draft.py` inserts verbatim or near-verbatim and writes only connective tissue around it.

### `category_framing`

Voices to acknowledge once for vocabulary, not compare in depth. Temporal goes here for durable execution. Renders as a single parenthetical or short reference in the draft, typically in the lead.

### `detected_asymmetries`

First-class output. Surfaces structural differences in how the products are documented: concept hierarchy (e.g., one product files X under "concepts" while the other treats it as implicit), terminology divergence, evidence density imbalances per dimension, feature framing differences. The draft engages each asymmetry per `shared_rules.md` §6.

---

## Scoring

Computed during Pass 2. Three fields mechanical, one inline model judgment, one aggregate.

| field                        | source                                                             |
|------------------------------|--------------------------------------------------------------------|
| `brief_priority`             | code, scans `piece_brief.md` for the dimension/tension name        |
| `evidence_density`           | code, counts `evidence_refs` across both subjects                  |
| `disagreement_intensity`     | code: dimensions=position-divergence; tensions=`steelman_quality`  |
| `reader_decision_impact`     | model, one inline sentence per dimension/tension                   |
| `composite_weight`           | code: `brief_priority + reader_decision_impact.score + 1.0 * disagreement_intensity + 0.3 * log(evidence_density + 1)` |

The `reader_decision_impact.reasoning` field is auditable: a one-sentence justification for the score. If the model can't articulate WHY a reader's choice would shift on this dimension, it scores low.

The composite_weight formula is in code, not in the schema — tunable based on what the matrix output looks like in practice.

---

## Pass structure

The compare agent runs in two passes plus an asymmetry query:

1. **Pass 1 — Indexing.** Reads every claim from `outputs/extractions.json`. Builds cross-source pairings (recognizing terminology variants — e.g., Vercel's "build-time directives" ≡ Inngest's "magic strings"), maps each claim to dimensions and tensions. Builds on the per-claim `dimensions_covered` tagging the extract agent already produced; doesn't re-tag.
2. **Pass 2 — Composition.** For each dimension and tension, queries the Pass 1 index, composes the entry (positions, verdicts, steelmans, narrative_payload, scoring with inline reader_decision_impact reasoning).
3. **Asymmetry query.** Dedicated pass over the indexed map looking for structural differences. Outputs `detected_asymmetries`.

Then mechanical post-processing: compute `composite_weight`, sort dimensions and tensions descending, write `outputs/comparison_matrix.json`, render `outputs/comparison_brief.md` from the JSON via template.

---

## Outputs

- `outputs/comparison_matrix_<piece-id>.json` — primary, machine-readable, consumed by `agent_draft.py`
- `outputs/comparison_brief_<piece-id>.md` — secondary, human-readable, rendered mechanically from the JSON. Same content, formatted for editor review.

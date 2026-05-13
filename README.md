# Vercel content engineer case study

The pipeline that produced [Vercel Workflows vs Cloudflare Workflows](outputs/agent_draft_vercel-workflows-vs-cloudflare-workflows.md), a 2,800-word KB-style comparison article. Four agents, ~$7 per run, ~2 hours of human time. Editorial discipline lives in markdown files that every agent loads at runtime. Change a rule once, every agent sees it.

The pipeline output (`outputs/agent_draft_vercel-workflows-vs-cloudflare-workflows.md`) and a final edited version submitted as the case study (`outputs/final_draft_vercel-workflows-vs-cloudflare-workflows.md`) are both in the repo. Architecture walkthrough at [v0-conteng-case.vercel.app](https://v0-conteng-case.vercel.app).  Built as the case study for Vercel's Content Engineer role.

## How it works

**Extract** (Sonnet 4.6) reads each source URL and produces structured claims tagged by dimension, vendor, and disputed-claim references. Source handling is role-driven: `roles.json` maps each role to handling rules using a five-way taxonomy (`factual_authoritative`, `factual_with_attribution`, `partisan_critique`, `category_authority`, `community_signal`). Vendor docs become stated facts; competitor critiques become attributed quotes; HN discussions become thematic signals, never attributed to individual users.

**Compare** (Opus 4.7) runs two passes. The first identifies in-scope dimensions, editorial tensions, and category framings. The second composes each entry with positions, steel-mans, evidence references, draft-ready narrative payloads, and verdicts. Two decisions that mattered: the verdict default is `depends_on_workload` — `subject_a` and `subject_b` are reserved for cases where one product wins across all reasonable workloads (rare). And the `narrative_payload` field is authoritative prose, not a suggestion: the compare agent has the full evidence corpus in working memory when writing editorially-loaded passages, and the draft agent inserts them and writes the connective tissue.

**Draft + Revise** (Opus 4.7) composes the full piece against the matrix and a voice anchor (a structural sibling from `style_references` in `sources.json`, selected by metadata match), then self-reviews against the reader test and anti-patterns. The revision pass is the highest-leverage decision in the pipeline. It catches false balance, duplicated paragraphs, and voice drift the composer missed, for ~$1-2 in additional tokens.

The orchestrator (`run.py`) sequences the stages with progress indicators, cost estimates, and a human review checkpoint between Compare and Draft. Skip flags re-run partial pipelines.

## Editorial discipline as data

Three files do the work:

- `shared_rules.md` — universal principles. Voice register, source handling, treatment of disagreement, anti-patterns, reader test.
- `piece_brief.md` — per-piece specifics. Thesis, audience, editorial tensions, voice anchor declaration, scope, piece-specific anti-patterns.
- `roles.json` — source-handling lookup.

These load into every agent's system prompt via `prompt_context.py`. Adding a new article type means writing a new brief and adjusting roles — agent code doesn't change. Universal editorial standards don't drift per piece.

## To run

```bash
git clone https://github.com/aa-charles/vercel-content-engineer-case-study
cd vercel-content-engineer-case-study
pip install -r requirements.txt
cp .env.example .env  # add your ANTHROPIC_API_KEY
python3 run.py
```

A full run takes ~15–20 minutes and costs ~$7–9. `python3 run.py --status` shows the current state of `outputs/` without running anything. `--skip-extract`, `--skip-compare`, and `--skip-draft` re-run from a later stage (or stop before drafting).

## On Vercel Workflows

The pipeline currently runs locally in Python. The natural next step is running it on Vercel Workflows:

```typescript
// sketch: this pipeline as a Vercel Workflow
export async function contentPipeline(config: PipelineConfig) {
  'use workflow';

  const claims = await extractStage(config);
  const matrix = await compareStage(claims, config);

  // editorial review checkpoint — hook waits for human approval
  const approved = await waitForReview(matrix);
  if (!approved) return { status: 'rejected_at_review' };

  const draft = await draftStage(matrix, config);
  return { status: 'completed', article: draft };
}
```

Each agent stage becomes a step. The editorial review checkpoint becomes a hook. Durable streams carry pipeline progress to the case study site's run viewer. The 50 MB per-step payload is well-suited to passing the full claim corpus (~4 MB) between stages. Architectural sketch and migration plan at `docs/vercel-workflows-plan.md`.

## What I'd improve

- **Structured intake stage.** Writing `piece_brief.md` from scratch is the hardest part. The natural product is a two-stage flow: lightweight intake (subjects, URLs, voice anchor), then an auto-generated draft brief the user reviews before the pipeline runs.
- **Schema extension to other article types.** The architecture supports deep-dive, customer story, and tutorial as new schema definitions. Currently only the comparison-piece schema exists.
- **Source freshness checks.** Vercel's Workflows pricing model changed between research and editorial pass — a pre-run check on cached sources would catch this earlier.

## Repo layout

```
agent_extract.py              per-source claim extraction
agent_compare.py              matrix synthesis + asymmetry detection
agent_draft.py                compose + revise
prompt_context.py             editorial context loader + voice anchor selection
run.py                        orchestrator
utils.py                      shared helpers

sources.json                  source corpus + metadata + style references
piece_brief.md                per-piece editorial spec
shared_rules.md               universal editorial principles
roles.json                    source-handling lookup
comparison_matrix.schema.md   matrix output contract
process_notes.md              build observations — system-level failure modes caught during runs

outputs/
  extractions_<id>.json                Layer 1 output
  comparison_matrix_<id>.json          Layer 2 output
  comparison_brief_<id>.md             human-readable matrix view
  agent_draft_<id>.md                  Layer 3 output (initial draft)
  agent_draft_revision_notes_<id>.md   self-review notes from revision pass
  final_draft_<id>.md                  edited version, submitted as the case study
```

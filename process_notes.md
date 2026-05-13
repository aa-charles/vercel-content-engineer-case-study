# Process Notes

Captured observations from the build — moments where the system produced something instructive about the architecture. Chosen for what's most useful to the case-study writeup, not exhaustive.

## 2026-05-08 — Editorial context tightens extraction

After wiring `shared_rules.md` and `piece_brief.md` into the extract agent's system prompt, re-ran the smoke test on the Inngest source (the partisan-critique path).

- **Before editorial context:** 20 claims extracted.
- **After editorial context:** 15 claims extracted.

The 5 dropped claims were all noise from the perspective of the comparison piece — Inngest's own SDK pitch (Bun/Deno support, library-not-platform framing), tangential argument points (rate-limiting visibility, abstraction-layer complexity), and self-promotional product features (auto-tracing). All architecturally load-bearing arguments — build-time transformation, type safety, testing implications, debugging implications, step identity, multi-tenancy, replay precision, the Inngest-tried-implicit-IDs origin story — were preserved.

The dropped claims were the same ones flagged after the *first* smoke test as "the matrix would need to filter these anyway." They're now being dropped at extraction time. The comparison agent gets a cleaner input.

Read: the editorial context isn't decoration. It does real work — pushing the extractor toward claims that matter for *this comparison*, not arbitrary fact extraction. First evidence in the project that role-driven prompting + editorial context produces editorial signal, not just structured data.

## 2026-05-09 — Editorial interventions on first matrix output

Three patches applied after `agent_compare.py`'s first run on the full corpus, before greenlighting the draft agent. Documented as case-study evidence of where automated synthesis still needs human editorial intervention.

1. **Removed duplicate Temporal tension.** Setup call classified Temporal as both a `category_framing` entry (correct) and an `external_critique` tension (wrong). Patched by deleting the duplicate tension. *Why:* category authorities establish vocabulary; they're not disagreements. The setup prompt needs a stricter constraint preventing `category_authority` sources from being promoted to tensions.

2. **Backfilled `evidence_refs` for `substrate_asymmetry`.** The tension surfaced with 0 evidence claims — the model composed it from `piece_brief.md` framing without grounding in extracted claims. Patched by adding 4 evidence URLs (Fluid landing + Fluid engineering blog; Durable Objects concepts + Cloudflare Workflows engineering blog) and recomputing `evidence_density` and `composite_weight` for schema consistency. *Why:* the tension-evidence mapping fires on `disputed_claims_refs`, but architectural disagreements often don't have a directly-disputed claim ID. Future fix: agent should fall back to subject-level `platform_context` and `concepts` sources when `disputed_claims_refs` is empty for a `design_disagreement_between_subjects`-type tension.

3. **Added missing `lock_in_portability` dimension.** Skipped during composition because no extracted claims were tagged with this dimension — claims about Vercel's Worlds architecture got tagged `programming_model` or `compute_substrate` instead. Patched by hand-authoring the dimension entry (positions, verdict=`depends_on_workload`, `evidence_refs`, scoring). *Why:* extraction-stage dimension tagging is per-claim and conservative. When a claim describes a multi-runtime adapter pattern, the model picks the obvious dimension and may miss the implied portability dimension. Future fix: extraction prompt could consider second-order dimensions, or a post-extraction enrichment pass could re-tag against the full piece_brief in-scope list.

After patches: re-sorted dimensions and editorial_tensions by `composite_weight` descending to preserve the read-order-as-priority convention; re-rendered the comparison brief mechanically from the JSON via the template renderer (no model call).

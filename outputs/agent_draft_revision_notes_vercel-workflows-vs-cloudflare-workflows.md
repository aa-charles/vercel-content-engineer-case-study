**Reader test check:**
1. Decision by workload — Yes, the "When to choose" table is concrete and prescriptive.
2. Architectural difference — Yes, the lead names the fork clearly (directives + Fluid vs. classes + Durable Objects).
3. What Cloudflare does better — Yes, the "Where Cloudflare goes deeper" section is substantive (per-instance SQLite, edge proximity, CPU-only billing, refactor-safe IDs, testing tooling).

**Anti-pattern violations found:**

- **Section 2.2 ("State persistence and where code runs"), paragraphs 1–2: redundancy.** The first paragraph and the second paragraph both explain the Fluid Compute / Workers + Durable Objects substrate fork. The first paragraph also restates the lead's architectural fork ("One treats durable execution as an extension of the application; the other treats it as an explicit runtime primitive"). This is essay-thinking — circling back on framing instead of advancing. Collapse to a single tighter paragraph that delivers the substrate fact and moves on.

- **Section 2.4 (AI orientation), opening line: mild false-balance.** "They get there from different directions" is the kind of soft framing the brief warns against. Replace with something more directional.

- **Cost section closing paragraph: slight hedging.** "The right way to read these models is by workload shape" is fine, but the preceding sentence ("Vercel's model is more predictable for compute-heavy workflows with low event counts, but its event-based billing penalizes workflows with many small steps") undersells the contrast. Tighten.

- **"Get started" CTA link:** `vercel.com/workflows` is a guess; the safer, idiomatic Vercel-KB CTA points to docs and signup. Adjusted to be more conservative about the URL while keeping the CTA pattern.

- **Lead paragraph 1: slightly long for the WAF cadence.** The three-example riff ("The retry that should have run didn't…") is good texture but pushes the paragraph past the WAF piece's pace. Kept it but tightened the Temporal parenthetical so the paragraph lands faster.

- **Section 3.1 heading ("How directives let workflow code stay ordinary application code"):** Good — active, question-shaped. Kept.

- **Section 3.4 ("Framework-agnostic reach across the JavaScript ecosystem"):** This was added during draft but is light on substance compared to the others. Kept but tightened — the framework list does the work.

No structural changes needed. The piece names the fork in the lead, walks the four comparison dimensions, gives both products genuine "goes deeper" sections, addresses cost philosophically, and closes with a workload table. Revisions are local tightening.

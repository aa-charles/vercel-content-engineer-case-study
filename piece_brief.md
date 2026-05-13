# Piece Brief: Vercel Workflows vs Cloudflare Workflows

> Per-piece editorial spec. See shared_rules.md for universal principles.
> Read together with `shared_rules.md` and `roles.json`.
> Structural model: vercel.com/kb/guide/vercel-waf-vs-cloudflare-waf

## Subject

Comparison of Vercel Workflows and Cloudflare Workflows as durable execution platforms for production use.

## Thesis

Every multi-step backend process eventually outgrows stateless functions. The question is what runtime to anchor it to. A workflow runtime that runs as a managed orchestration layer on top of regional serverless compute can integrate tightly with your application framework and abstract away identity, state, and retry mechanics, but it lives where your app lives and inherits that platform's substrate. A workflow runtime that runs as a first-class primitive on a stateful edge platform exposes lower-level mechanics — explicit step IDs, per-instance databases, single-region instance pinning — and gives you direct access to a globally distributed runtime, but the developer experience is more primitive-shaped.

Vercel Workflows and Cloudflare Workflows sit on opposite sides of that choice. Vercel Workflows is built into the Vercel platform as an extension of normal application code, with build-time directives (`"use workflow"`, `"use step"`) that compile durable execution into ordinary TypeScript or Python functions. Cloudflare Workflows is a class-based runtime built on Workers and Durable Objects, with explicit `step.do()` calls and per-workflow SQLite databases co-located with compute. That architectural difference shapes programming model, state persistence, pricing, payload limits, AI tooling, and whether it makes sense to use one platform's workflows from inside the other.

This guide compares the two products so a developer can decide which fits their workload.

## Audience

Engineers evaluating durable execution platforms for production AI agents, long-running backends, or multi-step business processes. Comfortable reading engineering blogs and technical documentation. Familiar with serverless concepts and the basic idea of durable execution. Skeptical of marketing language. Reading the piece because they're choosing.

The piece does not need to define durable execution from first principles. It does need to be specific about what's distinct to *these two products* and to make recommendations by workload type.

## Voice anchor

Genre: head_to_head_comparison
Subject domain: developer_infrastructure
Register: technical_explanatory_vercel_leaning

## Commissioning context

Written for Vercel. Vercel's framing is the editorial home — when the products are equivalent, Vercel's terms are the default. Where Cloudflare's framing is more accurate, more honest, or where Cloudflare's product is better-suited to a use case, say so directly. The piece earns trust by being a fair, useful guide for the reader, not by celebrating Vercel.

## The angle

A practical comparison that names the architectural fork in the lead, walks through the dimensions where the two products meaningfully differ, identifies where each goes deeper, addresses the cost picture, and closes with workload-type recommendations. Confident, specific, prescriptive. Like the WAF piece, the comparison makes calls — not "which is better universally," but "for this kind of workload, this product fits."

## Structure (mirror the WAF article)

The piece should follow this structure. Section headings approximate; the draft agent should adapt phrasing while preserving the underlying organization.

**1. Lead (3–4 short paragraphs).**
Open with the architectural fork. Both products solve the same problem (durable execution: multi-step processes that survive crashes, sleep for hours or days, retry failed steps without restarting the whole workflow). Each company built it on top of a different conviction about what the runtime should be. Name what each runtime *is* in concrete terms — Vercel: managed orchestration on Fluid Compute with build-time directives; Cloudflare: class-based runtime on Workers and Durable Objects. End the lead with what the piece will do for the reader: "This guide compares the two so you can decide."

**2. How Vercel Workflows and Cloudflare Workflows compare.**
The structural spine of the piece. Three to four subsections, each ending in a comparison table with prose framing the table's significance. Subsections:

- *Programming model and step identity* — directives vs explicit step IDs, the build-time transformation question, what each implies for refactor safety and debugging. This is the section where the magic-strings debate lives. Surface Inngest's critique with attribution. Give Vercel's reasoning fair weight (skew protection, the React `"use client"`/`"use server"` lineage). The table should compare: programming style, step identity mechanism, refactor behavior, language support.

- *State persistence and where code runs* — centralized event log vs per-instance SQLite in Durable Objects; Fluid Compute regional execution vs V8 isolates and Durable Objects globally distributed. The table should compare: state model, state location, step transition cost, geographic distribution, single-instance vs horizontal scaling.

- *Limits and payload sizes* — Vercel 50 MB per step, 2 GB per run; Cloudflare 1 MiB per step return, 30-min step timeout. The architectural consequences are real: Cloudflare workloads with large AI payloads must use external storage and pass references; Vercel workloads can pass payloads naively between steps. Table comparing concrete limits.

- *AI orientation* — Vercel AI SDK + WorkflowAgent; Cloudflare Workers AI + Agents SDK. Both are real AI stories serving different shapes of AI developer. Table comparing AI integration surface, hosted inference availability, agent framework, language support for AI workloads.

**3. Where Vercel Workflows goes deeper.**
4–5 capabilities specific to or stronger on Vercel. Each as its own subsection with descriptive heading and 1–2 paragraphs of prose. Candidates:

- The directive-based programming model and what it gives developers (familiar async TypeScript, no API surface to learn for steps)
- AI SDK and WorkflowAgent integration (deeper than anything on the Cloudflare side for the TypeScript AI developer specifically)
- Native Python with feature parity (real differentiator for AI/ML developers)
- Generous payload limits designed for AI workloads (50 MB per step)
- Worlds architecture and open-source WDK (genuine portability claim, Postgres reference World in production)

**4. Where Cloudflare Workflows goes deeper.**
4–5 capabilities specific to or stronger on Cloudflare. Each as its own subsection. Candidates:

- Per-instance SQLite databases co-located with compute (state lives where compute lives, no network hop for state transitions)
- Globally distributed Workers runtime with zero cold starts at the edge (workflow trigger latency)
- CPU-time-only billing — never bills for I/O or LLM wait time, never bills for sleep
- Explicit step identity and step IDs (refactor-safe by design, no compile-time transformation surprises)
- Tighter coupling to broader Cloudflare primitives (R2 for cheap storage, Workers AI for hosted inference, KV, D1, Queues — all native)

**5. What they cost.**
Comparison table covering pricing models, included tiers, overage behavior. Both made unusual philosophical choices about what to bill for: Vercel bills three resources (events, data written, data retained); Cloudflare bills CPU time only. Make the philosophical contrast legible without modeling specific bills. Frame the cost question as: "Vercel charges for what passes through the system; Cloudflare charges for what computes."

**6. When to choose Vercel Workflows or Cloudflare Workflows.**
Workload-to-product decision table. Mirror the format of the WAF article's "When to choose" section. Rows by workload type, columns for product and reasoning. Suggested rows:

- AI agent or RAG pipeline in TypeScript, already on Vercel → Vercel
- Python ML workflow with heavy library dependencies → Vercel
- Workflow that needs to pass large AI payloads (images, long context) between steps → Vercel
- Workflow already running on Cloudflare Workers, using Durable Objects, R2, or Workers AI → Cloudflare
- Workload where edge proximity to users matters for trigger latency → Cloudflare
- Long-running workload with mostly idle wait time and explicit cost ceiling concerns → Cloudflare
- Workflow that needs explicit, refactor-safe step identity and resists compile-time transformation magic → Cloudflare
- Application using Next.js or the Vercel AI SDK → Vercel

Close the section and the piece with a single short paragraph that captures the practical bottom line: most teams choose based on which platform their application already lives on, and for teams making a fresh choice, the question is whether they want durable execution to feel like normal application code (Vercel) or to be an explicit runtime primitive (Cloudflare).

## Scope

**In scope:**
- Programming model (directives vs explicit step APIs, the build-time transformation question, refactor-safety)
- State persistence (centralized event log vs per-instance SQLite in Durable Objects)
- Where code runs (Fluid Compute regional vs Workers + Durable Objects at the edge)
- Pricing model and philosophy (three-resource billing vs CPU-time-only)
- Limits and payload sizes (50MB Vercel vs 1MiB Cloudflare; what the limits encourage architecturally)
- Language support (TypeScript + Python vs TypeScript-first)
- AI orientation (AI SDK + WorkflowAgent vs Workers AI + Agents SDK)
- Lock-in posture (Worlds architecture vs Cloudflare-native deep integration)
- Observability and testing maturity

**Out of scope:**
- Detailed comparison to Temporal, Inngest, AWS Lambda Durable Functions, Restate, DBOS. Mention as category context only; do not compare in depth.
- The full Vercel-on-AWS substrate question as a piece-defining theme. Surface as architectural context where it explains specific Vercel choices (Fluid Compute exists because of Lambda's constraints), but do not center it.
- Strategic positioning around agentic infrastructure as a category. The piece is about Workflows specifically.
- Specific cost calculations or modeled bills. Reference the philosophical contrast in pricing; don't build pricing examples.
- A "should you run both?" section. The WAF article has one because Cloudflare WAF is commonly deployed in front of Vercel as a reverse proxy. Workflows aren't deployed in front of one another; the equivalent question doesn't apply.

## Editorial tensions to surface

The matrix should mark these explicitly; the draft agent should engage with them directly.

- **Magic strings vs explicit identity.** The single sharpest design debate. Don't resolve it; explain both sides; give Vercel the steel-man (skew protection, React lineage) and Cloudflare the steel-man (refactor safety, debugging clarity). Surface Inngest's critique with attribution.
- **Architectural asymmetry — Fluid is to Vercel as Durable Objects are to Cloudflare, but not symmetrically.** Cloudflare Workflows is a managed orchestration layer on a more architecturally fundamental primitive (Durable Objects). Vercel Workflows is a managed orchestration layer on a more abstracted primitive (Fluid Compute). The asymmetry reflects what each company believes its product is. Surface this directly when discussing state and where code runs.
- **The substrate paragraph.** Vercel Workflows runs on Fluid Compute, which is custom infrastructure built on top of AWS Lambda. Don't dwell — but acknowledge briefly when discussing where code runs. Ignoring it leaves a hole sophisticated readers will notice.
- **The category-defining voice.** Temporal originated this category and developers reading the piece will know it. Acknowledge once as category context (probably in the lead or in a parenthetical when defining durable execution). Don't compare in depth.
- **The Cloudflare DX maturity gap.** Cloudflare shipped substantially better testing tooling in early 2026; their own blog calls the prior testing experience a "black-box process." Surface this honestly when comparing observability and testing — this is where Vercel goes deeper.

## Voice register

Match the WAF piece. Specifically:

- **Confident and specific, not breathless.** Declarative claims when evidence supports them. "Vercel runs as an embedded WAF in the same request path as your deployment" — that direct, that clear.
- **Technical precision over interpretive flourish.** Describe what something does, not how it feels to use it.
- **No marketing adjectives.** Cut "seamless," "powerful," "robust," "cutting-edge," "best-in-class," "industry-leading."
- **Explicit recommendations, conditioned on use case.** Phrases like "for [workload type], [product] is the better fit because [specific reason]." Not "both have tradeoffs."
- **Tables earn their place.** When a table communicates better than prose, use a table. Tables in this piece are load-bearing.
- **Short paragraphs.** The WAF piece runs at ~3-5 sentences per paragraph in body sections. Match that pace.

## Reader test

A developer reading this should come away able to make a decision. Specifically: they should know which product fits their workload type, why, and what the meaningful tradeoffs are. They should not feel sold to. They should feel guided.

A weaker version of the piece would summarize feature parity and conclude "both are good choices, depending on your needs." A stronger version names the architectural fork in the lead, walks through dimensions where the two products meaningfully differ, gives both products their due where they go deeper, and closes with specific workload-by-workload recommendations.

## Anti-patterns specific to this piece

In addition to the universal anti-patterns in `shared_rules.md`:

- **Don't write a philosophical essay.** This is a buyer's guide written at high editorial standard. The reader is choosing, not pondering.
- **Don't bury the architectural fork in the middle.** Lead with it.
- **Don't false-balance into mush.** When products meaningfully differ, name the difference and recommend by workload. Hedging dissolves real differences.
- **Don't omit the "where each goes deeper" sections.** This is the structural move that makes the piece feel fair and useful instead of feeling like a Vercel ad.
- **Don't try to crown a universal winner.** The piece's authority comes from being precisely correct about which product fits which workload, not from picking one.
- **Don't skip the cost section.** Pricing philosophy is a real point of differentiation and the reader needs it to make a decision.
- **Don't try to compare to Temporal in depth.** Mention as category context once; resist the temptation to make this a three-way piece.

# Comparison Brief: Compare Vercel Workflows vs Cloudflare Workflows for durable execution

> Auto-rendered from `comparison_matrix.json`. Edit the matrix, not this file.
> Generated: 2026-05-09

**Source summary:** Vercel Workflows (8 sources, 149 claims) · Cloudflare Workflows (9 sources, 158 claims) · third-party 34 claims · total 341

## Editorial tensions (in priority order)

### magic_strings_vs_explicit_identity  *(weight 9.33, design_disagreement_between_subjects)*

**Summary:** Build-time directives (Vercel) derive step identity implicitly vs explicit step IDs (Cloudflare) — the sharpest design debate, with Inngest critiquing Vercel's approach.

**Vercel's position:** Vercel uses build-time directives ('use workflow', 'use step') that derive step identity implicitly from code structure during compilation, modeled on the React 'use client'/'use server' lineage so durable execution feels like ordinary TypeScript or Python.

**Steelman:** Directives let developers write workflows as plain async functions with no API surface to learn — the same mental model as the rest of their Vercel application. The build-time transformation handles step boundaries, retry mechanics, and skew protection automatically, and migrating in-flight runs across code changes is a managed operation rather than a developer responsibility. For teams already working in the Next.js and React Server Components idiom, directives are a familiar signal that something non-standard is happening at the boundary.

**Cloudflare's position:** Cloudflare requires explicit step.do() calls with developer-assigned string IDs, making each step's state key a literal string in the source rather than a position derived at build time.

**Steelman:** Explicit IDs decouple workflow state from code structure: a developer can insert steps, reorder logic, add logging, or refactor freely, and in-flight workflows continue correctly as long as the assigned IDs are stable. Stack traces point at the code the developer wrote, breakpoints align with source lines, and tests can mock a plain step object without modeling a compiler. The cost is more ceremony per step; the benefit is that step identity is something the developer controls rather than something the framework infers.

**Steelman quality:** both_strong

**Draft placement:** Section 2, first subsection: 'Programming model and step identity'. This paragraph carries the central design debate of the piece and should sit in the prose framing immediately before or after the comparison table for that subsection.

**Narrative payload (draft-ready, insert verbatim or near-verbatim):**

> Vercel derives step identity at build time from the structure of the code itself; Cloudflare requires the developer to assign a string ID to every step.do() call. Vercel's case is lineage and ergonomics: the directive model follows React's 'use client'/'use server' convention, lets workflows read as ordinary TypeScript or Python, and treats in-flight migration across code changes as a managed concern. Cloudflare's case is that explicit IDs make step state a value the developer controls — workflows can be refactored, reordered, or rewritten in another language, and as long as the IDs hold, in-flight runs continue correctly. Inngest, which says it shipped an implicit model first and rewrote it after production breakage, argues that directive-derived identity corrupts sleeping workflows when code is edited and that a typo like 'use workfow' passes every type check before failing at runtime. The disagreement is real and unresolved: directives optimize for code that looks like the rest of your application, explicit IDs optimize for state that survives the code changing underneath it.

**Reader decision impact:** 3/3 — Step identity directly determines refactor safety, debugging experience, and long-term maintainability — readers choosing a durable execution platform will weight this dimension heavily.

**Evidence:** https://www.inngest.com/blog/explicit-apis-vs-magic-directives, https://news.ycombinator.com/item?id=45684217

### substrate_asymmetry  *(weight 6.483, design_disagreement_between_subjects)*

**Summary:** Cloudflare Workflows sits on a more architecturally fundamental primitive (Durable Objects); Vercel Workflows sits on a more abstracted primitive (Fluid Compute). The asymmetry reflects what each company believes its product is.

**Vercel's position:** Vercel Workflows is a managed orchestration layer on top of Fluid Compute, a regional serverless runtime that abstracts away instance lifecycle, concurrency, and scaling. Workflows are an extension of normal application code rather than a separate primitive.

**Steelman:** Most application developers don't want to reason about instance identity, state co-location, or replication semantics. Building Workflows on Fluid Compute means the runtime stays in the same shape as the rest of the app — regional serverless functions with familiar request semantics — and the workflow layer is a directive away. Developers get durable execution without learning a new primitive.

**Cloudflare's position:** Cloudflare Workflows is a class-based runtime built on Workers and Durable Objects. Each workflow instance maps to a Durable Object with its own SQLite database, co-located with compute, addressable globally.

**Steelman:** Durable Objects are already a stateful, globally addressable primitive with strong consistency and per-instance storage. Building Workflows on top of them means state lives where compute lives, step transitions don't pay a network hop to a central event log, and the workflow runtime inherits the geographic distribution of Workers. The lower-level primitive is exposed because it's useful.

**Steelman quality:** both_strong

**Draft placement:** Section 2, subsection on state persistence and where code runs. Can also be referenced briefly in the lead when naming the architectural fork.

**Narrative payload (draft-ready, insert verbatim or near-verbatim):**

> The asymmetry between the two products is not just stylistic — it reflects what each company believes a workflow runtime is. Vercel Workflows runs on Fluid Compute, a regional serverless substrate that hides instance identity and lifecycle from the developer; the workflow layer is a directive away from ordinary TypeScript or Python code. Cloudflare Workflows runs on Workers and Durable Objects, where each workflow instance is a Durable Object with its own SQLite database co-located with compute. One treats durable execution as an extension of the application; the other treats it as an explicit runtime primitive built on a more fundamental stateful object. Neither framing is wrong, but they produce different programming models, different state semantics, and different answers to where a workflow actually lives.

**Reader decision impact:** 3/3 — This asymmetry directly shapes how developers reason about state, geography, and integration with the rest of their stack — central to choosing between the two.

**Evidence:** https://vercel.com/fluid, https://vercel.com/blog/fluid-how-we-built-serverless-servers, https://developers.cloudflare.com/durable-objects/concepts/what-are-durable-objects/, https://blog.cloudflare.com/building-workflows-durable-execution-on-workers/

### fluid_on_aws_substrate  *(weight 4.483, subject_disclosure)*

**Summary:** Vercel Workflows runs on Fluid Compute, which is Vercel's custom infrastructure built on top of AWS Lambda. Acknowledge briefly when discussing where code runs.

**Disclosing subject:** Vercel

**Disclosure:** Vercel Workflows runs on Fluid Compute, which is Vercel's managed compute layer built on top of AWS Lambda. The workflow runtime inherits Lambda's execution substrate by way of Fluid's abstractions over it.

**Steelman quality:** asymmetric

**Draft placement:** Section 2, 'State persistence and where code runs' subsection — surface as architectural context when explaining where Vercel executes step code, before the comparison table.

**Narrative payload (draft-ready, insert verbatim or near-verbatim):**

> Vercel Workflows runs on Fluid Compute, which is Vercel's own compute layer built on top of AWS Lambda. That substrate matters: Fluid exists in part to soften Lambda's per-invocation execution model, and Workflows inherits the result — a managed orchestration layer that schedules step functions onto regional serverless compute Vercel operates on AWS. Cloudflare Workflows sits on a different substrate entirely: Workers and Durable Objects, running on Cloudflare's own globally distributed runtime. Neither approach is hidden, but the choice shapes everything downstream — where steps execute, how state is co-located with compute, and what each platform can offer at the edge.

**Reader decision impact:** 2/3 — The substrate explains why Vercel's runtime is regional rather than edge-distributed, which directly informs the trigger-latency and geographic-distribution decision rows.

**Evidence:** https://vercel.com/workflows, https://vercel.com/docs/workflows, https://workflow-sdk.dev/, https://vercel.com/docs/workflows/pricing

### cloudflare_testing_dx_gap  *(weight 4.483, subject_disclosure)*

**Summary:** Cloudflare's own engineering blog acknowledges the prior workflow testing experience was a 'black-box process' — a real DX gap, surfaced honestly when comparing observability and testing.

**Disclosing subject:** Cloudflare

**Disclosure:** Cloudflare's documentation acknowledges a substantial set of programming-model constraints that developers must internalize to use Workflows safely: steps must be idempotent and deterministically named, top-level state must be built exclusively from step.do return values, code outside steps may execute multiple times on engine restart, Promise.race and Promise.any need to be wrapped in step.do to cache correctly, Hyperdrive connections cannot be reused across steps, dangling promises from missing awaits silently swallow exceptions, and step timeouts cap at 30 minutes. The 'Rules of Workflows' page exists because the runtime exposes its mechanics directly, and developers who violate the rules get bugs that only manifest after a restart.

**Steelman quality:** asymmetric

**Draft placement:** Section 3 (Where Vercel Workflows goes deeper) — specifically as part of the observability/testing-and-DX-maturity argument, or as a closing beat in the programming model subsection of Section 2 to set up the 'where each goes deeper' framing.

**Narrative payload (draft-ready, insert verbatim or near-verbatim):**

> Cloudflare's own documentation lays out a substantial 'Rules of Workflows' page that developers need to internalize before shipping production code. Steps must be idempotent and deterministically named, top-level state must be built exclusively from step.do return values, and code outside steps may run more than once when the engine restarts. Promise.race and Promise.any need to be wrapped in step.do to cache correctly; Hyperdrive connections cannot be reused across steps; a missing await on step.do silently swallows exceptions. The rules exist because the runtime exposes its mechanics directly — Cloudflare Workflows is closer to a primitive than to a framework, and the surface area shows. For teams that want refactor-safe explicit step identity, this is the cost of admission; for teams that want durable execution to feel like ordinary application code, it's friction Vercel's directive model is designed to remove.

**Reader decision impact:** 2/3 — The rules page is real evidence that Cloudflare's lower-level model imposes cognitive overhead, which directly shapes the workload recommendations for teams that prefer abstraction over primitives.

**Evidence:** https://www.cloudflare.com/developer-platform/products/workflows/, https://developers.cloudflare.com/workflows/, https://developers.cloudflare.com/durable-objects/concepts/what-are-durable-objects/, https://developers.cloudflare.com/workflows/build/rules-of-workflows/

## Dimensions (in priority order)

### programming_model  *(weight 9.745)*

**Vercel:** Vercel Workflows uses build-time directives ('use workflow', 'use step') that turn ordinary async TypeScript or Python functions into durable workflows, with step identity derived implicitly from code structure and orchestration compiled away so workflow code looks like normal function calls.

**Cloudflare:** Cloudflare Workflows uses an explicit class-based model where developers extend WorkflowEntrypoint and wrap each unit of work in step.do('explicit-name', async () => ...), with developer-supplied string names acting as deterministic cache keys for memoized step results.

**Verdict:** depends_on_workload — Vercel's directive model wins for teams who want orchestration to feel like ordinary application code and value AI SDK ergonomics; Cloudflare's explicit step IDs win for workloads where refactor-safety, debuggability, and predictable step identity across deployments matter more than terseness.

**Reader decision impact:** 3/3 — This is the sharpest design fork between the two products and directly determines how a developer writes, refactors, and reasons about durable code, making it a primary basis for choosing between them.

**Scoring:** brief_priority=3 · evidence_density=11 · disagreement_intensity=3

### state_persistence  *(weight 8.584)*

**Vercel:** Vercel Workflows uses managed centralized persistence: every step, input, output, sleep, and error is automatically recorded in an optimized database, with deterministic replay surviving deployments and crashes. Developers do not interact with the state layer directly.

**Cloudflare:** Cloudflare Workflows persists state in a per-instance SQLite-backed Durable Object (the Engine), co-located with compute. Each workflow instance has its own strongly consistent SQLite database; step return values are memoized as cache keyed by step name, and state must be built exclusively from step.do return values because in-memory state is lost on hibernation.

**Verdict:** depends_on_workload — Cloudflare's per-instance co-located SQLite wins for workloads needing strong locality, isolation, and direct queryable state; Vercel's managed centralized log wins for workloads where developers want state persistence to be invisible and require no rules about what lives inside vs outside steps.

**Reader decision impact:** 3/3 — The state model dictates how developers structure workflow code (Cloudflare's hibernation rules force step.do discipline; Vercel's model permits naive variable use), making this a primary axis on which a reader's choice turns.

**Scoring:** brief_priority=3 · evidence_density=6 · disagreement_intensity=2

### compute_substrate  *(weight 8.538)*

**Vercel:** Vercel Workflows runs on Fluid Compute, a managed orchestration layer over AWS Lambda enhanced with in-function concurrency, active CPU pricing, and a Rust-based router across 19 regions; compute is regional and optimized for I/O-bound workloads with streaming and pre-warmed instances.

**Cloudflare:** Cloudflare Workflows runs on Workers and Durable Objects, where each workflow instance is a one-to-one SQLite-backed Durable Object Engine that co-locates compute and storage, runs close to the end user across Cloudflare's global edge, and uses native RPC and Alarms for durable execution.

**Verdict:** depends_on_workload — Cloudflare's edge-distributed Durable Objects win for globally distributed workloads needing low trigger latency and tight coupling to native primitives like R2 and Workers AI; Vercel's Fluid Compute wins for I/O-heavy and streaming workloads in regional execution where in-function concurrency and language flexibility (including Python) matter.

**Reader decision impact:** 3/3 — The substrate determines geographic distribution, state locality, language support, and what neighboring primitives are reachable natively — a foundational decision a reader must make based on where their app already lives and how their users are distributed.

**Scoring:** brief_priority=3 · evidence_density=5 · disagreement_intensity=2

### limits_and_payloads  *(weight 8.483)*

**Vercel:** Vercel Workflows allows up to 50 MB per step payload and 2 GB per run, with no limits on run duration, sleep duration, or queued runs; rate-limited requests retry with backoff rather than failing, and slower replay kicks in only past 2,000 events or 1 GB.

**Cloudflare:** Cloudflare Workflows caps step return values at 1 MiB (with ReadableStream support up to 16 MB chunks) and step timeouts at 30 minutes, pushing larger payloads to external R2 storage with reference keys passed between steps.

**Verdict:** depends_on_workload — Vercel fits workloads passing large AI payloads (images, long context) directly between steps; Cloudflare fits workloads where externalizing state to R2 is acceptable and the discipline of small step returns is welcome.

**Reader decision impact:** 3/3 — The 50x payload-size gap forces a concrete architectural choice: pass data naively between steps (Vercel) or refactor to external storage with reference passing (Cloudflare).

**Scoring:** brief_priority=3 · evidence_density=4 · disagreement_intensity=2

### pricing  *(weight 8.33)*

**Vercel:** Vercel bills Workflows across three resources tied to what passes through the system: Workflow Events (every state transition, $20 per million after 50K free), Workflow Data Written ($0.50/GB after 1GB free), and Workflow Data Retained ($0.50/GB-month). Functions invoked by workflows are billed separately at standard compute rates, and Vercel Queues usage is billed on top.

**Cloudflare:** Cloudflare bills Workflows on the same SKUs as Workers Standard: CPU time (milliseconds), Requests (only the initial invocation, not steps), and Storage. Idle time, sleep, and waiting on I/O do not incur CPU charges, and subrequests don't count as additional requests. Paid plan includes 10M requests/month and 30M CPU-ms/month with $0.02 per additional million CPU-ms.

**Verdict:** depends_on_workload — Cloudflare wins for long-idle or I/O-heavy workflows where sleep and API waits dominate; Vercel's model can be more predictable for compute-heavy workflows with low event counts but its event-based billing penalizes workflows with many small steps.

**Reader decision impact:** 3/3 — The pricing philosophies are fundamentally different — billing for what passes through versus what computes — and directly determine whether a given workload is cheap or expensive on each platform.

**Scoring:** brief_priority=3 · evidence_density=2 · disagreement_intensity=2

### language_support  *(weight 7.538)*

**Vercel:** Vercel Workflows supports JavaScript, TypeScript, and Python (Python in beta) via the open-source Workflow SDK and Vercel Python SDK, framework-agnostic across Next.js, Vite, Astro, Express, Fastify, Hono, Nitro, Nuxt, SvelteKit, NestJS, and TanStack Start.

**Cloudflare:** Cloudflare Workflows is TypeScript-first with class-based WorkflowEntrypoint and explicit step.do() calls; Python support launched in beta November 2025 via Pyodide with idiomatic Python adaptations (decorators, snake_case, asyncio.gather) and a stated goal of full feature parity with the JavaScript SDK.

**Verdict:** depends_on_workload — Vercel currently offers broader practical Python coverage and framework-agnostic JS/TS reach for application developers, while Cloudflare's Pyodide-based Python (with full CPython package support like pandas/matplotlib) better fits data/ML workloads running on its edge runtime.

**Reader decision impact:** 2/3 — Python developers and teams with non-Next.js framework choices will weigh language and framework support directly when picking a runtime.

**Scoring:** brief_priority=3 · evidence_density=5 · disagreement_intensity=2

### observability_testing  *(weight 7.208)*

**Vercel:** Vercel Workflows compiles directive-marked functions at build time into durable steps; testing and debugging happen against transformed code, and competitor critiques (Inngest, HN) argue this obscures stack traces, breakpoints, and step boundaries — Vercel's own observability and testing tooling story for Workflows is not surfaced in the extracted evidence.

**Cloudflare:** Cloudflare openly acknowledged in early 2026 that prior Workflows testing was 'a black-box process' that forced developers to disable isolated storage or skip tests entirely; it shipped a new vitest-pool-workers testing module (introspectWorkflow, introspectWorkflowInstance, step mocking, sleep disabling, isolated storage via `await using`) that runs locally and offline, with explicit string-based step identity making mocks and assertions readable.

**Verdict:** depends_on_workload — Cloudflare now has a concrete, documented local testing story with isolated storage and step mocking that fits teams who prioritize unit-testable workflows and refactor-safe explicit step IDs; Vercel's directive model is contested by competitors on debuggability grounds but better fits teams whose testing strategy centers on integration tests within a familiar TypeScript/Python codebase.

**Reader decision impact:** 2/3 — Teams with strong unit-test discipline will weigh Cloudflare's explicit step identity and new isolated testing APIs against the debugging concerns raised about Vercel's build-time transformation, though for many teams integration testing patterns make this a secondary factor.

**Scoring:** brief_priority=3 · evidence_density=1 · disagreement_intensity=2

### lock_in_portability  *(weight 6.54)*

**Vercel:** Vercel ships an open-source Workflow Development Kit organized around an adapter pattern called 'Worlds' — Local for development, Vercel for production, Postgres for self-hosted, with community adapters for MongoDB, Redis, and others. The same workflow code runs across runtimes; portability is positioned as a deliberate hedge against vendor lock-in.

**Cloudflare:** Cloudflare Workflows is deeply integrated with the broader Cloudflare stack — Workers, Durable Objects, R2, D1, KV, Workers AI. Portability is not a positioning claim; the SDK is open source and runs locally via Miniflare, but the architecture assumes Workers + Durable Objects and migration to other runtimes requires rewrites.

**Verdict:** depends_on_workload — Vercel for teams that want architectural optionality or have been burned by lock-in; Cloudflare for teams whose value comes from deep platform integration and don't expect to migrate.

**Reader decision impact:** 2/3 — Architectural lock-in is a long-horizon risk most teams undervalue at choice time but care about deeply once committed; Vercel's portability story is a legitimate differentiator for risk-aware buyers.

**Scoring:** brief_priority=2 · evidence_density=5 · disagreement_intensity=2

### ai_orientation  *(weight 6.416)*

**Vercel:** Vercel positions Workflows squarely at AI agent reliability as a primary use case, with WDK explicitly designed for AI agents reasoning across long contexts, RAG pipelines, and systems that must be 'both intelligent and dependable' — backed by deep AI SDK integration and WorkflowAgent tooling.

**Cloudflare:** Cloudflare frames Workflows as orchestration infrastructure for AI agents, data pipelines, and ML tasks, with Python support added specifically because that's the language of AI/ML, and pairs Workflows with Workers AI for hosted inference and the Agents SDK.

**Verdict:** depends_on_workload — Vercel goes deeper for TypeScript AI developers via the AI SDK and WorkflowAgent and supports Python with feature parity for ML workloads; Cloudflare wins when hosted inference (Workers AI) and tight coupling to edge primitives matter.

**Reader decision impact:** 3/3 — AI is the dominant use case driving durable execution adoption right now, and the choice between AI SDK/WorkflowAgent integration versus Workers AI hosted inference directly shapes which platform fits a given AI workload.

**Scoring:** brief_priority=2 · evidence_density=3 · disagreement_intensity=1

## Category framing

- **Temporal** on *durable execution*: Durable execution is defined as crash-proof execution — execution that continues despite process or hardware failures, with no consequence to the running application.; A durable execution platform provides an abstraction that insulates code from crashes and enables applications to continue running d
  Draft placement: Lead, parenthetical when defining the category

## Detected asymmetries

### evidence_density_imbalance

State persistence is documented far more heavily on the Cloudflare side (38 claims) than the Vercel side (5 claims). Cloudflare treats state as a first-class architectural concern with explicit documentation of per-instance SQLite, Durable Objects co-location, and state lifecycle. Vercel abstracts state behind the directive model and barely surfaces it as a developer-facing concept.

- Vercel: Vercel treats state persistence as an implementation detail of the runtime. Developers write ordinary async code with `"use workflow"` and `"use step"` directives; the platform handles event logging, replay, and durability without exposing the state model.
- Cloudflare: Cloudflare documents state as an explicit architectural primitive. Each workflow instance has its own SQLite database co-located with compute via Durable Objects. Developers reason about state location, instance pinning, and step-level persistence directly.

**Implication:** The asymmetry reveals what each company believes its product *is*. Vercel believes Workflows is a programming model — state is an implementation concern hidden behind directives. Cloudflare believes Workflows is a runtime primitive — state is part of the surface area developers must understand. This shapes everything downstream: debugging, refactor safety, and the mental model required to use the product effectively.

**Draft treatment:** Surface in the 'State persistence and where code runs' subsection as the architectural through-line. The table should make the asymmetry concrete (centralized event log vs per-instance SQLite). Prose should name that the asymmetry itself is informative — Vercel hides state, Cloudflare exposes it, and that difference reflects each company's conviction about what the product should be.

### evidence_density_imbalance

Observability and testing has 17 claims on the Cloudflare side (plus 6 third-party) and zero on the Vercel side in the extracted corpus. Cloudflare published a dedicated blog post in early 2026 acknowledging that prior testing was a 'black-box process' and shipping substantial tooling improvements.

- Vercel: Vercel's documentation does not foreground observability and testing as distinct concerns; the assumption appears to be that workflows inherit the broader Vercel platform's observability surface (logs, traces, dashboards).
- Cloudflare: Cloudflare explicitly treats workflow testing as a developer experience problem worth dedicated tooling and a launch post. The candor about prior limitations is itself notable — they named the gap publicly.

**Implication:** The reader cannot conclude from corpus density alone that Vercel's testing story is weaker; it may simply be less separately documented because it inherits the platform. But Cloudflare's explicit attention to testing tooling — and their public acknowledgment of where it was weak — is a real signal about DX maturity trajectory.

**Draft treatment:** Address honestly in the 'Where Vercel Workflows goes deeper' or observability discussion. Surface Cloudflare's own framing ('black-box process') with attribution per piece_brief.md editorial tensions. Do not over-claim Vercel superiority on testing absent direct evidence — frame as Vercel inheriting platform-level observability vs Cloudflare building workflow-specific tooling.

### feature_framing_difference

Steps are framed as a compile-time language feature on Vercel (`"use step"` directive transformed at build time) and as an explicit runtime API call on Cloudflare (`step.do(id, fn)` with required string identifier). The same underlying durability primitive is presented as a language-level construct vs a library-level construct.

- Vercel: Steps are a directive — part of how you write the function, not a method you call. The build pipeline transforms directive-marked functions into durable steps. Step identity is derived from code structure.
- Cloudflare: Steps are explicit method calls on a step object passed to the workflow's `run()` method. Each step takes a string ID as its first argument. Step identity is explicit and developer-controlled.

**Implication:** This is the load-bearing programming-model difference. It determines refactor behavior (rename a function: Vercel may need skew protection; Cloudflare doesn't care because IDs are explicit), debugging clarity (Cloudflare's step IDs appear directly in logs and dashboards; Vercel's are derived), and what each product feels like to use day-to-day. The framing difference is not cosmetic — it reflects different bets on where complexity should live.

**Draft treatment:** This is the centerpiece of the 'Programming model and step identity' subsection. The comparison table should make both framings concrete with side-by-side mental models (directive vs method call). Prose should give each side its steel-man per piece_brief.md: Vercel's React `"use client"`/`"use server"` lineage; Cloudflare's refactor-safety and debugging clarity.

### concept_hierarchy

Cloudflare Workflows is documented as sitting on top of a more architecturally fundamental, separately-documented primitive (Durable Objects, with its own concept page). Vercel Workflows is documented as sitting on top of Fluid Compute, which is platform infrastructure rather than a developer-facing primitive in the same way.

- Vercel: Fluid Compute is the substrate; developers don't typically reason about it when writing workflows. The substrate is platform-level (and itself runs on AWS Lambda, though this is rarely surfaced).
- Cloudflare: Durable Objects are a separately learnable primitive with their own conceptual documentation. Workflows is positioned as a managed orchestration layer on top — developers can understand Durable Objects independently and may already use them.

**Implication:** Cloudflare exposes its substrate as a primitive developers can compose with directly; Vercel keeps its substrate behind the application abstraction. This means a Cloudflare developer can reach below Workflows when they need to (using Durable Objects directly), while a Vercel developer's path below Workflows leads to ordinary serverless functions on Fluid Compute, not to a stateful primitive. The composition surface is structurally different.

**Draft treatment:** Surface in the 'State persistence and where code runs' subsection and again briefly in 'Where Cloudflare Workflows goes deeper' (tighter coupling to broader Cloudflare primitives). Note the asymmetry directly: Fluid is to Vercel as Durable Objects are to Cloudflare, but not symmetrically — DO is more architecturally fundamental and developer-facing.

### evidence_density_imbalance

Language support has 6 Vercel claims and 14 Cloudflare claims, but the substantive story inverts the count. Vercel ships TypeScript and Python with feature parity (a real differentiator). Cloudflare's higher claim density covers TypeScript-first plus a more recent, more limited Python story documented in a dedicated launch post.

- Vercel: TypeScript and Python are positioned as equal first-class languages for workflows, with feature parity emphasized — relevant for AI/ML developers whose libraries live in Python.
- Cloudflare: TypeScript is the primary language; Python support exists but was added later and is documented in a separate launch post, suggesting it may not yet have full parity with the TypeScript surface.

**Implication:** Raw claim counts mislead here. Cloudflare has more claims because Python required its own announcement and documentation; Vercel has fewer claims because Python parity is treated as an existing fact of the product. The narrative truth (Vercel: parity; Cloudflare: TypeScript-first with growing Python) runs opposite to claim density.

**Draft treatment:** Treat as a Vercel strength in 'Where Vercel Workflows goes deeper' (Native Python with feature parity). Do not let Cloudflare's higher claim count translate into a stronger-looking Python story in the draft. The AI orientation table should make the parity vs early-stage distinction concrete.

### terminology

The two products use different vocabulary for the same underlying concepts. Vercel speaks of 'workflows' and 'steps' as code constructs marked by directives; Cloudflare speaks of 'workflow instances' (each with its own ID and SQLite database) and 'steps' as method calls. 'Instance' is load-bearing terminology on the Cloudflare side, near-absent on the Vercel side.

- Vercel: A workflow is a function. Running it produces a durable execution; the runtime tracks event history. The 'instance' concept is implicit — the running workflow is the unit.
- Cloudflare: A workflow class is instantiated to produce a workflow instance, each with an ID, its own state, and (under the hood) its own Durable Object. Instances are the explicit unit of execution and addressing.

**Implication:** The terminology gap reflects the state asymmetry. Cloudflare needs 'instance' as a first-class term because each instance is a separately addressable, separately stateful entity. Vercel doesn't need it because the runtime abstracts instance identity behind the function-call mental model.

**Draft treatment:** When introducing each product in the lead, use each company's own terminology. In comparison tables, normalize where possible but flag where the underlying concepts diverge (e.g., 'state per instance' for Cloudflare, 'centralized event log' for Vercel). Don't force symmetry; the asymmetry of vocabulary is itself a finding.

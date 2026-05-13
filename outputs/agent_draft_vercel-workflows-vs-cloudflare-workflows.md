# Vercel Workflows vs Cloudflare Workflows

Every multi-step backend process eventually outgrows stateless functions. The retry that should have run didn't. The third-party API timed out and took the whole pipeline with it. The agent halfway through a long context window hit a deploy and lost its place. Durable execution — the category Temporal named — exists to solve that. The question is what runtime to anchor it to.

Vercel Workflows and Cloudflare Workflows sit on opposite sides of that question. Vercel Workflows is built into the Vercel platform as an extension of normal application code: build-time directives (`"use workflow"`, `"use step"`) compile durable execution into ordinary TypeScript or Python functions on Fluid Compute. Cloudflare Workflows is a class-based runtime built on Workers and Durable Objects, where each workflow instance is its own SQLite-backed Durable Object Engine and every step is an explicit `step.do('name', async () => …)` call.

That architectural fork shapes everything downstream — programming model, state persistence, payload limits, pricing, AI tooling, and lock-in posture. One product treats durable execution as a programming model that hides the runtime; the other treats it as an explicit runtime primitive built on a more fundamental stateful object.

This guide compares the two so you can decide which fits your workload.

## How Vercel Workflows and Cloudflare Workflows compare

The architectural fork above plays out across four dimensions where the products meaningfully differ: how you write a step, where state lives, what you can pass between steps, and how each platform integrates with AI tooling.

### Programming model and step identity

On Vercel, a workflow is a function. You add `"use workflow"` to mark it durable, `"use step"` to mark a unit of work, and the build pipeline transforms the result into a durable execution graph. Step identity is derived implicitly from the code's structure. The mental model is the same as the rest of a Vercel application — async TypeScript or Python with a directive at the boundary, modeled on React's `"use client"` and `"use server"` convention.

On Cloudflare, a workflow is a class. You extend `WorkflowEntrypoint`, implement `run(event, step)`, and wrap each unit of work in an explicit `step.do('fetch-user', async () => …)`. The string ID is required and load-bearing: it's the cache key the runtime uses to memoize that step's return value. Step identity is something you assign, not something the framework infers.

Vercel's case is lineage and ergonomics: the directive model follows React's `"use client"`/`"use server"` convention, lets workflows read as ordinary TypeScript or Python, and treats in-flight migration across code changes as a managed concern. Cloudflare's case is that explicit IDs make step state a value the developer controls — workflows can be refactored, reordered, or rewritten in another language, and as long as the IDs hold, in-flight runs continue correctly. Inngest, which says it shipped an implicit model first and rewrote it after production breakage, argues that directive-derived identity corrupts sleeping workflows when code is edited and that a typo like `'use workfow'` passes every type check before failing at runtime. The disagreement is real and unresolved: directives optimize for code that looks like the rest of your application, explicit IDs optimize for state that survives the code changing underneath it.

| Concern | Vercel Workflows | Cloudflare Workflows |
| --- | --- | --- |
| Programming style | Directive-marked async functions (`"use workflow"`, `"use step"`) | Class extending `WorkflowEntrypoint` with `run(event, step)` |
| Step identity | Derived implicitly from code structure at build time | Explicit string ID passed to `step.do(id, fn)` |
| Refactor behavior | Managed via skew protection for in-flight runs | Stable across refactors as long as step IDs are preserved |
| Language support | TypeScript, JavaScript, Python (parity) | TypeScript-first; Python in beta via Pyodide |
| Mental model | Workflow code looks like ordinary application code | Workflow code is an explicit runtime primitive |

### State persistence and where code runs

Vercel Workflows runs on Fluid Compute, Vercel's compute layer built on top of AWS Lambda; the workflow runtime is a managed orchestration layer that schedules step functions onto regional serverless compute. Cloudflare Workflows runs on Workers and Durable Objects directly — each workflow instance is a Durable Object with its own SQLite database co-located with compute. Cloudflare exposes Durable Objects as a separately documented primitive a developer can reach below the workflow layer to use; Vercel hides instance identity and lifecycle behind directives. The asymmetry reflects what each company believes a workflow runtime is.

The state model follows from the substrate. Vercel records every step input, output, sleep, and error to a centralized, optimized event log; deterministic replay rebuilds workflow state across deployments and crashes, and developers don't interact with the persistence layer. Cloudflare gives each workflow instance its own SQLite database in a Durable Object, co-located with the compute that runs it. State transitions don't pay a network hop to a central store, but the rules around what lives inside a step versus outside one become load-bearing — code outside `step.do()` may run more than once when the engine restarts.

| Concern | Vercel Workflows | Cloudflare Workflows |
| --- | --- | --- |
| State model | Centralized event log, deterministic replay | Per-instance SQLite in a Durable Object |
| State location | Managed by the platform | Co-located with compute |
| Compute substrate | Fluid Compute (regional, on AWS Lambda) | Workers + Durable Objects (globally distributed edge) |
| Geographic distribution | 19 regions | Cloudflare's global edge, instance pinned to one region |
| Developer-facing primitive below | Serverless functions on Fluid Compute | Durable Objects (separately documented, composable) |
| State as a developer concern | Hidden behind directives | Explicit; governed by a "Rules of Workflows" page |

### Limits and payloads

Vercel allows up to 50 MB per step return and 2 GB across an entire run, with no caps on run duration, sleep duration, or queued runs; replay slows only past 2,000 events or 1 GB of history. Cloudflare caps step return values at 1 MiB (with `ReadableStream` support up to 16 MB chunks) and step timeouts at 30 minutes. Workloads with payloads larger than 1 MiB on Cloudflare must externalize state to R2 and pass reference keys between steps.

The 50× gap is not an abstract spec difference. An AI workflow that needs to pass a long context window, a multi-megabyte image, or a structured retrieval result between steps can do so naively on Vercel. On Cloudflare, the same workflow needs an R2 write in step one and an R2 read in step two, with the reference key as the actual return value.

| Concern | Vercel Workflows | Cloudflare Workflows |
| --- | --- | --- |
| Per-step payload | 50 MB | 1 MiB return value (16 MB via `ReadableStream` chunks) |
| Per-run total | 2 GB | No documented run-level cap; constrained by storage |
| Step timeout | No fixed cap | 30 minutes |
| Sleep duration | Unlimited | Unlimited |
| Architectural pressure | Pass payloads directly between steps | Externalize to R2; pass reference keys |

### AI orientation

Both products position AI agent reliability as a primary use case, and each is built around a different shape of AI developer.

Vercel goes deep on the AI SDK and ships `WorkflowAgent`, tooling specifically designed for agents reasoning across long contexts and RAG pipelines. Python parity matters here too — ML libraries live in Python, and Vercel treats Python as a first-class workflow language alongside TypeScript. Cloudflare pairs Workflows with Workers AI for hosted inference and the Agents SDK, and added Python via Pyodide in November 2025 with full CPython package support including pandas and matplotlib, explicitly because that's the language of AI/ML.

| Concern | Vercel Workflows | Cloudflare Workflows |
| --- | --- | --- |
| Primary AI integration | Vercel AI SDK, `WorkflowAgent` | Workers AI (hosted inference), Agents SDK |
| Hosted inference | External providers via AI SDK | Workers AI, native to the platform |
| Python for AI/ML | TypeScript and Python at parity | TypeScript-first; Python in beta via Pyodide |
| Large AI payloads between steps | Up to 50 MB per step | 1 MiB cap pushes payloads to R2 |

## Where Vercel Workflows goes deeper

### How directives let workflow code stay ordinary application code

The directive model is the load-bearing claim of Vercel Workflows. A workflow is a function with `"use workflow"` at the top; a step is a function with `"use step"` at the top. There is no API surface to learn, no class to extend, no method object to thread through your call stack. The workflow reads as the same TypeScript or Python a developer was writing yesterday.

Cloudflare's own documentation lays out a substantial "Rules of Workflows" page that developers need to internalize before shipping production code. Steps must be idempotent and deterministically named, top-level state must be built exclusively from `step.do` return values, and code outside steps may run more than once when the engine restarts. `Promise.race` and `Promise.any` need to be wrapped in `step.do` to cache correctly; Hyperdrive connections cannot be reused across steps; a missing await on `step.do` silently swallows exceptions. The rules exist because the runtime exposes its mechanics directly — Cloudflare Workflows is closer to a primitive than to a framework, and the surface area shows. For teams that want refactor-safe explicit step identity, this is the cost of admission; for teams that want durable execution to feel like ordinary application code, it's friction Vercel's directive model is designed to remove.

### Native Python with feature parity

Python support on Vercel ships through the Vercel Python SDK with the same workflow primitives as the TypeScript SDK. For a team building an AI or ML workload — where pandas, NumPy, and the model-provider SDKs live natively in Python — this matters more than a feature checkbox suggests. Cloudflare added Python in beta in November 2025 via Pyodide with idiomatic adaptations (decorators, snake_case, `asyncio.gather`) and a stated goal of full parity, but parity is the destination, not the current state. Vercel's Python is a first-class language for Workflows today.

### Generous payload limits designed for AI workloads

50 MB per step is not a marketing number; it's an architectural decision that lets a workflow pass an entire AI-generated image, a long retrieval context, or a transcribed audio file directly between steps. The alternative — externalizing every nontrivial payload to object storage and passing reference keys — is workable but adds ceremony to every step boundary. For workflows where most steps return non-trivial data, the difference compounds across the run.

### Framework-agnostic reach across the JavaScript ecosystem

The Workflow SDK runs across Next.js, Vite, Astro, Express, Fastify, Hono, Nitro, Nuxt, SvelteKit, NestJS, and TanStack Start. A team that already chose its framework doesn't need to revisit that choice to add durable execution. Cloudflare Workflows assumes Workers and Durable Objects; the SDK is open source and runs locally in Miniflare, but the architectural assumption holds.

### The Worlds architecture and an open-source SDK

The Workflow Development Kit is open source and organized around an adapter pattern called Worlds — Local for development, Vercel for production, Postgres for self-hosted, with community adapters for MongoDB and Redis. The same workflow code runs across runtimes. For teams that have been burned by lock-in or want optionality on the persistence layer, this is a deliberate hedge built into the product, not a portability story bolted on after the fact.

## Where Cloudflare Workflows goes deeper

### Per-instance SQLite co-located with compute

Each Cloudflare workflow instance is backed by a dedicated SQLite database living inside a Durable Object, in the same place the workflow code runs. Step transitions don't traverse a network to reach a centralized event log. For workloads where state locality matters — many fast steps, strong consistency requirements, queryable per-instance state — this is a meaningfully different architecture than Vercel's centralized model.

### Globally distributed compute close to users

Workers run on Cloudflare's edge across hundreds of cities. Workflow triggers and step execution happen close to the end user, with V8 isolates that have effectively no cold start. Vercel Workflows runs regionally on Fluid Compute. For workloads where trigger latency from a globally distributed user base matters more than language flexibility, edge proximity is a real Cloudflare advantage.

### CPU-time-only billing for I/O-heavy and idle workflows

Cloudflare bills only for CPU time consumed. Sleep doesn't bill. Waiting on an LLM doesn't bill. Subrequests to other services don't count as additional requests. For workflows that spend most of their wall-clock time waiting — long retries, scheduled multi-day jobs, agents waiting on slow inference — the cost ceiling is bounded by actual computation.

### Explicit, refactor-safe step identity

The mirror of Vercel's directive model: because step IDs are strings the developer assigns, they are stable across refactors, visible in stack traces, and addressable in dashboards. A developer can rename functions, reorder logic, or rewrite a step's implementation in a different language, and as long as the assigned IDs hold, in-flight workflows continue correctly. Tests can mock a step object as a plain value without modeling a build-time compiler.

### Tighter coupling to Cloudflare primitives

Workflows compose natively with R2 for cheap storage, Workers AI for hosted inference, KV for fast key-value lookup, D1 for SQL, and Queues for message passing. Durable Objects sit below Workflows as a separately documented primitive — a developer can reach below the workflow layer when they need to, using DO directly. For teams already on Cloudflare, the integration density is real and difficult to replicate from outside.

### A documented testing story with isolated storage and step mocking

Cloudflare's own engineering blog called the prior Workflows testing experience a "black-box process" and shipped a substantial overhaul in early 2026: a `vitest-pool-workers` testing module with `introspectWorkflow`, `introspectWorkflowInstance`, step mocking, sleep disabling, and isolated storage via `await using`, all running locally and offline. Explicit string-based step identity makes mocks and assertions readable. Vercel Workflows inherits the broader Vercel observability and testing surface rather than shipping workflow-specific testing primitives; for teams whose discipline centers on isolated unit tests of workflow steps, Cloudflare's tooling is currently more direct.

## What they cost

The two products made different bets about what to bill for. Vercel charges across three resources tied to what passes through the system: Workflow Events, Data Written, and Data Retained. Cloudflare charges across the same SKUs as Workers Standard: CPU time, Requests, and Storage — billing only for what computes.

| Pricing axis | Vercel Workflows | Cloudflare Workflows |
| --- | --- | --- |
| Billing philosophy | Bills what passes through the system | Bills what computes |
| Primary unit | Workflow Events (every state transition) | CPU time (milliseconds) |
| Sleep / idle / I/O wait | Not billed for compute; events still recorded | Not billed at all |
| Initial trigger | Counts as a Workflow Event | One Request; no charge for subrequests or per-step requests |
| Included tier | 50K events, 1 GB written, then $20 per million events / $0.50 per GB | Paid plan: 10M requests/month, 30M CPU-ms/month |
| Overage | $20 per million events; $0.50/GB written; $0.50/GB-month retained | $0.02 per additional million CPU-ms |
| Underlying compute | Functions invoked by workflows billed separately at standard compute rates | Included in CPU-time billing |

The shapes that benefit from each model are different. Cloudflare's CPU-only billing is unusually friendly to long-idle workflows — agents waiting on slow inference, scheduled multi-day jobs, retries with backoff — where wall-clock time vastly exceeds compute time. Vercel's event-based billing is more predictable for workflows with a small number of large steps, but it adds up faster for workflows with many small steps. Read the models by workload shape, not by sticker price.

## When to choose Vercel Workflows or Cloudflare Workflows

The right choice usually comes down to where your application already lives, what languages your team writes in, and which architectural property matters more for your workload — abstraction or explicit primitives.

| If your workload looks like... | Choose | Why |
| --- | --- | --- |
| AI agent or RAG pipeline in TypeScript on Vercel or Next.js | Vercel Workflows | Deep AI SDK and `WorkflowAgent` integration; directive model keeps workflow code in the same idiom as the rest of the app |
| Python ML workflow with pandas, NumPy, or model SDKs | Vercel Workflows | First-class Python with feature parity to the TypeScript SDK |
| AI agent passing >1 MB of context, images, or long retrieval results between steps | Vercel Workflows | 50 MB per-step payload removes the need to externalize state to object storage |
| Application on a non-Next.js framework (Hono, Fastify, NestJS, SvelteKit, etc.) | Vercel Workflows | Framework-agnostic SDK across the JS ecosystem |
| Team that wants portability and an open-source persistence layer | Vercel Workflows | Worlds architecture with Postgres, Local, and community adapters |
| Workload already on Cloudflare Workers, Durable Objects, R2, or Workers AI | Cloudflare Workflows | Native composition with the rest of the Cloudflare stack; Workers AI for hosted inference |
| Globally distributed users where trigger latency matters | Cloudflare Workflows | Workers run at the edge with effectively zero cold start |
| Long-idle workflow dominated by sleep or I/O wait | Cloudflare Workflows | CPU-time-only billing; sleep and I/O wait don't bill |
| Workflow that must survive heavy refactoring with explicit step identity | Cloudflare Workflows | Developer-assigned string IDs are stable across code changes |
| Team that needs isolated unit tests for individual steps with mocking | Cloudflare Workflows | `vitest-pool-workers` with `introspectWorkflow`, step mocking, isolated storage |
| Compliance or workload requiring per-instance, queryable state | Cloudflare Workflows | Per-instance SQLite database co-located with compute |

Most teams choose based on which platform their application already lives on. For teams making a fresh choice, the question is whether you want durable execution to feel like normal application code — workflows as functions, state as an implementation detail, payloads passed naively — or to be an explicit runtime primitive built on a stateful object you can also use directly.

## Get started with Vercel Workflows

If your application is already on Vercel, Workflows is a directive away. Add `"use workflow"` to a function, mark long-running operations with `"use step"`, and deploy. The Workflow SDK is open source, and the AI SDK and `WorkflowAgent` are ready for AI agent and RAG workloads out of the box. [Sign up for a free account](https://vercel.com/signup) to try it.

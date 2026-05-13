# Vercel Workflows vs Cloudflare Workflows

*A detailed guide to Vercel Workflows vs Cloudflare Workflows: directive-based programming model, per-instance Durable Objects, payload limits for AI workloads, CPU-time billing, framework reach, and when to choose each platform for durable execution.*

Shipping a long-running or multi-step process to production used to mean splitting your code across queues, workers, status tables, retry logic, and monitoring, or adding a separate orchestration system that would require maintenance on top of your core application compute. AI agents that reason for hours and pipelines that fan out across model calls have made this category urgent.

Durable execution runtimes remove that layer entirely, handling persistence, retries, and resumption inside the runtime itself.

Vercel Workflows and Cloudflare Workflows both offer durable execution but have taken opposite bets on what that runtime should be. Vercel makes a workflow a function you mark with a directive. Cloudflare makes it a class you extend with explicit step calls. This architectural fork shapes everything downstream: programming model, state persistence, payload limits, pricing, AI tooling, and portability.

This guide compares the two so you can decide which best fits your workload.

---

## How Vercel Workflows and Cloudflare Workflows compare

The runtime differences play out across four dimensions: how you write a step, where state lives, what you can pass between steps, and how each platform handles AI workloads.

### Programming model and step identity

You add `"use workflow"` at the top to mark the function as durable, and `"use step"` on inner functions to mark units of work. The SDK compiles these into durable routes at build time, with step identity derived from the code's structure. The mental model is the same as the rest of your application, since workflow code is async TypeScript or Python with a directive at the boundary that changes how the runtime treats the code below it.

A workflow on Vercel: 

```typescript
export async function chargeCustomer(orderId: string) {
  'use workflow';

  const order = await fetchOrder(orderId);
  const charge = await processPayment(order);
  await sendReceipt(order, charge);

  return charge.id;
}

async function fetchOrder(id: string) {
  'use step';
  return await db.orders.findOne({ id });
}

async function processPayment(order) {
  'use step';
  return await stripe.charges.create({
    amount: order.total,
    customer: order.customerId,
  });
}

async function sendReceipt(order, charge) {
  'use step';
  await email.send(order.email, charge);
}
```

A Cloudflare workflow is a class. You extend `WorkflowEntrypoint`, implement `run(event, step)`, and wrap each unit of work in `step.do('fetch-order', async () => …)`. You assign the IDs; the framework doesn't infer them.

A workflow on Cloudflare:

```typescript
import { WorkflowEntrypoint, WorkflowEvent, WorkflowStep } from 'cloudflare:workers';

export class ChargeCustomer extends WorkflowEntrypoint<Env, { orderId: string }> {
  async run(event: WorkflowEvent<{ orderId: string }>, step: WorkflowStep) {
    const order = await step.do('fetch-order', async () => {
      return await this.env.DB.findOne(event.payload.orderId);
    });

    const charge = await step.do('process-payment', async () => {
      return await this.env.STRIPE.charges.create({
        amount: order.total,
        customer: order.customerId,
      });
    });

    await step.do('send-receipt', async () => {
      await this.env.EMAIL.send(order.email, charge);
    });

    return charge.id;
  }
}
```


Vercel's directive model is borrowed from React's `"use client"`/`"use server"` convention and aims for the same thing: keep the workflow code as ordinary TypeScript or Python. When you deploy new code while workflows are still running, [skew protection](https://vercel.com/docs/skew-protection) handles the mismatch. Old runs finish on old code, new runs start on new code. Cloudflare's design gives you direct control over step identity. The string ID passed to `step.do()` is the cache key the runtime uses to memoize that step's return. As long as you keep those IDs stable across refactors, in-flight workflows continue running correctly. Which route fits better depends on whether you want workflow code to feel like ordinary application code, or whether you want explicit, refactor-safe step identity you assign and reason about directly.

### State persistence and where code runs

Vercel Workflows runs step functions on [Fluid compute](https://vercel.com/docs/fluid-compute), with the workflow runtime sitting above as a managed orchestration layer that queues steps, runs each one, and hands off between them. State lives in a centralized [event log](https://workflow-sdk.dev/docs/how-it-works/event-sourcing) that records every step input, output, stream chunk, sleep, hook, and error in a run. The runtime replays that log deterministically to rebuild state across deploys and crashes. You don't touch the persistence layer.

Cloudflare Workflows runs directly on Workers and Durable Objects. Each workflow instance is a Durable Object with its own SQLite database co-located with the compute that executes it. State transitions are local and you can drop below the workflow layer to use Durable Objects directly when needed. The trade-off is that the engine can restart mid-run and replay code outside `step.do()` more than once, which makes Cloudflare's ["Rules of Workflows"](https://developers.cloudflare.com/workflows/build/rules-of-workflows/) required reading before shipping.

Both products surface workflow runs through dashboards and CLIs: Vercel via the platform observability tab and `workflow inspect runs --backend vercel`, Cloudflare via the Workers dashboard and `wrangler tail`.

### Limits and payloads  

Vercel [allows](https://vercel.com/docs/workflows/pricing#workflow-run-limits) up to 50 MB per step return and 2 GB across an entire run. Run duration, sleep duration, and queued runs are uncapped; replay starts to slow past 2,000 events or 1 GB of history. Past that, breaking the workflow into child runs maintains replay performance.

Cloudflare [caps](https://developers.cloudflare.com/workflows/reference/limits/) return values at 1 MiB, with `ReadableStream<Uint8Array>` for binary outputs up to 16 MB per chunk, and a 365-day cap on sleep. Anything bigger than 1 MiB must be moved to external storage such as R2, with a reference key passed forward.  

| Limit                            | Vercel Workflows                                                                                                                                                    | Cloudflare Workflows                                                                                          |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Per-step return value            | 50 MB                                                                                                                                                               | 1 MiB (`ReadableStream<Uint8Array>` for binary outputs up to 16 MB chunks)                                    |
| Per-run total state              | 2 GB (replay slows past 2K events or 1 GB)                                                                                                                          | 100 MB Free / 1 GB Paid                                                                                       |
| Per-step duration                | Up to 800s wall-clock on Pro and Enterprise (Active CPU billed during execution, inherits [Vercel Functions limits](https://vercel.com/docs/functions/limitations)) | Up to 5 min CPU time on Paid (default 30s; wall-clock unlimited)                                              |
| Steps per run                    | 10K                                                                                                                                                                 | 1,024 Free / 10K default on Paid, configurable to 25K                                                         |
| Run creations per second         | 1K                                                                                                                                                                  | 100 per second on Free / 300 per second per account, 100 per second per workflow on Paid                      |
| Sleep duration                   | No limit                                                                                                                                                            | 365 days                                                                                                      |
| Concurrency                      | Up to 100K                                                                                                                                                          | 10K actively running at once; 50K total instances per account on Paid, 100 on Free (waiting instances exempt) |
| State retention after completion | 1 day Hobby / 7 days Pro / 30 days Enterprise                                                                                                                       | 3 days Free / 30 days Paid                                                                                    |

This gap is operational. An AI workflow that needs to pass a long context window, a multi-megabyte image, or a structured retrieval result between steps can do so directly on Vercel. You return the value and pick it up in the next step. On Cloudflare, the same workflow becomes an R2 write in step one, an R2 read in step two, and a reference key as the return value between them. The best choice depends on payload size. Steps under 1 MiB are fine on either; anything bigger requires the R2 round-trip on Cloudflare.

### AI orientation

Both products name AI agent reliability as a primary use case but they approach it from different angles. Vercel starts from the JavaScript application side with deep AI SDK integration; Cloudflare starts from the platform-primitives side, with hosted inference running on the same edge as workflow execution. Since either platform works well for most AI workloads, the practical difference is where your AI code lives.

Vercel's AI SDK and Workflow SDK are built around the same type systems and idioms, so you write an agent the same way you write any other workflow. Tools become `"use step"` functions and AI SDK v7's [`WorkflowAgent`](https://ai-sdk.dev/v7/docs/agents/workflow-agent) handles agent state, tool calling, and resumption as workflow primitives. The Python SDK is in beta but tracks the TypeScript SDK directly, with the same workflow, step, sleep, and hook primitives. That's the same language pandas, NumPy, and most model-provider SDKs live in natively.

Cloudflare exposes Workers AI as a binding inside the workflow's `env`, alongside D1, KV, R2, Queues, and Vectorize for embeddings. A model call from inside a step is `this.env.AI.run(...)`, the same idiom as any other Cloudflare binding. Python landed in November 2025 via Pyodide with full CPython support, including pandas and matplotlib. Which fits better depends on whether you want your AI work to live at the application layer or as a platform primitive with co-located inference.

--- 

## Where Vercel Workflows goes deeper

The section above primarily shows where the two products overlap. Those below go deeper into the capabilities that are specific to Vercel Workflows.

### How directives let workflow code stay ordinary application code  

The directive model is the headline pitch of Vercel Workflows. A workflow is a function with `"use workflow"` at the top; a step is a function with `"use step"` at the top. There is no API surface to learn, no class to extend, and no method object to thread through your call stack. The workflow reads as the TypeScript or Python you were already writing.

The cost on Cloudflare is the ["Rules of Workflows"](https://developers.cloudflare.com/workflows/build/rules-of-workflows/) page. Code outside `step.do()` may run more than once when the engine restarts, top-level state must come exclusively from `step.do()` return values, `Promise.race` and `Promise.any` need to be wrapped in `step.do()` to cache correctly, Hyperdrive connections can't be reused across steps, and a missing await on `step.do()` silently swallows exceptions. The rules exist because the runtime exposes its mechanics directly. For teams that want refactor-safe explicit step identity, those rules are the tradeoff. For teams that want durable execution to feel like ordinary application code, the directive model is designed to remove them.

### How Workflows surfaces itself to coding agents 

A coding agent working on a system it can't observe is guessing. Most orchestration platforms expose runs through a dashboard meant for humans; the agent either screen-scrapes or asks the developer to copy-paste run state into the prompt. Neither approach scales when the agent is doing real work across long sessions.

The Workflow SDK ships a CLI (`npx workflow inspect runs --backend vercel`) that returns the same run state a developer would see in the dashboard, in a format the agent can consume directly. There's also a Workflows [skill](https://vercel.com/docs/agent-resources/skills) in the CLI ecosystem (`npx skills add <owner/repo>`) that gives the agent product knowledge about Workflows without needing to re-explain it in every prompt. Cloudflare's `wrangler` CLI tails logs but doesn't ship workflow-specific inspection or a coding-agent skill.

### How framework-agnostic reach removes the migration tax

Adding durable execution to an existing application usually means committing to its framework. A workflow runtime built around Next.js doesn't help if your application is on Hono; one built around Workers doesn't help if you're on Fastify. Teams end up either rebuilding routes onto the supported framework or running a second orchestration layer alongside their existing stack.

The Workflow SDK runs [across](https://workflow-sdk.dev/docs/getting-started) Next.js, Vite, Astro, Express, Fastify, Hono, Nitro, Nuxt, SvelteKit, and TanStack Start, with a Python SDK in beta. A team that already chose its framework doesn't need to revisit that choice to add durable execution. The directive model compiles into framework-appropriate routes at build time. Cloudflare Workflows assumes Workers and Durable Objects. The SDK is open source and runs locally in Miniflare, but it can't be brought to a different runtime.

### How Worlds let workflows run on any infrastructure

Most durable execution products tie the SDK to the runtime. The workflow code that runs on the vendor's cloud can't be lifted to your own infrastructure without rewriting it.

The Workflow SDK is organized around an adapter pattern called Worlds. Each World provides the three components a workflow needs (an event log, a queue, and compute), backed by different infrastructure. Local World runs zero-config on your machine for development. Vercel World is managed and runs on Fluid compute and [Vercel Queues](https://vercel.com/docs/queues). The Postgres World is the self-hosted reference implementation that customers run in production today. Community Worlds for MongoDB, Redis, Turso, and Jazz Cloud are already shipped.

Same workflow code, different runtimes. The SDK is open source under the same license as the AI SDK and Chat SDK. See [Workflow Worlds](https://workflow-sdk.dev/worlds) for the full list with maintainer status and end-to-end encryption support.

### How encryption-by-default ships with every workflow

Sensitive data flows through workflow steps constantly. Agents handling PII pass it between steps; payment workflows accumulate card data; tool calls return API keys, customer information, and internal state. Encrypting that data at the application layer means adding an encryption library, managing key rotation, and auditing the whole pipeline. Most teams either skip it or do it inconsistently across workflows.

Vercel Workflows [encrypts](https://workflow-sdk.dev/docs/how-it-works/encryption) inputs, step arguments, return values, hook payloads, and stream data by default, before any of it is written to the event log. Decryption only happens inside the deployment running the workflow. Nothing is readable in transit or at rest outside your environment. When you need to inspect encrypted data through the dashboard or the `workflow` CLI, explicit decryption is supported with a full audit trail.

Cloudflare Workflows doesn't ship workflow-layer encryption today. Security at the workflow layer is the developer's responsibility to implement.

### How durable streams reconnect clients to in-progress workflows

AI agents and long-running pipelines stream output as they work. When the client disconnects, most streaming systems either drop the output, force the workflow to abort, or require a reconnection layer built around Redis, pub-sub, and external state management. For agents that take minutes or hours to complete, a user kicks off a job, walks away, and comes back to find the stream gone.

`getWritable()` returns a persistent [stream](https://workflow-sdk.dev/docs/foundations/streaming) that the workflow writes to regardless of whether a client is connected. Stream chunks are durably persisted in the run's event log. On the client, `WorkflowChatTransport` detects when a stream ends without a finish event and reconnects automatically. It pulls the `x-workflow-run-id` from the initial POST response and calls a GET endpoint at `{api}/{runId}/stream` to resume from the last event received. Multiple clients can connect to the same run; the link works if shared with another user. [Flora](https://vercel.com/blog/how-flora-shipped-a-creative-agent-on-vercels-ai-stack) uses this pattern across their 50+ image-model pipeline. Customers kick off jobs, close their laptop, and come back to completed results.

Cloudflare supports `ReadableStream<Uint8Array>` for large binary outputs from a single step but hasn't shipped an equivalent client-resumption pattern at the workflow layer. 

---

## Where Cloudflare Workflows goes deeper

Cloudflare offers capabilities that fall outside Vercel Workflows' current scope. If your workload depends on any of these, Cloudflare Workflows may be the right primary choice, or worth running alongside Vercel for specific subsystems.

### Per-instance SQLite co-located with compute

Each Cloudflare workflow instance is backed by a dedicated SQLite database that lives inside its Durable Object, on the same machine as the workflow code. Step transitions read and write against a local file. SQL queries against per-instance state are available directly through the Durable Objects Storage API. For workloads with many fast steps, strong per-instance consistency requirements, or per-instance state you want to query directly, Cloudflare's per-instance SQLite is meaningfully different from Vercel's centralized event log.

### Globally distributed compute close to users

Workers run on Cloudflare's network across 330+ cities in 125+ countries, with V8 isolates that have effectively no cold start. Workflow triggers and step execution can happen in the city closest to the end user. Vercel Workflows runs regionally on Fluid compute. For workloads where trigger latency from a globally distributed user base matters, or for workloads with users in regions where Vercel doesn't currently have a compute region close by, edge proximity is a real Cloudflare advantage.

### CPU-time-only billing for I/O-heavy and idle workflows

Cloudflare's billing model has fewer dimensions: CPU milliseconds consumed, requests handled, and storage retained. Inside a single step, time spent waiting on an LLM call, an external API, or a subrequest doesn't accumulate billed CPU. Vercel pauses Active CPU billing during I/O wait inside a step too, but Vercel also bills per Workflow Step transition and per GB-hour of provisioned memory while the Function instance is alive, including during I/O wait. For workflows like scheduled multi-day jobs or agents waiting on slow inference, Cloudflare's model means compute cost tracks just the CPU-ms actually consumed: no per-step accrual and no memory-during-wait accrual. Sleep between steps doesn't bill compute on either platform.

### Explicit, refactor-safe step identity

Cloudflare steps are identified by string names the developer passes to `step.do("step-name", ...)`. Rename functions, reorder code, or rewrite a step in a different language, and in-flight workflows continue correctly as long as the name holds. Step names appear in stack traces, dashboard run views, and the `step.name`/`step.count` context properties for logging and loop disambiguation. Vercel addresses refactor-safety through skew protection, but the mental model differs: an explicit string ID you can reason about versus a directive whose identity is inferred from source position.

### Tighter coupling to Cloudflare primitives

Workflows access Cloudflare services through in-process bindings. The workflow's `env` exposes R2 for object storage, KV for key-value, D1 for SQL, Queues for message passing, Workers AI for hosted inference, Hyperdrive for connection pooling to external Postgres/MySQL, and Vectorize for embeddings. Durable Objects sit below Workflows as a separately documented primitive. A developer can reach below the workflow layer when they need to and use DO directly. Vercel Workflows composes with Vercel's primitives and external services via standard SDKs, but doesn't have the same in-process binding model. Every external call is a fetch with its own auth and latency.

### A documented testing story with isolated storage and step mocking

Cloudflare's engineering [blog](https://blog.cloudflare.com/better-testing-for-workflows/) called the prior testing experience for Workflows a "black box." The team shipped a substantial overhaul in November 2025. The `cloudflare:test` module (in `@cloudflare/vitest-pool-workers` 0.9.0+) provides `introspectWorkflow` and `introspectWorkflowInstance` for capturing instances, plus modifiers for mocking step results, disabling sleeps, forcing step errors, and injecting mock events. Everything runs against isolated per-test storage with automatic cleanup via `await using`. Explicit string-based step IDs make assertions readable in test output. Vercel Workflows inherits Vercel's broader observability surface but doesn't ship workflow-specific testing primitives today. For teams whose discipline centers on isolated unit tests of workflow steps, Cloudflare's tooling is currently more direct.

--- 

## What they cost

Vercel and Cloudflare both bill for what compute consumes, but the dimensions differ. Vercel Workflows adds a Step accrual ($2.50 per 100K Steps) on top of the underlying Vercel Functions on Fluid compute, which bills invocations, Active CPU, and provisioned memory separately. Storage is billed in GB-Hours. Cloudflare folds compute into a single CPU-millisecond dimension and doesn't bill memory separately; requests and storage (GB-month) are billed alongside. Sleep doesn't bill compute on either platform.

| Feature                | Vercel Workflows                                                                               | Cloudflare Workflows                                                                         |
| ---------------------- | ---------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Hobby / Free tier      | 50K Workflow Steps, 720 GB-Hours storage included                                              | Workers Free: 100K requests/day (shared with Workers), 10ms CPU per invocation, 1 GB storage |
| Paid tier inclusions   | Pro ($20/month): $20 in monthly usage credits                                                  | Workers Paid ($5/mo): 10M requests, 30M CPU-ms, 1 GB storage                                 |
| Overage rates          | $2.50 per 100K Steps; $0.00069 per GB-Hour                                                     | $0.30 per million requests; $0.02 per million CPU-ms; $0.20 per GB-month                     |
| Workflow invocation    | One Step (for the first step's execution)                                                      | One Request; subrequests don't incur additional request costs                                |
| I/O wait inside a step | Active CPU paused; one Step billed per execution; provisioned memory continues to bill         | Active CPU paused; no additional billing                                                     |
| Underlying compute     | Functions invoked by workflow steps billed at standard Vercel Functions on Fluid compute rates | Included in CPU-time billing                                                                 |

For workflows with predictable step counts and large per-step payloads, Vercel's per-Step billing tracks throughput directly and the bill is easy to forecast. For workflows that spend most of their wall-clock time waiting on inference, long retries, or external APIs, Cloudflare's CPU-time-only billing means the bill tracks just the seconds of actual computation, regardless of wall-clock duration.

The right pricing model usually comes down to workload shape. Two workflows with the same step count but different I/O patterns can land in very different cost ranges on the same platform, and each platform's model is calibrated for a different shape.

----

## When to choose Vercel Workflows or Cloudflare Workflows

The right product depends on what you're running, what languages your team writes in, and which capabilities are hard requirements for your workload.

| If your workload looks like...                                                     | Choose               | Why                                                                                                                       |
| ---------------------------------------------------------------------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| AI agent or RAG pipeline in TypeScript on Vercel                                   | Vercel Workflows     | Deep AI SDK and `WorkflowAgent` integration; directive model keeps workflow code in the same idiom as the rest of the app |
| Python AI or ML workflow with pandas, NumPy, or model SDKs                         | Vercel Workflows     | Python SDK in beta tracks the TypeScript SDK directly with the same workflow, step, sleep, and hook primitives            |
| AI agent passing >1 MB of context, images, or long retrieval results between steps | Vercel Workflows     | 50 MB per-step payload and 2 GB per-run state removes the need to externalize to object storage                           |
| User-facing AI agent that streams progress and must survive client disconnects     | Vercel Workflows     | `getWritable()` plus `WorkflowChatTransport` for stream reconnection from any point, no Redis or custom pub/sub           |
| Workflow handling PII, payment data, or sensitive tool outputs                     | Vercel Workflows     | End-to-end encryption by default for step inputs, outputs, and stream chunks; explicit decryption is audited              |
| Application on a non-Next.js framework (Hono, Fastify, SvelteKit, Astro, etc.)     | Vercel Workflows     | Framework-agnostic SDK across the JavaScript ecosystem                                                                    |
| Team that wants portability across infrastructure or open-source persistence       | Vercel Workflows     | Worlds adapter pattern (Local, Vercel, Postgres, MongoDB, Redis, Turso, Jazz Cloud)                                       |
| Coding agents inspect, scaffold, or debug workflow runs as part of the dev loop    | Vercel Workflows     | CLI for run inspection plus a Workflows skill installable through the `skills` ecosystem                                  |
| Workload already on Cloudflare Workers, Durable Objects, R2, or Workers AI         | Cloudflare Workflows | Native composition through in-process bindings (no network hop, no auth, no extra latency)                                |
| Globally distributed users where trigger latency matters                           | Cloudflare Workflows | Workers run on Cloudflare's network across 330+ cities with effectively zero cold start                                   |
| Long-running workflow dominated by retries or LLM wait                             | Cloudflare Workflows | Only actual CPU-ms billed, regardless of wall-clock duration                                                              |
| Team that wants explicit string-based step IDs as a developer mental model         | Cloudflare Workflows | `step.do("step-name", ...)` is the unit of identity, visible in stack traces and dashboards                               |
| Discipline centered on isolated unit tests of workflow steps with mocking          | Cloudflare Workflows | `cloudflare:test` module with `introspectWorkflow`, step mocking, sleep disabling, isolated storage                       |
| Per-instance state you want to query directly via SQL                              | Cloudflare Workflows | Per-instance SQLite database co-located with compute, accessible through the Durable Objects Storage API                  |

Most teams choose based on where their application already lives. For those making a fresh choice, the question is what you want durable execution to feel like. Vercel makes it ordinary application code: workflows as functions, state as an implementation detail, payloads passed directly. Cloudflare makes it an explicit runtime primitive: steps you name, state you can query directly, infrastructure you can reach below and use.

---

## Get started with Vercel Workflows

If your application is already on Vercel, Workflows is a directive away. Add `"use workflow"` to a function, mark long-running operations with `"use step"`, deploy, and watch every run in the Observability tab. The AI SDK and `WorkflowAgent` are ready for agent and RAG workloads out of the box, the Python SDK is in beta, and the open-source SDK works across Next.js, Hono, SvelteKit, and the rest of the JavaScript ecosystem. [Sign up for a free account](https://vercel.com/signup) to try it.
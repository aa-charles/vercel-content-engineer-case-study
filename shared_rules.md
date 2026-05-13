# Shared Rules

> Universal editorial and operational principles for the comparison pipeline.
> Applies to every comparison piece this system produces.
> Read alongside `roles.json` (source handling lookup table) and the current
> `piece_brief.md` (per-piece specifics).

## 1. The category of writing

Every piece this system produces is a **technical comparison guide for
developers**, written in the voice and structure of the Vercel knowledge
base comparison family (vercel-vs-netlify, vercel-vs-fastly,
vercel-waf-vs-cloudflare-waf). Read the existing pieces in that family as
the canonical reference. The audience is technically literate, time-constrained,
and reading the piece because they are choosing.

The piece is not an essay, not a feature roundup, not a marketing page. It
is a guide that helps a reader make a decision and explains the architectural
reasoning behind that decision.

## 2. The neutrality principle

The piece is commissioned by `${primary_subject_vendor}` (defined in
`piece_brief.md`). Their framing is the editorial home — when the products
are roughly equivalent on a dimension, use the commissioning vendor's terms.
Where `${other_subject_vendor}`'s framing is more accurate, more honest, or
where their product is better-suited to a use case, **say so directly**.

Fair accounting is a structural requirement, not just a rhetorical one.
Every comparison piece must include a section where the non-commissioning
product is given dedicated space to go deeper. The structure of the piece
does the work of fairness so the prose can stay confidently in the
commissioning vendor's voice.

A piece that fails this test reads as marketing. A piece that passes it
reads as authoritative — confident about the commissioning vendor while
giving readers the information they need to make their own call.

## 3. The structural spine

Every comparison piece has the same load-bearing structure:

- **Lead (3–4 short paragraphs).** Define what each product is in concrete
  architectural terms. Name the architectural fork — the choice each
  company made that explains everything else. Close with what the guide
  will do for the reader.
- **How [Product A] and [Product B] compare.** Multiple subsections, each
  ending in a comparison table. Tables are load-bearing, not decoration.
  Use them when a table communicates more cleanly than prose.
- **Where each goes deeper.** Either a symmetric pair of sections
  ("Where A goes deeper" / "Where B goes deeper") or an asymmetric
  variant ("[Vendor A] platform deep dive" + "[Vendor B]-specific
  capabilities"). The piece brief specifies which.
- **What they cost.** Comparison table covering pricing model, included
  tiers, and unusual pricing choices. Reference pricing philosophy; do
  not model specific bills.
- **When to choose [A] or [B].** Workload → product → why decision
  table. Specific rows by workload type. This section is required.
- **Closing paragraph and CTA.** Short summary of the practical bottom
  line, then a "Get started" line for the commissioning vendor.

The piece brief may add or remove sections depending on the comparison
(e.g., "Should you run both?" applies when products are commonly stacked;
"Self-serve vs sales-assisted" applies when access models differ). The
sections above are the universal core.

## 4. Voice register

Match the cadence and texture of the Vercel KB comparison family.

- **Confident and specific.** Declarative claims when evidence supports
  them. "Vercel runs as an embedded firewall in the same request path as
  your deployment." Not "Vercel is a leading firewall solution."
- **Concrete numbers.** Use specifics — "~300ms," "126+ PoPs," "20+
  providers," "1 MiB per step return." Vague claims weaken the piece.
- **Short paragraphs.** 3–5 sentences in body sections. Long paragraphs
  signal essay-thinking, not guide-thinking.
- **No marketing adjectives.** Ban list: seamless, powerful, robust,
  cutting-edge, best-in-class, industry-leading, world-class. Describe
  what something does, not how it feels to use it.
- **Inline competitor callouts.** Inside subsections about the
  commissioning vendor, brief callouts comparing to the other vendor are
  expected: "[Other vendor] comparison: ..."
- **Recommendations are specific and conditional.** Phrases like "for
  [workload type], [product] is the better fit because [specific
  reason]." Never "both have tradeoffs."
- **Active subsection headings.** Body subsection headings that describe a
  capability should be active — describing what the capability does, what
  it enables, or the problem it solves — rather than passive labels.
  Prefer "How directives let workflow code function like application code"
  to "The directive-based programming model." Mirrors the WAF piece pattern
  ("How framework-aware rules remove the regex problem," "How sub-300ms
  rule propagation matters during an incident"). Audience is developers —
  verbs over nouns, but no marketing punch.

## 5. Source handling

Every source has a `role` (declared in `sources.json`) that determines how
it should be read. The mapping from `role` to handling rules lives in
`roles.json`, not in this file. Agents look up handling rules
programmatically.

The principles `roles.json` encodes:

- **Vendor docs and pricing pages are factually authoritative** for that
  vendor's product. Treat as ground truth for what the product does.
- **Vendor blog and engineering posts are factual but require attribution.**
  The framing belongs to the vendor; the facts are reliable.
- **Competitor critiques are partisan.** Always name the source explicitly
  ("Inngest argues..."). Never let competitor framing slip in as neutral.
- **Category authority sources (e.g., Temporal on durable execution) get
  cited for framing and vocabulary**, with attribution for specific
  arguments.
- **Community discussion sources are evidence of debate, not authoritative
  claims.** Paraphrase the sentiment, never extract individual commenter
  claims as facts.
- **Style references never enter the extraction pipeline.** They are voice
  samples for the draft agent only.

When sources conflict, weight by `claim_handling`: authoritative >
attribution > partisan > community. When the conflict itself is
editorially interesting, surface it rather than resolve it.

## 6. Treatment of disagreement and asymmetry

When sources disagree on a substantive point, **surface the disagreement
rather than resolve it**. Readers are sophisticated; trust them with the
debate. Naming a disagreement honestly is more credible than picking a
side.

When the products are structured asymmetrically — different concept
hierarchies, different terminology, different content emphasis — the
asymmetry is a finding, not noise. Surface it directly. The way each
company structures its product reveals what each company believes its
product *is*.

## 7. Quoting and copyright

> **Stage scope.** These rules apply to the draft agent's output. The
> extract agent should preserve verbatim quotes from sources where
> present — downstream agents need them for attribution, and the draft
> agent applies quote limits when rendering the final piece.

- **Default to paraphrase.** Direct quotes are reserved for cases where
  the exact wording matters (legal claims, distinctive vendor framing,
  technical precision).
- **Maximum one direct quote per source**, fewer than 15 words.
- **Never quote community sources directly.** Paraphrase community
  sentiment with appropriate hedging.
- **Always name competitor sources** when citing their critique. The
  reader needs to know the framing is partisan.
- **Never reproduce code blocks, pricing tables, or feature lists
  verbatim** from vendor sources. Paraphrase the substance, restructure
  the form.

## 8. Anti-patterns

Concrete things the system should never produce:

- **False balance.** "Both products have tradeoffs." Dead language. When
  the products meaningfully differ, name the difference and recommend by
  workload.
- **Universal winner.** "Product X is better." The piece's authority
  comes from being precisely correct about which product fits which
  workload, not from picking one.
- **Marketing copy with attribution.** "Vendor describes their product
  as fast, powerful, and easy to use." If the source uses marketing
  adjectives, paraphrase the underlying claim without inheriting the
  adjectives.
- **Feature inventory disguised as comparison.** A list of features each
  product has is not a comparison. A comparison names what each product
  bets on and walks the reader through the consequences.
- **Hedging that dissolves real differences.** "It depends on your needs"
  is true but useless. Name the specific needs and which product fits
  each.
- **Burying the architectural fork.** The lead must name the choice each
  company made. Putting it in section 4 is structural failure.
- **Ignoring the category authority.** Most comparison topics have a
  category-defining voice (Temporal for durable execution, Cloudflare
  for CDN, etc.). Acknowledge once as context. Sophisticated readers
  notice when this is missing.

## 9. The reader test

A developer reading the finished piece should come away able to:

1. Make a decision about which product fits their workload.
2. Explain the architectural difference between the products in their
   own words.
3. Articulate at least one thing the non-commissioning product does
   better than the commissioning one.

If a reader can do all three after reading the piece, the piece worked.
If they can do (1) but not (3), the piece is too partisan. If they can
do (3) but not (1), the piece is too neutral. The system targets all
three, every time.

## 10. Write to the question the reader is asking

Every body section answers one question a developer would ask while
evaluating the product. The heading names the question; the prose
answers it.

This is the load-bearing pattern across the Vercel KB comparison family.
Compare: "The directive-based programming model" (a label) versus "How
directives let workflow code feel like the rest of your application" (a
question with an answer). The first describes a feature; the second
tells the reader why they should care and what they get.

The reader is always asking some version of: how does this work in
practice, what would I actually see and do, how is this different from
what I have today, what would change about my workflow if I adopted it.
Sections that don't answer one of those questions are not earning their
place.

To answer the question well:

- **Show the code first.** When the question involves how something is
  written, configured, or invoked, the answer leads with the actual
  shape of the code, configuration, or call. The developer should be
  able to picture writing it before reading the philosophy behind it.
  The WAF article shows `checkBotId()`; the Workflows comparison should
  show `'use workflow'` next to `step.do()`.
- **Show the lifecycle.** For products that run over time, the question
  the reader is asking is some form of "what happens when I use this?"
  Answer with: how it's triggered, where it executes, what the developer
  sees while it runs, what happens when it fails, what they do in
  response.
- **Numbers, not adjectives.** "Under 300ms globally" answers a
  question. "Fast propagation" doesn't. The WAF article never says fast;
  it says how fast.
- **Real outcomes, named.** When the source corpus contains a specific
  customer, project, or incident — Mux migrating to Vercel Workflows,
  Cloudflare's Deep Analysis catching a 500% bot spike — surface it.
  Concrete proof points answer the question "does this actually work?"
  in a way no abstraction can.

The test for any body section: can a developer reading it picture
themselves doing the thing described, with code or configuration they
could write, in a workflow they recognize from their own work? If yes,
the section earned its place. If no, the section is describing a
feature instead of answering a question.

Architectural framing belongs in the lead and in tension paragraphs —
those are the places where philosophy is the answer the reader needs.
Everywhere else, the section is structured around a question, and the
answer is concrete.

# Hermes Cloud Infrastructure + MRR Plan

> **For Hermes:** This is a planning-only document. Use it to drive future implementation and delegation.

**Goal:** Turn Hermes into a durable, revenue-generating agent platform with reliable infrastructure, better internal autonomy, and one or two paid offerings that can compound into MRR.

**Architecture:** Keep the core system simple: ambrosia is the control plane for local development and user-facing UI, raven is the workhorse for heavier agent workloads, and Tailscale/Caddy are the access layer. Build a thin orchestration layer that can spawn isolated agent workers, track their work, and route tasks to the cheapest reliable execution path. Monetization should start with a narrow, high-value service built on top of those capabilities, not a generic AI app.

**Tech Stack:** Hermes agent stack, Cursor Agent CLI, raven, ambrosia, Tailscale, Caddy, open-webui, Linear, GitHub, gbrain, cron, shell tooling.

---

## What we’re optimizing for

1. Reliability: the assistant should keep running without manual babysitting.
2. Leverage: more agents on raven when the work is parallelizable.
3. Productization: every internal improvement should point toward something sellable.
4. Compounding MRR: repeatable workflow value, not one-off consulting.

---

## Strategic bets

### Bet 1: Hermes Cloud as an "AI operations layer"
Make Hermes the system that routes, remembers, monitors, and executes work across machines and agents. The product is not just chat; it is task completion with persistence.

### Bet 2: Sell workflow outcomes, not access to models
The easiest MRR comes from services where the user values completion, speed, and continuity more than raw model access:
- human+AI task processing
- operator-style assistant services
- internal automation for small teams
- ongoing research/monitoring with summaries and actions

### Bet 3: Internal dogfood becomes the product
Every pain point we solve for ourselves becomes a candidate paid feature:
- memory / context compression
- agent delegation
- multi-machine orchestration
- health monitoring / self-healing
- Slack/Linear/GitHub task handling

---

## Infrastructure plan

### 1) Make raven the execution tier
Objective: use raven for parallel agent work so the local machine stays responsive.

Concrete actions:
- Standardize a "task worker" pattern on raven for long-running or parallelizable jobs.
- Keep a small set of worker profiles: research, coding, QA, monitoring.
- Ensure each worker has clear isolation: separate worktree, separate logs, separate scratch space.
- Use cron only for scheduled jobs that are truly periodic; use workers for everything else.

Why it matters:
- lets Hermes stay interactive
- increases throughput without tying up ambrosia
- makes it easy to scale by adding more workers later

### 2) Build a lightweight task router
Objective: decide where work goes before a human has to.

Routing rules:
- local/interactive = ambrosia
- parallel/research-heavy = raven worker
- repeatable fetch/monitor jobs = cron or worker with schedule
- customer-facing request = queue + worker + review

The router should consider:
- task type
- expected duration
- need for browser/web access
- need for GitHub/Linear writes
- need for persistent context

### 3) Formalize memory and context
Objective: keep Hermes better than a stateless agent.

Concrete actions:
- continue using gbrain as long-term memory for durable facts
- treat session_search as the "recent working memory" layer
- summarize recurring projects into concise notes after major work
- store decision logs: what we tried, what worked, what failed, what to do next

This matters for both internal quality and future product features.

### 4) Separate control plane from workers
Objective: reduce blast radius and make autonomy safer.

Control plane:
- coordination logic
- memory
- scheduling
- task intake
- approval rules for risky actions

Workers:
- code changes
- web research
- repo inspection
- customer work
- monitoring jobs

If a worker fails, the control plane should recover and reschedule, not die with it.

### 5) Add observability for the mission
Objective: know what Hermes is doing and whether it is generating value.

Track:
- tasks completed per day
- tasks delegated to raven
- time saved on recurring workflows
- number of actionable insights captured
- number of revenue-related experiments shipped
- number of customer-ready outputs generated

This becomes the dashboard for the mission.

---

## MRR plan

### Offer A: AI task concierge for busy operators
Target user: small business owners, founders, operators, and technical solo founders.

Promise:
- give me a task
- I turn it into completed work, research, artifacts, and follow-up
- if needed, I route parts to agents and keep context across sessions

Packaging:
- monthly subscription with a fixed number of "operator tasks"
- include summaries, action items, and delivered artifacts
- premium tier for faster turnaround and more parallel work

Why this is likely to sell:
- clear outcome
- recurring need
- users pay to remove cognitive load

### Offer B: Research + monitoring subscription
Target user: people who want ongoing intelligence on a niche.

Examples:
- repo watch + product trend summaries
- market research / competitor monitoring
- alerting on opportunities
- curated reports with recommended action

Packaging:
- weekly digest
- watchlists
- alerts when something important changes
- optional follow-up action recommendations

Why this is likely to sell:
- recurring value
- low marginal cost once the pipeline exists
- easy to productize from current skills

### Offer C: Hermes Cloud for power users
Target user: people who want a private, agentic workspace.

Promise:
- private assistant memory
- task routing
- repo-aware work
- browser/research capability
- human review when needed

This is the long-term platform play, but it should only happen after we prove a simpler service.

---

## What to research from trending repos

Research order:
1. claude-mem
2. open-agents
3. superpowers
4. andrej-karpathy-skills
5. voicebox

What we’re looking for:
- memory architecture
- skill/workflow packaging
- orchestration patterns
- onboarding and retention mechanics
- anything that turns capability into habit

Decision rule:
- if a repo teaches us how to make Hermes more persistent, more agentic, or easier to sell, it is worth studying
- if it is just a demo, skip it

---

## 30-day execution plan

### Week 1: Inventory and stabilization
- Inventory current Hermes/raven services.
- Identify the main failure modes in delegation and auth.
- Define the worker profiles we actually need.
- Write down the current mission metrics.

### Week 2: Workerization
- Make raven the default parallel work target.
- Standardize a worker launch pattern.
- Create a simple task routing policy.
- Add basic logging/health checks for workers.

### Week 3: Research and product framing
- Deep-read the top trending repos that map to our mission.
- Extract reusable patterns for memory, skills, and orchestration.
- Write a one-page positioning doc for the first paid offer.

### Week 4: Revenue prototype
- Turn one internal workflow into a sellable service spec.
- Define deliverables, SLA, and pricing.
- Create the first intake flow and customer-facing description.
- Decide what to build first versus what to manual-service first.

---

## Risks / tradeoffs

- Overbuilding infrastructure before demand exists.
- Chasing generic AI assistant vibes instead of a specific paid outcome.
- Too many workers without a routing policy.
- Memory and delegation becoming brittle if we don’t standardize.
- Monetization getting delayed by internal perfectionism.

Mitigation:
- ship the simplest service that solves a real problem
- keep the orchestration thin
- make every infrastructure change justify itself with either reliability or revenue

---

## Immediate next decisions

1. Which paid offer do we want to test first: AI task concierge or monitoring/research?
2. Do we want raven optimized for worker throughput or for long-lived service jobs first?
3. What is the minimum dashboard we need to see whether Hermes is making progress?
4. Which of the trending repos should be researched immediately for reusable patterns?

---

## Recommended next step

Start with:
- worker routing on raven
- a simple internal dashboard
- one narrow paid offer

That gives us infrastructure leverage and a path to MRR without waiting on a grand platform build.

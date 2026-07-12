# Roadmap — opendata

> From a runnable demo to the open standard for data-team context. Sequenced so
> the riskiest, highest-value thing (grounded-answer accuracy) is proven early,
> and monetization only starts once single-player is genuinely delightful.

Related: [`architecture.md`](./architecture.md) · [`onboarding.md`](./onboarding.md)
· [`golden-sql.md`](./golden-sql.md) · [`connectors.md`](./connectors.md).

## North-star metrics

- **TTFGA** — time-to-first-grounded-answer (< 2 min, zero forms).
- **Activation** — 1 source connected + 1 successful grounded ask.
- **Answer accuracy** — % of asks that return the correct result (measured by the
  eval harness; the golden set is ground truth).
- **Adoption** — GitHub stars, weekly active projects, design partners → later,
  paying teams.

---

## Phase 0 — Vertical slice ✅ (done)

dbt Core + DuckDB + offline engine (golden → metric → generated, read-only
guarded) + Typer/Rich CLI + entry-point connector plugins + design docs. Runs
offline on `examples/toy`. *This is where we are.*

---

## Phase 1 — First real answer (single-player MVP)

**Goal:** a real data team runs `opendata init` on their own dbt + warehouse and
gets a real, grounded answer in under two minutes. Turns the demo into a product.

**Deliverables**
- [ ] **Postgres connector** — detect from `~/.dbt/profiles.yml` / `DATABASE_URL`;
      read-only execute. (Most common, easiest — do first.)
- [ ] **Snowflake connector** + the read-only **`GRANT` generator** (onboarding §6).
- [ ] **Claude LLM provider** — real text-to-SQL behind the model-agnostic
      interface; BYO API key; Ollama option for fully-local.
- [ ] **Embeddings retrieval** — replace the lexical stub (sqlite-vec / LanceDB);
      embed schema, metrics, goldens, and past queries.
- [ ] **Self-repair loop** — feed SQL/DB errors back to the model, bounded retries.
- [ ] **Metric-first compilation** — resolve to dbt metrics via MetricFlow /
      Semantic Layer instead of hand-written SQL when a metric exists.
- [ ] **Query-history ingestion** — pull warehouse history as "past analysis".
- [ ] **Golden capture** — inline "save as golden" after an ask; `opendata verify`.
- [ ] **Eval harness v1** — `opendata eval` scores the engine against the golden
      set (result / shape / execution). Accuracy is a tracked number from day one.

**Exit criteria:** 5–10 design partners hit **TTFGA < 2 min** on their *own* stack;
baseline accuracy measured and trending up.

**Decisions to lock:** vector index (sqlite-vec vs LanceDB); metric compilation
(MetricFlow vs our own IR); default model + whether managed inference ships now.

---

## Phase 2 — The curation flywheel + ecosystem (make it sticky)

**Goal:** the team's knowledge compounds, and the community can extend opendata.

**Deliverables**
- [ ] **Golden SQL lifecycle** — propose → review → approve; staleness detection;
      **CI check** (`opendata verify` in GitHub Actions); coverage in `status`.
- [ ] **dbt Cloud connector** — Semantic Layer metrics + run history.
- [ ] **First BI / product connectors** — PostHog, Metabase, Looker (LookML).
      These prove the ecosystem model end-to-end.
- [ ] **`opendata connector new`** scaffolder + **conformance test kit**
      (`opendata.testing`) — makes writing a connector ≈ "fill in four methods".
- [ ] **Connector registry v0** — `connectors.json` + a hub page on the web.
- [ ] **Golden family** — golden metrics / joins / glossary beyond raw SQL.

**Exit criteria:** goldens visibly compounding (coverage climbs); ≥3
first-party/community connectors live; conformance kit public; "good first
connector" list drawing external PRs.

---

## Phase 3 — Team / multiplayer (opendata Cloud beta) — monetization begins

**Goal:** single-player golden SQL becomes multiplayer; first revenue.

**Deliverables**
- [ ] **FastAPI server** — same engine, HTTP transport.
- [ ] **Hosted context store** on object storage + **always-on indexing**.
- [ ] **Web workspace** in `opendata-web` — ask UI, shared golden library, lineage
      (the app, not just the marketing site).
- [ ] **Auth / orgs / roles**; shared golden library with approvals + **audit log**.
- [ ] **Managed OAuth** for SaaS connectors; **VPC connector-agent** for warehouses
      (creds never leave the customer's infra).
- [ ] **Managed inference ("opendata Zen"-style)** — optional, thin margin; BYO-key
      stays the default.
- [ ] **Billing** — seats + usage.

**Exit criteria:** first paying teams; team-tier value = collaboration +
governance on golden SQL. (Commercial detail in the private strategy repo.)

---

## Phase 4 — Scale, agents, enterprise

**Goal:** breadth, the agent surface, and enterprise readiness.

**Deliverables**
- [ ] **Breadth** — BigQuery, Databricks, Redshift, DuckDB-files; Tableau, Mode,
      Hex; Slack, Notion (prose analysis).
- [ ] **Agent / MCP interface** — expose opendata's context to AI agents via an MCP
      server. "Context for every query" for agents, not just humans.
- [ ] **Semantic cache** as a real subsystem (dogfoods the object-storage side-bet).
- [ ] **Enterprise** — SSO/SCIM, RBAC, PII controls, self-host support, SLAs.
- [ ] **Registry maturity** — verified tier + security review, partner program.
- [ ] **Accuracy program** — continuous eval, a public benchmark + leaderboard.

---

## Cross-cutting workstreams (run in parallel throughout)

- **DX & onboarding polish** — the `init` flow is the product's front door; keep
  optimizing TTFGA and drop-off (instrument the funnel; opt-in anonymous telemetry).
- **Security** — read-only always, secrets never in-repo, supply-chain trust for
  connectors (tiers, review, signing).
- **Docs & DevRel** — the docs *are* the adoption engine (opencode-style).
- **Community** — Discord, contributor program, "good first connector".
- **Marketing site** — `opendata-web` iterates alongside the product.

---

## Decisions to lock (with recommendations)

| Decision | Recommendation |
|---|---|
| Runtime | **Python-first** — decided. |
| Vector index | **sqlite-vec** to start (zero-dep, embedded); LanceDB if scale demands. |
| Metric compilation | Lean on **dbt MetricFlow / Semantic Layer**; only build our own IR if it blocks. |
| Connector distribution | **Separate PyPI packages** via entry points (community owns their repo); revisit monorepo if conformance enforcement gets hard. |
| Default model | **Claude default + BYO-key**; managed inference deferred to Phase 3. |

---

## The first sprint (do this next)

Highest leverage = de-risk **grounded-answer accuracy** on real data, because it's
the make-or-break and it's measurable:

1. **Postgres connector** (detect from dbt profiles) — run on a real warehouse.
2. **Claude provider** — real text-to-SQL, replacing the offline stub.
3. **Embeddings retrieval** + **self-repair loop**.
4. **Eval harness v1** — turn `examples/toy` (and a partner's schema) into a scored
   accuracy suite.

Ship that, point it at one design partner's dbt+Postgres, and we have a real
product with a number attached to its quality. Everything else builds on it.

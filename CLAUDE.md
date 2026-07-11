# CLAUDE.md — opendata-backend

Context for Claude Code (and humans) working in this repo.

## What opendata is

The open-source data workspace in the AI era. It connects a data team's
**warehouse, dbt metrics, dashboards, and past analysis** into one shared
context, then answers questions grounded in it (with the SQL and lineage shown).
Tagline: *10× the impact your data team can have.* Inspired by OpenCode; built
for data teams.

## Strategic direction (decided)

- **Company model: the opencode model** — a broad, open-source, adoption-led tool.
  The moat is usage + community, not a narrow hosted primitive. Onboarding is the
  most important surface (adoption dies on auth friction).
- The **turbopuffer model** (one narrow object-storage primitive with a $ claim)
  was considered and set aside for opendata — it's tracked as a *separate* set of
  side-bets. Business, monetization, GTM, and those side-bets live in the
  **private `opendata-strategy` repo**, not here. Do not put pricing/margin/GTM
  specifics in this public repo.
- Frontend/marketing site: **`opendata-web`** (private). Design language borrowed
  from turbopuffer + opencode: monospace, dark navy, blue-primary / red-accent
  duotone, ASCII-box components.

## Design docs (read these first)

- [`docs/architecture.md`](docs/architecture.md) — components, context-store data
  model, connector SDK, the answer-engine pipeline, build order.
- [`docs/onboarding.md`](docs/onboarding.md) — seamless onboarding: auto-detect
  existing creds, `opendata init`, connector catalog, trust model.
- [`docs/golden-sql.md`](docs/golden-sql.md) — the curation layer (golden SQL /
  metrics / joins). The compounding moat; make it *fun*.
- [`docs/connectors.md`](docs/connectors.md) — the community connector ecosystem:
  entry-point plugins, conformance kit, trust tiers. The other compounding moat.

## Architecture in one breath

`CLI/API → Engine → [Connectors → Context Store] + [Answer Engine → Executor]`.
Answer engine precedence: **golden hit → metric-first → generate**, always
`sqlglot`-validated (read-only + LIMIT) before executing. See architecture §6.

## Stack & layout

Python-first (the data ecosystem is Python-native). `typer`+`rich` CLI,
`sqlglot` for SQL safety/transpile, `duckdb` for the local/toy path, model-
agnostic LLM layer (Claude default, BYO-key). Layout is documented in
architecture §3; code is under `src/opendata/`.

## Run the vertical slice (offline, no API key)

```bash
uv venv && uv pip install -e .
.venv/bin/opendata init  --yes --path examples/toy
.venv/bin/opendata ask   "weekly active teams last 8 weeks" --path examples/toy
.venv/bin/opendata status --path examples/toy
.venv/bin/opendata doctor --path examples/toy
```

`examples/toy/` is a bundled dbt manifest + DuckDB seed + a pre-seeded golden, so
the whole detect → index → answer loop runs with no external DB and no LLM key
(an offline `StubProvider` stands in for Claude).

## Conventions

- **Read-only, always.** SQL is guarded at parse time (`sql/validate.py`). Never
  add a code path that can mutate a warehouse.
- **Secrets never in the repo.** Config (`.opendata/config.yml`) holds references
  only; real secrets come from env/keychain. Runtime artifacts
  (`config.yml`, `context.json`, `warehouse.duckdb`) are gitignored.
- **Connectors are pluggable** — implement the `Connector` protocol
  (`connectors/base.py`) and `register()`; keep `detect()` fast + side-effect-free.
- **Correctness is measured.** The golden set doubles as the eval set; treat the
  answer engine as an experiment surface (see architecture §7).

## Status

v0.1 vertical slice runs end-to-end on the toy fixture. Next: real warehouse
connectors (Postgres/Snowflake), a Claude provider, embeddings-based retrieval,
the eval harness, and the FastAPI server for `opendata-web`.

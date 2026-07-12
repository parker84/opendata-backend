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

## Roadmap

Full phased build plan: [`docs/roadmap.md`](docs/roadmap.md). We're at **Phase 0
done** (vertical slice). Next up: **Phase 1** — first real answer (Postgres +
Claude provider + embeddings retrieval + eval harness).

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
.venv/bin/opendata eval  --path examples/toy
.venv/bin/opendata status --path examples/toy
.venv/bin/opendata doctor --path examples/toy
```

`examples/toy/` is a bundled dbt manifest + DuckDB seed + a pre-seeded golden, so
the whole detect → index → answer loop runs with no external DB and no LLM key
(an offline `StubProvider` stands in for Claude).

**Real Claude provider:** `uv pip install -e ".[llm]"` + `export ANTHROPIC_API_KEY=…`.
`llm/provider.py` uses the Anthropic SDK — `claude-opus-4-8` by default (override
via `OPENDATA_MODEL`), adaptive thinking, structured-output SQL, and a self-repair
method the engine calls on execution errors (generated path only). Selection fails
soft to the stub when the SDK/key is absent, so the offline path always works.
`opendata eval` scores the engine against the golden set (the eval ground truth).
When editing this provider, consult the `claude-api` skill for current SDK usage.

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

## Testing

`pip install -e ".[dev]" && pytest` — 37 tests (SQL guard, golden match/save/verify,
context store, connector detect + GRANT, engine golden/metric/generated paths,
eval accuracy, provider gating). GitHub Actions CI (`.github/workflows/ci.yml`)
runs pytest + `opendata verify` + `opendata eval` on every push/PR. The `toy`
pytest fixture `init`s a hermetic copy of `examples/toy`.

## Status

Phase 1 largely done: multi-warehouse execution dispatch (`connectors/execute.py`),
**Postgres** connector (detect from `DATABASE_URL`/dbt profiles, GRANT generator;
live exec needs a DB), **Claude** provider + self-repair, **golden lifecycle**
(`save`/`verify`), **eval harness**, tests + CI. Next (see `docs/roadmap.md`):
embeddings retrieval, Snowflake, query-history ingestion, then the FastAPI server
for `opendata-web`.

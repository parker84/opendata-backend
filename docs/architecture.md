# Architecture — opendata backend

> How opendata connects to a team's stack, builds one shared context, and answers
> questions grounded in it. This is the spec the code is scaffolded against.

Related: [`onboarding.md`](./onboarding.md) (how sources connect) ·
[`golden-sql.md`](./golden-sql.md) (the curation layer).

---

## 1. Components

opendata is five components behind one core, exposed via CLI first and an HTTP
API later.

```
        ┌──────────────────────────────────────────────────────────┐
  CLI ─▶ │  ENGINE (orchestrator)                                   │
  API ─▶ │                                                          │
        │   ┌────────────┐   index     ┌──────────────────────────┐ │
        │   │ CONNECTORS │ ──────────▶ │  CONTEXT STORE           │ │
        │   │ dbt · wh · │             │  catalog · lineage graph │ │
        │   │ posthog…   │             │  · vector index · golden │ │
        │   └────────────┘             └────────────┬─────────────┘ │
        │                                            │ retrieve      │
        │   ┌─────────────────────────────────────────▼───────────┐ │
        │   │ ANSWER ENGINE                                        │ │
        │   │ golden? → metric? → generate → validate → execute   │ │
        │   │            ▲ self-repair loop ▲                      │ │
        │   └───────────────────────────┬─────────────────────────┘ │
        │                    answer + SQL + lineage + provenance     │
        └──────────────────────────────────────────────────────────┘
                 ▲ semantic cache wraps generate + execute ▲
```

1. **Connectors** — pluggable ingest (`detect / validate / grant_sql / index`).
2. **Context store** — the unified catalog + lineage graph + vector index +
   golden library. The heart.
3. **Answer engine** — question → grounded SQL/metric → result. The hard part.
4. **Execution layer** — read-only SQL against the warehouse.
5. **CLI + API** — one engine, two transports.

---

## 2. Stack

Python-first — the ecosystem opendata must speak to (dbt, MetricFlow, warehouse
drivers, `sqlglot`, LLM/embedding SDKs) is Python-native.

| Concern | Choice |
|---|---|
| SQL parse / validate / transpile | **`sqlglot`** (dialect-aware; guards non-`SELECT`) |
| Warehouse execution | native drivers behind an adapter; `duckdb` for the local/toy path |
| dbt context | parse `target/manifest.json`; MetricFlow / Semantic Layer for metrics |
| Context store | **SQLite/DuckDB** (catalog) + **`sqlite-vec`/LanceDB** (vectors) |
| LLM | model-agnostic wrapper, **Claude default**, BYO-key, Ollama for local |
| CLI / TUI | **Typer + Rich** |
| Server (later) | **FastAPI** |
| Packaging | `uv` / `pipx`; `pyproject.toml`; `curl \| bash` installer later |

---

## 3. Repo layout

```
opendata/
├── docs/                      # onboarding.md · architecture.md · golden-sql.md
├── pyproject.toml
├── src/opendata/
│   ├── cli.py                 # Typer app: init · ask · doctor · status · connect
│   ├── engine.py              # orchestrator: retrieve → resolve → execute
│   ├── config.py              # .opendata/config.yml load/write (secret refs only)
│   ├── context/
│   │   ├── store.py           # catalog + vectors (SQLite/DuckDB)
│   │   ├── models.py          # Table, Column, Metric, Lineage, Golden, PastQuery
│   │   └── retrieve.py        # ranking: golden → metric → schema retrieval
│   ├── connectors/
│   │   ├── base.py            # Connector Protocol + registry
│   │   ├── dbt_core.py        # manifest.json (zero-auth)
│   │   ├── warehouse_duckdb.py# local/toy execution + schema
│   │   └── warehouse_pg.py    # detect from ~/.dbt/profiles.yml (later)
│   ├── sql/
│   │   ├── validate.py        # sqlglot: parse, read-only guard, LIMIT inject
│   │   └── dialect.py         # transpile per warehouse
│   ├── llm/
│   │   └── provider.py        # LLMProvider Protocol; Claude + Stub(offline)
│   ├── golden/
│   │   └── store.py           # .opendata/golden/*.sql read/verify
│   └── eval/
│       └── harness.py         # golden set → accuracy metric
└── examples/toy/              # bundled dbt + DuckDB fixture for `init` demo
```

---

## 4. Context store — data model

The context store is the unified representation everything retrieves from. Core
entities (see `context/models.py`):

- **Table** — `id, connection, schema, name, description, row_estimate, tags`.
- **Column** — `table_id, name, type, description, is_pii, sample_values`.
- **Metric** — `id, name, definition, sql/metricflow_ref, owner, source` (dbt,
  LookML, or hand-defined golden). Metrics **outrank** raw tables in retrieval.
- **Lineage** edge — `from_id → to_id, kind` (model→model, metric→model,
  dashboard→query). Powers "what feeds this number."
- **PastQuery** — `sql, question?, source, run_count, last_seen`. From warehouse
  history + BI logs; fuels retrieval and golden suggestions.
- **Golden** — `id, question, aliases[], sql|metric, owner, status, verified_at,
  expects`. The verified layer (see `golden-sql.md`).

Two indexes over these:

- **Catalog** (relational, SQLite/DuckDB) — exact lookups, joins, lineage walks.
- **Vector index** (`sqlite-vec`/LanceDB) — embeddings of table/column/metric
  descriptions, past queries, and golden questions for semantic retrieval.

Storage is **local-first** (`.opendata/context.db`), incremental, and resumable.
Hosted mode backs the same schema with object storage.

---

## 5. Connector SDK

Adding a source = implementing four methods. Fast, side-effect-free `detect()` is
what powers the auto-detected onboarding checklist.

```python
class Connector(Protocol):
    key: str                          # "dbt_core", "duckdb", "snowflake", …
    kind: Literal["semantic", "warehouse", "bi", "product", "prose"]

    def detect(self, env: Env) -> DetectResult | None: ...   # no network, no writes
    def validate(self, cfg: ConnConfig) -> HealthReport: ...  # read-only, powers doctor
    def grant_sql(self, cfg: ConnConfig) -> str | None: ...   # least-priv setup to paste
    def index(self, cfg: ConnConfig, sink: ContextSink) -> IndexStats: ...
```

Connectors register into a global registry; `init` runs every connector's
`detect()` and presents the hits. See `connectors/base.py`.

---

## 6. Answer engine — the pipeline

`engine.ask(question)` runs, in order (see `engine.py`):

1. **Retrieve** — embed the question; pull candidate goldens, metrics, tables,
   past queries; walk lineage for neighbors. (`context/retrieve.py`)
2. **Golden hit?** exact/semantic match → **reuse verbatim**, skip generation.
3. **Metric-first** — if it maps to a defined metric → compile via the semantic
   layer, don't hand-write SQL. *The correctness moat.*
4. **Generate** — LLM writes SQL constrained to retrieved schema + dialect, with
   nearby goldens as few-shot examples. (`llm/provider.py`)
5. **Validate** — `sqlglot` parse; reject non-`SELECT`; inject `LIMIT`; cost/row
   guard; `EXPLAIN`/dry-run. (`sql/validate.py`)
6. **Execute** read-only → rows. (`connectors/warehouse_*`)
7. **Self-repair** — on DB error, feed it back to the model; bounded retries.
8. **Return** `Answer{rows, sql, provenance}` — provenance = which golden/metric,
   lineage, and whether it was reused or generated. Always show the work.
9. **Offer to save** the verified result as a new golden — closing the loop.

**Semantic cache** wraps steps 3–6: `(question → sql)` and `(sql → result)`.
That cache is itself an object-storage primitive (see side-bets in the private
strategy repo) — opendata dogfoods it.

**Guardrails (always on):** read-only enforced at parse time, statement timeout,
row/byte cap, allow/deny schema + PII lists from config.

---

## 7. Correctness plan — eval harness (build alongside, not after)

Text-to-SQL accuracy is the make-or-break risk, so it's measured from day one.

- The **golden set is the eval set**: `(question → expected SQL/answer/shape)`.
- `opendata eval` runs the engine over the set and scores: exact-result match,
  shape match, and execution success. (`eval/harness.py`)
- Track accuracy per release; a regression fails CI. Treat the engine as an
  experiment surface — the unfair advantage for a data/experimentation founder.

---

## 8. Build order (vertical slice first)

Ship the thinnest path to time-to-first-grounded-answer, then widen:

1. **dbt Core connector** (`manifest.json`, zero-auth) — richest context first.
2. **DuckDB warehouse** (toy/local execution) — no external DB to demo.
3. **Context store v0** — catalog + vector retrieval.
4. **Answer engine v0** — golden → metric → generate → validate → execute, with
   an **offline Stub LLM** so the whole slice runs with no API key.
5. **CLI** — `init · ask · doctor · status`.
6. Then: Postgres/Snowflake connectors, Claude provider, semantic cache, FastAPI
   server, hosted mode.

The scaffold in this repo implements 1–5 against `examples/toy/`.

---

## 9. Decisions to lock

- **Runtime**: Python-first (recommended) vs. single-binary. Gates packaging.
- **Default vs BYO model**: ship hosted default (Claude) + local (Ollama), or
  BYO-only at first?
- **Vector index**: `sqlite-vec` (zero-dep, embedded) vs LanceDB (scales better).
- **Metric compilation**: lean on dbt MetricFlow vs. our own metric IR.

---

*Status: draft v1. The scaffold follows §3 and §8; §6–§7 are where the product is
won.*

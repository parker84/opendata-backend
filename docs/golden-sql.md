# Golden SQL — the curation layer

> Let data teams turn a good answer into *the* answer — verified, reusable, and
> owned. Curation should feel like the fun part, not the chore.

Text-to-SQL that regenerates from scratch every time is a party trick. What makes
opendata a no-brainer for a real data team is that **the team's knowledge
compounds**: every verified answer makes the next one faster, cheaper, and more
correct. That accumulated, human-verified knowledge is **golden SQL** (and golden
metrics, joins, and glossary — see §7).

---

## 1. What "golden" means

A **golden** is a human-verified mapping:

```
question (+ its natural variations)  →  canonical SQL / metric  →  expected shape
```

owned by someone, versioned in git, and trusted enough that opendata will *reuse
it verbatim* instead of guessing. It's the difference between "the model wrote
some SQL" and "this is how our team calculates weekly active teams, approved by
@finance."

---

## 2. Why it's the core of the product

Golden SQL is not a side feature — it's the flywheel and the moat:

- **Accuracy** — verified answers beat generated ones, every time.
- **Cost** — a golden hit skips LLM generation entirely (cache), and near-misses
  become few-shot examples that make generation cheaper and better. This directly
  lowers token spend (and, under a token-cut model, the user's bill — incentives
  aligned).
- **Trust** — every answer can say "grounded in golden `active_team`, approved by
  @finance 6d ago." Data teams live or die on trust in the number.
- **Lock-in (the good kind)** — a team's golden library is *their* institutional
  knowledge, versioned and growing. It's the thing that's painful to leave and
  worth paying to collaborate on (see the team tier in the private strategy repo).

```
ask ──▶ answer ──▶ verify ──▶ golden ──▶ future asks reuse it
 ▲                                              │
 └───────────  better + cheaper + trusted  ◀────┘
```

---

## 3. Make curation *fun and easy* (the no-brainer bar)

Curation only compounds if people actually do it. So it has to be a keystroke,
not a workflow.

- **Inline, one keystroke.** After any answer:
  ```
  ✓ 8 rows.  save as golden?  [y]es / [e]dit / [n]o › y
  ✓ saved → .opendata/golden/weekly_active_teams.sql   (owner: you)
  ```
- **Git-native storage.** Goldens are files a data team already knows how to
  review (§6). Proposing one is a PR; approving it is a review. No new ritual —
  it's the ritual they already enjoy from dbt.
- **They're testable, like dbt tests.** `opendata verify` re-runs every golden and
  checks it still parses, runs, and returns the expected shape. Wire it into CI:
  a schema change that breaks a golden fails the PR. Curation becomes a *safety
  net*, not busywork.
- **Coverage as a game.** `opendata status` shows *golden coverage* — "42 goldens
  cover 78% of questions asked this month." Teams chase the number; the number is
  literally product quality. Add streaks / a leaderboard if it stays tasteful.
- **Suggest goldens automatically.** When opendata sees the same question asked 3+
  times and answered consistently, it nudges: "This got asked 5×. Promote to
  golden?" The system does the noticing; the human does the approving.

---

## 4. How the engine uses goldens

Retrieval precedence in the answer engine (see `architecture.md` §engine):

1. **Exact / semantic match to a golden** → reuse its SQL/metric verbatim. No
   generation. (Fastest, cheapest, most trusted.)
2. **No exact match, but similar goldens exist** → inject them as **few-shot
   examples** into generation. The team's style and joins guide the model.
3. **No goldens nearby** → fall back to metric-first, then generated SQL — and
   then *offer to save the verified result as a new golden*, closing the loop.

Goldens also serve as the **regression suite**: they're the ground-truth set the
eval harness scores against (this is how we measure text-to-SQL accuracy over
time — see `architecture.md`).

---

## 5. Lifecycle & staleness

```
draft ──▶ proposed (PR) ──▶ approved ──▶ verified ──▶ [schema drift] ──▶ stale
                                            ▲                              │
                                            └────────  re-verify  ◀────────┘
```

- **Propose → review → approve.** Ownership and approval are first-class (the
  collaboration surface). A golden without an owner is a draft.
- **Staleness detection.** When indexed schema/metadata drifts under a golden
  (renamed column, changed metric), `opendata doctor` flags it and ships the
  one-command re-verify. Goldens never rot silently.

---

## 6. Storage format — `.opendata/golden/*.sql`

Human-readable, PR-reviewable, secret-free. A golden is a `.sql` file with a
small frontmatter header:

```sql
---
id: weekly_active_teams
question: "weekly active teams, last 8 weeks"
aliases:                       # natural variations that map here
  - "WAT by week"
  - "how many teams were active each week"
metric: active_team            # if it compiles from the semantic layer
owner: "@finance"
status: approved               # draft | proposed | approved
verified_at: 2026-07-10
expects:                       # shape check for `opendata verify`
  columns: [week, active_teams]
  min_rows: 1
---
SELECT date_trunc('week', e.occurred_at) AS week,
       COUNT(DISTINCT e.team_id)          AS active_teams
FROM   analytics.events e
WHERE  e.occurred_at >= current_date - INTERVAL '8 weeks'
GROUP  BY 1 ORDER BY 1;
```

Committing this file is what makes teammate #2's answer instant and identical.

---

## 7. Beyond SQL — the rest of the "golden" family

The same verify-and-reuse pattern extends to everything a data team argues about:

- **Golden metrics** — canonical definitions ("ARR = …") that outrank ad-hoc SQL.
  Sourced from dbt/LookML where they exist; hand-defined where they don't.
- **Golden joins** — the blessed way to connect `events` ⨝ `dim_teams`, so the
  model never invents a wrong key.
- **Business glossary / synonyms** — "MAU", "active", "churned" mapped to precise
  definitions, so plain-language questions resolve the way the team means them.
- **Canonical entities** — the one true `customer` / `team` / `order` grain.

All of it is versioned, owned, and reusable — the team's shared brain.

---

## 8. Governance (where the team tier lives)

Single-player golden SQL is free and local (git). The multiplayer version —
shared library, ownership + approvals, audit log, "who changed this metric and
why", role-based edit rights — is the collaboration/governance surface that a
team pays for. Design detail for the paid tier lives in the private strategy
repo; the *feature* is designed to be free and delightful solo, and valuable
enough to pay for together.

---

*Status: draft for v1. The single most important thing to make delightful — if
curation is fun, opendata compounds; if it's a chore, it's just another
text-to-SQL toy.*

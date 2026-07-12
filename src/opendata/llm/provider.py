"""LLM provider abstraction.

Model-agnostic by design (opencode ethos: bring your own model). The default in
production is Claude (Anthropic Python SDK); an offline StubProvider stands in so
the whole pipeline runs with no API key. Selection:

    OPENDATA_MODEL unset / "auto"  → Claude if ANTHROPIC_API_KEY is set and the
                                     `anthropic` SDK is installed, else stub
    OPENDATA_MODEL="stub"          → force offline stub
    OPENDATA_MODEL="claude-…"      → that Claude model id (needs the SDK)
"""

from __future__ import annotations

import json
import os
from typing import Optional, Protocol

from ..context.store import Retrieved

# Default Claude model. Per Anthropic guidance, default to the flagship unless
# the operator picks another via OPENDATA_MODEL. BYO-key; nothing is sent unless
# a key/profile is configured.
DEFAULT_CLAUDE_MODEL = "claude-opus-4-8"


class LLMProvider(Protocol):
    name: str

    def generate_sql(self, question: str, context: Retrieved, examples: list | None = None) -> str:
        ...


def _render_schema(context: Retrieved) -> str:
    lines = []
    for t in context.tables:
        cols = ", ".join(f"{c.name} {c.type}".strip() for c in t.columns)
        desc = f"  -- {t.description}" if t.description else ""
        lines.append(f"{t.fqn}({cols}){desc}")
    for m in context.metrics:
        if m.sql:
            lines.append(f"-- metric {m.name}: {m.definition}\n--   {m.sql}")
    return "\n".join(lines) or "(no tables retrieved)"


class StubProvider:
    """Offline, no-API-key generation: SELECT * from the most relevant table."""

    name = "stub"

    def generate_sql(self, question: str, context: Retrieved, examples: list | None = None) -> str:
        if not context.tables:
            raise RuntimeError("no tables in context to query")
        return f"SELECT * FROM {context.tables[0].fqn}"


_SQL_SCHEMA = {
    "type": "object",
    "properties": {"sql": {"type": "string", "description": "A single read-only SELECT."}},
    "required": ["sql"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You are a precise analytics engineer. Given a question and a database schema, "
    "write ONE read-only DuckDB SQL SELECT that answers it using only the provided "
    "tables and columns. Prefer defined metrics when they fit. Never write DDL or "
    "DML (no INSERT/UPDATE/DELETE/CREATE/DROP). Return only the SQL."
)


class ClaudeProvider:
    """Real text-to-SQL via the Anthropic Python SDK. Grounded in retrieved schema
    + nearby golden examples; structured output guarantees a parseable SQL string."""

    name = "claude"

    def __init__(self, model: str | None = None):
        import anthropic  # imported lazily so the base install stays offline

        self.model = model or DEFAULT_CLAUDE_MODEL
        self._client = anthropic.Anthropic()

    def _ask(self, system: str, prompt: str) -> str:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=2000,
            thinking={"type": "adaptive"},
            output_config={"format": {"type": "json_schema", "schema": _SQL_SCHEMA}},
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        return json.loads(text)["sql"]

    def _examples_block(self, examples: list | None) -> str:
        if not examples:
            return ""
        out = ["\nExamples of how this team writes queries (reuse their style/joins):"]
        for g in examples[:3]:
            out.append(f"Q: {g.question}\nSQL: {g.sql}")
        return "\n".join(out)

    def generate_sql(self, question: str, context: Retrieved, examples: list | None = None) -> str:
        prompt = (
            f"Schema:\n{_render_schema(context)}\n"
            f"{self._examples_block(examples)}\n\n"
            f"Question: {question}\nWrite the SQL."
        )
        return self._ask(_SYSTEM, prompt)

    def repair_sql(self, question: str, bad_sql: str, error: str, context: Retrieved) -> str:
        prompt = (
            f"Schema:\n{_render_schema(context)}\n\n"
            f"Question: {question}\n"
            f"This SQL failed:\n{bad_sql}\n\nError:\n{error}\n\n"
            "Return corrected read-only SQL."
        )
        return self._ask(_SYSTEM, prompt)


def _anthropic_available() -> bool:
    try:
        import anthropic  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def get_provider(name: Optional[str] = None) -> LLMProvider:
    name = name or os.getenv("OPENDATA_MODEL")
    if name in (None, "", "auto"):
        if os.getenv("ANTHROPIC_API_KEY") and _anthropic_available():
            return ClaudeProvider()
        return StubProvider()
    if name == "stub":
        return StubProvider()
    if _anthropic_available():
        return ClaudeProvider(model=name)
    # Asked for a real model but the SDK isn't installed — fail soft to stub.
    return StubProvider()

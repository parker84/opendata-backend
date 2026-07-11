"""LLM provider abstraction.

Model-agnostic by design (opencode ethos: bring your own model). The default in
production is Claude; a real ClaudeProvider would call the Anthropic SDK here.
For the offline slice we ship StubProvider so the whole pipeline runs with no API
key — it does naive schema-grounded generation, deliberately weak, so the value
of goldens + metrics (which bypass it) is obvious.
"""

from __future__ import annotations

from typing import Optional, Protocol

from ..context.store import Retrieved


class LLMProvider(Protocol):
    name: str

    def generate_sql(self, question: str, context: Retrieved) -> str:
        ...


class StubProvider:
    """Offline, no-API-key generation: SELECT * from the most relevant table."""

    name = "stub"

    def generate_sql(self, question: str, context: Retrieved) -> str:
        if not context.tables:
            raise RuntimeError("no tables in context to query")
        t = context.tables[0]
        return f"SELECT * FROM {t.fqn}"


def get_provider(name: Optional[str] = None) -> LLMProvider:
    # Real dispatch (claude/ollama/...) lands here; stub is the offline default.
    return StubProvider()

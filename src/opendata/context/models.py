"""Core entities in the context store (see docs/architecture.md §4)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Column:
    name: str
    type: str = ""
    description: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "type": self.type, "description": self.description}

    @classmethod
    def from_dict(cls, d: dict) -> "Column":
        return cls(name=d["name"], type=d.get("type", ""), description=d.get("description", ""))


@dataclass
class Table:
    connection: str
    schema: str
    name: str
    description: str = ""
    columns: list[Column] = field(default_factory=list)

    @property
    def fqn(self) -> str:
        return f"{self.schema}.{self.name}" if self.schema else self.name

    def to_dict(self) -> dict:
        return {
            "connection": self.connection,
            "schema": self.schema,
            "name": self.name,
            "description": self.description,
            "columns": [c.to_dict() for c in self.columns],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Table":
        return cls(
            connection=d.get("connection", ""),
            schema=d.get("schema", ""),
            name=d["name"],
            description=d.get("description", ""),
            columns=[Column.from_dict(c) for c in d.get("columns", [])],
        )


@dataclass
class Metric:
    name: str
    label: str = ""
    definition: str = ""
    sql: str = ""
    owner: str = ""
    source: str = ""  # dbt | lookml | golden

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "definition": self.definition,
            "sql": self.sql,
            "owner": self.owner,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Metric":
        return cls(
            name=d["name"],
            label=d.get("label", ""),
            definition=d.get("definition", ""),
            sql=d.get("sql", ""),
            owner=d.get("owner", ""),
            source=d.get("source", ""),
        )

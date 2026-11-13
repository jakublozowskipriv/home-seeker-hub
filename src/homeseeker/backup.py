"""Whole-database backup as gzipped JSON, and restore into an empty database.

The weekly workflow encrypts the file before it leaves the runner: the repository is
public and the data includes family members' e-mails and comments.
"""

from __future__ import annotations

import gzip
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, func, insert, select, text
from sqlalchemy.engine import Engine

from .db import metadata

FORMAT = 1


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def export(engine: Engine, path: str | Path) -> dict[str, int]:
    """Write every table to `path` (.json.gz); returns row counts per table."""
    data: dict[str, Any] = {"format": FORMAT, "tables": {}}
    counts = {}
    with engine.connect() as conn:
        for table in metadata.sorted_tables:
            rows = [
                {k: _jsonable(v) for k, v in row._mapping.items()}
                for row in conn.execute(select(table))
            ]
            data["tables"][table.name] = rows
            counts[table.name] = len(rows)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    return counts


def restore(engine: Engine, path: str | Path) -> dict[str, int]:
    """Load a backup into a database whose tables are empty (refuses otherwise)."""
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("format") != FORMAT:
        raise ValueError(f"Unknown backup format: {data.get('format')}")
    tables = data["tables"]
    counts = {}
    with engine.begin() as conn:
        for table in metadata.sorted_tables:
            if conn.execute(select(func.count()).select_from(table)).scalar_one():
                raise ValueError(
                    f"Table {table.name} is not empty – restore needs an empty database"
                )
        for table in metadata.sorted_tables:  # parents before children (foreign keys)
            rows = tables.get(table.name) or []
            dates = [c.name for c in table.columns if isinstance(c.type, DateTime)]
            for row in rows:
                for name in dates:
                    if row.get(name):
                        row[name] = datetime.fromisoformat(row[name])
            if rows:
                conn.execute(insert(table), rows)
            counts[table.name] = len(rows)
        if engine.dialect.name == "postgresql":
            # Explicit ids were inserted: move the id sequences past them.
            for table in metadata.sorted_tables:
                id_col = table.columns.get("id")
                if id_col is not None and id_col.autoincrement is True:
                    conn.execute(
                        text(
                            f"select setval(pg_get_serial_sequence('{table.name}', 'id'), "
                            f"coalesce((select max(id) from {table.name}), 0) + 1, false)"
                        )
                    )
    return counts

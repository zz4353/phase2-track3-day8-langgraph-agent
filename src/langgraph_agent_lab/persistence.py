"""Checkpointer adapter."""

from __future__ import annotations

import sqlite3
from importlib import import_module
from typing import Any, cast

from langgraph.checkpoint.base import BaseCheckpointSaver


def build_checkpointer(
    kind: str = "memory",
    database_url: str | None = None,
) -> BaseCheckpointSaver[Any] | None:
    """Return a LangGraph checkpointer.

    TODO(student): add SQLite/Postgres support for the extension track.
    The starter uses MemorySaver so the lab can run without infrastructure.
    """
    if kind == "none":
        return None
    if kind == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()
    if kind == "sqlite":
        try:
            sqlite_module = import_module("langgraph.checkpoint.sqlite")
        except ImportError as exc:
            raise RuntimeError(
                "SQLite checkpointer requires: pip install langgraph-checkpoint-sqlite"
            ) from exc
        conn = sqlite3.connect(database_url or "checkpoints.db", check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        sqlite_saver = sqlite_module.SqliteSaver(conn=conn)
        return cast(BaseCheckpointSaver[Any], sqlite_saver)
    if kind == "postgres":
        try:
            postgres_module = import_module("langgraph.checkpoint.postgres")
        except ImportError as exc:
            raise RuntimeError(
                "Postgres checkpointer requires: pip install langgraph-checkpoint-postgres"
            ) from exc
        postgres_saver = postgres_module.PostgresSaver.from_conn_string(database_url or "")
        return cast(BaseCheckpointSaver[Any], postgres_saver)
    raise ValueError(f"Unknown checkpointer kind: {kind}")

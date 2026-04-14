"""SQLite-backed memory store for Jarvis conversation history, facts, and action log."""

import json
import sqlite3
from typing import Any

from loguru import logger


class MemoryDB:
    """Persistent storage backed by SQLite.

    Schema (created on first run, idempotent):
        conversations  — turn-by-turn dialogue history per session
        memory_facts   — long-lived user preferences, facts, and instructions
        action_log     — audit trail of every tool execution

    All connections use the context-manager pattern and row_factory = sqlite3.Row
    so that results are dict-like without an ORM dependency.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        logger.info(f"MemoryDB initializing at {db_path!r}")
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema bootstrap
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        """Create all tables and indexes if they do not already exist."""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    session_id  TEXT NOT NULL,
                    role        TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                    content     TEXT NOT NULL,
                    model_used  TEXT,
                    tokens_used INTEGER
                );

                CREATE INDEX IF NOT EXISTS idx_conversations_session
                    ON conversations (session_id, timestamp);

                CREATE TABLE IF NOT EXISTS memory_facts (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    category   TEXT NOT NULL CHECK(category IN ('preference', 'fact', 'instruction')),
                    content    TEXT NOT NULL,
                    active     INTEGER NOT NULL DEFAULT 1
                );

                CREATE INDEX IF NOT EXISTS idx_memory_facts_active
                    ON memory_facts (active, category);

                CREATE TABLE IF NOT EXISTS action_log (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    session_id TEXT NOT NULL,
                    tool_name  TEXT NOT NULL,
                    parameters TEXT NOT NULL,
                    result     TEXT,
                    success    INTEGER NOT NULL DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_action_log_session
                    ON action_log (session_id, timestamp);
                """
            )
        logger.debug("MemoryDB schema initialized")

    # ------------------------------------------------------------------
    # Conversations
    # ------------------------------------------------------------------

    def save_turn(
        self,
        role: str,
        content: str,
        session_id: str,
        model_used: str | None = None,
    ) -> int:
        """Insert a conversation turn and return the new row id.

        Args:
            role: Speaker role — "user", "assistant", or "system".
            content: Raw text content of the turn.
            session_id: Identifier grouping turns into one conversation session.
            model_used: LLM model string used for assistant turns (None for user).

        Returns:
            The auto-generated integer row id.
        """
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                INSERT INTO conversations (session_id, role, content, model_used)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, content, model_used),
            )
            row_id: int = cursor.lastrowid  # type: ignore[assignment]
        logger.debug(f"save_turn: session={session_id!r} role={role!r} id={row_id}")
        return row_id

    def get_history(self, session_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Return the most recent conversation turns for a session, oldest first.

        Args:
            session_id: Session identifier to filter by.
            limit: Maximum number of turns to return.

        Returns:
            List of dicts with keys: role, content, model_used, timestamp.
        """
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT role, content, model_used, timestamp
                FROM conversations
                WHERE session_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()

        # Reverse so the oldest turn comes first (chronological for LLM history)
        history = [dict(row) for row in reversed(rows)]
        logger.debug(f"get_history: session={session_id!r} returned {len(history)} turns")
        return history

    def get_all_sessions(self) -> list[str]:
        """Return a deduplicated list of all session IDs in conversations."""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT DISTINCT session_id FROM conversations ORDER BY session_id"
            ).fetchall()
        return [row["session_id"] for row in rows]

    # ------------------------------------------------------------------
    # Memory facts
    # ------------------------------------------------------------------

    def save_fact(self, category: str, content: str) -> int:
        """Insert a new memory fact and return its row id.

        Args:
            category: One of "preference", "fact", or "instruction".
            content: Human-readable fact content.

        Returns:
            The auto-generated integer row id.
        """
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                INSERT INTO memory_facts (category, content)
                VALUES (?, ?)
                """,
                (category, content),
            )
            row_id: int = cursor.lastrowid  # type: ignore[assignment]
        logger.debug(f"save_fact: category={category!r} id={row_id}")
        return row_id

    def get_active_facts(self, category: str | None = None) -> list[dict[str, Any]]:
        """Return all active (non-deleted) memory facts.

        Args:
            category: Optional filter — "preference", "fact", or "instruction".
                      If None, all active facts are returned.

        Returns:
            List of dicts with keys: id, category, content, created_at, updated_at.
        """
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            if category is not None:
                rows = conn.execute(
                    """
                    SELECT id, category, content, created_at, updated_at
                    FROM memory_facts
                    WHERE active = 1 AND category = ?
                    ORDER BY created_at ASC
                    """,
                    (category,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, category, content, created_at, updated_at
                    FROM memory_facts
                    WHERE active = 1
                    ORDER BY created_at ASC
                    """
                ).fetchall()
        facts = [dict(row) for row in rows]
        logger.debug(f"get_active_facts: category={category!r} returned {len(facts)} facts")
        return facts

    def deactivate_fact(self, fact_id: int) -> None:
        """Soft-delete a memory fact by setting active = 0.

        Args:
            fact_id: The id of the fact to deactivate.
        """
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute(
                """
                UPDATE memory_facts
                SET active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (fact_id,),
            )
        logger.debug(f"deactivate_fact: id={fact_id}")

    # ------------------------------------------------------------------
    # Action log
    # ------------------------------------------------------------------

    def log_action(
        self,
        session_id: str,
        tool_name: str,
        parameters: dict[str, Any],
        result: dict[str, Any],
        success: bool,
    ) -> int:
        """Insert a tool execution record and return its row id.

        Args:
            session_id: Session in which the tool was called.
            tool_name: Name of the tool that was executed.
            parameters: Tool arguments as a Python dict (serialized to JSON).
            result: Tool return value as a Python dict (serialized to JSON).
            success: Whether the tool execution succeeded.

        Returns:
            The auto-generated integer row id.
        """
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                INSERT INTO action_log (session_id, tool_name, parameters, result, success)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    tool_name,
                    json.dumps(parameters),
                    json.dumps(result),
                    int(success),
                ),
            )
            row_id: int = cursor.lastrowid  # type: ignore[assignment]
        logger.debug(
            f"log_action: session={session_id!r} tool={tool_name!r} "
            f"success={success} id={row_id}"
        )
        return row_id

    def get_action_log(
        self,
        session_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return recent action log entries.

        Args:
            session_id: Optional session filter. If None, returns entries from all sessions.
            limit: Maximum number of entries to return (most recent first).

        Returns:
            List of dicts with keys: id, timestamp, session_id, tool_name,
            parameters (dict), result (dict), success (bool).
        """
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            if session_id is not None:
                rows = conn.execute(
                    """
                    SELECT id, timestamp, session_id, tool_name, parameters, result, success
                    FROM action_log
                    WHERE session_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (session_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, timestamp, session_id, tool_name, parameters, result, success
                    FROM action_log
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

        entries: list[dict[str, Any]] = []
        for row in rows:
            entry = dict(row)
            # Deserialize JSON blobs back to Python dicts
            entry["parameters"] = json.loads(entry["parameters"])
            entry["result"] = json.loads(entry["result"]) if entry["result"] else None
            entry["success"] = bool(entry["success"])
            entries.append(entry)

        logger.debug(
            f"get_action_log: session={session_id!r} returned {len(entries)} entries"
        )
        return entries

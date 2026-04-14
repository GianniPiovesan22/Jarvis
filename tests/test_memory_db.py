"""
Unit tests for MemoryDB.

All tests use a temporary SQLite file via tmp_path — no in-memory shortcuts
so we exercise the real file I/O path and schema bootstrap.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from memory.db import MemoryDB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


SESSION = "test-session-001"


def _raw_tables(db_path: str) -> set[str]:
    """Return the set of table names present in the database."""
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    return {row[0] for row in rows}


# ---------------------------------------------------------------------------
# 8.5.1 — Schema creation
# ---------------------------------------------------------------------------


def test_schema_creation(tmp_path: Path) -> None:
    """All 3 tables must exist immediately after MemoryDB init."""
    db_path = str(tmp_path / "test.db")
    MemoryDB(db_path)

    tables = _raw_tables(db_path)
    assert "conversations" in tables
    assert "memory_facts" in tables
    assert "action_log" in tables


def test_schema_is_idempotent(tmp_path: Path) -> None:
    """Creating MemoryDB twice on the same file must not raise."""
    db_path = str(tmp_path / "test.db")
    MemoryDB(db_path)
    MemoryDB(db_path)  # should not raise (CREATE TABLE IF NOT EXISTS)

    tables = _raw_tables(db_path)
    assert len({"conversations", "memory_facts", "action_log"} & tables) == 3


# ---------------------------------------------------------------------------
# 8.5.2 — save_turn / get_history
# ---------------------------------------------------------------------------


def test_save_and_get_history_returns_all_turns(memory_db: MemoryDB) -> None:
    """save_turn x3, then get_history(limit=10) returns all 3 chronologically."""
    memory_db.save_turn(role="user", content="hola", session_id=SESSION)
    memory_db.save_turn(role="assistant", content="hola, ¿cómo estás?", session_id=SESSION, model_used="llama3.2:1b")
    memory_db.save_turn(role="user", content="bien gracias", session_id=SESSION)

    history = memory_db.get_history(session_id=SESSION, limit=10)

    assert len(history) == 3
    # Oldest first (chronological)
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "hola"
    assert history[1]["role"] == "assistant"
    assert history[2]["content"] == "bien gracias"


def test_get_history_includes_model_used(memory_db: MemoryDB) -> None:
    """model_used is preserved and returned in history."""
    memory_db.save_turn(
        role="assistant",
        content="respuesta",
        session_id=SESSION,
        model_used="claude-haiku-test",
    )
    history = memory_db.get_history(session_id=SESSION, limit=5)

    assert len(history) == 1
    assert history[0]["model_used"] == "claude-haiku-test"


# ---------------------------------------------------------------------------
# 8.5.3 — get_history limit
# ---------------------------------------------------------------------------


def test_get_history_limit_returns_only_last_n(memory_db: MemoryDB) -> None:
    """Save 5 turns, get_history(limit=2) returns only the last 2."""
    for i in range(5):
        memory_db.save_turn(role="user", content=f"msg {i}", session_id=SESSION)

    history = memory_db.get_history(session_id=SESSION, limit=2)

    assert len(history) == 2
    # The two MOST RECENT turns, returned in chronological order (oldest first)
    assert history[0]["content"] == "msg 3"
    assert history[1]["content"] == "msg 4"


def test_get_history_different_sessions_isolated(memory_db: MemoryDB) -> None:
    """get_history filters by session_id — other sessions are invisible."""
    memory_db.save_turn(role="user", content="session A", session_id="session-A")
    memory_db.save_turn(role="user", content="session B", session_id="session-B")

    history_a = memory_db.get_history(session_id="session-A", limit=10)
    assert len(history_a) == 1
    assert history_a[0]["content"] == "session A"


# ---------------------------------------------------------------------------
# 8.5.4 — save_fact / get_active_facts
# ---------------------------------------------------------------------------


def test_save_and_get_facts(memory_db: MemoryDB) -> None:
    """save_fact then get_active_facts returns the saved fact."""
    memory_db.save_fact(category="preference", content="le gusta el mate")

    facts = memory_db.get_active_facts()

    assert len(facts) == 1
    assert facts[0]["category"] == "preference"
    assert facts[0]["content"] == "le gusta el mate"


def test_get_active_facts_returns_multiple(memory_db: MemoryDB) -> None:
    """Multiple facts are all returned."""
    memory_db.save_fact(category="preference", content="café sin azúcar")
    memory_db.save_fact(category="fact", content="vive en Buenos Aires")
    memory_db.save_fact(category="instruction", content="responder en español")

    facts = memory_db.get_active_facts()
    assert len(facts) == 3


def test_get_active_facts_filters_by_category(memory_db: MemoryDB) -> None:
    """Category filter works correctly."""
    memory_db.save_fact(category="preference", content="prefiero oscuro")
    memory_db.save_fact(category="fact", content="desarrollador de software")

    prefs = memory_db.get_active_facts(category="preference")
    facts = memory_db.get_active_facts(category="fact")

    assert len(prefs) == 1
    assert prefs[0]["content"] == "prefiero oscuro"
    assert len(facts) == 1
    assert facts[0]["content"] == "desarrollador de software"


# ---------------------------------------------------------------------------
# 8.5.5 — deactivate_fact
# ---------------------------------------------------------------------------


def test_deactivate_fact_hides_it_from_get_active_facts(memory_db: MemoryDB) -> None:
    """deactivate_fact soft-deletes — get_active_facts no longer returns it."""
    fact_id = memory_db.save_fact(category="fact", content="dato a borrar")

    memory_db.deactivate_fact(fact_id)

    facts = memory_db.get_active_facts()
    assert all(f["id"] != fact_id for f in facts)


def test_deactivate_fact_keeps_other_facts(memory_db: MemoryDB) -> None:
    """Deactivating one fact leaves others active."""
    id1 = memory_db.save_fact(category="preference", content="keep me")
    id2 = memory_db.save_fact(category="preference", content="delete me")

    memory_db.deactivate_fact(id2)

    facts = memory_db.get_active_facts()
    assert len(facts) == 1
    assert facts[0]["id"] == id1
    assert facts[0]["content"] == "keep me"


# ---------------------------------------------------------------------------
# 8.5.6 — log_action
# ---------------------------------------------------------------------------


def test_log_action_with_dict_parameters(memory_db: MemoryDB) -> None:
    """log_action serializes dict parameters to JSON without errors."""
    row_id = memory_db.log_action(
        session_id=SESSION,
        tool_name="set_volume",
        parameters={"level": 75},
        result={"success": True, "result": "done", "error": None},
        success=True,
    )

    assert isinstance(row_id, int)
    assert row_id > 0


def test_log_action_json_roundtrip(memory_db: MemoryDB, tmp_path: Path) -> None:
    """parameters dict is stored as JSON and deserialized back correctly."""
    params = {"command": "ls -la", "sudo": False, "nested": {"key": "value"}}
    memory_db.log_action(
        session_id=SESSION,
        tool_name="run_command",
        parameters=params,
        result={"success": True, "result": "output", "error": None},
        success=True,
    )

    entries = memory_db.get_action_log(session_id=SESSION)
    assert len(entries) == 1
    assert entries[0]["parameters"] == params


# ---------------------------------------------------------------------------
# 8.5.7 — get_action_log
# ---------------------------------------------------------------------------


def test_get_action_log_returns_all_entries(memory_db: MemoryDB) -> None:
    """log_action x3, get_action_log returns all 3 with correct fields."""
    tools = ["tool_a", "tool_b", "tool_c"]
    for name in tools:
        memory_db.log_action(
            session_id=SESSION,
            tool_name=name,
            parameters={"arg": name},
            result={"success": True, "result": name, "error": None},
            success=True,
        )

    entries = memory_db.get_action_log(session_id=SESSION)

    assert len(entries) == 3
    entry_names = {e["tool_name"] for e in entries}
    assert entry_names == {"tool_a", "tool_b", "tool_c"}


def test_get_action_log_entry_has_required_fields(memory_db: MemoryDB) -> None:
    """Each action log entry has id, timestamp, session_id, tool_name, parameters, result, success."""
    memory_db.log_action(
        session_id=SESSION,
        tool_name="get_clipboard",
        parameters={},
        result={"success": True, "result": "copied text", "error": None},
        success=True,
    )

    entries = memory_db.get_action_log(session_id=SESSION)
    assert len(entries) == 1

    entry = entries[0]
    for field in ("id", "timestamp", "session_id", "tool_name", "parameters", "result", "success"):
        assert field in entry, f"Missing field: {field}"

    assert entry["session_id"] == SESSION
    assert entry["tool_name"] == "get_clipboard"
    assert entry["success"] is True
    assert isinstance(entry["parameters"], dict)
    assert isinstance(entry["result"], dict)


def test_get_action_log_failure_entry(memory_db: MemoryDB) -> None:
    """success=False is stored and retrieved correctly as a bool."""
    memory_db.log_action(
        session_id=SESSION,
        tool_name="broken_tool",
        parameters={},
        result={"success": False, "result": None, "error": "boom"},
        success=False,
    )

    entries = memory_db.get_action_log(session_id=SESSION)
    assert entries[0]["success"] is False
    assert entries[0]["result"]["error"] == "boom"


def test_get_action_log_without_session_filter_returns_all(memory_db: MemoryDB) -> None:
    """get_action_log(session_id=None) returns entries from all sessions."""
    memory_db.log_action("session-X", "tool_x", {}, {"success": True, "result": None, "error": None}, True)
    memory_db.log_action("session-Y", "tool_y", {}, {"success": True, "result": None, "error": None}, True)

    all_entries = memory_db.get_action_log()
    session_ids = {e["session_id"] for e in all_entries}
    assert "session-X" in session_ids
    assert "session-Y" in session_ids

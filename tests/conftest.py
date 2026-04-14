"""
Shared pytest fixtures for Jarvis test suite.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from core.config_loader import Config, LLMConfig, MemoryConfig, TTSConfig, UIConfig, WakeWordConfig, WhisperConfig, load_config
from memory.db import MemoryDB


@pytest.fixture
def config(tmp_path):
    """
    Load config from the fixture YAML.

    Uses a hostname that won't match any real machine, so common defaults
    apply. Tests that need a specific profile should patch socket.gethostname.
    """
    fixture_yaml = Path(__file__).parent / "fixtures" / "config.yaml"
    return load_config(str(fixture_yaml))


@pytest.fixture
def llm_config():
    """A default LLMConfig with known thresholds (simple=6, medium=20)."""
    return LLMConfig()


@pytest.fixture
def minimal_config() -> Config:
    """Minimal Config built directly from dataclasses — no file loading.

    Uses small word limits and dummy URLs to avoid any I/O.
    """
    return Config(
        whisper=WhisperConfig(device="cpu", model="tiny"),
        llm=LLMConfig(
            simple_word_limit=6,
            medium_word_limit=20,
            ollama_url="http://localhost:11434",
            ollama_model="llama3.2:1b",
            claude_haiku="claude-haiku-test",
            claude_sonnet="claude-sonnet-test",
            gemini_model="gemini-test",
            gemini_api_key_env="GEMINI_API_KEY",
            max_tokens=100,
            history_turns=5,
        ),
        tts=TTSConfig(voice="test-voice", speed=1.0),
        memory=MemoryConfig(db_path=":memory:", max_history_turns=10),
        ui=UIConfig(position="bottom-right", orb_size=88, opacity=0.9),
        wake_word=WakeWordConfig(model_path="models/test.onnx", threshold=0.5),
        profile_name="test",
    )


@pytest.fixture
def memory_db(tmp_path: Path) -> MemoryDB:
    """MemoryDB backed by a temporary SQLite file."""
    return MemoryDB(str(tmp_path / "test.db"))


@pytest.fixture
def tool_registry() -> dict:
    """Registry with fake async callables for dispatcher tests.

    Contains:
    - "fake_success": returns {"success": True, "result": "ok", "error": None}
    - "fake_error": raises a generic RuntimeError
    - "fake_not_implemented": raises NotImplementedError
    """
    success_mock = AsyncMock(return_value={"success": True, "result": "ok", "error": None})
    error_mock = AsyncMock(side_effect=RuntimeError("tool exploded"))
    not_impl_mock = AsyncMock(side_effect=NotImplementedError("stub"))

    return {
        "fake_success": success_mock,
        "fake_error": error_mock,
        "fake_not_implemented": not_impl_mock,
    }

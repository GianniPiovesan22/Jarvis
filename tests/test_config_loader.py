"""
Unit tests for core/config_loader.py.

Uses the fixture YAML in tests/fixtures/config.yaml.
Tests cover:
  - Default config when no hostname matches
  - Profile merge when hostname matches (whisper device/model, ollama_model)
  - All sections map to correct typed dataclasses
  - FileNotFoundError on missing file
  - _filter_keys removes unknown keys gracefully
"""

from __future__ import annotations

import socket
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from core.config_loader import (
    Config,
    LLMConfig,
    MemoryConfig,
    TTSConfig,
    UIConfig,
    WakeWordConfig,
    WhisperConfig,
    load_config,
)

FIXTURE_YAML = Path(__file__).parent / "fixtures" / "config.yaml"


# ---------------------------------------------------------------------------
# No-match path (default hostname won't match fixture profiles)
# ---------------------------------------------------------------------------


def test_load_config_returns_config_instance() -> None:
    cfg = load_config(str(FIXTURE_YAML))
    assert isinstance(cfg, Config)


def test_load_config_default_profile_name_when_no_match() -> None:
    with patch("socket.gethostname", return_value="unknown-host-xyz"):
        cfg = load_config(str(FIXTURE_YAML))
    assert cfg.profile_name == "default"


def test_load_config_default_whisper_device_when_no_match() -> None:
    with patch("socket.gethostname", return_value="unknown-host-xyz"):
        cfg = load_config(str(FIXTURE_YAML))
    assert cfg.whisper.device == "cpu"
    assert cfg.whisper.model == "small"


def test_load_config_llm_defaults() -> None:
    with patch("socket.gethostname", return_value="unknown-host-xyz"):
        cfg = load_config(str(FIXTURE_YAML))
    assert cfg.llm.simple_word_limit == 6
    assert cfg.llm.medium_word_limit == 20
    assert cfg.llm.ollama_url == "http://localhost:11434"
    assert cfg.llm.claude_haiku == "claude-haiku-4-5-20251001"
    assert cfg.llm.claude_sonnet == "claude-sonnet-4-6"
    assert cfg.llm.gemini_model == "gemini-2.0-flash"
    assert cfg.llm.max_tokens == 500
    assert cfg.llm.history_turns == 10


def test_load_config_tts_section() -> None:
    cfg = load_config(str(FIXTURE_YAML))
    assert isinstance(cfg.tts, TTSConfig)
    assert cfg.tts.voice == "es_ES-davefx-high"
    assert cfg.tts.speed == pytest.approx(1.1)


def test_load_config_memory_section() -> None:
    cfg = load_config(str(FIXTURE_YAML))
    assert isinstance(cfg.memory, MemoryConfig)
    assert cfg.memory.db_path == "memory/test.db"
    assert cfg.memory.max_history_turns == 50


def test_load_config_ui_section() -> None:
    cfg = load_config(str(FIXTURE_YAML))
    assert isinstance(cfg.ui, UIConfig)
    assert cfg.ui.position == "bottom-right"
    assert cfg.ui.orb_size == 88
    assert cfg.ui.opacity == pytest.approx(0.92)


def test_load_config_wake_word_section() -> None:
    cfg = load_config(str(FIXTURE_YAML))
    assert isinstance(cfg.wake_word, WakeWordConfig)
    assert cfg.wake_word.model_path == "models/hey_jarvis.onnx"
    assert cfg.wake_word.threshold == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# Profile match path
# ---------------------------------------------------------------------------


def test_load_config_matches_test_profile() -> None:
    with patch("socket.gethostname", return_value="jarvis-test-host"):
        cfg = load_config(str(FIXTURE_YAML))
    assert cfg.profile_name == "test_pc"
    assert cfg.whisper.device == "cpu"
    assert cfg.whisper.model == "tiny"
    assert cfg.llm.ollama_model == "llama3.2:1b"


def test_load_config_profile_overrides_ollama_model(tmp_path: Path) -> None:
    """Profile with a different ollama_model overrides the llm section default."""
    config_data = {
        "profiles": {
            "mybox": {
                "hostname": "mybox-host",
                "whisper_device": "rocm",
                "whisper_model": "medium",
                "ollama_model": "llama3.2:3b",
            }
        },
        "llm": {
            "ollama_model": "llama3.2:1b",  # would be the default
            "simple_word_limit": 6,
            "medium_word_limit": 20,
        },
    }
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.dump(config_data))

    with patch("socket.gethostname", return_value="mybox-host"):
        cfg = load_config(str(cfg_file))

    assert cfg.profile_name == "mybox"
    assert cfg.whisper.device == "rocm"
    assert cfg.whisper.model == "medium"
    assert cfg.llm.ollama_model == "llama3.2:3b"  # profile override applied


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_load_config_raises_on_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/path/config.yaml")


def test_load_config_unknown_yaml_keys_ignored(tmp_path: Path) -> None:
    """Extra keys in YAML sections don't crash the loader."""
    config_data = {
        "llm": {
            "simple_word_limit": 5,
            "unknown_future_key": "some_value",
        },
    }
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(yaml.dump(config_data))

    cfg = load_config(str(cfg_file))
    assert cfg.llm.simple_word_limit == 5  # known key loaded
    # unknown_future_key ignored silently — no AttributeError

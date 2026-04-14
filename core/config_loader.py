"""
Config loader for Jarvis.

Reads config.yaml, auto-detects the active profile by hostname,
merges profile-specific overrides onto common defaults, and returns
a fully-typed Config dataclass tree.

Usage:
    from core.config_loader import load_config
    config = load_config()          # reads config.yaml from cwd
    config = load_config("path/to/config.yaml")
"""

from __future__ import annotations

import dataclasses
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

import yaml
from loguru import logger

# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


@dataclass
class WhisperConfig:
    device: str = "cpu"   # "cpu" | "rocm" | "cuda"
    model: str = "small"  # "tiny" | "small" | "medium" | "large-v3"


@dataclass
class LLMConfig:
    simple_word_limit: int = 6
    medium_word_limit: int = 20
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:1b"
    claude_haiku: str = "claude-haiku-4-5-20251001"
    claude_sonnet: str = "claude-sonnet-4-6"
    gemini_model: str = "gemini-2.0-flash"
    gemini_api_key_env: str = "GEMINI_API_KEY"
    max_tokens: int = 500
    history_turns: int = 10


@dataclass
class TTSConfig:
    voice: str = "es_ES-davefx-high"
    speed: float = 1.1


@dataclass
class MemoryConfig:
    db_path: str = "memory/jarvis.db"
    max_history_turns: int = 50


@dataclass
class UIConfig:
    position: str = "bottom-right"
    orb_size: int = 88
    opacity: float = 0.92


@dataclass
class WakeWordConfig:
    model_path: str = "models/hey_jarvis.onnx"
    threshold: float = 0.7


@dataclass
class Config:
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    wake_word: WakeWordConfig = field(default_factory=WakeWordConfig)
    profile_name: str = "default"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_DC = TypeVar("_DC")


def _filter_keys(data: dict[str, Any], cls: type[_DC]) -> dict[str, Any]:
    """Return only the keys from *data* that exist as fields on *cls*."""
    field_names = {f.name for f in dataclasses.fields(cls)}  # type: ignore[arg-type]
    return {k: v for k, v in data.items() if k in field_names}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(path: str = "config.yaml") -> Config:
    """
    Load and merge config from *path*.

    1. Reads the YAML file.
    2. Detects hostname via socket.gethostname().
    3. Finds the matching profile (by hostname field) — warns if none found.
    4. Merges profile-specific overrides (whisper_device, whisper_model,
       ollama_model) onto the common section defaults.
    5. Returns a fully-typed Config.

    Raises:
        FileNotFoundError: if *path* does not exist.
        yaml.YAMLError:    if the file is malformed.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path.resolve()}")

    raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    hostname = socket.gethostname()
    logger.debug("Detected hostname: {}", hostname)

    # --- 1. Find matching profile ----------------------------------------
    profile_data: dict[str, Any] = {}
    profile_name = "default"

    for name, profile in raw.get("profiles", {}).items():
        if profile.get("hostname") == hostname:
            profile_data = dict(profile)
            profile_name = name
            logger.info("Active profile: {} (hostname={})", name, hostname)
            break
    else:
        logger.warning(
            "No profile matched hostname '{}' — using common defaults. "
            "Add a profile with hostname: '{}' to config.yaml to silence this.",
            hostname,
            hostname,
        )

    # --- 2. Build WhisperConfig (profile overrides device + model) --------
    whisper_cfg = WhisperConfig(
        device=profile_data.get("whisper_device", "cpu"),
        model=profile_data.get("whisper_model", "small"),
    )

    # --- 3. Build LLMConfig (common section + profile's ollama_model) -----
    raw_llm: dict[str, Any] = dict(raw.get("llm", {}))
    if "ollama_model" in profile_data:
        raw_llm["ollama_model"] = profile_data["ollama_model"]

    llm_cfg = LLMConfig(**_filter_keys(raw_llm, LLMConfig))

    # --- 4. Remaining sections (no profile overrides) ---------------------
    tts_cfg = TTSConfig(**_filter_keys(raw.get("tts", {}), TTSConfig))
    memory_cfg = MemoryConfig(**_filter_keys(raw.get("memory", {}), MemoryConfig))
    ui_cfg = UIConfig(**_filter_keys(raw.get("ui", {}), UIConfig))
    wake_word_cfg = WakeWordConfig(**_filter_keys(raw.get("wake_word", {}), WakeWordConfig))

    return Config(
        whisper=whisper_cfg,
        llm=llm_cfg,
        tts=tts_cfg,
        memory=memory_cfg,
        ui=ui_cfg,
        wake_word=wake_word_cfg,
        profile_name=profile_name,
    )

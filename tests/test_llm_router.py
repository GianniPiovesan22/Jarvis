"""
Unit tests for LLMRouter.

No I/O. No mocks needed — router is a pure function.
Tests cover:
  - Keyword + word-count heuristic (all three default targets)
  - Force override (any target, including gemini_flash)
  - ML classifier registration and override
  - Edge cases: empty text, exact threshold boundaries
"""

from __future__ import annotations

import pytest

from core.config_loader import LLMConfig
from core.llm_router import SIMPLE_PATTERNS, LLMRouter, RouteTarget


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def router() -> LLMRouter:
    """Router with default thresholds (simple=6, medium=20)."""
    return LLMRouter(LLMConfig())


# ---------------------------------------------------------------------------
# Heuristic routing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        # local: short (≤6 words) + keyword
        ("abrir firefox", "local"),
        ("bajá el volumen", "local"),
        ("screenshot", "local"),
        ("cerrar spotify", "local"),
        ("subí el brillo", "local"),
        ("bloqueá la pantalla ahora", "local"),
        # claude_haiku: no simple keyword but ≤20 words
        ("cuánta memoria RAM tengo disponible ahora mismo", "claude_haiku"),
        ("qué procesos están usando más CPU en este momento", "claude_haiku"),
        ("mostrá el estado de la batería del sistema", "claude_haiku"),
        # claude_sonnet: >20 words
        (
            "escribime un script de bash que monitoree los procesos y me avise "
            "cuando algo use más del 80 porciento de CPU con un log en archivo",
            "claude_sonnet",
        ),
        (
            "analizá este error de Python que tengo en el proyecto y explicame "
            "por qué está fallando el test de integración con la base de datos "
            "sqlite en el contexto de asyncio",
            "claude_sonnet",
        ),
    ],
)
def test_keyword_heuristic(router: LLMRouter, text: str, expected: RouteTarget) -> None:
    assert router.route(text) == expected


# ---------------------------------------------------------------------------
# Force override
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, force, expected",
    [
        # force wins even when keyword would route to local
        ("abrir firefox", "claude_sonnet", "claude_sonnet"),
        ("abrir firefox", "gemini_flash", "gemini_flash"),
        ("abrir firefox", "claude_haiku", "claude_haiku"),
        # force wins even for long complex text
        (
            "escribime un script de bash muy largo y complejo con múltiples funciones",
            "local",
            "local",
        ),
        # force=None → heuristic still runs
        ("abrir firefox", None, "local"),
    ],
)
def test_force_override(
    router: LLMRouter, text: str, force: RouteTarget | None, expected: RouteTarget
) -> None:
    assert router.route(text, force=force) == expected


# ---------------------------------------------------------------------------
# Threshold boundary conditions
# ---------------------------------------------------------------------------


def test_exactly_at_simple_limit_with_keyword(router: LLMRouter) -> None:
    # 6 words, contains keyword "abrir" → local
    text = "por favor abrir el firefox ya"
    assert len(text.split()) == 6
    assert router.route(text) == "local"


def test_one_over_simple_limit_with_keyword(router: LLMRouter) -> None:
    # 7 words, has keyword but exceeds simple_word_limit → haiku (not local)
    text = "por favor podés abrir el firefox para mí"
    assert len(text.split()) > 6
    # keyword "abrir" is present but word count is too high
    assert router.route(text) == "claude_haiku"


def test_exactly_at_medium_limit(router: LLMRouter) -> None:
    # 20 words, no keyword → claude_haiku (still at or below medium limit)
    words = ["palabra"] * 20
    text = " ".join(words)
    assert len(text.split()) == 20
    assert router.route(text) == "claude_haiku"


def test_one_over_medium_limit(router: LLMRouter) -> None:
    # 21 words, no keyword → claude_sonnet
    words = ["palabra"] * 21
    text = " ".join(words)
    assert len(text.split()) == 21
    assert router.route(text) == "claude_sonnet"


def test_empty_text_routes_to_haiku(router: LLMRouter) -> None:
    # Empty string: 0 words, no keyword, 0 ≤ 20 → haiku
    # (0 ≤ 6 but no keyword, so rule 1 fails; 0 ≤ 20 → rule 2 matches)
    assert router.route("") == "claude_haiku"


def test_single_non_keyword_word(router: LLMRouter) -> None:
    # 1 word, no keyword → haiku (short but no keyword so rule 1 fails)
    assert router.route("hola") == "claude_haiku"


# ---------------------------------------------------------------------------
# ML classifier registration
# ---------------------------------------------------------------------------


def test_register_classifier_overrides_heuristic(router: LLMRouter) -> None:
    """Registered classifier takes priority over keyword heuristic."""

    def always_gemini(text: str) -> RouteTarget:
        return "gemini_flash"

    router.register_classifier(always_gemini)

    # Would normally route to "local" via keyword heuristic
    assert router.route("abrir firefox") == "gemini_flash"
    assert router.route("bajá el volumen") == "gemini_flash"


def test_force_overrides_classifier(router: LLMRouter) -> None:
    """force= wins even when ML classifier is registered."""

    def always_gemini(text: str) -> RouteTarget:
        return "gemini_flash"

    router.register_classifier(always_gemini)

    # force beats classifier
    assert router.route("abrir firefox", force="local") == "local"
    assert router.route("texto cualquiera", force="claude_sonnet") == "claude_sonnet"


def test_classifier_receives_original_text(router: LLMRouter) -> None:
    """Classifier is called with the unmodified original text."""
    received: list[str] = []

    def capture_classifier(text: str) -> RouteTarget:
        received.append(text)
        return "claude_haiku"

    router.register_classifier(capture_classifier)
    router.route("Hola Jarvis, ¿cómo estás?")

    assert received == ["Hola Jarvis, ¿cómo estás?"]


# ---------------------------------------------------------------------------
# SIMPLE_PATTERNS sanity check
# ---------------------------------------------------------------------------


def test_simple_patterns_are_non_empty_strings() -> None:
    assert all(isinstance(p, str) and p for p in SIMPLE_PATTERNS)


def test_simple_patterns_are_lowercase() -> None:
    assert all(p == p.lower() for p in SIMPLE_PATTERNS)

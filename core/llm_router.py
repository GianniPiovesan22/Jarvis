"""
LLM Router for Jarvis.

Pure synchronous module — no I/O, no imports of heavy ML libraries.
Routes a user's transcribed command to the appropriate LLM target
based on word count and keyword matching.

Routing algorithm:
    1. If *force* is provided (CLI flag) → return it unconditionally.
    2. If an ML classifier is registered → delegate to it.
    3. Otherwise use keyword-based heuristic:
       - short (≤ simple_limit words) + keyword match → "local"
       - medium (≤ medium_limit words)                → "claude_haiku"
       - long / complex                               → "claude_sonnet"

"gemini_flash" is NOT in the default routing path. It is only reachable
via --force-gemini (i.e. passing force="gemini_flash").

Extension point: call router.register_classifier(fn) to plug in an ML
classifier that overrides the keyword heuristic without touching the
force-override or public API.
"""

from __future__ import annotations

from typing import Callable, Literal

from loguru import logger

from core.config_loader import LLMConfig

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

RouteTarget = Literal["local", "claude_haiku", "claude_sonnet", "gemini_flash"]

# ---------------------------------------------------------------------------
# Simple keyword patterns (from SPEC section 4.3)
# ---------------------------------------------------------------------------

SIMPLE_PATTERNS: list[str] = [
    "abr",
    "cerr",
    "abrir",
    "cerrar",
    "subí",
    "bajá",
    "volumen",
    "brillo",
    "wifi",
    "apagá",
    "reiniciá",
    "abrí",
    "qué hora",
    "screenshot",
    "bloqueá",
]


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


class LLMRouter:
    """
    Routes a user command to the best LLM target.

    Args:
        config: LLMConfig dataclass — provides simple_word_limit and
                medium_word_limit thresholds.
    """

    def __init__(self, config: LLMConfig) -> None:
        self._simple_limit: int = config.simple_word_limit
        self._medium_limit: int = config.medium_word_limit
        self._classifier: Callable[[str], RouteTarget] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(self, text: str, force: RouteTarget | None = None) -> RouteTarget:
        """
        Decide which LLM should handle *text*.

        Args:
            text:  The user's transcribed command (raw, any case).
            force: If provided, returned immediately — CLI flag wins.

        Returns:
            One of: "local", "claude_haiku", "claude_sonnet", "gemini_flash".
        """
        if force is not None:
            logger.debug("Router: force={} override active", force)
            return force

        if self._classifier is not None:
            target = self._classifier(text)
            logger.debug("Router: ML classifier → {}", target)
            return target

        target = self._keyword_route(text)
        logger.debug("Router: keyword heuristic → {} (text={!r})", target, text[:60])
        return target

    def register_classifier(self, fn: Callable[[str], RouteTarget]) -> None:
        """
        Register an ML classifier to replace the keyword heuristic.

        The classifier receives the raw user text and must return a
        RouteTarget literal. It is called only when force=None.

        Args:
            fn: A callable (str) -> RouteTarget. Should be fast (< 50 ms).
        """
        self._classifier = fn
        logger.info("Router: ML classifier registered ({})", fn.__name__)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _keyword_route(self, text: str) -> RouteTarget:
        """Keyword + word-count heuristic routing."""
        words = text.split()
        text_lower = text.lower()

        # Rule 1: short AND contains a simple-action keyword → Ollama local
        if len(words) <= self._simple_limit and any(p in text_lower for p in SIMPLE_PATTERNS):
            return "local"

        # Rule 2: medium length → Claude Haiku (fast, cheap cloud)
        if len(words) <= self._medium_limit:
            return "claude_haiku"

        # Rule 3: long / complex → Claude Sonnet (reasoning, code, analysis)
        return "claude_sonnet"

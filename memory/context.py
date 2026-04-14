"""ContextBuilder — assembles prompt context from memory for LLM injection.

Stub implementation. Will be fleshed out once the core pipeline is stable.
"""

from loguru import logger

from memory.db import MemoryDB


class ContextBuilder:
    """Builds LLM-ready context strings from MemoryDB contents.

    Combines active memory facts and recent conversation history into
    a structured system prompt addition.
    """

    def __init__(self, db: MemoryDB) -> None:
        self._db = db

    def build_system_context(self, session_id: str) -> str:
        """Build a system context string from active facts for injection into LLM prompts.

        Args:
            session_id: Current session identifier (used to exclude own turns if needed).

        Returns:
            A formatted string suitable for inclusion in the system prompt.

        Raises:
            NotImplementedError: Not yet implemented.
        """
        logger.debug(f"build_system_context called for session={session_id!r}")
        raise NotImplementedError("context.ContextBuilder.build_system_context not yet implemented")

    def build_history(self, session_id: str, limit: int = 10) -> list[dict[str, str]]:
        """Return recent conversation history formatted for LLM messages array.

        Args:
            session_id: Session to pull history from.
            limit: Maximum number of turns to include.

        Returns:
            List of dicts with 'role' and 'content' keys, oldest first.

        Raises:
            NotImplementedError: Not yet implemented.
        """
        logger.debug(
            f"build_history called for session={session_id!r} limit={limit}"
        )
        raise NotImplementedError("context.ContextBuilder.build_history not yet implemented")

    def summarize_facts(self, category: str | None = None) -> str:
        """Summarize active memory facts into a human-readable string.

        Args:
            category: Optional filter — "preference", "fact", or "instruction".

        Returns:
            Formatted summary string.

        Raises:
            NotImplementedError: Not yet implemented.
        """
        logger.debug(f"summarize_facts called with category={category!r}")
        raise NotImplementedError("context.ContextBuilder.summarize_facts not yet implemented")

"""Tool stubs for browser and web operations."""

from loguru import logger


async def open_url(url: str) -> dict:
    """Abre una URL en el navegador predeterminado del sistema.

    Args:
        url: URL completa a abrir (ej. "https://github.com").

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug(f"open_url called with url={url!r}")
    raise NotImplementedError("browser.open_url not yet implemented")


async def web_search(query: str) -> dict:
    """Realiza una búsqueda web con la consulta especificada.

    Args:
        query: Texto de búsqueda (ej. "python asyncio tutorial").

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: url (str) con la URL de búsqueda abierta.
    """
    logger.debug(f"web_search called with query={query!r}")
    raise NotImplementedError("browser.web_search not yet implemented")

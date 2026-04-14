"""Tool implementations for browser and web operations."""

import asyncio
from urllib.parse import quote_plus

from loguru import logger


async def open_url(url: str) -> dict:
    """Abre una URL en el navegador predeterminado del sistema via xdg-open.

    Valida que la URL comience con http:// o https://. Si no tiene esquema,
    antepone https:// automáticamente. El proceso se lanza de forma desacoplada
    (detached) para no bloquear el event loop.

    Args:
        url: URL a abrir (ej. "https://github.com" o "github.com").

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: url (str) con la URL efectivamente abierta.
    """
    logger.debug(f"open_url called with url={url!r}")

    if not url or not url.strip():
        return {"success": False, "result": None, "error": "URL vacía"}

    try:
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        proc = await asyncio.create_subprocess_exec(
            "xdg-open", url,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        # Fire and forget — xdg-open exits immediately after handing off to browser
        asyncio.get_event_loop().create_task(_wait_proc(proc))

        logger.info(f"Opened URL: {url}")
        return {"success": True, "result": {"url": url}, "error": None}
    except Exception as e:
        logger.error(f"open_url failed: {e}")
        return {"success": False, "result": None, "error": str(e)}


async def _wait_proc(proc: asyncio.subprocess.Process) -> None:
    """Helper to await a detached process without blocking the caller."""
    try:
        await proc.wait()
    except Exception:
        pass


async def web_search(query: str) -> dict:
    """Realiza una búsqueda en DuckDuckGo con la consulta especificada.

    URL-encodea la query y abre el resultado en el navegador predeterminado
    via xdg-open. Devuelve la URL de búsqueda construida.

    Args:
        query: Texto de búsqueda (ej. "python asyncio tutorial").

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: url (str) con la URL de búsqueda abierta.
    """
    logger.debug(f"web_search called with query={query!r}")

    if not query or not query.strip():
        return {"success": False, "result": None, "error": "Consulta de búsqueda vacía"}

    try:
        encoded = quote_plus(query)
        search_url = f"https://duckduckgo.com/?q={encoded}"

        result = await open_url(search_url)
        if not result["success"]:
            return result

        logger.info(f"Web search opened: {search_url}")
        return {"success": True, "result": {"url": search_url}, "error": None}
    except Exception as e:
        logger.error(f"web_search failed: {e}")
        return {"success": False, "result": None, "error": str(e)}

"""Tool stubs for clipboard operations."""

from loguru import logger


async def get_clipboard() -> dict:
    """Obtiene el contenido actual del portapapeles del sistema.

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: content (str) con el texto del portapapeles.
    """
    logger.debug("get_clipboard called")
    raise NotImplementedError("clipboard.get_clipboard not yet implemented")


async def set_clipboard(content: str) -> dict:
    """Copia texto al portapapeles del sistema.

    Args:
        content: Texto a copiar al portapapeles.

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug(f"set_clipboard called with content length={len(content)}")
    raise NotImplementedError("clipboard.set_clipboard not yet implemented")

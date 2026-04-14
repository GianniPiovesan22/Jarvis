"""Tool stubs for application management (open, close, list, focus)."""

from loguru import logger


async def open_app(name: str) -> dict:
    """Abre una aplicación por nombre o comando.

    Args:
        name: Nombre o comando de la aplicación a abrir (ej. "firefox", "gedit").

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug(f"open_app called with name={name!r}")
    raise NotImplementedError("apps.open_app not yet implemented")


async def close_app(name: str) -> dict:
    """Cierra una aplicación por nombre.

    Args:
        name: Nombre del proceso o ventana a cerrar.

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug(f"close_app called with name={name!r}")
    raise NotImplementedError("apps.close_app not yet implemented")


async def list_windows() -> dict:
    """Lista todas las ventanas abiertas en el escritorio.

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: windows (list[dict]) con id, title, app.
    """
    logger.debug("list_windows called")
    raise NotImplementedError("apps.list_windows not yet implemented")


async def focus_window(title: str) -> dict:
    """Enfoca una ventana específica por su título.

    Args:
        title: Título (parcial o completo) de la ventana a enfocar.

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug(f"focus_window called with title={title!r}")
    raise NotImplementedError("apps.focus_window not yet implemented")

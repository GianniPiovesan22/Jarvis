"""Tool stubs for desktop notification operations."""

from loguru import logger


async def send_notification(title: str, body: str, urgency: str = "normal") -> dict:
    """Envía una notificación de escritorio al usuario.

    Args:
        title: Título de la notificación.
        body: Cuerpo o mensaje de la notificación.
        urgency: Nivel de urgencia: "low", "normal" o "critical". Por defecto "normal".

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug(f"send_notification called: title={title!r}, urgency={urgency!r}")
    raise NotImplementedError("notifications.send_notification not yet implemented")

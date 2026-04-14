"""Tool implementations for desktop notification operations."""

import asyncio

from loguru import logger

_VALID_URGENCIES = {"low", "normal", "critical"}


async def send_notification(title: str, body: str, urgency: str = "normal") -> dict:
    """Envía una notificación de escritorio via notify-send (libnotify).

    Args:
        title: Título de la notificación.
        body: Cuerpo o mensaje de la notificación.
        urgency: Nivel de urgencia: "low", "normal" o "critical". Por defecto "normal".

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: title (str), body (str), urgency (str).
    """
    logger.debug(f"send_notification called: title={title!r}, urgency={urgency!r}")
    try:
        if urgency not in _VALID_URGENCIES:
            return {
                "success": False,
                "result": None,
                "error": f"Invalid urgency {urgency!r}. Must be one of: {sorted(_VALID_URGENCIES)}",
            }

        proc = await asyncio.create_subprocess_exec(
            "notify-send",
            f"--urgency={urgency}",
            title,
            body,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            return {"success": False, "result": None, "error": err_msg or "notify-send failed"}

        logger.info(f"Sent notification [{urgency}]: {title!r}")
        return {
            "success": True,
            "result": {"title": title, "body": body, "urgency": urgency},
            "error": None,
        }

    except FileNotFoundError:
        msg = "notify-send not found. Install libnotify: sudo pacman -S libnotify"
        logger.error(msg)
        return {"success": False, "result": None, "error": msg}
    except Exception as e:
        logger.error(f"send_notification failed: {e}")
        return {"success": False, "result": None, "error": str(e)}

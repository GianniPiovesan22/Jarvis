"""Tool stubs for system-level operations (volume, brightness, wifi, etc.)."""

from loguru import logger


async def set_volume(level: int) -> dict:
    """Ajusta el volumen del sistema al nivel especificado (0-100).

    Args:
        level: Nivel de volumen entre 0 y 100.

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug(f"set_volume called with level={level}")
    raise NotImplementedError("system.set_volume not yet implemented")


async def set_brightness(level: int) -> dict:
    """Ajusta el brillo de la pantalla al nivel especificado (0-100).

    Args:
        level: Nivel de brillo entre 0 y 100.

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug(f"set_brightness called with level={level}")
    raise NotImplementedError("system.set_brightness not yet implemented")


async def get_wifi_status() -> dict:
    """Obtiene el estado actual de la conexión WiFi.

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: connected (bool), ssid (str | None), signal (int | None).
    """
    logger.debug("get_wifi_status called")
    raise NotImplementedError("system.get_wifi_status not yet implemented")


async def toggle_wifi() -> dict:
    """Activa o desactiva el WiFi según su estado actual.

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: enabled (bool).
    """
    logger.debug("toggle_wifi called")
    raise NotImplementedError("system.toggle_wifi not yet implemented")


async def get_system_info() -> dict:
    """Obtiene información general del sistema (CPU, RAM, disco, etc.).

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: cpu_percent, ram_percent, disk_percent, uptime.
    """
    logger.debug("get_system_info called")
    raise NotImplementedError("system.get_system_info not yet implemented")


async def take_screenshot() -> dict:
    """Toma una captura de pantalla y la guarda en el directorio de imágenes.

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: path (str) con la ruta al archivo guardado.
    """
    logger.debug("take_screenshot called")
    raise NotImplementedError("system.take_screenshot not yet implemented")


async def shutdown() -> dict:
    """Apaga el sistema de forma segura.

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug("shutdown called")
    raise NotImplementedError("system.shutdown not yet implemented")


async def reboot() -> dict:
    """Reinicia el sistema de forma segura.

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug("reboot called")
    raise NotImplementedError("system.reboot not yet implemented")


async def lock_screen() -> dict:
    """Bloquea la pantalla del sistema.

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug("lock_screen called")
    raise NotImplementedError("system.lock_screen not yet implemented")

"""Tool stubs for terminal and command execution."""

from loguru import logger


async def run_command(command: str, sudo: bool = False) -> dict:
    """Ejecuta un comando en la terminal y retorna su salida.

    Args:
        command: Comando a ejecutar (ej. "ls -la", "df -h").
        sudo: Si True, ejecuta el comando con privilegios de superusuario.

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: stdout (str), stderr (str), returncode (int).
    """
    logger.debug(f"run_command called with command={command!r}, sudo={sudo}")
    raise NotImplementedError("terminal.run_command not yet implemented")


async def open_terminal(cwd: str | None = None) -> dict:
    """Abre una nueva ventana de terminal, opcionalmente en un directorio específico.

    Args:
        cwd: Directorio de trabajo inicial. Si es None, usa el home del usuario.

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug(f"open_terminal called with cwd={cwd!r}")
    raise NotImplementedError("terminal.open_terminal not yet implemented")


async def run_script(path: str) -> dict:
    """Ejecuta un script de shell o Python por su ruta de archivo.

    Args:
        path: Ruta al archivo de script a ejecutar.

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: stdout (str), stderr (str), returncode (int).
    """
    logger.debug(f"run_script called with path={path!r}")
    raise NotImplementedError("terminal.run_script not yet implemented")

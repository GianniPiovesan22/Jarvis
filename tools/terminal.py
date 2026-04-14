"""Tool implementations for terminal and command execution."""

import asyncio
import shlex
from pathlib import Path

from loguru import logger

_COMMAND_TIMEOUT = 30  # seconds


async def run_command(command: str, sudo: bool = False) -> dict:
    """Ejecuta un comando en la terminal y retorna su salida. Implemented.

    Usa create_subprocess_exec (no shell) para evitar inyección de comandos.
    Parsea el comando con shlex.split para soportar argumentos con espacios.

    Args:
        command: Comando a ejecutar (ej. "ls -la", "df -h").
        sudo: Si True, antepone sudo a la lista de argumentos.

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: stdout (str), stderr (str), returncode (int).
    """
    logger.debug(f"run_command called with command={command!r}, sudo={sudo}")

    if not command or not command.strip():
        return {"success": False, "result": None, "error": "Comando vacío"}

    try:
        try:
            args = shlex.split(command)
        except ValueError as e:
            return {"success": False, "result": None, "error": f"Comando inválido: {e}"}

        if sudo:
            args = ["sudo"] + args

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_COMMAND_TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            err = f"Comando agotó el tiempo ({_COMMAND_TIMEOUT}s): {command!r}"
            logger.error(err)
            return {"success": False, "result": None, "error": err}

        stdout_str = stdout.decode().strip()
        stderr_str = stderr.decode().strip()
        returncode = proc.returncode

        logger.info(f"Command finished (rc={returncode}): {command!r}")
        return {
            "success": returncode == 0,
            "result": {
                "stdout": stdout_str,
                "stderr": stderr_str,
                "returncode": returncode,
            },
            "error": stderr_str if returncode != 0 else None,
        }
    except Exception as e:
        logger.exception("run_command error")
        return {"success": False, "result": None, "error": str(e)}


async def open_terminal(cwd: str | None = None) -> dict:
    """Abre una nueva ventana de terminal, opcionalmente en un directorio específico. Implemented.

    Args:
        cwd: Directorio de trabajo inicial. Si es None, usa el home del usuario.

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug(f"open_terminal called with cwd={cwd!r}")
    try:
        directory = cwd.strip() if cwd and cwd.strip() else str(Path.home())

        proc = await asyncio.create_subprocess_exec(
            "kitty", "--directory", directory,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        logger.info(f"Terminal opened in {directory!r} (PID {proc.pid})")
        return {"success": True, "result": {"cwd": directory, "pid": proc.pid}, "error": None}
    except FileNotFoundError:
        err = "kitty not found in PATH"
        logger.error(err)
        return {"success": False, "result": None, "error": err}
    except Exception as e:
        logger.exception("open_terminal error")
        return {"success": False, "result": None, "error": str(e)}


async def run_script(path: str) -> dict:
    """Ejecuta un script de shell o Python por su ruta de archivo. Implemented.

    Args:
        path: Ruta al archivo de script a ejecutar.

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: stdout (str), stderr (str), returncode (int).
    """
    logger.debug(f"run_script called with path={path!r}")

    if not path or not path.strip():
        return {"success": False, "result": None, "error": "Ruta de script vacía"}

    try:
        script_path = Path(path).expanduser().resolve()

        if not script_path.exists():
            err = f"Script not found: {path!r}"
            logger.error(err)
            return {"success": False, "result": None, "error": err}

        suffix = script_path.suffix.lower()
        if suffix == ".py":
            interpreter = "python3"
        elif suffix == ".sh":
            interpreter = "bash"
        else:
            err = f"Unsupported script extension: {suffix!r} (expected .py or .sh)"
            logger.error(err)
            return {"success": False, "result": None, "error": err}

        proc = await asyncio.create_subprocess_exec(
            interpreter, str(script_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_COMMAND_TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            err = f"Script agotó el tiempo ({_COMMAND_TIMEOUT}s): {path!r}"
            logger.error(err)
            return {"success": False, "result": None, "error": err}

        stdout_str = stdout.decode().strip()
        stderr_str = stderr.decode().strip()
        returncode = proc.returncode

        logger.info(f"Script finished (rc={returncode}): {path!r}")
        return {
            "success": returncode == 0,
            "result": {
                "stdout": stdout_str,
                "stderr": stderr_str,
                "returncode": returncode,
            },
            "error": stderr_str if returncode != 0 else None,
        }
    except Exception as e:
        logger.exception("run_script error")
        return {"success": False, "result": None, "error": str(e)}

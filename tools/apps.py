"""Tool implementations for application management (open, close, list, focus)."""

import asyncio
import json

from loguru import logger

# Mapping of common spoken/alias names to actual commands
APP_MAP: dict[str, str] = {
    "firefox": "firefox",
    "browser": "firefox",
    "chrome": "google-chrome-stable",
    "chromium": "chromium",
    "spotify": "spotify",
    "music": "spotify",
    "code": "code",
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "terminal": "kitty",
    "kitty": "kitty",
    "files": "thunar",
    "thunar": "thunar",
    "nautilus": "nautilus",
    "file manager": "thunar",
    "discord": "discord",
    "telegram": "telegram-desktop",
    "slack": "slack",
    "steam": "steam",
    "obsidian": "obsidian",
    "vlc": "vlc",
    "gimp": "gimp",
    "inkscape": "inkscape",
    "thunarfm": "thunar",
    "pcmanfm": "pcmanfm",
    "dolphin": "dolphin",
}


async def open_app(name: str) -> dict:
    """Abre una aplicación por nombre o comando. Implemented.

    Args:
        name: Nombre o comando de la aplicación a abrir (ej. "firefox", "gedit").

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug(f"open_app called with name={name!r}")
    try:
        normalized = name.lower().strip()
        command = APP_MAP.get(normalized, normalized)
        logger.info(f"Launching app: {command} (requested: {name!r})")

        # Detach: don't wait for the process — Jarvis must not block
        proc = await asyncio.create_subprocess_exec(
            command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            # start_new_session detaches from Jarvis's process group
            start_new_session=True,
        )
        logger.info(f"App launched: {command} (PID {proc.pid})")
        return {"success": True, "result": {"command": command, "pid": proc.pid}, "error": None}
    except FileNotFoundError:
        err = f"Command not found: {command!r}"
        logger.error(err)
        return {"success": False, "result": None, "error": err}
    except Exception as e:
        logger.exception("open_app error")
        return {"success": False, "result": None, "error": str(e)}


async def close_app(name: str) -> dict:
    """Cierra una aplicación por nombre. Implemented.

    Args:
        name: Nombre del proceso o ventana a cerrar.

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug(f"close_app called with name={name!r}")
    try:
        normalized = name.lower().strip()
        # Resolve alias to real command name for pkill
        command = APP_MAP.get(normalized, normalized)

        proc = await asyncio.create_subprocess_exec(
            "pkill", "-f", command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        # pkill exits 1 if no processes matched — treat as "not running"
        if proc.returncode == 1:
            msg = f"No running process matched: {command!r}"
            logger.warning(msg)
            return {"success": False, "result": None, "error": msg}

        if proc.returncode not in (0, 1):
            err = stderr.decode().strip()
            logger.error(f"close_app pkill failed: {err}")
            return {"success": False, "result": None, "error": err}

        logger.info(f"Closed app: {command}")
        return {"success": True, "result": {"closed": command}, "error": None}
    except Exception as e:
        logger.exception("close_app error")
        return {"success": False, "result": None, "error": str(e)}


async def list_windows() -> dict:
    """Lista todas las ventanas abiertas en el escritorio. Implemented.

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: windows (list[dict]) con id, title, class, workspace.
    """
    logger.debug("list_windows called")
    try:
        proc = await asyncio.create_subprocess_exec(
            "hyprctl", "clients", "-j",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode().strip()
            logger.error(f"list_windows failed: {err}")
            return {"success": False, "result": None, "error": err}

        clients = json.loads(stdout.decode())
        windows = [
            {
                "id": client.get("address", ""),
                "title": client.get("title", ""),
                "class": client.get("class", ""),
                "workspace": client.get("workspace", {}).get("name", ""),
            }
            for client in clients
        ]
        logger.info(f"Found {len(windows)} windows")
        return {"success": True, "result": {"windows": windows}, "error": None}
    except json.JSONDecodeError as e:
        logger.error(f"list_windows JSON parse error: {e}")
        return {"success": False, "result": None, "error": f"JSON parse error: {e}"}
    except Exception as e:
        logger.exception("list_windows error")
        return {"success": False, "result": None, "error": str(e)}


async def focus_window(title: str) -> dict:
    """Enfoca una ventana específica por su título. Implemented.

    Args:
        title: Título (parcial o completo) de la ventana a enfocar.

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug(f"focus_window called with title={title!r}")
    try:
        proc = await asyncio.create_subprocess_exec(
            "hyprctl", "clients", "-j",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode().strip()
            logger.error(f"focus_window hyprctl clients failed: {err}")
            return {"success": False, "result": None, "error": err}

        clients = json.loads(stdout.decode())
        search = title.lower()

        matched = None
        for client in clients:
            client_title = client.get("title", "").lower()
            client_class = client.get("class", "").lower()
            if search in client_title or search in client_class:
                matched = client
                break

        if matched is None:
            err = f"No window found matching: {title!r}"
            logger.warning(err)
            return {"success": False, "result": None, "error": err}

        address = matched.get("address", "")
        focus_proc = await asyncio.create_subprocess_exec(
            "hyprctl", "dispatch", "focuswindow", f"address:{address}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await focus_proc.communicate()
        if focus_proc.returncode != 0:
            err = stderr.decode().strip()
            logger.error(f"focus_window dispatch failed: {err}")
            return {"success": False, "result": None, "error": err}

        logger.info(f"Focused window: {matched.get('title')!r} (address: {address})")
        return {
            "success": True,
            "result": {"title": matched.get("title"), "class": matched.get("class"), "address": address},
            "error": None,
        }
    except json.JSONDecodeError as e:
        logger.error(f"focus_window JSON parse error: {e}")
        return {"success": False, "result": None, "error": f"JSON parse error: {e}"}
    except Exception as e:
        logger.exception("focus_window error")
        return {"success": False, "result": None, "error": str(e)}

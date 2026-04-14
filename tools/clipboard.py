"""Tool implementations for clipboard operations (Wayland via wl-paste/wl-copy)."""

import asyncio

from loguru import logger


async def get_clipboard() -> dict:
    """Obtiene el contenido actual del portapapeles del sistema via wl-paste.

    Maneja graciosamente el portapapeles vacío (retorna string vacío en lugar
    de error). Si wl-paste no está instalado, retorna un error descriptivo.

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: content (str) con el texto del portapapeles.
    """
    logger.debug("get_clipboard called")
    try:
        proc = await asyncio.create_subprocess_exec(
            "wl-paste", "--no-newline",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        # wl-paste exits with code 1 when clipboard is empty — treat it as empty content
        if proc.returncode == 1:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            # Common message when clipboard is empty: "Nothing is copied"
            if "Nothing is copied" in err_msg or "no selection" in err_msg.lower() or err_msg == "":
                logger.debug("Clipboard is empty")
                return {"success": True, "result": {"content": ""}, "error": None}
            # Any other non-zero exit with stderr is a real error
            return {"success": False, "result": None, "error": err_msg or "wl-paste failed"}

        content = stdout.decode("utf-8", errors="replace")
        logger.info(f"Got clipboard content ({len(content)} chars)")
        return {"success": True, "result": {"content": content}, "error": None}

    except FileNotFoundError:
        msg = "wl-paste not found. Install wl-clipboard: sudo pacman -S wl-clipboard"
        logger.error(msg)
        return {"success": False, "result": None, "error": msg}
    except Exception as e:
        logger.error(f"get_clipboard failed: {e}")
        return {"success": False, "result": None, "error": str(e)}


async def set_clipboard(content: str) -> dict:
    """Copia texto al portapapeles del sistema via wl-copy.

    El contenido se pasa por stdin al proceso wl-copy para soportar cualquier
    carácter especial sin problemas de escaping en shell.

    Args:
        content: Texto a copiar al portapapeles.

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: length (int) con la cantidad de caracteres copiados.
    """
    logger.debug(f"set_clipboard called with content length={len(content)}")
    try:
        proc = await asyncio.create_subprocess_exec(
            "wl-copy",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate(input=content.encode("utf-8"))

        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            return {"success": False, "result": None, "error": err_msg or "wl-copy failed"}

        logger.info(f"Set clipboard content ({len(content)} chars)")
        return {"success": True, "result": {"length": len(content)}, "error": None}

    except FileNotFoundError:
        msg = "wl-copy not found. Install wl-clipboard: sudo pacman -S wl-clipboard"
        logger.error(msg)
        return {"success": False, "result": None, "error": msg}
    except Exception as e:
        logger.error(f"set_clipboard failed: {e}")
        return {"success": False, "result": None, "error": str(e)}

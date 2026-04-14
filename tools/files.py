"""Tool implementations for file system operations."""

import asyncio
import shutil
from pathlib import Path

from loguru import logger

_MAX_FILE_SIZE = 50 * 1024  # 50 KB


def _expand(path: str) -> Path:
    """Expand ~ and resolve symlinks/relative components to an absolute Path."""
    return Path(path).expanduser().resolve()


async def read_file(path: str) -> dict:
    """Lee el contenido de un archivo de texto (máximo 50 KB).

    Expande ~ automáticamente. Rechaza archivos binarios y archivos que
    superen el límite de 50 KB para evitar problemas de memoria.

    Args:
        path: Ruta absoluta o relativa al archivo a leer (soporta ~).

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: content (str) con el contenido del archivo,
        size_bytes (int) con el tamaño del archivo.
    """
    logger.debug(f"read_file called with path={path!r}")

    if not path or not path.strip():
        return {"success": False, "result": None, "error": "Ruta de archivo vacía"}

    try:
        p = _expand(path)

        if not p.exists():
            return {"success": False, "result": None, "error": f"File not found: {p}"}
        if not p.is_file():
            return {"success": False, "result": None, "error": f"Not a file: {p}"}

        size = p.stat().st_size
        if size > _MAX_FILE_SIZE:
            return {
                "success": False,
                "result": None,
                "error": f"File too large ({size} bytes > {_MAX_FILE_SIZE} bytes limit): {p}",
            }

        try:
            content = await asyncio.to_thread(p.read_text, encoding="utf-8")
        except UnicodeDecodeError:
            return {
                "success": False,
                "result": None,
                "error": f"Binary file or non-UTF-8 encoding, cannot read as text: {p}",
            }

        logger.info(f"Read file: {p} ({size} bytes)")
        return {"success": True, "result": {"content": content, "size_bytes": size}, "error": None}
    except Exception as e:
        logger.error(f"read_file failed: {e}")
        return {"success": False, "result": None, "error": str(e)}


async def list_directory(path: str) -> dict:
    """Lista el contenido de un directorio, dirs primero luego archivos.

    Para cada entrada devuelve: name, type (file|dir|symlink), size en bytes.
    Los symlinks reportan el tamaño del link mismo, no del destino.

    Args:
        path: Ruta al directorio a listar (soporta ~).

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: entries (list[dict]) con name, type, size.
    """
    logger.debug(f"list_directory called with path={path!r}")

    if not path or not path.strip():
        return {"success": False, "result": None, "error": "Ruta de directorio vacía"}

    try:
        p = _expand(path)

        if not p.exists():
            return {"success": False, "result": None, "error": f"Path not found: {p}"}
        if not p.is_dir():
            return {"success": False, "result": None, "error": f"Not a directory: {p}"}

        def _scan() -> list[dict]:
            entries = []
            for entry in p.iterdir():
                if entry.is_symlink():
                    kind = "symlink"
                    size = entry.lstat().st_size
                elif entry.is_dir():
                    kind = "dir"
                    size = 0
                else:
                    kind = "file"
                    size = entry.stat().st_size
                entries.append({"name": entry.name, "type": kind, "size": size})
            # dirs first, then files and symlinks, alphabetically within each group
            entries.sort(key=lambda e: (0 if e["type"] == "dir" else 1, e["name"].lower()))
            return entries

        entries = await asyncio.to_thread(_scan)
        logger.info(f"Listed directory: {p} ({len(entries)} entries)")
        return {"success": True, "result": {"entries": entries}, "error": None}
    except Exception as e:
        logger.error(f"list_directory failed: {e}")
        return {"success": False, "result": None, "error": str(e)}


async def move_file(source: str, destination: str) -> dict:
    """Mueve o renombra un archivo o directorio.

    Valida que el origen exista antes de mover. Expande ~ en ambas rutas.

    Args:
        source: Ruta de origen (soporta ~).
        destination: Ruta de destino (soporta ~).

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: source (str) y destination (str) con las rutas resueltas.
    """
    logger.debug(f"move_file called with source={source!r}, destination={destination!r}")

    if not source or not source.strip():
        return {"success": False, "result": None, "error": "Ruta de origen vacía"}
    if not destination or not destination.strip():
        return {"success": False, "result": None, "error": "Ruta de destino vacía"}

    try:
        src = _expand(source)
        dst = _expand(destination)

        if not src.exists():
            return {"success": False, "result": None, "error": f"Source not found: {src}"}

        await asyncio.to_thread(shutil.move, str(src), str(dst))
        logger.info(f"Moved: {src} → {dst}")
        return {
            "success": True,
            "result": {"source": str(src), "destination": str(dst)},
            "error": None,
        }
    except Exception as e:
        logger.error(f"move_file failed: {e}")
        return {"success": False, "result": None, "error": str(e)}


_FORBIDDEN_PATHS = {
    Path("/"),
    Path("/home"),
    Path("/home/giannip"),
}


def _is_safe_to_delete(p: Path) -> tuple[bool, str]:
    """Retorna (es_seguro, motivo). Una ruta es insegura si es protegida o demasiado superficial.

    Args:
        p: Ruta ya resuelta (expanduser + resolve) a verificar.
    """
    # p already resolved by _expand — check directly
    if p in _FORBIDDEN_PATHS:
        return False, f"Ruta protegida, operación rechazada: {p}"
    # Paths with fewer than 3 components after root (e.g. /home or /tmp) are unsafe
    if len(p.parts) < 3:
        return False, f"Ruta demasiado superficial para eliminar (< 3 componentes): {p}"
    return True, ""


async def delete_file(path: str) -> dict:
    """Elimina un archivo o directorio vacío.

    Incluye protecciones de seguridad: rechaza /, /home, /home/giannip y
    cualquier ruta con menos de 3 componentes. No elimina directorios con contenido.

    Args:
        path: Ruta al archivo o directorio vacío a eliminar (soporta ~).

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: path (str) con la ruta eliminada.
    """
    logger.debug(f"delete_file called with path={path!r}")

    if not path or not path.strip():
        return {"success": False, "result": None, "error": "Ruta de archivo vacía"}

    try:
        p = _expand(path)

        safe, reason = _is_safe_to_delete(p)
        if not safe:
            logger.warning(f"delete_file REFUSED: {reason}")
            return {"success": False, "result": None, "error": reason}

        if not p.exists():
            return {"success": False, "result": None, "error": f"Path not found: {p}"}

        if p.is_symlink() or p.is_file():
            await asyncio.to_thread(p.unlink)
            logger.info(f"Deleted file: {p}")
        elif p.is_dir():
            await asyncio.to_thread(p.rmdir)  # fails if non-empty — intentional
            logger.info(f"Deleted empty directory: {p}")
        else:
            return {"success": False, "result": None, "error": f"Unknown file type: {p}"}

        return {"success": True, "result": {"path": str(p)}, "error": None}
    except OSError as e:
        logger.error(f"delete_file OS error: {e}")
        return {"success": False, "result": None, "error": str(e)}
    except Exception as e:
        logger.error(f"delete_file failed: {e}")
        return {"success": False, "result": None, "error": str(e)}


async def create_file(path: str, content: str = "") -> dict:
    """Crea un nuevo archivo con contenido opcional, creando directorios padre si hacen falta.

    Si el archivo ya existe, lo sobreescribe. Expande ~ automáticamente.

    Args:
        path: Ruta donde crear el archivo (soporta ~).
        content: Contenido inicial del archivo. Por defecto vacío.

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: path (str) con la ruta creada y size_bytes (int).
    """
    logger.debug(f"create_file called with path={path!r}")

    if not path or not path.strip():
        return {"success": False, "result": None, "error": "Ruta de archivo vacía"}

    try:
        p = _expand(path)

        def _write() -> int:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return p.stat().st_size

        size = await asyncio.to_thread(_write)
        logger.info(f"Created file: {p} ({size} bytes)")
        return {"success": True, "result": {"path": str(p), "size_bytes": size}, "error": None}
    except Exception as e:
        logger.error(f"create_file failed: {e}")
        return {"success": False, "result": None, "error": str(e)}

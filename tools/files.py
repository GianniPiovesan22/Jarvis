"""Tool stubs for file system operations."""

from loguru import logger


async def read_file(path: str) -> dict:
    """Lee el contenido de un archivo de texto.

    Args:
        path: Ruta absoluta o relativa al archivo a leer.

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: content (str) con el contenido del archivo.
    """
    logger.debug(f"read_file called with path={path!r}")
    raise NotImplementedError("files.read_file not yet implemented")


async def list_directory(path: str) -> dict:
    """Lista el contenido de un directorio.

    Args:
        path: Ruta al directorio a listar.

    Returns:
        Contrato estándar { success, result, error }.
        result incluye: entries (list[dict]) con name, type (file|dir), size.
    """
    logger.debug(f"list_directory called with path={path!r}")
    raise NotImplementedError("files.list_directory not yet implemented")


async def move_file(source: str, destination: str) -> dict:
    """Mueve o renombra un archivo o directorio.

    Args:
        source: Ruta de origen del archivo o directorio.
        destination: Ruta de destino.

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug(f"move_file called with source={source!r}, destination={destination!r}")
    raise NotImplementedError("files.move_file not yet implemented")


async def delete_file(path: str) -> dict:
    """Elimina un archivo o directorio vacío.

    Args:
        path: Ruta al archivo o directorio a eliminar.

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug(f"delete_file called with path={path!r}")
    raise NotImplementedError("files.delete_file not yet implemented")


async def create_file(path: str, content: str = "") -> dict:
    """Crea un nuevo archivo con contenido opcional.

    Args:
        path: Ruta donde crear el archivo.
        content: Contenido inicial del archivo. Por defecto vacío.

    Returns:
        Contrato estándar { success, result, error }.
    """
    logger.debug(f"create_file called with path={path!r}")
    raise NotImplementedError("files.create_file not yet implemented")

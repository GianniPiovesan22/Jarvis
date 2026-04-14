"""Tool system — TOOL_REGISTRY and TOOL_SCHEMAS for all Jarvis tools.

TOOL_REGISTRY maps tool names to async callables.
TOOL_SCHEMAS provides JSON Schema definitions (Claude/Gemini compatible).
"""

from typing import Any, Callable

from tools import apps, browser, clipboard, files, notifications, system, terminal

# ---------------------------------------------------------------------------
# Registry — maps every tool name to its async callable
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    # system.py
    "set_volume": system.set_volume,
    "set_brightness": system.set_brightness,
    "get_wifi_status": system.get_wifi_status,
    "toggle_wifi": system.toggle_wifi,
    "get_system_info": system.get_system_info,
    "take_screenshot": system.take_screenshot,
    "shutdown": system.shutdown,
    "reboot": system.reboot,
    "lock_screen": system.lock_screen,
    # apps.py
    "open_app": apps.open_app,
    "close_app": apps.close_app,
    "list_windows": apps.list_windows,
    "focus_window": apps.focus_window,
    # terminal.py
    "run_command": terminal.run_command,
    "open_terminal": terminal.open_terminal,
    "run_script": terminal.run_script,
    # browser.py
    "open_url": browser.open_url,
    "web_search": browser.web_search,
    # files.py
    "read_file": files.read_file,
    "list_directory": files.list_directory,
    "move_file": files.move_file,
    "delete_file": files.delete_file,
    "create_file": files.create_file,
    # clipboard.py
    "get_clipboard": clipboard.get_clipboard,
    "set_clipboard": clipboard.set_clipboard,
    # notifications.py
    "send_notification": notifications.send_notification,
}

# ---------------------------------------------------------------------------
# Schemas — one entry per tool, Claude input_schema format
# Gemini adapter maps these dicts to types.FunctionDeclaration + types.Schema.
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    # ── system ──────────────────────────────────────────────────────────────
    {
        "name": "set_volume",
        "description": "Ajusta el volumen del sistema al nivel especificado (0-100)",
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                    "description": "Nivel de volumen entre 0 y 100",
                }
            },
            "required": ["level"],
        },
    },
    {
        "name": "set_brightness",
        "description": "Ajusta el brillo de la pantalla al nivel especificado (0-100)",
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                    "description": "Nivel de brillo entre 0 y 100",
                }
            },
            "required": ["level"],
        },
    },
    {
        "name": "get_wifi_status",
        "description": "Obtiene el estado actual de la conexión WiFi del sistema",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "toggle_wifi",
        "description": "Activa o desactiva el WiFi según su estado actual",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_system_info",
        "description": "Obtiene información general del sistema: CPU, RAM, disco y uptime",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "take_screenshot",
        "description": "Toma una captura de pantalla y la guarda en el directorio de imágenes",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "shutdown",
        "description": "Apaga el sistema de forma segura",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "reboot",
        "description": "Reinicia el sistema de forma segura",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "lock_screen",
        "description": "Bloquea la pantalla del sistema",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # ── apps ────────────────────────────────────────────────────────────────
    {
        "name": "open_app",
        "description": "Abre una aplicación por nombre o comando de sistema",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nombre o comando de la aplicación (ej. 'firefox', 'gedit')",
                }
            },
            "required": ["name"],
        },
    },
    {
        "name": "close_app",
        "description": "Cierra una aplicación por nombre de proceso o ventana",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nombre del proceso o ventana a cerrar",
                }
            },
            "required": ["name"],
        },
    },
    {
        "name": "list_windows",
        "description": "Lista todas las ventanas abiertas en el escritorio",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "focus_window",
        "description": "Enfoca una ventana específica buscándola por su título",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Título parcial o completo de la ventana a enfocar",
                }
            },
            "required": ["title"],
        },
    },
    # ── terminal ────────────────────────────────────────────────────────────
    {
        "name": "run_command",
        "description": "Ejecuta un comando en la terminal y retorna stdout y stderr",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Comando a ejecutar (ej. 'ls -la', 'df -h')",
                },
                "sudo": {
                    "type": "boolean",
                    "description": "Si true, ejecuta con privilegios de superusuario",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "open_terminal",
        "description": "Abre una nueva ventana de terminal, opcionalmente en un directorio específico",
        "input_schema": {
            "type": "object",
            "properties": {
                "cwd": {
                    "type": "string",
                    "description": "Directorio de trabajo inicial. Omitir para usar el home del usuario",
                }
            },
            "required": [],
        },
    },
    {
        "name": "run_script",
        "description": "Ejecuta un script de shell o Python por su ruta de archivo",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta al archivo de script a ejecutar",
                }
            },
            "required": ["path"],
        },
    },
    # ── browser ─────────────────────────────────────────────────────────────
    {
        "name": "open_url",
        "description": "Abre una URL en el navegador predeterminado del sistema",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL completa a abrir (ej. 'https://github.com')",
                }
            },
            "required": ["url"],
        },
    },
    {
        "name": "web_search",
        "description": "Realiza una búsqueda web y abre el navegador con los resultados",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Texto de búsqueda (ej. 'python asyncio tutorial')",
                }
            },
            "required": ["query"],
        },
    },
    # ── files ───────────────────────────────────────────────────────────────
    {
        "name": "read_file",
        "description": "Lee y retorna el contenido de un archivo de texto",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta absoluta o relativa al archivo a leer",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_directory",
        "description": "Lista el contenido de un directorio con nombre, tipo y tamaño",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta al directorio a listar",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "move_file",
        "description": "Mueve o renombra un archivo o directorio",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Ruta de origen del archivo o directorio",
                },
                "destination": {
                    "type": "string",
                    "description": "Ruta de destino",
                },
            },
            "required": ["source", "destination"],
        },
    },
    {
        "name": "delete_file",
        "description": "Elimina un archivo o directorio vacío",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta al archivo o directorio a eliminar",
                }
            },
            "required": ["path"],
        },
    },
    {
        "name": "create_file",
        "description": "Crea un nuevo archivo con contenido opcional",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta donde crear el archivo",
                },
                "content": {
                    "type": "string",
                    "description": "Contenido inicial del archivo. Por defecto vacío",
                },
            },
            "required": ["path"],
        },
    },
    # ── clipboard ───────────────────────────────────────────────────────────
    {
        "name": "get_clipboard",
        "description": "Obtiene el contenido actual del portapapeles del sistema",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "set_clipboard",
        "description": "Copia texto al portapapeles del sistema",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Texto a copiar al portapapeles",
                }
            },
            "required": ["content"],
        },
    },
    # ── notifications ───────────────────────────────────────────────────────
    {
        "name": "send_notification",
        "description": "Envía una notificación de escritorio al usuario",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Título de la notificación",
                },
                "body": {
                    "type": "string",
                    "description": "Cuerpo o mensaje de la notificación",
                },
                "urgency": {
                    "type": "string",
                    "enum": ["low", "normal", "critical"],
                    "description": "Nivel de urgencia: low, normal o critical",
                },
            },
            "required": ["title", "body"],
        },
    },
]

__all__ = ["TOOL_REGISTRY", "TOOL_SCHEMAS"]

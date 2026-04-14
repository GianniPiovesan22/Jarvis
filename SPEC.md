# SPEC.md — JARVIS: Asistente de IA Local para Linux
**Versión:** 1.0  
**Autor:** Gianni Piovesan  
**Stack:** Python · Whisper · Ollama (local) · Claude API (nube) · Piper TTS · PyQt6  
**Plataforma:** CachyOS (Arch Linux) + notebook Linux  
**Metodología:** Spec-Driven Development (SDD)

---

## 1. VISIÓN DEL PROYECTO

Jarvis es un asistente de IA de voz activado por wake word que corre **100% en local** (STT + TTS + LLM base) con escalada inteligente a Claude API cuando se necesita potencia real. El usuario dice "Ey Jarvis", Jarvis escucha, un router decide si el comando es simple (Ollama local) o complejo (Claude API), ejecuta acciones reales en el sistema, y responde con voz natural. Tiene una **UI futurista** tipo orbe robótico que se despliega en la esquina inferior derecha al activarse.

---

## 2. ARQUITECTURA

```
Micrófono
    │
    ▼
[Wake Word Detection]     ← openwakeword (local, siempre escuchando)
    │ "Ey Jarvis" detectado
    ▼
[Audio Capture]           ← pyaudio / sounddevice (graba hasta silencio)
    │
    ▼
[STT — Speech to Text]    ← faster-whisper (local, modelo medium, español)
    │ texto transcripto
    ▼
[LLM Router]              ← clasifica complejidad del comando
    │
    ├─── SIMPLE ──────────→ [Ollama local]
    │                         Llama 3.2 3B (PC con ROCm)
    │                         Llama 3.2 1B (notebook CPU)
    │                         abrir apps, volumen, terminal
    │                         ~0.5s, sin costo API
    │
    └─── COMPLEJO ────────→ [Claude API]
                              claude-haiku  → comandos medios
                              claude-sonnet → código, análisis,
                                             prompts largos,
                                             razonamiento
    │
    ▼
[Tool Dispatcher]         ← ejecuta acciones reales en el sistema
    │ resultado de la acción
    ▼
[Response Generation]     ← LLM activo construye respuesta hablada
    │
    ▼
[TTS — Text to Speech]    ← piper-tts (local, voz español neutro)
    │
    ▼
Respuesta hablada + UI actualizada
```

---

## 3. ESTRUCTURA DE CARPETAS

```
jarvis/
├── SPEC.md
├── CLAUDE.md
├── main.py                    # Entry point
├── config.yaml                # Configuración por entorno (PC / notebook)
├── requirements.txt
│
├── core/
│   ├── wake_word.py           # Detección "Ey Jarvis" con openwakeword
│   ├── audio_capture.py       # Grabación de audio post-wake-word
│   ├── stt.py                 # faster-whisper → texto
│   ├── tts.py                 # piper-tts → audio hablado
│   ├── llm_router.py          # Clasifica complejidad → elige modelo
│   ├── llm_ollama.py          # Cliente Ollama (local)
│   ├── llm_claude.py          # Cliente Claude API (nube)
│   └── dispatcher.py          # Enruta tool_calls a los tools correctos
│
├── tools/                     # Herramientas ejecutables por Jarvis
│   ├── __init__.py            # Registro de todos los tools
│   ├── system.py              # Volumen, brillo, wifi, apagar, reiniciar
│   ├── apps.py                # Abrir/cerrar aplicaciones
│   ├── terminal.py            # Ejecutar comandos bash, abrir terminales
│   ├── files.py               # Leer, mover, buscar archivos
│   ├── browser.py             # Abrir URLs, búsquedas web
│   ├── clipboard.py           # Leer/escribir portapapeles
│   └── notifications.py       # Enviar notificaciones al sistema
│
├── memory/
│   ├── db.py                  # SQLite — memoria persistente entre sesiones
│   ├── context.py             # Gestión del contexto activo de la sesión
│   └── jarvis.db              # Base de datos SQLite (gitignored)
│
└── ui/
    ├── overlay.py             # Ventana PyQt6 futurista (overlay)
    ├── assets/
    │   ├── waveform.py        # Animación de onda de audio en tiempo real
    │   └── styles.qss         # Estilos Qt futuristas
    └── tray.py                # Ícono en system tray
```

---

## 4. COMPONENTES TÉCNICOS

### 4.1 Wake Word Detection
- **Librería:** `openwakeword`
- **Modelo custom:** entrenar con frases "Ey Jarvis" / "Hey Jarvis"
- **Fallback:** modelo "hey_jarvis" pre-entrenado si existe, sino "alexa" como placeholder
- Corre en thread separado, siempre activo con consumo mínimo de CPU

### 4.2 STT — Speech to Text
- **Librería:** `faster-whisper`
- **Modelo:** `medium` (balance velocidad/precisión para español)
- **Idioma forzado:** `es` (español)
- **VAD:** Silero VAD integrado para detectar fin de frase automáticamente
- **Hardware:** CPU en notebook, puede aprovechar ROCm (RX 6600 XT) en PC principal

### 4.3 LLM — Router Híbrido Local + Nube

#### LLM Router (`llm_router.py`)
Analiza el texto transcripto y decide qué modelo usar según la complejidad:

```python
SIMPLE_PATTERNS = [
    "abr", "cerr", "abrir", "cerrar", "subí", "bajá",
    "volumen", "brillo", "wifi", "apagá", "reiniciá",
    "abrí", "qué hora", "screenshot", "bloqueá"
]

def route(text: str) -> Literal["local", "claude_haiku", "claude_sonnet"]:
    text_lower = text.lower()
    # Comandos cortos y simples → local
    if len(text.split()) <= 6 and any(p in text_lower for p in SIMPLE_PATTERNS):
        return "local"
    # Comandos medios → haiku
    if len(text.split()) <= 20:
        return "claude_haiku"
    # Comandos complejos, código, análisis → sonnet
    return "claude_sonnet"
```

#### LLM Local — Ollama (`llm_ollama.py`)
- **Modelo PC:** `llama3.2:3b` — corre con ROCm en RX 6600 XT, ~0.5s latencia
- **Modelo notebook:** `llama3.2:1b` — corre en CPU, ~1.5s latencia
- **Tool use:** implementado manualmente con JSON parsing (Ollama no tiene tool use nativo en todos los modelos)
- **Uso:** comandos simples del sistema, respuestas rápidas sin razonamiento complejo

#### LLM Nube — Claude API (`llm_claude.py`)
- **claude-haiku-4-5:** comandos medios, respuestas conversacionales
- **claude-sonnet-4-6:** razonamiento complejo, escritura de código, prompts para Claude Code, análisis de archivos
- **Tool use nativo** con JSON schema completo
- **Historial:** últimas N interacciones incluidas en cada llamada

### 4.4 Tool Dispatcher
Recibe `tool_calls` de Claude y ejecuta la función correspondiente:

```python
TOOL_REGISTRY = {
    "run_command": tools.terminal.run_command,
    "open_app": tools.apps.open_app,
    "close_app": tools.apps.close_app,
    "open_terminal": tools.terminal.open_terminal,
    "set_volume": tools.system.set_volume,
    "set_brightness": tools.system.set_brightness,
    "get_wifi_status": tools.system.get_wifi_status,
    "toggle_wifi": tools.system.toggle_wifi,
    "open_url": tools.browser.open_url,
    "web_search": tools.browser.web_search,
    "read_file": tools.files.read_file,
    "list_directory": tools.files.list_directory,
    "move_file": tools.files.move_file,
    "get_clipboard": tools.clipboard.get_clipboard,
    "set_clipboard": tools.clipboard.set_clipboard,
    "send_notification": tools.notifications.send_notification,
    "shutdown": tools.system.shutdown,
    "reboot": tools.system.reboot,
    "lock_screen": tools.system.lock_screen,
    "get_system_info": tools.system.get_system_info,
    "take_screenshot": tools.system.take_screenshot,
}
```

### 4.5 TTS — Text to Speech
- **Librería:** `piper-tts`
- **Voz:** `es_ES-davefx-high` o similar español masculino natural
- **Output:** reproducción directa vía `sounddevice` o `aplay`
- **Streaming:** generar y reproducir por chunks para reducir latencia

### 4.6 Memoria Persistente (SQLite)
```sql
-- Historial de conversaciones
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    role TEXT,           -- 'user' | 'assistant'
    content TEXT,
    session_id TEXT
);

-- Hechos recordados sobre el usuario
CREATE TABLE memory_facts (
    id INTEGER PRIMARY KEY,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    category TEXT,       -- 'preference' | 'fact' | 'instruction'
    content TEXT,
    active BOOLEAN DEFAULT 1
);

-- Log de acciones ejecutadas
CREATE TABLE action_log (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    tool_name TEXT,
    parameters TEXT,     -- JSON
    result TEXT,
    success BOOLEAN
);
```

---

## 5. HERRAMIENTAS (TOOLS)

### system.py
| Tool | Descripción | Parámetros |
|------|-------------|------------|
| `set_volume` | Ajusta volumen del sistema | `level: int (0-100)` |
| `set_brightness` | Ajusta brillo de pantalla | `level: int (0-100)` |
| `get_wifi_status` | Estado de la red wifi | — |
| `toggle_wifi` | Activa/desactiva wifi | `enable: bool` |
| `get_system_info` | CPU, RAM, disco, uptime | — |
| `take_screenshot` | Captura pantalla | `region: str optional` |
| `shutdown` | Apaga el sistema | `delay_seconds: int` |
| `reboot` | Reinicia el sistema | `delay_seconds: int` |
| `lock_screen` | Bloquea la sesión | — |

### apps.py
| Tool | Descripción | Parámetros |
|------|-------------|------------|
| `open_app` | Abre una aplicación | `name: str` |
| `close_app` | Cierra una aplicación | `name: str` |
| `list_windows` | Lista ventanas abiertas | — |
| `focus_window` | Enfoca ventana por nombre | `name: str` |

### terminal.py
| Tool | Descripción | Parámetros |
|------|-------------|------------|
| `run_command` | Ejecuta comando bash | `command: str, sudo: bool` |
| `open_terminal` | Abre terminal nueva | `cwd: str optional` |
| `run_script` | Ejecuta un script .sh | `path: str` |

### browser.py
| Tool | Descripción | Parámetros |
|------|-------------|------------|
| `open_url` | Abre URL en navegador | `url: str` |
| `web_search` | Busca en DuckDuckGo | `query: str` |

### files.py
| Tool | Descripción | Parámetros |
|------|-------------|------------|
| `read_file` | Lee contenido de archivo | `path: str` |
| `list_directory` | Lista directorio | `path: str` |
| `move_file` | Mueve archivo | `src: str, dst: str` |
| `delete_file` | Elimina archivo | `path: str` |
| `create_file` | Crea archivo con contenido | `path: str, content: str` |

---

## 6. UI — OVERLAY FUTURISTA

### Concepto visual
Una **ventana overlay** que permanece oculta y se **despliega desde la esquina inferior derecha** al detectar el wake word. Estética: HUD de ciencia ficción, fondo negro semitransparente con bordes cyan/verde neón, animaciones de escaneo y waveform en tiempo real.

### Estados de la UI
```
IDLE        → Ventana oculta / ícono tray minimalista
LISTENING   → Se despliega overlay: animación de onda de audio activa
PROCESSING  → Indicador de "pensando" (spinner neón giratorio)
SPEAKING    → Texto de respuesta aparece letra por letra (typewriter effect)
ERROR       → Borde rojo parpadeante + mensaje de error
```

### Componentes visuales
- **Header:** `JARVIS v1.0` con fecha/hora en tiempo real
- **Waveform:** Visualización de onda de audio mientras escucha
- **Transcripción:** Texto STT aparece en tiempo real
- **Respuesta:** Texto de Jarvis con efecto typewriter
- **Status bar:** Estado actual (ESCUCHANDO / PROCESANDO / HABLANDO)
- **Historial mini:** Últimas 3 interacciones visibles

### Paleta de colores
```python
COLORS = {
    "bg": "#050a0e",           # Negro profundo
    "bg_overlay": "#0a1520cc", # Fondo semitransparente
    "primary": "#00d4ff",      # Cyan neón
    "secondary": "#00ff88",    # Verde neón
    "accent": "#ff6b35",       # Naranja acento
    "text": "#e0f0ff",         # Blanco azulado
    "text_dim": "#4a7a9b",     # Gris azulado
    "border": "#1a4060",       # Borde sutil
    "error": "#ff3366",        # Rojo error
}
```

### Animaciones
- **Slide-in:** La ventana se desliza desde abajo-derecha (300ms ease-out)
- **Scanline:** Efecto de línea de escaneo horizontal periódica
- **Pulse:** El borde principal pulsa al escuchar
- **Waveform:** Barras de audio animadas en tiempo real con PyQtGraph o canvas

---

## 7. SISTEMA DE PERSONALIDAD (SYSTEM PROMPT)

```
Sos Jarvis, un asistente de IA personal corriendo en la PC de Gianni.
Sos conciso, directo y eficiente — como el Jarvis de Iron Man.
Respondés en español rioplatense.
Nunca decís frases innecesarias. Vas al punto.
Cuando ejecutás una acción, confirmás brevemente qué hiciste.
Si algo no podés hacer, lo decís directo sin rodeos.
Tenés acceso completo al sistema. Usás las herramientas disponibles sin dudar.
Recordás el contexto de conversaciones anteriores.
```

---

## 8. CONFIGURACIÓN (config.yaml)

```yaml
# Detectado automáticamente por hostname
profiles:
  pc_principal:                  # CachyOS desktop
    hostname: "cachyos-pc"
    whisper_device: "rocm"       # AMD RX 6600 XT
    whisper_model: "medium"
    ollama_model: "llama3.2:3b"  # ROCm accelerated
    
  notebook:
    hostname: "cachyos-notebook"
    whisper_device: "cpu"
    whisper_model: "small"
    ollama_model: "llama3.2:1b"  # Liviano para CPU

# Común a todos
wake_word:
  model_path: "models/hey_jarvis.onnx"
  threshold: 0.7

llm:
  # Router: umbral de palabras para escalar a nube
  simple_word_limit: 6
  medium_word_limit: 20
  # Ollama
  ollama_url: "http://localhost:11434"
  # Claude API
  claude_haiku: "claude-haiku-4-5-20251001"
  claude_sonnet: "claude-sonnet-4-6"
  max_tokens: 500
  history_turns: 10
  
tts:
  voice: "es_ES-davefx-high"
  speed: 1.1
  
memory:
  db_path: "memory/jarvis.db"
  max_history_turns: 50
  
ui:
  position: "bottom-right"
  orb_size: 88
  opacity: 0.92
```

---

## 9. INSTALACIÓN Y DEPENDENCIAS

```bash
# requirements.txt
faster-whisper>=1.0.0
openwakeword>=0.6.0
piper-tts>=1.2.0
pyaudio>=0.2.14
sounddevice>=0.4.6
anthropic>=0.34.0
ollama>=0.3.0          # Cliente Ollama Python
PyQt6>=6.6.0
PyQtGraph>=0.13.0
pyyaml>=6.0
numpy>=1.24.0
loguru>=0.7.0
```

```bash
# Setup inicial
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Descargar modelo de voz piper
python scripts/download_voice.py es_ES-davefx-high

# Entrenar / descargar wake word model
python scripts/setup_wake_word.py

# Primer arranque
python main.py
```

---

## 10. FLUJO PRINCIPAL (main.py)

```python
async def main():
    config = load_config()
    memory = MemoryDB(config.memory.db_path)
    ui = JarvisOverlay(config.ui)
    tts = TTSEngine(config.tts)
    stt = STTEngine(config.whisper)
    router = LLMRouter(config.llm)
    ollama = OllamaClient(config.llm)
    claude = ClaudeClient(config.llm)
    dispatcher = ToolDispatcher(TOOL_REGISTRY)
    
    ui.start()
    
    async for audio_chunk in wake_word_stream():
        if wake_word_detected(audio_chunk):
            await handle_interaction(ui, stt, router, ollama, claude, dispatcher, tts, memory)

async def handle_interaction(ui, stt, router, ollama, claude, dispatcher, tts, memory):
    ui.set_state("LISTENING")
    audio = await capture_until_silence()
    
    ui.set_state("PROCESSING")
    text = await stt.transcribe(audio)
    ui.show_transcription(text)
    
    # Router decide qué LLM usar
    target = router.route(text)       # "local" | "claude_haiku" | "claude_sonnet"
    llm = ollama if target == "local" else claude
    
    response = await llm.chat(text, model=target)
    
    if response.tool_calls:
        for tool_call in response.tool_calls:
            result = await dispatcher.execute(tool_call)
            response = await llm.complete_with_result(result)
    
    ui.set_state("SPEAKING")
    ui.show_response(response.text)
    await tts.speak(response.text)
    
    memory.save_turn("user", text, model_used=target)
    memory.save_turn("assistant", response.text)
    
    await asyncio.sleep(5)
    ui.set_state("IDLE")
```

---

## 11. CLAUDE.md (para Claude Code)

```markdown
# CLAUDE.md — Jarvis Assistant

## Stack
- Python 3.12+, asyncio
- faster-whisper para STT
- openwakeword para wake word detection
- Ollama (local) para comandos simples — llama3.2:3b / 1b
- Claude API (anthropic SDK) para comandos complejos — haiku / sonnet
- LLM Router: clasifica automáticamente por complejidad
- piper-tts para TTS
- PyQt6 para UI overlay (orbe robótico animado)
- SQLite para memoria persistente

## Convenciones
- Async/await en todo el pipeline de audio
- Cada tool retorna siempre: `{ success: bool, result: any, error: str | None }`
- Logs con loguru
- Config cargada de config.yaml con perfil auto-detectado por hostname
- No hardcodear paths, todo relativo al project root
- `model_used` guardado en SQLite para analizar qué % va a local vs nube

## Comandos
- `python main.py` → arrancar Jarvis
- `python main.py --no-ui` → modo terminal headless
- `python main.py --test-tts "Hola Gianni"` → test de voz
- `python main.py --test-stt` → test de transcripción
- `python main.py --force-local` → forzar Ollama para todo
- `python main.py --force-claude` → forzar Claude para todo
- `python scripts/train_wake_word.py` → entrenar wake word custom

## Variables de entorno requeridas
- ANTHROPIC_API_KEY
- OLLAMA_URL (opcional, default: http://localhost:11434)
```

---

## 12. ROADMAP

### MVP (v1.0)
- [x] Spec completo
- [ ] Wake word "Ey Jarvis" funcionando
- [ ] STT con faster-whisper en español
- [ ] Ollama local con llama3.2 para comandos simples
- [ ] Claude API haiku/sonnet para comandos complejos
- [ ] LLM Router básico (por longitud + keywords)
- [ ] Tool use básico (run_command, open_app, set_volume)
- [ ] TTS con piper
- [ ] UI overlay con orbe robótico animado
- [ ] Memoria SQLite básica

### v1.1
- [ ] UI orbe con todos los estados animados (idle/listening/processing/speaking)
- [ ] Tool set completo (todos los tools del spec)
- [ ] Config multi-perfil PC/notebook con modelo Ollama diferente
- [ ] Wake word entrenado custom con "Ey Jarvis"
- [ ] Router mejorado con clasificador ML liviano

### v1.2
- [ ] ROCm acceleration para STT y Ollama en PC principal
- [ ] Modo "conversación continua" (no requiere re-trigger)
- [ ] Integración con OpenGravity / BrescoPack tools
- [ ] Plugin system para agregar tools custom fácilmente
- [ ] Stats de uso: % local vs nube, latencia promedio por modelo

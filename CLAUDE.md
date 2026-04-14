# CLAUDE.md — Jarvis Assistant

## Stack

- Python 3.12+, asyncio throughout
- **STT:** faster-whisper (local, Spanish, medium model on PC / small on notebook)
- **Wake word:** openwakeword with custom "Ey Jarvis" model
- **LLM local:** Ollama — llama3.2:3b (PC, ROCm) / llama3.2:1b (notebook, CPU)
- **LLM cloud:** Claude API (anthropic SDK) — haiku for medium commands, sonnet for complex
- **LLM cloud alt:** Google Gemini — gemini-2.5-flash (activated via --force-gemini only)
- **LLM Router:** classifies command complexity automatically — local → haiku → sonnet
- **TTS:** edge-tts (Microsoft neural TTS, voice es-AR-TomasNeural)
- **UI:** PyQt6 overlay — futuristic robot orb, bottom-right corner
- **Memory:** SQLite (conversations, memory_facts, action_log)
- **HTTP:** httpx.AsyncClient for Ollama; anthropic SDK for Claude; google-genai for Gemini

## Architecture

Three LLM providers all implement the `LLMProvider` Protocol (core/protocols.py):
- `OllamaClient` — local, httpx async, manual JSON tool parsing
- `ClaudeClient` — cloud, anthropic SDK, native tool_use blocks
- `GeminiClient` — cloud, google-genai sync wrapped in asyncio.to_thread

Router output → LLM_MAP dispatch in main.py:
```python
LLM_MAP = {
    "local":         ollama,
    "claude_haiku":  claude,
    "claude_sonnet": claude,
    "gemini_flash":  gemini,
}
```

## AudioCapture

`core/audio_capture.py` — sounddevice-based mic recording with adaptive silence detection.

Constructor params:
- `silence_duration` (default 1.5s) — how long to wait in silence before stopping
- `max_duration` (default 10s) — safety ceiling
- `calibration_time` (default 0.3s) — time to measure ambient noise before applying threshold

No `silence_threshold` param — the threshold is computed adaptively (2× ambient RMS, minimum 0.005).
Returned bytes are int16 mono 16 kHz PCM — directly consumable by faster-whisper after float32 conversion.

## Conventions

- Async/await everywhere in the audio pipeline
- Every tool function returns exactly: `{"success": bool, "result": Any, "error": str | None}`
- Logs with `loguru` — never `print()` or `logging`
- Config loaded from `config.yaml`, profile auto-detected by `socket.gethostname()`
- No hardcoded paths — everything relative to project root
- `model_used` saved in SQLite for local vs cloud usage stats
- No pydantic — stdlib `dataclasses` only

## CLI Commands

```bash
python main.py                          # start Jarvis (full mode)
python main.py --no-ui                  # headless terminal mode
python main.py --test-tts "Hola"        # test TTS voice
python main.py --test-stt               # test STT transcription
python main.py --force-local            # route ALL commands to Ollama
python main.py --force-claude           # route ALL commands to claude-sonnet
python main.py --force-gemini           # route ALL commands to gemini-flash
python main.py --trigger                # send SIGUSR1 to running Jarvis (keyboard trigger)
python main.py --listen-once            # capture audio once, process, and exit (no wake word)
python scripts/train_wake_word.py       # train custom wake word model
```

## Keyboard Shortcut (Super+J)

Jarvis supports a global hotkey trigger as the PRIMARY activation method — more reliable than the wake word.

**How it works:**
1. On startup, Jarvis writes its PID to `/tmp/jarvis.pid`
2. `scripts/trigger.sh` reads that PID and sends `SIGUSR1`
3. Jarvis handles SIGUSR1 by immediately triggering `_handle_wake_word()` (skips wake word detection)

**Hyprland config** — add to `~/.config/hypr/hyprland.conf`:
```
bind = SUPER, J, exec, /home/giannip/projects/Jarvis/scripts/trigger.sh
```

Or copy/symlink the script to your Hyprland scripts folder:
```bash
ln -s /home/giannip/projects/Jarvis/scripts/trigger.sh ~/.config/hypr/scripts/jarvis-trigger.sh
```

Wake word stays active as a secondary/bonus trigger. Threshold is set to 0.5 in `config.yaml`.

## Hyprland Window Rules

`scripts/hyprland-rules.conf` is loaded once at overlay init via `hyprctl keyword source`.
It sets: float, pin, noborder, noshadow, nofocus, position (bottom-right), size.
No manual `movewindowpixel` dispatch — rules are applied by the compositor before render.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes (for Claude) | Anthropic API key — read by SDK automatically |
| `GEMINI_API_KEY` | Yes (for --force-gemini) | Google Gemini API key |
| `OLLAMA_URL` | No | Override Ollama URL (default: http://localhost:11434) |

## Testing

```bash
uv run pytest                           # all tests
uv run pytest tests/test_llm_router.py  # single module
uv run pytest -k "router"               # by keyword
uv run pytest --cov=core                # with coverage
```

Tests use:
- `respx` to mock httpx calls (Ollama)
- `unittest.mock.AsyncMock` for Claude SDK
- `asyncio.to_thread` patching for Gemini
- Real SQLite in-memory for MemoryDB tests
- Fixture YAML for config tests

No test ever makes a real HTTP call.

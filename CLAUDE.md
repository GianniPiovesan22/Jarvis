# CLAUDE.md — Jarvis Assistant

## Stack

- Python 3.12+, asyncio throughout
- **STT:** faster-whisper (local, Spanish, medium model on PC / small on notebook)
- **Wake word:** openwakeword with custom "Ey Jarvis" model
- **LLM local:** Ollama — llama3.2:3b (PC, ROCm) / llama3.2:1b (notebook, CPU)
- **LLM cloud:** Claude API (anthropic SDK) — haiku for medium commands, sonnet for complex
- **LLM cloud alt:** Google Gemini — gemini-2.0-flash (activated via --force-gemini only)
- **LLM Router:** classifies command complexity automatically — local → haiku → sonnet
- **TTS:** piper-tts (local, Spanish voice es_ES-davefx-high)
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
python scripts/train_wake_word.py       # train custom wake word model
```

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

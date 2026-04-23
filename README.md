# Zara Neural Command Center

> Advanced AI assistant with real-time React dashboard, live screen capture, pygame orb streaming, and full desktop control.

---

## Project Structure

```
Friday/
├── main.py                  ← Main event loop (boot here)
├── zara_core.py             ← LLM brain (Groq + Llama 3.3 70B)
├── ws_bridge.py             ← WebSocket server → React UI  ★ UPDATED
├── orb_bridge.py            ← Pygame orb renderer → React UI  ★ NEW
├── apply_main_patch.py      ← One-time patch script  ★ NEW
│
├── action_engine.py         ← Execute system actions
├── agent_orchestrator.py    ← Multi-agent teams
├── bg_speaker_detector.py   ← Direct vs background speech
├── clipboard_engine.py      ← Clipboard read/process
├── engagement_engine.py     ← Idle proactive prompts
├── free_web_tools.py        ← 40+ free API integrations
├── gender_detector.py       ← Voice/text gender detection
├── learning_engine.py       ← Post-mortem code analysis
├── local_ears.py            ← Mic input + Whisper STT
├── local_voice.py           ← Edge-TTS + ElevenLabs TTS
├── memory_vault.py          ← SQLite + ChromaDB memory
├── messaging_agent.py       ← WhatsApp/Telegram/etc.
├── output_router.py         ← Route LLM output to voice/visual/action
├── proactive_engine.py      ← Background RIA synthesis
├── secure_sandbox.py        ← AST-based code safety
├── session_manager.py       ← Session persistence
├── smart_router.py          ← Groq → Ollama → cache fallback
├── state.py                 ← Shared multiprocess state
├── ui_engine.py             ← Pygame desktop UI
├── web_agent.py             ← Playwright web browsing
├── zara_eyes.py             ← Vision / screen analysis
├── zara_pipeline.py         ← Audio pipeline
├── zara_window_manager.py   ← Win32 window control
│
└── zara-dashboard/          ← React + Electron UI
    ├── src/
    │   ├── App.jsx          ← Full dashboard  ★ UPDATED
    │   ├── index.js         ← Entry point
    │   ├── components/
    │   │   ├── NeuralSphere.jsx  ← WebGL orb (canvas fallback)
    │   │   └── TitleBar.jsx
    │   └── store/
    │       └── zaraStore.js ← Zustand store  ★ UPDATED
    └── package.json
```

---

## Quick Start

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
# Windows extras:
pip install pywin32 websockets psutil pillow
```

### 2. Set Environment Variables

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_api_key_here
DEEPGRAM_API_KEY=your_deepgram_key       # optional
ELEVENLABS_API_KEY=your_eleven_key       # optional
```

### 3. Apply the One-Time Patch

```bash
python apply_main_patch.py
```

This wires the pygame orb bridge and orb state sync into `main.py` and `ws_bridge.py` automatically.

### 4. Start Zara Backend

```bash
python main.py
```

### 5. Start React Dashboard

```bash
cd zara-dashboard
npm install
npm start
# Opens at http://localhost:3000
```

### 6. Run as Desktop App (Electron)

```bash
cd zara-dashboard
npm run electron
```

---

## What's New

### ★ Live Window List (Windows Panel)
The Windows panel now shows **real open and minimized windows** from your desktop, refreshed every 5 seconds via the WebSocket bridge. No more fake static data.

- Click **📷** to capture any window into the Zara UI
- Click **🔍** to ask Zara to analyze and inspect a window
- Click **⊞** / **⊟** to focus or minimize directly from the dashboard
- Use **Full Desktop** to capture the entire screen

### ★ Screen Capture & Window Viewer
Any app window (Spotify, Chrome, VS Code, etc.) can be pulled directly into the Zara UI:

1. Go to the **Windows** tab
2. Click **📷** next to any window, or type: *"Show me Spotify"*
3. A live 10fps feed of that window appears in the panel
4. Click **🔍 Analyze** — Zara inspects it and reports what she sees

Zara can detect errors, describe UI state, and suggest fixes based on what's visible.

### ★ Pygame Orb Streaming
The animated neural orb from `ui_engine.py` (pygame) is now rendered headlessly and streamed as base64 PNG frames to the React UI at 15fps.

- The orb in the **Windows** panel mirrors the exact orb from `main.py`
- Color and animation state stay perfectly in sync with Zara's actual state
- Falls back gracefully to the WebGL NeuralSphere if the backend is offline

### ★ Real Memory Stats
The **Memory** panel now shows live data from `memory_vault.py` — actual stored memory count and recent memories, updated every 30 seconds.

### ★ Fixed: All Info Now Fetched
Previously the React UI used hardcoded demo data for:
- Window list → now live from `win32gui` via `ws_bridge.get_windows()`
- Memory stats → now live from `memory_vault` via `_memory_stats_loop()`
- API health → was simulated, now set correctly from `main.py` on boot
- System metrics → was simulated, now live from `psutil` every 2.5s

---

## Architecture

```
main.py
  │
  ├── ws_bridge.start_bridge()     → WebSocket :8765
  │     ├── _metrics_loop()        → CPU/RAM/GPU/disk every 2.5s
  │     ├── _windows_loop()        → Live window list every 5s
  │     ├── _orb_loop()            → Pygame orb frames at 15fps
  │     ├── _screen_capture_loop() → Screen/window frames at 10fps (on demand)
  │     └── _memory_stats_loop()   → Memory vault stats every 30s
  │
  ├── orb_bridge.start_orb_bridge()
  │     └── Headless pygame surface → renders orb → base64 PNG → ws_bridge
  │
  └── NeuralVisualizer (pygame desktop window) — unchanged
        └── Same orb, same state, now also mirrored in React
```

```
React (localhost:3000)
  │
  └── zaraStore.js (Zustand)
        └── connectWsBridge() → ws://localhost:8765
              ├── snapshot     → hydrates all state on connect
              ├── state        → ZaraState, gender, honorific
              ├── metrics      → CPU/RAM/GPU/disk
              ├── message      → conversation log
              ├── transcript   → live/final speech text
              ├── windows      → open + minimized window list
              ├── orb_frame    → base64 PNG from pygame
              ├── screen_frame → base64 JPEG screen capture
              └── memory_stats → vault counts + recent memories
```

---

## WebSocket Protocol

### Server → Client

| Type | Payload | Description |
|------|---------|-------------|
| `snapshot` | Full state object | Sent once on connect |
| `state` | `{ zaraState, honorific, gender }` | State changes |
| `metrics` | `{ cpu, ram, gpu, disk }` | Every 2.5s |
| `message` | `{ role, text }` | Conversation |
| `transcript` | `{ text, live }` | Speech transcript |
| `windows` | `{ open: [...], minimized: [...] }` | Every 5s |
| `orb_frame` | `{ frame: "<base64 PNG>" }` | ~15fps |
| `screen_frame` | `{ frame: "<base64 JPEG>", title }` | ~10fps when active |
| `memory_stats` | `{ stored, semantic, recent }` | Every 30s |
| `api_health` | `{ groq, deepgram, ollama, elevenlabs }` | On change |
| `volume` | `{ level, muted }` | On change |
| `speaker` | `{ context }` | On change |

### Client → Server

| Type | Fields | Description |
|------|--------|-------------|
| `command` | `text` | Send voice command to Zara |
| `volume` | `level` | Set system volume (0–100) |
| `gender` | `value` | Set honorific (male/female/reset) |
| `capture_screen` | — | Start full desktop capture |
| `capture_window` | `title` | Start capturing specific window |
| `stop_capture` | — | Stop capture stream |
| `get_windows` | — | Force window list refresh |
| `window_action` | `hwnd, action` | Focus/minimize/restore/close |
| `bg_detection` | `enabled` | Toggle background speaker detection |

---

## Dashboard Panels

| Panel | Live Data | Description |
|-------|-----------|-------------|
| **Intel** | ✓ Backend | State, metrics, volume, speaker context, conversation |
| **Windows** | ✓ Backend | Live open/minimized windows, screen capture, orb viewer |
| **Memory** | ✓ Backend | Real memory vault stats and recent memories |
| **Claude** | Static | All 74 capability categories (expandable) |
| **Tools** | ✓ Backend | Sends real commands via WebSocket |
| **Config** | ✓ Backend | Gender, honorific, API health, toggles |

---

## Capabilities (74 total)

| Category | Count | Highlights |
|----------|-------|------------|
| Reasoning & Analysis | 7 | Multi-step logic, debugging, statistics |
| Code & Engineering | 10 | 40+ languages, security analysis, test writing |
| Web & Research | 10 | Playwright, DuckDuckGo, 40+ free APIs |
| Vision & Multimodal | 8 | Screen OCR, error detection, Moondream vision |
| Writing & Communication | 10 | 100+ languages, docs, email, social copy |
| Math & Science | 7 | Calculus, ML guidance, engineering calcs |
| Memory & Context | 7 | SQLite vault, ChromaDB, session persistence |
| System & Automation | 9 | File ops, sandboxed scripts, window management |
| Messaging | 6 | WhatsApp/Telegram/Discord/Slack with confirmation |

---

## Build EXE

```bash
cd zara-dashboard
npm run dist
# Output: dist/Zara Setup 2.0.0.exe
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Windows panel shows no windows | Ensure backend is running; `pip install pywin32` |
| Orb not showing in Windows tab | Run `python apply_main_patch.py`, restart backend |
| `ws_bridge` import error | `pip install websockets psutil` |
| Screen capture is black | Some DRM-protected apps block capture; use full desktop mode |
| React can't connect to backend | Check firewall allows `localhost:8765`; backend must be running first |
| `PIL` not found | `pip install pillow` |

---

## Requirements Summary

```
Python 3.10+
pygame>=2.6.0
websockets>=12.0
psutil>=5.9.0
Pillow>=10.0.0
pywin32>=306          # Windows only — for live window list
requests>=2.31.0
edge-tts>=6.0.0
faster-whisper>=1.0.0
groq / GROQ_API_KEY   # Required for LLM
```

React: Node 18+, npm 9+

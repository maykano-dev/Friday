# Zara Neural Command Center — React + Electron Dashboard

## Project Structure

```
zara-dashboard/
├── electron/
│   ├── main.js          ← Electron main process (window, tray, backend spawn)
│   └── preload.js       ← IPC bridge (secure context isolation)
├── src/
│   ├── App.jsx          ← Full dashboard layout + all panels
│   ├── index.js         ← React entry point
│   ├── components/
│   │   ├── NeuralSphere.jsx  ← 3D animated WebGL sphere
│   │   └── TitleBar.jsx      ← Frameless window titlebar
│   └── store/
│       └── zaraStore.js      ← Global Zustand state
├── public/
│   └── index.html
└── package.json
```

---

## Quick Start (Browser Dev Mode)

```bash
cd zara-dashboard
npm install
npm start
# Opens at http://localhost:3000
```

---

## Run as Desktop App (Electron)

```bash
npm install
npm run electron
# Starts React dev server + opens Electron window
```

---

## Build EXE (Windows)

```bash
# 1. Install dependencies
npm install

# 2. Build React app + package as Windows installer
npm run dist

# Output: dist/Zara Setup 2.0.0.exe
# Silent install, system tray, no console window
```

The EXE will:
- Install Zara as a desktop app
- Add a system tray icon (double-click to open)
- Auto-start the Python backend (`main.py`) on launch
- Run frameless with custom titlebar
- Support "Always on Top" mode
- Package the Python backend files from `../` (parent directory)

---

## Features

### Dashboard Panels

| Panel | Contents |
|---|---|
| **Intel** | Zara state, volume slider, speaker detection, system metrics, conversation log |
| **Windows** | Active windows, minimized-to-taskbar list, window commands |
| **Memory** | Memory vault stats, recent memories, semantic search count |
| **Claude** | All 70+ Claude capabilities organized by category |
| **Tools** | Web research, messaging, system tools, voice command reference |
| **Config** | Gender/honorific, API health, always-on-top, media ducking toggles |

### Key Capabilities Built Into Dashboard

- **3D Neural Sphere** — color-shifts per state (blue=standby, red=listening, cyan=thinking, green=talking, amber=executing)
- **Silent Volume Control** — slider sends silent pycaw commands to backend, no Windows OSD
- **Background Speaker Detection** — live indicator showing direct vs background speech
- **Message Confirmation Dialog** — shows app, recipient, and full message before sending
- **Gender Detection** — updates honorific badge live from conversation
- **Window Manager** — separate lists for active and minimized-to-taskbar windows
- **Live Transcript** — rolling 3-line display at bottom
- **System Metrics** — CPU/RAM/GPU/Disk with color thresholds

---

## Backend Communication (Electron ↔ Python)

The Electron main process spawns `main.py` with `windowsHide: true` (no console popup).

React → Backend: `window.electron.sendCommand(text)` → writes JSON to stdin
Backend → React: stdout lines emitted as `backend:log` IPC events

For real integration, modify `main.py` to accept stdin JSON commands:

```python
import sys, json, threading

def stdin_listener():
    for line in sys.stdin:
        try:
            cmd = json.loads(line.strip())
            if cmd.get('type') == 'command':
                response = generate_response(cmd['text'])
                print(json.dumps({'type': 'response', 'text': response}), flush=True)
        except Exception:
            pass

threading.Thread(target=stdin_listener, daemon=True).start()
```

---

## Claude's Capabilities (All Available in Zara)

### Reasoning & Analysis (7)
- Multi-step logical reasoning and deduction
- Hypothesis testing and validation  
- Root cause analysis and debugging
- Pattern recognition across domains
- Causal inference and argument evaluation
- Mathematical proofs and derivations
- Statistical analysis and interpretation

### Code & Engineering (10)
- Code generation in 40+ languages
- Full-stack app architecture
- Code review, refactoring, optimization
- Bug detection and autonomous fixing
- Unit test / integration test writing
- API design and documentation
- Database schema design
- Security vulnerability analysis
- Shell scripts and automation
- Regex, parsing, data transformation

### Web & Research (10)
- Real-time web search (DuckDuckGo, Wikipedia)
- Multi-source research synthesis
- Stealth web browsing (Playwright)
- Form filling and web automation
- News aggregation (HN, DEV.to)
- Weather, crypto, exchange rates
- GitHub, NPM, PyPI lookups
- CVE security database
- Country/university/holiday data
- URL shortening and QR codes

### Vision & Multimodal (8)
- Screen reading and OCR
- Error detection from screenshots
- Vision-guided UI automation
- Image analysis and description
- Document and PDF understanding
- Code screenshot reading
- Camera feed analysis
- Visual context for task assistance

### Writing & Communication (10)
- Long-form creative writing
- Technical documentation
- Email and message drafting
- Summarization at any length
- Translation (100+ languages)
- Tone and style adaptation
- Proofreading and editing
- Report and proposal writing
- Social media copy
- Persuasive writing

### Math & Science (7)
- Algebra, calculus, linear algebra
- Statistics and probability
- Physics, chemistry, biology
- Unit conversion
- Data science and ML guidance
- Symbolic computation
- Engineering calculations

### Memory & Context (7)
- SQLite long-term memory vault
- ChromaDB semantic search
- Keyword-extracted indexing
- Session persistence
- Proactive suggestions
- Learning from failures
- User preference tracking

### System & Automation (9)
- File creation, editing, organization
- Script execution with sandboxing
- App launching and window management
- Multi-agent orchestration
- Background task management
- Silent volume control (pycaw)
- Media playback control
- Screenshot capture
- Clipboard processing

### Messaging (6)
- WhatsApp with confirmation
- Telegram, Discord, Slack, Teams
- Gmail / Outlook email
- SMS via Phone Link
- Universal UI automation
- Pre-send confirmation dialog

**Total: 74 capabilities across 9 categories**

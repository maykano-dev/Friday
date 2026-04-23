import { create } from 'zustand';

export const ZARA_STATES = ['STANDBY', 'LISTENING', 'THINKING', 'TALKING', 'EXECUTING'];

// Add history for metrics charting
const initialMetrics = { 
  cpu: 0, ram: 0, gpu: 0, disk: 0,
  history: [] // Last 30 data points
};

export const useZaraStore = create((set, get) => ({
  // ... existing state ...
  zaraState: 'STANDBY',
  setZaraState: (s) => set({ zaraState: s }),

  // Gender / Honorific
  gender: 'unknown',
  honorific: 'Sir',
  setGender: (g) => {
    const h = g === 'female' ? "Ma'am" : 'Sir';
    set({ gender: g, honorific: h });
  },
  resetGender: () => set({ gender: 'unknown', honorific: 'Sir' }),

  // Volume
  volume: 60,
  isMuted: false,
  setVolume: (v) => set({ volume: Math.max(0, Math.min(100, v)) }),
  setMuted: (m) => set({ isMuted: m }),

  // Mic
  micActive: false,
  setMicActive: (v) => set({ micActive: v }),

  // Transcripts
  liveTranscript: '',
  transcriptHistory: [],
  setLiveTranscript: (t) => set({ liveTranscript: t }),
  pushTranscript: (t) => set((s) => ({
    transcriptHistory: [...s.transcriptHistory.slice(-49), t],
    liveTranscript: t,
  })),

  // Conversation log
  conversation: [
    { id: 1, role: 'zara', text: 'Neural core initialized. Ready.', ts: Date.now() },
  ],
  addMessage: (role, text) => set((s) => ({
    conversation: [...s.conversation.slice(-99), {
      id: Date.now(), role, text, ts: Date.now(),
    }],
  })),

  // Background speaker detection
  speakerContext: 'none',
  bgDetectionEnabled: true,
  setSpeakerContext: (c) => set({ speakerContext: c }),
  setBgDetectionEnabled: (v) => set({ bgDetectionEnabled: v }),

  // Updated Metrics Logic
  metrics: initialMetrics,
  setMetrics: (m) => set((state) => {
    const newHistory = [...state.metrics.history, { ts: Date.now(), ...m }].slice(-30);
    return { metrics: { ...m, history: newHistory } };
  }),

  // Add a "Pulse" state for UI effects
  uiPulse: 1.0,
  triggerPulse: () => {
    set({ uiPulse: 2.0 });
    setTimeout(() => set({ uiPulse: 1.0 }), 400);
  },

  // ── Windows (LIVE from backend) ──────────────────────────────────────────
  openWindows: [],
  minimizedWindows: [],
  setWindows: (open, minimized) => set({ openWindows: open, minimizedWindows: minimized }),

  // ── Orb frame (pygame rendered, streamed from backend) ───────────────────
  orbFrame: null,    // base64 PNG
  setOrbFrame: (f) => set({ orbFrame: f }),

  // ── Screen/window capture ────────────────────────────────────────────────
  screenFrame: null,          // base64 JPEG
  screenFrameTitle: null,     // which window is being shown
  captureActive: false,
  setScreenFrame: (f, title) => set({ screenFrame: f, screenFrameTitle: title }),
  setCaptureActive: (v) => set({ captureActive: v }),

  // ── Memory ───────────────────────────────────────────────────────────────
  memoryStats: { stored: 0, semantic: 0 },
  recentMemories: [],
  setMemoryStats: (s) => set({ memoryStats: s }),
  setRecentMemories: (m) => set({ recentMemories: m }),

  // API health
  apiHealth: {
    groq: 'checking',
    ollama: 'offline',
    deepgram: 'checking',
    elevenlabs: 'offline',
  },
  setApiHealth: (updates) => set((s) => ({ apiHealth: { ...s.apiHealth, ...updates } })),

  // Settings
  alwaysOnTop: false,
  mediaDucking: false,
  setAlwaysOnTop: (v) => set({ alwaysOnTop: v }),
  setMediaDucking: (v) => set({ mediaDucking: v }),

  // Pending message confirmation
  pendingMessage: null,
  setPendingMessage: (m) => set({ pendingMessage: m }),
  clearPendingMessage: () => set({ pendingMessage: null }),

  // Active panel
  activePanel: 'intelligence',
  setActivePanel: (p) => set({ activePanel: p }),

  // Toasts
  toasts: [],
  addToast: (text, type = 'info') => {
    const id = Date.now();
    set((s) => ({ toasts: [...s.toasts, { id, text, type }] }));
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), 3200);
  },
  removeToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),

  // WebSocket connection status
  wsConnected: false,
  setWsConnected: (v) => set({ wsConnected: v }),

  // ── Claude capabilities ─────────────────────────────────────────────────
  claudeCapabilities: {
    reasoning: true, codeGeneration: true, webSearch: true,
    imageAnalysis: true, documentAnalysis: true, mathCalculations: true,
    creativeWriting: true, dataAnalysis: true, multilingual: true,
    memoryRetrieval: true, taskPlanning: true, errorAnalysis: true,
  },

  // ── Context Wing ──────────────────────────────────────────────────────────
  contextCards: [],
  addContextCard: (card) => set((s) => ({
    contextCards: [card, ...s.contextCards].slice(0, 15) // Keep last 15 items
  })),
}));

// ── WebSocket Bridge ──────────────────────────────────────────────────────────
const WS_URL = 'ws://localhost:8765';
let _ws = null;
let _reconnectTimer = null;

function applySnapshot(snap, store) {
  if (snap.zaraState)     store.setZaraState(snap.zaraState);
  if (snap.gender)        store.setGender(snap.gender);
  if (snap.honorific)     store.setGender(snap.gender || 'unknown');
  if (typeof snap.volume === 'number')  store.setVolume(snap.volume);
  if (typeof snap.muted  === 'boolean') store.setMuted(snap.muted);
  if (snap.liveTranscript)  store.setLiveTranscript(snap.liveTranscript);
  if (snap.speakerContext)  store.setSpeakerContext(snap.speakerContext);
  if (snap.apiHealth)       store.setApiHealth(snap.apiHealth);
  if (snap.windows) {
    store.setWindows(snap.windows.open || [], snap.windows.minimized || []);
  }
  if (Array.isArray(snap.conversation)) {
    snap.conversation.forEach(m => store.addMessage(m.role, m.text));
  }
}

export function connectWsBridge() {
  if (_ws && _ws.readyState < 2) return;

  _ws = new WebSocket(WS_URL);

  _ws.onopen = () => {
    useZaraStore.getState().setWsConnected(true);
    useZaraStore.getState().addToast('⚡ Backend connected');
    if (_reconnectTimer) { clearTimeout(_reconnectTimer); _reconnectTimer = null; }
    // Request window list immediately
    wsSend({ type: 'get_windows' });
  };

  _ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      const store = useZaraStore.getState();
      const { type, payload } = msg;

      switch (type) {
        case 'snapshot':
          applySnapshot(payload, store);
          break;
        case 'state':
          store.setZaraState(payload.zaraState);
          if (payload.gender) store.setGender(payload.gender);
          if (typeof payload.capturing === 'boolean') store.setCaptureActive(payload.capturing);
          break;
        case 'metrics':
          store.setMetrics(payload);
          break;
        case 'message':
          store.addMessage(payload.role, payload.text);
          break;
        case 'transcript':
          payload.live
            ? store.setLiveTranscript(payload.text)
            : store.pushTranscript(payload.text);
          break;
        case 'speaker':
          store.setSpeakerContext(payload.context);
          break;
        case 'api_health':
          store.setApiHealth(payload);
          break;
        case 'volume':
          store.setVolume(payload.level);
          store.setMuted(payload.muted);
          break;
        case 'windows':
          store.setWindows(payload.open || [], payload.minimized || []);
          break;
        case 'orb_frame':
          store.setOrbFrame(payload.frame);
          break;
        case 'screen_frame':
          store.setScreenFrame(payload.frame, payload.title);
          store.setCaptureActive(true);
          break;
        case 'memory_stats':
          store.setMemoryStats({ stored: payload.stored, semantic: payload.semantic });
          store.setRecentMemories(payload.recent || []);
          break;
        case 'context_card':
          store.addContextCard(payload);
          break;
        case 'window_sync':
          store.setWindows(payload.open, payload.minimized);
          break;
        default:
          break;
      }
    } catch { /* ignore parse errors */ }
  };

  _ws.onclose = () => {
    useZaraStore.getState().setWsConnected(false);
    _reconnectTimer = setTimeout(connectWsBridge, 3000);
  };

  _ws.onerror = () => _ws.close();
}

export function wsSend(msg) {
  if (_ws && _ws.readyState === 1) {
    _ws.send(JSON.stringify(msg));
  }
}

import { create } from 'zustand';

// ── Types ──────────────────────────────────────────────────────────
export const ZARA_STATES = ['STANDBY', 'LISTENING', 'THINKING', 'TALKING', 'EXECUTING'];

const initialMetrics = { cpu: 0, ram: 0, gpu: 0, disk: 0 };

// ── Main Store ─────────────────────────────────────────────────────
export const useZaraStore = create((set, get) => ({
  // Core state
  zaraState: 'STANDBY',
  setZaraState: (s) => set({ zaraState: s }),

  // Gender / Honorific
  gender: localStorage.getItem('zara_gender') || 'unknown',
  honorific: localStorage.getItem('zara_gender') === 'female' ? "Ma'am" : 'Sir',
  setGender: (g) => {
    const h = g === 'female' ? "Ma'am" : 'Sir';
    localStorage.setItem('zara_gender', g);
    set({ gender: g, honorific: h });
  },
  resetGender: () => {
    localStorage.removeItem('zara_gender');
    set({ gender: 'unknown', honorific: 'Sir' });
  },

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
    { id: 1, role: 'zara', text: 'Systems online. Neural core initialized.', ts: Date.now() },
  ],
  addMessage: (role, text) => set((s) => ({
    conversation: [...s.conversation.slice(-99), {
      id: Date.now(), role, text, ts: Date.now(),
    }],
  })),

  // Background speaker detection
  speakerContext: 'none', // 'direct' | 'background' | 'none'
  bgDetectionEnabled: true,
  setSpeakerContext: (c) => set({ speakerContext: c }),
  setBgDetectionEnabled: (v) => set({ bgDetectionEnabled: v }),

  // System metrics
  metrics: initialMetrics,
  setMetrics: (m) => set({ metrics: m }),

  // Open windows
  openWindows: [],
  minimizedWindows: [],
  setWindows: (open, minimized) => set({ openWindows: open, minimizedWindows: minimized }),

  // Memory
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

  // Active panel/tab
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

  // Claude capabilities
  claudeCapabilities: {
    reasoning: true, codeGeneration: true, webSearch: true,
    imageAnalysis: true, documentAnalysis: true, mathCalculations: true,
    creativeWriting: true, dataAnalysis: true, multilingual: true,
    memoryRetrieval: true, taskPlanning: true, errorAnalysis: true,
  },
}));

// ── WebSocket Bridge ───────────────────────────────────────────────
// Connects to ws_bridge.py on port 8765 and hydrates the store live.
const WS_URL = 'ws://localhost:8765';
let _ws = null;
let _reconnectTimer = null;

function applySnapshot(snap, store) {
  if (snap.zaraState)    store.setZaraState(snap.zaraState);
  if (snap.honorific || snap.gender) {
    store.setGender(snap.gender || store.gender);
  }
  if (typeof snap.volume === 'number') store.setVolume(snap.volume);
  if (typeof snap.muted  === 'boolean') store.setMuted(snap.muted);
  if (snap.liveTranscript) store.setLiveTranscript(snap.liveTranscript);
  if (snap.speakerContext) store.setSpeakerContext(snap.speakerContext);
  if (snap.apiHealth)    store.setApiHealth(snap.apiHealth);
  if (Array.isArray(snap.conversation)) {
    // bulk-load last 100
    snap.conversation.forEach(m => store.addMessage(m.role, m.text));
  }
}

export function connectWsBridge() {
  if (_ws && _ws.readyState < 2) return; // already open/connecting

  _ws = new WebSocket(WS_URL);

  _ws.onopen = () => {
    useZaraStore.getState().setWsConnected(true);
    useZaraStore.getState().addToast('⚡ Backend connected');
    if (_reconnectTimer) { clearTimeout(_reconnectTimer); _reconnectTimer = null; }
  };

  _ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      const store = useZaraStore.getState();
      const { type, payload } = msg;

      if (type === 'snapshot')   { applySnapshot(payload, store); return; }
      if (type === 'state')      { store.setZaraState(payload.zaraState);
                                   if (payload.gender) store.setGender(payload.gender);
                                   return; }
      if (type === 'metrics')    { store.setMetrics(payload); return; }
      if (type === 'message')    { store.addMessage(payload.role, payload.text); return; }
      if (type === 'transcript') { payload.live
                                     ? store.setLiveTranscript(payload.text)
                                     : store.pushTranscript(payload.text);
                                   return; }
      if (type === 'speaker')    { store.setSpeakerContext(payload.context); return; }
      if (type === 'api_health') { store.setApiHealth(payload); return; }
      if (type === 'volume')     { store.setVolume(payload.level); store.setMuted(payload.muted); return; }
    } catch { /* ignore parse errors */ }
  };

  _ws.onclose = () => {
    useZaraStore.getState().setWsConnected(false);
    _reconnectTimer = setTimeout(connectWsBridge, 3000); // auto-reconnect
  };

  _ws.onerror = () => _ws.close();
}

// Expose send helper for commands from the UI
export function wsSend(msg) {
  if (_ws && _ws.readyState === 1) {
    _ws.send(JSON.stringify(msg));
  }
}

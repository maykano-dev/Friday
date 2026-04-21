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

  // Claude capabilities in use
  claudeCapabilities: {
    reasoning: true,
    codeGeneration: true,
    webSearch: true,
    imageAnalysis: true,
    documentAnalysis: true,
    mathCalculations: true,
    creativeWriting: true,
    dataAnalysis: true,
    multilingual: true,
    memoryRetrieval: true,
    taskPlanning: true,
    errorAnalysis: true,
  },
}));

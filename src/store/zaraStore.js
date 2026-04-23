import { create } from 'zustand';

export const ZARA_STATES = ['STANDBY', 'LISTENING', 'THINKING', 'TALKING', 'EXECUTING'];

const initialMetrics = { cpu: 0, ram: 0, gpu: 0, disk: 0, voiceAmp: 0, history: [] };
const WS_URL = 'ws://localhost:8765';

function getStoredGender() {
  try {
    return localStorage.getItem('zara_gender') || 'unknown';
  } catch {
    return 'unknown';
  }
}

function saveGender(gender) {
  try {
    if (gender === 'unknown') {
      localStorage.removeItem('zara_gender');
      return;
    }
    localStorage.setItem('zara_gender', gender);
  } catch {
    // Non-fatal in non-browser contexts.
  }
}

function genderToHonorific(gender) {
  return gender === 'female' ? "Ma'am" : 'Sir';
}

let _ws = null;
let _reconnectTimer = null;

function _sendWsRaw(msg) {
  if (_ws && _ws.readyState === 1) {
    _ws.send(JSON.stringify(msg));
  }
}

export const useZaraStore = create((set, get) => {
  const persistedGender = getStoredGender();

  return {
    // Core state
    zaraState: 'STANDBY',
    setZaraState: (s) => set({ zaraState: s }),
    activeMode: 'standard', // standard, code, trade, logistics
    setMode: (m) => set({ activeMode: m }),

    // Gender / Honorific
    gender: persistedGender,
    honorific: genderToHonorific(persistedGender),
    setGender: (g) => {
      saveGender(g);
      set({ gender: g, honorific: genderToHonorific(g) });
    },
    resetGender: () => {
      saveGender('unknown');
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
    contextCards: [],
    setConversation: (messages) =>
      set({
        conversation: (messages || []).slice(-100).map((m, i) => ({
          id: Date.now() + i,
          role: m.role || 'zara',
          text: m.text || '',
          ts: Date.now(),
        })),
      }),
    addMessage: (role, text) =>
      set((s) => ({
        conversation: [
          ...s.conversation.slice(-99),
          { id: Date.now(), role, text, ts: Date.now() },
        ],
      })),

    // Dual-track subtitles (pygame parity)
    subtitleZara: '',
    subtitleUser: '',
    setSubtitles: ({ zara, user }) =>
      set((s) => ({
        subtitleZara: typeof zara === 'string' ? zara : s.subtitleZara,
        subtitleUser: typeof user === 'string' ? user : s.subtitleUser,
      })),

    // Background speaker detection
    speakerContext: 'none',
    bgDetectionEnabled: true,
    setSpeakerContext: (c) => set({ speakerContext: c }),
    setBgDetectionEnabled: (v) => {
      set({ bgDetectionEnabled: v });
      _sendWsRaw({ type: 'bg_detection', enabled: !!v });
    },

    // System metrics
    metrics: initialMetrics,
    setMetrics: (m) => set((s) => {
      const data = m || initialMetrics;
      const history = s.metrics?.history || [];
      const newHistory = [...history, data].slice(-30);
      return { metrics: { ...data, history: newHistory } };
    }),

    // Background task pulse text (pygame parity)
    bgTaskText: '',
    setBgTaskText: (t) => set({ bgTaskText: t || '' }),

    // Windows
    openWindows: [],
    minimizedWindows: [],
    setWindows: (open, minimized) => set({ openWindows: open, minimizedWindows: minimized }),

    // Orb frame (pygame-rendered stream)
    orbFrame: null,
    setOrbFrame: (f) => set({ orbFrame: f }),

    // Screen/window capture
    screenFrame: null,
    screenFrameTitle: null,
    captureActive: false,
    setScreenFrame: (f, title) => set({ screenFrame: f, screenFrameTitle: title }),
    setCaptureActive: (v) => set({ captureActive: v }),

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
      setTimeout(() => {
        set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
      }, 3200);
    },
    removeToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),

    // WebSocket connection status
    wsConnected: false,
    setWsConnected: (v) => set({ wsConnected: v }),

    // Claude capabilities
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

    // Agent Orchestration
    agentTasks: [],
    setAgentTask: (task) => set((s) => {
      const idx = s.agentTasks.findIndex(t => t.id === task.id);
      if (idx >= 0) {
        const newTasks = [...s.agentTasks];
        newTasks[idx] = { ...newTasks[idx], ...task };
        return { agentTasks: newTasks };
      }
      return { agentTasks: [...s.agentTasks, task].slice(-10) };
    }),
  };
});

function applySnapshot(snap, store) {
  if (!snap) return;

  if (snap.zaraState) store.setZaraState(snap.zaraState);
  if (snap.activeMode) store.setMode(snap.activeMode);
  if (snap.gender) store.setGender(snap.gender);
  if (typeof snap.volume === 'number') store.setVolume(snap.volume);
  if (typeof snap.muted === 'boolean') store.setMuted(snap.muted);
  if (typeof snap.liveTranscript === 'string') store.setLiveTranscript(snap.liveTranscript);
  store.setSubtitles({
    zara: typeof snap.subtitleZara === 'string' ? snap.subtitleZara : undefined,
    user: typeof snap.subtitleUser === 'string' ? snap.subtitleUser : undefined,
  });
  if (snap.speakerContext) store.setSpeakerContext(snap.speakerContext);
  if (typeof snap.bgTask === 'string') store.setBgTaskText(snap.bgTask);
  if (snap.apiHealth) store.setApiHealth(snap.apiHealth);
  if (snap.windows) store.setWindows(snap.windows.open || [], snap.windows.minimized || []);
  if (Array.isArray(snap.conversation)) store.setConversation(snap.conversation);
}

export function connectWsBridge() {
  if (_ws && _ws.readyState < 2) return;

  _ws = new WebSocket(WS_URL);

  _ws.onopen = () => {
    const store = useZaraStore.getState();
    store.setWsConnected(true);
    store.addToast('Backend connected');
    if (_reconnectTimer) {
      clearTimeout(_reconnectTimer);
      _reconnectTimer = null;
    }
    _sendWsRaw({ type: 'get_windows' });
    _sendWsRaw({ type: 'bg_detection', enabled: store.bgDetectionEnabled });
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
          if (payload?.zaraState) store.setZaraState(payload.zaraState);
          if (payload?.gender) store.setGender(payload.gender);
          if (typeof payload?.capturing === 'boolean') {
            store.setCaptureActive(payload.capturing);
            if (!payload.capturing) {
              store.setScreenFrame(null, null);
            }
          }
          break;
        case 'metrics':
          store.setMetrics(payload || initialMetrics);
          break;
        case 'message':
          if (payload?.role && typeof payload?.text === 'string') {
            store.addMessage(payload.role, payload.text);
          }
          break;
        case 'transcript':
          if (!payload) break;
          if (payload.live) store.setLiveTranscript(payload.text || '');
          else store.pushTranscript(payload.text || '');
          break;
        case 'subtitle':
          store.setSubtitles({
            zara: typeof payload?.zara === 'string' ? payload.zara : undefined,
            user: typeof payload?.user === 'string' ? payload.user : undefined,
          });
          break;
        case 'speaker':
          if (payload?.context) store.setSpeakerContext(payload.context);
          break;
        case 'bg_task':
          store.setBgTaskText(payload?.text || '');
          break;
        case 'api_health':
          if (payload) store.setApiHealth(payload);
          break;
        case 'volume':
          if (typeof payload?.level === 'number') store.setVolume(payload.level);
          if (typeof payload?.muted === 'boolean') store.setMuted(payload.muted);
          break;
        case 'windows':
          store.setWindows(payload?.open || [], payload?.minimized || []);
          break;
        case 'orb_frame':
          if (payload?.frame) store.setOrbFrame(payload.frame);
          break;
        case 'screen_frame':
          if (payload?.frame) {
            store.setScreenFrame(payload.frame, payload.title || null);
            store.setCaptureActive(true);
          }
          break;
        case 'context_card':
          if (payload) useZaraStore.setState((s) => ({ contextCards: [payload, ...s.contextCards].slice(0, 10) }));
          break;
        case 'memory_stats':
          store.setMemoryStats({
            stored: payload?.stored || 0,
            semantic: payload?.semantic || 0,
          });
          store.setRecentMemories(payload?.recent || []);
          break;
        case 'agent_task':
          if (payload) store.setAgentTask(payload);
          break;
        default:
          break;
      }
    } catch {
      // Ignore malformed payloads; keep stream resilient.
    }
  };

  _ws.onclose = () => {
    useZaraStore.getState().setWsConnected(false);
    _reconnectTimer = setTimeout(connectWsBridge, 3000);
  };

  _ws.onerror = () => {
    _ws.close();
  };
}

export function wsSend(msg) {
  _sendWsRaw(msg);
}

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import TitleBar from './components/TitleBar';
import NeuralSphere from './components/NeuralSphere';
import { useZaraStore, wsSend } from './store/zaraStore';
import ContextWing from './components/ContextWing';
import WindowMatrix from './components/WindowMatrix';
import MetricCard from './components/MetricCard';
import AgentTimeline from './components/AgentTimeline';
import { Activity, Layers, Cpu, Database, Code, Package, GraduationCap } from 'lucide-react';
import NeuralHeartbeat from './components/NeuralHeartbeat';
import OmniSearch from './components/OmniSearch';
import AutoDebugConsole from './components/AutoDebugConsole';
import SubtitleOverlay from './components/SubtitleOverlay';

const GLOBAL_CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=JetBrains+Mono:wght@400;700&display=swap');
  
  * { margin:0; padding:0; box-sizing:border-box; }
  :root {
    --bg: #020408; 
    --surface: rgba(10, 15, 28, 0.7);
    --cyan: #00d4ff;
    --magenta: #ff00ff;
    --border: rgba(0, 212, 255, 0.15);
    --text: #e8eaf6;
    --sans: 'Inter', sans-serif;
    --mono: 'JetBrains Mono', monospace;
  }

  html, body, #root { 
    height: 100%; 
    background: var(--bg); 
    color: var(--text); 
    overflow: hidden; 
    font-family: var(--sans);
  }

  /* Custom Scrollbar */
  ::-webkit-scrollbar { width: 4px; }
  ::-webkit-scrollbar-thumb { background: rgba(0, 212, 255, 0.3); border-radius: 10px; }

  /* Digital Grain */
  body::before {
    content: "";
    position: fixed;
    inset: 0;
    background-image: url("https://grainy-gradients.vercel.app/noise.svg");
    opacity: 0.04;
    pointer-events: none;
    z-index: 999;
  }

  .message-entry {
    animation: blurEntry 0.5s cubic-bezier(0.4, 0, 0.2, 1);
  }

  @keyframes blurEntry {
    from { opacity: 0; filter: blur(20px); transform: translateY(10px); }
    to { opacity: 1; filter: blur(0px); transform: translateX(0); }
  }
`;

const T = {
  bg: '#020408',
  cyan: '#00d4ff',
  magenta: '#ff00ff',
  glass: {
    background: 'rgba(10, 15, 28, 0.7)',
    backdropFilter: 'blur(20px) saturate(180%)',
    border: '1px solid rgba(0, 212, 255, 0.15)',
    boxShadow: '0 8px 32px 0 rgba(0, 0, 0, 0.8), inset 0 0 10px rgba(0, 212, 255, 0.05)',
    borderRadius: '20px',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden'
  },
  label: {
    fontFamily: '"Inter", sans-serif',
    fontSize: '10px',
    fontWeight: 700,
    letterSpacing: '0.12em',
    textTransform: 'uppercase',
    color: 'rgba(0, 212, 255, 0.6)',
  },
  mono: { fontFamily: '"JetBrains Mono", monospace' }
};

const CAPABILITY_GROUPS = [
  { group:'Reasoning & Analysis', color:'#00d4ff', items:['Multi-step logical reasoning','Hypothesis testing and validation','Root cause analysis and debugging','Pattern recognition across domains','Causal inference and argument evaluation','Mathematical proofs and derivations','Statistical analysis and interpretation'] },
  { group:'Code & Engineering', color:'#00ff9d', items:['Code generation in 40+ languages','Full-stack app architecture','Code review, refactoring, optimization','Bug detection and autonomous fixing','Unit & integration test writing','API design and documentation','Database schema design','Security vulnerability analysis','Shell scripts and automation','Regex, parsing, data transformation'] },
  { group:'Web & Research', color:'#b47dff', items:['Real-time web search (DuckDuckGo, Wikipedia)','Multi-source research synthesis','Playwright stealth web browsing','Form filling and web automation','News aggregation (HN, DEV.to)','Weather, crypto, exchange rates','GitHub, NPM, PyPI lookups','CVE security database','Country/university/holiday data','URL shortening and QR codes'] },
  { group:'Vision & Multimodal', color:'#ffb547', items:['Screen reading and OCR','Error detection from screenshots','Vision-guided UI automation (Moondream)','Image analysis and description','Document and PDF understanding','Code screenshot reading','Camera feed analysis','Visual context for task assistance'] },
  { group:'Writing & Communication', color:'#ff9d6a', items:['Long-form creative writing','Technical documentation','Email and message drafting','Summarization at any length','Translation across 100+ languages','Tone and style adaptation','Proofreading and editing','Report and proposal writing','Social media copy','Persuasive writing'] },
  { group:'Math & Science', color:'#00ffce', items:['Algebra, calculus, linear algebra','Statistics and probability','Physics, chemistry, biology','Unit conversion','Data science and ML guidance','Symbolic computation','Engineering calculations'] },
  { group:'Memory & Context', color:'#ff4d6a', items:['SQLite long-term memory vault','ChromaDB semantic search','Keyword-extracted indexing','Session persistence','Proactive suggestions','Learning from failures','User preference tracking'] },
  { group:'System & Automation', color:'#7b8ab8', items:['File creation, editing, organization','Script execution with sandboxing','App launching and window management','Multi-agent orchestration','Background task management','Silent volume control','Media playback control','Screenshot capture','Clipboard processing'] },
  { group:'Messaging', color:'#00d4ff', items:['WhatsApp with confirmation','Telegram, Discord, Slack, Teams','Gmail / Outlook email','SMS via Phone Link','Universal UI automation','Pre-send confirmation dialog'] },
];

function NeuralSparkline({ name, value, history, color }) {
  // Generate a dynamic SVG path from metrics history
  const points = (history || []).map((h, i) => `${i * 10},${40 - (h[name.toLowerCase()] / 2.5)}`).join(' ');

  return (
    <div style={{ ...T.card, background: 'rgba(11, 22, 39, 0.4)', backdropFilter: 'blur(10px)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ ...T.label, color }}>{name}</span>
        <span style={{ ...T.mono, fontSize: 14, color }}>{value}%</span>
      </div>
      <svg width="100%" height="40" style={{ overflow: 'visible' }}>
        <motion.polyline
          fill="none"
          stroke={color}
          strokeWidth="2"
          points={points}
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 0.5 }}
        />
        <motion.polyline
          fill="none"
          stroke={color}
          strokeWidth="6"
          points={points}
          style={{ opacity: 0.15, filter: 'blur(4px)' }}
        />
      </svg>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
//  INTEL PANEL
// ══════════════════════════════════════════════════════════════════
function IntelPanel() {
  const { zaraState, metrics, conversation, wsConnected } = useZaraStore();
  const convRef = useRef(null);
  useEffect(() => { if (convRef.current) convRef.current.scrollTop = convRef.current.scrollHeight; }, [conversation]);

  const stateColors = { STANDBY: '#0060ff', LISTENING: '#ff2244', THINKING: '#00d4ff', TALKING: '#00ff9d', EXECUTING: '#ffb547' };

  return (
    <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* State & Metrics Bento Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <div style={{ ...T.card, gridColumn: 'span 2' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <span style={T.label}>Neural State</span>
              <div style={{ ...T.mono, fontSize: 24, fontWeight: 800, color: stateColors[zaraState] || 'var(--cyan)', lineHeight: 1 }}>{zaraState}</div>
            </div>
            <motion.div 
              animate={{ opacity: [0.4, 1, 0.4] }} 
              transition={{ duration: 2, repeat: Infinity }}
              style={{ width: 10, height: 10, borderRadius: '50%', background: wsConnected ? 'var(--green)' : 'var(--red)', marginTop: 4 }}
            />
          </div>
        </div>
        
        <MetricCard name="CPU" value={metrics?.cpu || 0} history={metrics?.history || []} color="var(--cyan)" />
        <MetricCard name="RAM" value={metrics?.ram || 0} history={metrics?.history || []} color="var(--purple)" />
        <MetricCard name="GPU" value={metrics?.gpu || 0} history={metrics?.history || []} color="var(--green)" />
        <MetricCard name="Disk" value={metrics?.disk || 0} history={metrics?.history || []} color="var(--amber)" />
      </div>

      {/* Conversation Log */}
      <div style={{ ...T.card, flex: 1 }}>
        <span style={T.label}>Active Dialogue</span>
        <div ref={convRef} style={{ maxHeight: 300, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {(conversation || []).slice(-15).map((msg) => (
            <div key={msg?.id || Math.random()} className="message-entry">
              <div style={{ fontSize: 9, ...T.mono, color: msg?.role === 'user' ? 'var(--green)' : 'var(--cyan)', marginBottom: 2 }}>
                {msg?.role === 'user' ? '► USER' : '► ZARA'}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text)', background: 'rgba(255,255,255,0.03)', padding: '8px 10px', borderRadius: '8px', borderLeft: `2px solid ${msg?.role === 'user' ? 'var(--green)' : 'var(--cyan)'}` }}>
                {msg?.text || ''}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
//  WINDOWS + SCREEN CAPTURE PANEL  (live from backend)
// ══════════════════════════════════════════════════════════════════
function WindowsPanel() {
  const { openWindows, minimizedWindows, screenFrame, screenFrameTitle,
    captureActive, setCaptureActive, addMessage, addToast } = useZaraStore();

  const handleWindowAction = (hwnd, action, title) => {
    wsSend({ type: 'window_action', hwnd, action });
    addToast(`${action}: ${title}`);
  };

  const startCapture = (title) => {
    if (title === '__desktop__') {
      wsSend({ type: 'capture_screen' });
    } else {
      wsSend({ type: 'capture_window', title });
    }
    addToast(`📷 Capturing: ${title || 'Desktop'}`);
  };

  const stopCapture = () => {
    wsSend({ type: 'stop_capture' });
    setCaptureActive(false);
  };

  const refreshWindows = () => {
    wsSend({ type: 'get_windows' });
    addToast('Refreshing window list...');
  };

  const askZaraAbout = (title) => {
    const cmd = `Look at the ${title} window and tell me what you see. Check for any problems.`;
    wsSend({ type: 'command', text: cmd });
    wsSend({ type: 'capture_window', title });
    addMessage('user', cmd);
    addToast(`🔍 Zara is inspecting ${title}`);
  };

  return (
    <div style={{ padding:12, display:'flex', flexDirection:'column', gap:8 }}>

      {/* Screen capture viewer */}
      {screenFrame && (
        <div style={{ ...T.card, padding:0, overflow:'hidden', position:'relative' }}>
          <div style={{ padding:'8px 12px', borderBottom:'1px solid var(--border)',
            display:'flex', justifyContent:'space-between', alignItems:'center' }}>
            <span style={{ fontSize:10, ...T.mono, color:'var(--cyan)', letterSpacing:'0.12em' }}>
              📺 {screenFrameTitle || 'SCREEN CAPTURE'}
              {captureActive && <span style={{ marginLeft:8, color:'var(--red)', animation:'captureRing 1.5s infinite' }}>● LIVE</span>}
            </span>
            <div style={{ display:'flex', gap:5 }}>
              <QABtn onClick={() => askZaraAbout(screenFrameTitle || 'Desktop')}>🔍 Analyze</QABtn>
              <QABtn onClick={stopCapture} style={{ color:'var(--red)' }}>✕ Stop</QABtn>
            </div>
          </div>
          <img
            src={`data:image/jpeg;base64,${screenFrame}`}
            alt="screen capture"
            style={{ width:'100%', display:'block', maxHeight:220, objectFit:'contain', background:'#000' }}
          />
        </div>
      )}

      {/* Orb viewer — shows live pygame orb */}
      <OrbViewer />

      {/* Quick capture buttons */}
      <div style={T.card}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
          <span style={T.label}>Screen Capture</span>
          <QABtn onClick={refreshWindows}>↻ Refresh</QABtn>
        </div>
        <div style={{ display:'flex', flexWrap:'wrap', gap:5 }}>
          <QABtn onClick={() => startCapture('__desktop__')}>🖥 Full Desktop</QABtn>
          {openWindows.slice(0, 6).map(w => (
            <QABtn key={w.hwnd || w.title} onClick={() => startCapture(w.title)}>
              {w.process?.replace('.exe','') || w.title.slice(0,12)}
            </QABtn>
          ))}
        </div>
      </div>

      {/* Active windows — LIVE Matrix View */}
      <div style={T.card}>
        <span style={T.label}>Window Matrix ({openWindows.length})</span>
        <WindowMatrix />
      </div>

      {/* Minimized windows — LIVE */}
      <div style={T.card}>
        <span style={T.label}>Minimized ({minimizedWindows.length})</span>
        {minimizedWindows.length
          ? minimizedWindows.slice(0, 8).map(w => (
            <WindowItem key={w.hwnd || w.title} window={w} minimized
              onAction={(act) => handleWindowAction(w.hwnd, act, w.title)}
              onCapture={() => startCapture(w.title)}
              onAsk={() => askZaraAbout(w.title)}
            />
          ))
          : <span style={{ fontSize:11, color:'var(--text3)', ...T.mono }}>No minimized windows</span>
        }
      </div>

      {/* Quick commands */}
      <div style={T.card}>
        <span style={T.label}>Quick Commands</span>
        <div style={{ display:'flex', flexWrap:'wrap', gap:5 }}>
          {['Minimize all','Show desktop','Restore all','Snap left','Snap right','Maximize','List windows'].map(cmd => (
            <QABtn key={cmd} onClick={() => wsSend({ type:'command', text:cmd })}>{cmd}</QABtn>
          ))}
        </div>
      </div>
    </div>
  );
}

// Pygame orb rendered by backend and displayed here
function OrbViewer() {
  const orbFrame = useZaraStore(s => s.orbFrame);
  const zaraState = useZaraStore(s => s.zaraState);
  const stateColors = { STANDBY:'#0060ff', LISTENING:'#ff2244', THINKING:'#00d4ff', TALKING:'#00ff9d', EXECUTING:'#ffb547' };

  if (!orbFrame) {
    return (
      <div style={{ ...T.card, textAlign:'center', padding:'16px 12px' }}>
        <span style={T.label}>Neural Orb (Pygame)</span>
        <div style={{ fontSize:10, color:'var(--text3)', ...T.mono }}>
          Orb not streaming — ensure orb_bridge.py is running
        </div>
        <div style={{ fontSize:9, color:'var(--text3)', ...T.mono, marginTop:4 }}>
          Add to main.py: from orb_bridge import start_orb_bridge; start_orb_bridge()
        </div>
      </div>
    );
  }

  return (
    <div style={{ ...T.card, padding:0, overflow:'hidden' }}>
      <div style={{ padding:'6px 12px', borderBottom:'1px solid var(--border)',
        display:'flex', justifyContent:'space-between', alignItems:'center' }}>
        <span style={{ fontSize:9, ...T.mono, letterSpacing:'0.12em', color:'var(--text3)', textTransform:'uppercase' }}>
          Neural Orb — Pygame
        </span>
        <span style={{ fontSize:9, ...T.mono, color: stateColors[zaraState]||'var(--cyan)' }}>
          {zaraState}
        </span>
      </div>
      <div style={{ background:'#0a0c10', display:'flex', justifyContent:'center', padding:8 }}>
        <img
          src={`data:image/png;base64,${orbFrame}`}
          alt="Neural orb"
          style={{ width:120, height:120, imageRendering:'pixelated', borderRadius:'50%',
            boxShadow:`0 0 20px ${stateColors[zaraState]||'#0060ff'}40` }}
        />
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
//  MEMORY PANEL  (live from backend)
// ══════════════════════════════════════════════════════════════════
function MemoryPanel() {
  const { recentMemories, memoryStats, wsConnected } = useZaraStore();

  const statCards = [
    ['Stored', memoryStats.stored || '—', 'var(--cyan)'],
    ['Semantic', memoryStats.semantic || '—', 'var(--green)'],
  ];

  return (
    <div style={{ padding:12, display:'flex', flexDirection:'column', gap:8 }}>
      <div style={{ ...T.card, display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
        {statCards.map(([label, val, color]) => (
          <div key={label} style={{ background:'var(--bg3)', border:'1px solid var(--border)', borderRadius:6, padding:8 }}>
            <span style={{ ...T.label, marginBottom:3 }}>{label}</span>
            <div style={{ ...T.mono, fontSize:18, fontWeight:700, color }}>{val}</div>
          </div>
        ))}
      </div>

      <div style={T.card}>
        <span style={T.label}>Recent Memories {!wsConnected && '(offline)'}</span>
        {recentMemories.length > 0
          ? recentMemories.map((m, i) => (
            <div key={i} style={{ background:'var(--bg3)', border:'1px solid var(--border)', borderRadius:6, padding:8, marginBottom:5 }}>
              <div style={{ fontSize:11, color:'var(--text2)', lineHeight:1.5 }}>
                {typeof m === 'string' ? m : m.text || JSON.stringify(m)}
              </div>
            </div>
          ))
          : [
            { tag:'preference', text:'User prefers dark mode interfaces', time:'persisted' },
            { tag:'task', text:'Music app: Spotify | Artist: Chris Brown', time:'persisted' },
            { tag:'personal', text:'Gender: Male — Honorific: Sir', time:'persisted' },
          ].map((m, i) => (
            <div key={i} style={{ background:'var(--bg3)', border:'1px solid var(--border)', borderRadius:6, padding:8, marginBottom:5 }}>
              <div style={{ fontSize:9, ...T.mono, color:'var(--purple)', letterSpacing:'0.1em', textTransform:'uppercase', marginBottom:2 }}>{m.tag}</div>
              <div style={{ fontSize:11, color:'var(--text2)', lineHeight:1.5 }}>{m.text}</div>
              <div style={{ fontSize:9, ...T.mono, color:'var(--text3)', marginTop:3, textAlign:'right' }}>{m.time}</div>
            </div>
          ))
        }
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
//  CAPABILITIES PANEL
// ══════════════════════════════════════════════════════════════════
function CapabilitiesPanel() {
  const [expanded, setExpanded] = useState(null);
  return (
    <div style={{ padding:12, display:'flex', flexDirection:'column', gap:6 }}>
      <div style={{ fontSize:10, ...T.mono, color:'var(--text2)', lineHeight:1.7,
        background:'var(--surface)', border:'1px solid var(--border)', borderRadius:8, padding:10, marginBottom:4 }}>
        Zara is powered by Groq + Llama 3.3 70B. All capabilities are available via voice and the command bar.
      </div>
      {CAPABILITY_GROUPS.map((group) => (
        <div key={group.group} style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:8, overflow:'hidden' }}>
          <button onClick={() => setExpanded(expanded===group.group ? null : group.group)}
            style={{ width:'100%', padding:'9px 12px', display:'flex', alignItems:'center',
              justifyContent:'space-between', background:'transparent', border:'none', cursor:'pointer', color:'var(--text)', textAlign:'left' }}>
            <div style={{ display:'flex', alignItems:'center', gap:8 }}>
              <div style={{ width:7, height:7, borderRadius:'50%', background:group.color, flexShrink:0 }} />
              <span style={{ fontSize:12, fontWeight:600, color:group.color }}>{group.group}</span>
              <span style={{ fontSize:10, ...T.mono, color:'var(--text3)' }}>{group.items.length}</span>
            </div>
            <span style={{ color:'var(--text3)', fontSize:12 }}>{expanded===group.group?'▲':'▼'}</span>
          </button>
          {expanded===group.group && (
            <div style={{ padding:'0 12px 10px', borderTop:'1px solid var(--border)', paddingTop:8 }}>
              {group.items.map((item, i) => (
                <div key={i} style={{ display:'flex', alignItems:'flex-start', gap:6, marginBottom:4 }}>
                  <div style={{ width:4, height:4, borderRadius:'50%', background:group.color, marginTop:5, flexShrink:0 }} />
                  <span style={{ fontSize:11, color:'var(--text2)', lineHeight:1.5 }}>{item}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
//  TOOLS PANEL
// ══════════════════════════════════════════════════════════════════
function ToolsPanel() {
  const { addMessage, setPendingMessage, addToast } = useZaraStore();

  const runTool = (cmd) => {
    addMessage('user', cmd);
    wsSend({ type: 'command', text: cmd });
    addToast(cmd.substring(0, 50));
  };

  const demoMsgConfirm = () => {
    setPendingMessage({
      app: 'WhatsApp', appIcon: '💬',
      recipient: 'John Doe',
      message: 'Hey, are you free this evening? Want to catch up.',
    });
  };

  return (
    <div style={{ padding:12, display:'flex', flexDirection:'column', gap:8 }}>
      {[
        { label:'Web Research', color:'var(--cyan)', actions:['Latest AI news','Hacker News today','Bitcoin price','Weather in London','GitHub user torvalds','Search for quantum computing'] },
        { label:'Messaging', color:'var(--green)', actions:['Open WhatsApp','Open Telegram','Open Discord','Open Slack'], extra:<QABtn onClick={demoMsgConfirm} style={{ marginTop:6 }}>Demo: Message Confirm</QABtn> },
        { label:'System', color:'var(--amber)', actions:['Take a screenshot','System status','What is my IP?','Time in Tokyo','Shorten URL','Generate QR code'] },
        { label:'Knowledge', color:'var(--purple)', actions:['Define serendipity','Synonyms for happy','Tell me about France','Number fact about 42'] },
      ].map(({ label, color, actions, extra }) => (
        <div key={label} style={T.card}>
          <span style={{ ...T.label, color }}>{label}</span>
          <div style={{ display:'flex', flexWrap:'wrap', gap:5 }}>
            {actions.map(a => <QABtn key={a} onClick={() => runTool(a)}>{a}</QABtn>)}
          </div>
          {extra}
        </div>
      ))}

      <div style={{ ...T.card, background:'var(--bg3)' }}>
        <span style={T.label}>Voice Command Examples</span>
        <div style={{ fontSize:10, ...T.mono, color:'var(--text3)', lineHeight:2 }}>
          {['"Send a message to John on WhatsApp saying hi"','"Volume to 40 percent"','"Play Stonebwoy on Spotify"','"Snap Chrome to the left"','"What windows are open?"','"Search for React best practices"','"Take a screenshot"','"Define obfuscation"','"Remind me to call mom in 30 minutes"','"Write a Python script to sort a CSV"'].map(ex => (
            <div key={ex} style={{ color:'var(--text2)' }}>{ex}</div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
//  SETTINGS PANEL
// ══════════════════════════════════════════════════════════════════
function SettingsPanel() {
  const { gender, setGender, resetGender, honorific,
    alwaysOnTop, setAlwaysOnTop, mediaDucking, setMediaDucking,
    bgDetectionEnabled, setBgDetectionEnabled, apiHealth } = useZaraStore();

  const isElectron = window.electron?.isElectron;

  return (
    <div style={{ padding:12, display:'flex', flexDirection:'column', gap:8 }}>
      <div style={T.card}>
        <span style={T.label}>User Profile</span>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:6, marginBottom:8 }}>
          {[['Honorific', honorific, 'var(--purple)'], ['Gender', gender==='unknown'?'Detecting':gender, 'var(--green)']].map(([l, v, c]) => (
            <div key={l} style={{ background:'var(--bg3)', border:'1px solid var(--border)', borderRadius:6, padding:8 }}>
              <span style={T.label}>{l}</span>
              <div style={{ ...T.mono, fontSize:13, color:c }}>{v}</div>
            </div>
          ))}
        </div>
        <div style={{ display:'flex', gap:6 }}>
          <QABtn onClick={() => { setGender('male'); wsSend({ type:'gender', value:'male' }); }}>♂ Male</QABtn>
          <QABtn onClick={() => { setGender('female'); wsSend({ type:'gender', value:'female' }); }}>♀ Female</QABtn>
          <QABtn onClick={() => { resetGender(); wsSend({ type:'gender', value:'reset' }); }}>⟳ Reset</QABtn>
        </div>
      </div>

      <div style={T.card}>
        <span style={T.label}>API Health</span>
        {Object.entries(apiHealth).map(([key, status]) => (
          <div key={key} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'4px 0' }}>
            <span style={{ fontSize:11, ...T.mono, color:'var(--text2)' }}>{key}</span>
            <span style={{ fontSize:10, ...T.mono,
              color: status==='online'?'var(--green)':status==='checking'?'var(--amber)':'var(--text3)' }}>
              {status.toUpperCase()}
            </span>
          </div>
        ))}
      </div>

      <div style={T.card}>
        <span style={T.label}>Options</span>
        <Toggle label="Always on Top" value={alwaysOnTop} onChange={(v) => { setAlwaysOnTop(v); if (isElectron) window.electron.alwaysOnTop(v); }} />
        <Toggle label="Media Ducking" value={mediaDucking} onChange={setMediaDucking} />
        <Toggle label="Background Detection" value={bgDetectionEnabled} onChange={setBgDetectionEnabled} />
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
//  SHARED COMPONENTS
// ══════════════════════════════════════════════════════════════════
function VolumeCard({ volume, isMuted, setVolume }) {
  const bars = Array.from({ length:20 }, (_, i) => i);
  const litCount = Math.round(volume / 100 * 20);
  const handleVolumeChange = (v) => { setVolume(v); wsSend({ type:'volume', level:v }); };
  return (
    <div style={T.card}>
      <span style={T.label}>Volume Control</span>
      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:6 }}>
        <span style={{ fontSize:11, ...T.mono, color:'var(--text2)' }}>System Audio</span>
        <span style={{ ...T.mono, fontSize:13, color: isMuted?'var(--red)':'var(--cyan)' }}>{isMuted?'MUTED':`${volume}%`}</span>
      </div>
      <input type="range" min={0} max={100} value={volume}
        onChange={e => handleVolumeChange(+e.target.value)}
        style={{ width:'100%', height:4, accentColor:'var(--cyan)', cursor:'pointer', marginBottom:8 }} />
      <div style={{ display:'flex', gap:2, height:16 }}>
        {bars.map(i => (
          <div key={i} style={{ flex:1, borderRadius:2,
            background: i<litCount?(i>=16?'var(--amber)':'var(--cyan)'):'var(--surface2)',
            transition:'background 0.1s' }} />
        ))}
      </div>
    </div>
  );
}

function MetricBar({ name, value, critThreshold, warnThreshold }) {
  const color = value>critThreshold?'var(--red)':value>warnThreshold?'var(--amber)':'var(--cyan)';
  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:3 }}>
        <span style={{ fontSize:10, ...T.mono, color:'var(--text3)' }}>{name}</span>
        <span style={{ fontSize:10, ...T.mono, color }}>{value}%</span>
      </div>
      <div style={{ height:3, background:'var(--surface2)', borderRadius:2, overflow:'hidden' }}>
        <div style={{ height:'100%', width:`${value}%`, background:color, borderRadius:2, transition:'width 0.4s, background 0.3s' }} />
      </div>
    </div>
  );
}

function WindowItem({ window: w, minimized, onAction, onCapture, onAsk }) {
  const [hover, setHover] = useState(false);
  return (
    <div style={{ display:'flex', alignItems:'center', gap:8, padding:'5px 8px',
      background: hover?'var(--surface2)':'var(--bg3)',
      border:`1px solid ${hover?'var(--border2)':'var(--border)'}`,
      borderRadius:6, marginBottom:4, transition:'all 0.15s' }}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      <div style={{ width:7, height:7, borderRadius:2, background: minimized?'var(--text3)':'var(--cyan)', flexShrink:0 }} />
      <div style={{ fontSize:11, ...T.mono, color: minimized?'var(--text2)':'var(--text)', flex:1,
        overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
        {w.title}
      </div>
      <div style={{ display:'flex', gap:3, flexShrink:0 }}>
        {onCapture && <QABtn onClick={onCapture} title="Capture this window">📷</QABtn>}
        {onAsk && <QABtn onClick={onAsk} title="Ask Zara about this window">🔍</QABtn>}
        {minimized
          ? <QABtn onClick={() => onAction('restore')}>↑</QABtn>
          : <>
              <QABtn onClick={() => onAction('minimize')}>⊟</QABtn>
              <QABtn onClick={() => onAction('focus')}>⊞</QABtn>
            </>
        }
      </div>
    </div>
  );
}

function Toggle({ label, value, onChange }) {
  return (
    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'6px 0' }}>
      {label && <span style={{ fontSize:11, ...T.mono, color:'var(--text2)' }}>{label}</span>}
      <div onClick={() => onChange(!value)}
        style={{ width:32, height:18, borderRadius:9, cursor:'pointer',
          background: value?'var(--cyan)':'var(--surface2)',
          position:'relative', transition:'background 0.2s', flexShrink:0 }}>
        <div style={{ width:14, height:14, borderRadius:'50%', background:'#fff',
          position:'absolute', top:2, left: value?16:2, transition:'left 0.2s' }} />
      </div>
    </div>
  );
}

function QABtn({ onClick, children, style: extra, title }) {
  const [hover, setHover] = useState(false);
  return (
    <button onClick={onClick} title={title}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      style={{ padding:'4px 9px', fontSize:10, fontFamily:'var(--mono)', letterSpacing:'0.06em',
        background: hover?'var(--surface2)':'var(--surface)',
        border:'1px solid var(--border)', borderRadius:5, color:'var(--text2)',
        cursor:'pointer', transition:'all 0.15s', whiteSpace:'nowrap', ...extra }}>
      {children}
    </button>
  );
}

// ── Message confirm dialog ──────────────────────────────────────────────────
function MessageConfirmDialog() {
  const { pendingMessage, clearPendingMessage, addMessage, addToast } = useZaraStore();
  if (!pendingMessage) return null;
  const { app, appIcon, recipient, message } = pendingMessage;
  const confirm = () => {
    const cmd = `Confirmed — send message to ${recipient} on ${app}: ${message}`;
    wsSend({ type:'command', text:cmd });
    addMessage('user', `✓ Message sent to ${recipient} via ${app}`);
    addToast(`✓ Message sent via ${app}`);
    clearPendingMessage();
  };
  return (
    <div style={{ position:'fixed', inset:0, background:'rgba(6,8,16,0.85)', display:'flex', alignItems:'center', justifyContent:'center', zIndex:9999 }}>
      <div style={{ background:'var(--surface)', border:'1px solid var(--border2)', borderRadius:14, padding:24, width:320, animation:'fadeIn 0.2s ease' }}>
        <div style={{ fontSize:10, ...T.mono, color:'var(--text3)', letterSpacing:'0.15em', marginBottom:12 }}>CONFIRM MESSAGE</div>
        <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:12, background:'var(--bg3)', padding:'8px 12px', borderRadius:8 }}>
          <span style={{ fontSize:22 }}>{appIcon}</span>
          <div>
            <div style={{ fontSize:11, ...T.mono, color:'var(--cyan)' }}>{app}</div>
            <div style={{ fontSize:12, color:'var(--text2)' }}>To: {recipient}</div>
          </div>
        </div>
        <div style={{ fontSize:13, color:'var(--text)', lineHeight:1.6, background:'var(--bg3)', padding:'10px 12px', borderRadius:8, marginBottom:14, borderLeft:'2px solid var(--cyan)' }}>
          "{message}"
        </div>
        <div style={{ display:'flex', gap:8 }}>
          <button onClick={confirm} style={{ flex:1, padding:'9px 0', borderRadius:8, background:'var(--green)', border:'none', color:'#000', fontFamily:'var(--mono)', fontSize:11, fontWeight:700, cursor:'pointer', letterSpacing:'0.1em' }}>SEND</button>
          <button onClick={clearPendingMessage} style={{ flex:1, padding:'9px 0', borderRadius:8, background:'var(--surface2)', border:'1px solid var(--border)', color:'var(--text2)', fontFamily:'var(--mono)', fontSize:11, cursor:'pointer', letterSpacing:'0.1em' }}>CANCEL</button>
        </div>
      </div>
    </div>
  );
}

// ── Toasts ─────────────────────────────────────────────────────────────────
function Toasts() {
  const { toasts, removeToast } = useZaraStore();
  return (
    <div style={{ position:'fixed', bottom:200, right:12, display:'flex', flexDirection:'column', gap:6, zIndex:9998 }}>
      {toasts.map(t => (
        <div key={t.id} onClick={() => removeToast(t.id)}
          style={{ background:'var(--surface2)', border:'1px solid var(--border2)', borderRadius:8,
            padding:'8px 14px', fontSize:11, ...T.mono, color:'var(--text)',
            cursor:'pointer', animation:'fadeIn 0.2s ease', maxWidth:280,
            borderLeft:`3px solid ${t.type==='error'?'var(--red)':t.type==='success'?'var(--green)':'var(--cyan)'}` }}>
          {t.text}
        </div>
      ))}
    </div>
  );
}

// ── Pygame parity overlay (subtitle + background task pulse) ───────────────
function NeuralPygameOverlay() {
  const { subtitleZara, subtitleUser, bgTaskText } = useZaraStore();
  const [subtitleStartedAt, setSubtitleStartedAt] = useState(0);
  const [tick, setTick] = useState(Date.now());

  useEffect(() => {
    if (subtitleZara || subtitleUser) {
      setSubtitleStartedAt(Date.now());
    }
  }, [subtitleZara, subtitleUser]);

  useEffect(() => {
    const id = setInterval(() => setTick(Date.now()), 100);
    return () => clearInterval(id);
  }, []);

  const subtitleElapsed = subtitleStartedAt ? (tick - subtitleStartedAt) / 1000 : 999;
  const subtitleAlpha = subtitleElapsed <= 5 ? 1 : Math.max(0, 1 - (subtitleElapsed - 5));
  const pulse = 0.55 + 0.45 * Math.sin(tick / 250);

  return (
    <>
      {bgTaskText && (
        <div style={{
          position:'absolute',
          top:18,
          right:20,
          zIndex:6,
          fontFamily:'var(--mono)',
          fontSize:12,
          color:'rgb(120,200,255)',
          opacity:pulse,
          textShadow:'0 0 10px rgba(0,212,255,0.35)',
          pointerEvents:'none',
        }}>
          {bgTaskText}
        </div>
      )}

      {subtitleAlpha > 0 && (subtitleUser || subtitleZara) && (
        <div style={{
          position:'absolute',
          left:'50%',
          bottom:48,
          transform:'translateX(-50%)',
          width:'min(75%, 860px)',
          zIndex:6,
          display:'flex',
          flexDirection:'column',
          gap:8,
          textAlign:'center',
          pointerEvents:'none',
          opacity:subtitleAlpha,
          transition:'opacity 120ms linear',
        }}>
          {subtitleUser && (
            <div style={{
              fontFamily:'var(--sans)',
              fontSize:18,
              color:'rgb(180,255,180)',
              textShadow:'0 2px 8px rgba(0,0,0,0.65)',
              lineHeight:1.3,
              wordBreak:'break-word',
            }}>
              {subtitleUser}
            </div>
          )}
          {subtitleZara && (
            <div style={{
              fontFamily:'var(--sans)',
              fontSize:18,
              color:'rgb(230,240,255)',
              textShadow:'0 2px 8px rgba(0,0,0,0.65)',
              lineHeight:1.3,
              wordBreak:'break-word',
            }}>
              {subtitleZara}
            </div>
          )}
        </div>
      )}
    </>
  );
}

// ── Bottom bar ─────────────────────────────────────────────────────────────
function BottomBar({ onSend }) {
  const [text, setText] = useState('');
  const { liveTranscript, zaraState } = useZaraStore();
  const inputRef = useRef(null);

  const submit = () => {
    const t = text.trim();
    if (!t) return;
    onSend(t);
    setText('');
  };

  return (
    <div style={{ height:'100%', background:'var(--bg2)', borderTop:'1px solid var(--border)', display:'flex', flexDirection:'column' }}>
      {/* Live transcript */}
      <div style={{ padding:'6px 16px 4px', borderBottom:'1px solid var(--border)', minHeight:28 }}>
        <span style={{ fontSize:10, ...T.mono, color:'var(--text3)', letterSpacing:'0.1em' }}>
          {liveTranscript ? (
            <><span style={{ color:'var(--red)', animation:'pulseBlink 1s infinite' }}>●</span>{' '}{liveTranscript}</>
          ) : (
            <span style={{ color:'var(--text3)' }}>Awaiting voice input...</span>
          )}
        </span>
      </div>

      {/* Input row */}
      <div style={{ flex:1, display:'flex', alignItems:'center', padding:'0 12px', gap:8 }}>
        <div style={{ width:8, height:8, borderRadius:'50%', flexShrink:0,
          background: zaraState==='LISTENING'?'var(--red)':'var(--text3)',
          animation: zaraState==='LISTENING'?'pulseBlink 1s infinite':'none' }} />
        <input ref={inputRef} value={text} onChange={e => setText(e.target.value)}
          onKeyDown={e => e.key==='Enter' && submit()}
          placeholder="Type a command or question..."
          style={{ flex:1, background:'transparent', border:'none', outline:'none',
            color:'var(--text)', fontSize:13, fontFamily:'var(--mono)' }} />
        <button onClick={submit}
          style={{ padding:'6px 14px', background:'var(--cyan-dim)', border:'1px solid var(--border2)',
            borderRadius:6, color:'var(--cyan)', fontFamily:'var(--mono)', fontSize:11,
            cursor:'pointer', letterSpacing:'0.08em', flexShrink:0 }}>
          SEND
        </button>
      </div>

      {/* Metrics strip */}
      <div style={{ padding:'4px 16px', borderLeft:'1px solid var(--border)' }}>
        <MetricsSection />
      </div>

      <style>{`@keyframes waveAnim { 0%,100%{height:4px} 50%{height:16px} }`}</style>
    </div>
  );
}

function MetricsSection() {
  const metrics = useZaraStore(s => s.metrics);
  return (
    <div style={{ display:'flex', gap:14, height:24, alignItems:'flex-end', paddingBottom:4 }}>
      {[['CPU',metrics.cpu,80,60],['RAM',metrics.ram,85,70],['GPU',metrics.gpu,90,75],['DISK',metrics.disk,95,85]].map(([n,v,c,w]) => (
        <div key={n} style={{ flex:1 }}>
          <div style={{ display:'flex', justifyContent:'space-between', marginBottom:3 }}>
            <span style={{ fontSize:9, ...T.mono, color:'var(--text3)' }}>{n}</span>
            <span style={{ fontSize:9, ...T.mono, color:v>c?'var(--red)':v>w?'var(--amber)':'var(--cyan)' }}>{v}%</span>
          </div>
          <div style={{ height:3, background:'var(--surface2)', borderRadius:2, overflow:'hidden' }}>
            <div style={{ height:'100%', width:`${v}%`, borderRadius:2, transition:'width 0.5s',
              background:v>c?'var(--red)':v>w?'var(--amber)':'var(--cyan)' }} />
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Sidebar ────────────────────────────────────────────────────────────────
const NAV_ITEMS = [
  { id:'intelligence', icon:'◎', label:'Intel' },
  { id:'windows', icon:'⊞', label:'Windows' },
  { id:'memory', icon:'⬡', label:'Memory' },
  { id:'capabilities', icon:'⟡', label:'Claude' },
  { id:'tools', icon:'⚙', label:'Tools' },
  { id:'settings', icon:'◈', label:'Config' },
];

function Sidebar() {
  const { activePanel, setActivePanel } = useZaraStore();
  return (
    <nav style={{ width:56, background:'var(--bg2)', borderRight:'1px solid var(--border)',
      display:'flex', flexDirection:'column', alignItems:'center', padding:'12px 0', gap:3 }}>
      {NAV_ITEMS.map(({ id, icon, label }) => {
        const active = activePanel===id;
        return (
          <button key={id} title={label} onClick={() => setActivePanel(id)}
            style={{ width:38, height:38, borderRadius:9, display:'flex', alignItems:'center',
              justifyContent:'center', cursor:'pointer',
              border:`1px solid ${active?'var(--border2)':'transparent'}`,
              background: active?'var(--cyan-dim)':'transparent',
              color: active?'var(--cyan)':'var(--text3)',
              fontSize:16, transition:'all 0.2s' }}
            onMouseEnter={e => !active && (e.currentTarget.style.background='var(--surface)')}
            onMouseLeave={e => !active && (e.currentTarget.style.background='transparent')}>
            {icon}
          </button>
        );
      })}
    </nav>
  );
}

// ══════════════════════════════════════════════════════════════════
//  MODE SWITCHER COMPONENTS
// ══════════════════════════════════════════════════════════════════
const ModeButton = ({ mode, icon: Icon, active }) => (
  <motion.button
    whileHover={{ scale: 1.05, boxShadow: '0 0 20px var(--cyan-glow)' }}
    onClick={() => wsSend({ type: 'command', text: `<EXECUTE>{"action": "setup_workspace", "mode": "${mode}"}</EXECUTE>` })}
    style={{ 
      ...T.card, 
      display: 'flex', 
      gap: 10, 
      alignItems: 'center', 
      cursor: 'pointer',
      background: active ? 'var(--cyan-glow)' : 'var(--surface)',
      borderColor: active ? 'var(--cyan)' : 'var(--border)',
      transition: 'all 0.3s ease'
    }}
  >
    <Icon size={16} color={active ? '#fff' : 'var(--cyan)'} />
    <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.05em', color: active ? '#fff' : 'var(--text)' }}>{mode.toUpperCase()}</span>
  </motion.button>
);

// ══════════════════════════════════════════════════════════════════
//  MAIN APP
// ══════════════════════════════════════════════════════════════════
export default function App() {
  const { activePanel, addMessage, setZaraState, addToast, activeMode,
    setPendingMessage, wsConnected, zaraState, orbFrame, metrics, contextCards } = useZaraStore();

  const handleSend = useCallback((text) => {
    addMessage('user', text);
    setZaraState('THINKING');
    wsSend({ type: 'command', text });
  }, [addMessage, setZaraState]);

  return (
    <>
      <style>{GLOBAL_CSS}</style>
      <NeuralHeartbeat />
      <OmniSearch />
      <AutoDebugConsole />
      
      <div style={{ 
        display: 'grid', 
        gridTemplateAreas: `
          "intel core wings"
          "matrix core wings"
          "chat chat wings"
        `,
        gridTemplateColumns: '1fr 1.6fr 1fr',
        gridTemplateRows: '240px 1fr 160px',
        gap: '16px', padding: '16px', height: '100vh', background: T.bg
      }}>
        {/* System Intelligence: Live Sparklines */}
        <motion.div layout style={{ gridArea: 'intel', ...T.glass, padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Cpu size={14} color="var(--cyan)" />
            <span style={T.label}>System Intelligence</span>
          </div>
          <IntelPanel /> 
        </motion.div>

        {/* System Matrix: Real-time Window Tracking */}
        <motion.div layout style={{ gridArea: 'matrix', ...T.glass, padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Layers size={14} color="var(--cyan)" />
            <span style={T.label}>System Matrix</span>
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
            <WindowMatrix />
          </div>
        </motion.div>

        {/* The Brain: Reactive 3D Core */}
        <div style={{ gridArea: 'core', position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
          {orbFrame ? (
            <motion.img
              src={`data:image/png;base64,${orbFrame}`}
              animate={{ scale: zaraState === 'TALKING' ? [1, 1.05, 1] : 1 }}
              transition={{ duration: 0.5, repeat: Infinity }}
              style={{ width: 'min(70vh, 90%)', height: 'min(70vh, 90%)', objectFit: 'contain' }}
            />
          ) : <NeuralSphere />}
          
          <NeuralPygameOverlay />
          <SubtitleOverlay />
          
          <div style={{ position: 'absolute', bottom: 40, width: '100%', display: 'flex', justifyContent: 'center', gap: 12 }}>
            <ModeButton mode="coding" icon={Code} active={activeMode === 'coding'} />
            <ModeButton mode="logistics" icon={Package} active={activeMode === 'logistics'} />
            <ModeButton mode="study" icon={GraduationCap} active={activeMode === 'study'} />
          </div>
        </div>

        {/* The Wing: Multimodal Context History */}
        <motion.div layout style={{ gridArea: 'wings', ...T.glass, padding: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <Database size={14} color="var(--magenta)" />
            <span style={T.label}>Context Wing</span>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 12 }}>
            <ContextWing />
            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12 }}>
              <AgentTimeline />
            </div>
          </div>
        </motion.div>

        {/* Command Center: Unified Input */}
        <motion.div layout style={{ gridArea: 'chat', ...T.glass, padding: '10px 24px', justifyContent: 'center' }}>
          <BottomBar onSend={handleSend} />
        </motion.div>
      </div>

      <MessageConfirmDialog />
      <Toasts />
    </>
  );
}

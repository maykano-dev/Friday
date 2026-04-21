import React, { useState, useEffect, useRef, useCallback } from 'react';
import TitleBar from './components/TitleBar';
import NeuralSphere from './components/NeuralSphere';
import { useZaraStore, wsSend } from './store/zaraStore';

// ── CSS Variables injected globally ───────────────────────────────
const GLOBAL_CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;500;600;700;800&display=swap');
  * { margin:0; padding:0; box-sizing:border-box; }
  :root {
    --bg:#060810; --bg2:#0b0e1a; --bg3:#111627;
    --surface:#141b2d; --surface2:#1c2540;
    --border:rgba(0,212,255,0.12); --border2:rgba(0,212,255,0.25);
    --cyan:#00d4ff; --cyan-dim:rgba(0,212,255,0.13); --cyan-glow:rgba(0,212,255,0.3);
    --green:#00ff9d; --green-dim:rgba(0,255,157,0.1);
    --amber:#ffb547; --amber-dim:rgba(255,181,71,0.1);
    --red:#ff4d6a; --red-dim:rgba(255,77,106,0.1);
    --purple:#b47dff; --purple-dim:rgba(180,125,255,0.1);
    --text:#e8eaf6; --text2:#7b8ab8; --text3:#4a567a;
    --mono:'Space Mono',monospace; --sans:'Syne',sans-serif;
    font-family: var(--sans);
  }
  html,body,#root { height:100%; background:var(--bg); color:var(--text); overflow:hidden; }
  ::-webkit-scrollbar { width:3px; } ::-webkit-scrollbar-thumb { background:var(--border2); border-radius:2px; }
  input,button,select { font-family:inherit; }
  @keyframes fadeIn { from{opacity:0;transform:translateY(4px)} to{opacity:1;transform:translateY(0)} }
  @keyframes pulseBlink { 0%,100%{opacity:1} 50%{opacity:0.3} }
`;

// ── Tokens / mini DS ──────────────────────────────────────────────
const T = {
  card: { background:'var(--surface)', border:'1px solid var(--border)', borderRadius:8, padding:'12px' },
  label: { fontSize:9, fontFamily:'var(--mono)', letterSpacing:'0.15em', color:'var(--text3)', textTransform:'uppercase', marginBottom:6, display:'block' },
  mono: { fontFamily:'var(--mono)' },
};

// ── Capability groups for Claude-powered features ─────────────────
const CAPABILITY_GROUPS = [
  {
    group: 'Reasoning & Analysis',
    color: '#00d4ff',
    items: [
      'Multi-step logical reasoning and deduction',
      'Hypothesis testing and validation',
      'Root cause analysis and debugging',
      'Pattern recognition across domains',
      'Causal inference and argument evaluation',
      'Mathematical proofs and derivations',
      'Statistical analysis and interpretation',
    ],
  },
  {
    group: 'Code & Engineering',
    color: '#00ff9d',
    items: [
      'Code generation in 40+ languages',
      'Full-stack app architecture and scaffolding',
      'Code review, refactoring, and optimization',
      'Bug detection and autonomous fixing (verified_execute)',
      'Unit test and integration test writing',
      'API design and documentation',
      'Database schema design and query optimization',
      'Security vulnerability analysis (CVE lookup)',
      'Shell scripts and automation',
      'Regex, parsing, data transformation',
    ],
  },
  {
    group: 'Web & Research',
    color: '#b47dff',
    items: [
      'Real-time web search (DuckDuckGo, Wikipedia)',
      'Multi-source research synthesis',
      'Playwright-powered stealth web browsing',
      'Form filling and web automation',
      'News aggregation (Hacker News, DEV.to)',
      'Weather, crypto, exchange rate lookups',
      'GitHub, NPM, PyPI package information',
      'CVE security database queries',
      'Country, university, and public holiday data',
      'URL shortening and QR code generation',
    ],
  },
  {
    group: 'Vision & Multimodal',
    color: '#ffb547',
    items: [
      'Screen reading and OCR (pytesseract)',
      'Error detection from screenshots',
      'Vision-guided UI automation (Moondream)',
      'Image analysis and description',
      'Document and PDF understanding',
      'Code screenshot reading and execution',
      'Camera feed analysis',
      'Visual context for task assistance',
    ],
  },
  {
    group: 'Writing & Communication',
    color: '#ff9d6a',
    items: [
      'Long-form creative writing and storytelling',
      'Technical documentation generation',
      'Email and message drafting',
      'Summarization at any length',
      'Translation across 100+ languages',
      'Tone and style adaptation',
      'Proofreading and editing',
      'Report and proposal writing',
      'Social media copy',
      'Persuasive and argumentative writing',
    ],
  },
  {
    group: 'Math & Science',
    color: '#00ffce',
    items: [
      'Algebra, calculus, linear algebra',
      'Statistics and probability',
      'Physics, chemistry, biology explanations',
      'Unit conversion and formula application',
      'Data science and ML concept guidance',
      'Symbolic computation guidance',
      'Engineering calculations',
    ],
  },
  {
    group: 'Memory & Context',
    color: '#ff4d6a',
    items: [
      'SQLite-backed long-term memory vault',
      'ChromaDB semantic vector search',
      'Keyword-extracted memory indexing',
      'Session persistence across restarts',
      'Context-aware proactive suggestions',
      'Learning from past code failures',
      'User preference tracking',
    ],
  },
  {
    group: 'System & Automation',
    color: '#7b8ab8',
    items: [
      'File creation, editing, and organization',
      'Script execution with sandboxing',
      'App launching and window management',
      'Multi-agent orchestration (planner → coder → reviewer)',
      'Background task management',
      'Volume control (silent, no OSD)',
      'Media playback control',
      'Screenshot capture',
      'Clipboard reading and processing',
    ],
  },
  {
    group: 'Messaging & Communication',
    color: '#00d4ff',
    items: [
      'WhatsApp message sending with confirmation',
      'Telegram, Discord, Slack, Teams integration',
      'Email via Gmail / Outlook',
      'SMS via Windows Phone Link',
      'Universal messaging with UI automation',
      'Message confirmation before sending',
    ],
  },
];

// ══════════════════════════════════════════════════════════════════
//  PANEL COMPONENTS
// ══════════════════════════════════════════════════════════════════

function IntelPanel() {
  const { zaraState, speakerContext, bgDetectionEnabled, setBgDetectionEnabled,
    conversation, metrics, volume, isMuted, setVolume, wsConnected } = useZaraStore();

  const convRef = useRef(null);
  useEffect(() => {
    if (convRef.current) convRef.current.scrollTop = convRef.current.scrollHeight;
  }, [conversation]);

  const stateColors = {
    STANDBY:'#0060ff', LISTENING:'#ff2244', THINKING:'#00d4ff',
    TALKING:'#00ff9d', EXECUTING:'#ffb547'
  };

  return (
    <div style={{ padding:12, display:'flex', flexDirection:'column', gap:8 }}>
      {/* State */}
      <div style={T.card}>
        <span style={T.label}>Current State</span>
        <div style={{ ...T.mono, fontSize:20, fontWeight:700, color: stateColors[zaraState] || '#00d4ff', lineHeight:1 }}>
          {zaraState}
        </div>
        <div style={{ fontSize:11, color:'var(--text2)', marginTop:4, ...T.mono }}>
          {zaraState === 'STANDBY' ? 'Awaiting input' :
           zaraState === 'LISTENING' ? 'Transcribing speech...' :
           zaraState === 'THINKING' ? 'Processing query...' :
           zaraState === 'TALKING' ? 'Speaking response...' : 'Executing task...'}
        </div>
      </div>

      {/* Volume */}
      <VolumeCard volume={volume} isMuted={isMuted} setVolume={setVolume} />

      {/* Speaker detection */}
      <div style={T.card}>
        <span style={T.label}>Speaker Detection</span>
        <div style={{ display:'flex', alignItems:'center', gap:6, padding:'6px 10px', background:'var(--bg3)', borderRadius:6, border:'1px solid var(--border)' }}>
          <div style={{
            width:6, height:6, borderRadius:'50%', flexShrink:0,
            background: speakerContext === 'direct' ? 'var(--green)' :
                        speakerContext === 'background' ? 'var(--amber)' : 'var(--text3)',
            animation: speakerContext !== 'none' ? 'pulseBlink 1.5s infinite' : 'none',
          }} />
          <span style={{ fontSize:10, ...T.mono, color:'var(--text2)' }}>
            {speakerContext === 'direct' ? 'Direct address detected' :
             speakerContext === 'background' ? 'Background speech — ignoring' : 'Monitoring...'}
          </span>
        </div>
        <Toggle label="BG Detection" value={bgDetectionEnabled} onChange={setBgDetectionEnabled} />
      </div>

      {/* System metrics */}
      <div style={T.card}>
        <span style={T.label}>System Metrics</span>
        <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
          {[['CPU', metrics.cpu, 80, 60], ['RAM', metrics.ram, 85, 70], ['GPU', metrics.gpu, 90, 75]].map(([name, val, critT, warnT]) => (
            <MetricBar key={name} name={name} value={val} critThreshold={critT} warnThreshold={warnT} />
          ))}
        </div>
      </div>

      {/* Conversation */}
      <div style={{ ...T.card, maxHeight:240 }}>
        <span style={T.label}>Conversation</span>
        <div ref={convRef} style={{ overflowY:'auto', maxHeight:190, display:'flex', flexDirection:'column', gap:5 }}>
          {conversation.map((msg) => (
            <div key={msg.id} style={{ display:'flex', flexDirection:'column', gap:2, animation:'fadeIn 0.2s ease' }}>
              <div style={{ fontSize:9, ...T.mono, letterSpacing:'0.1em', textTransform:'uppercase',
                color: msg.role === 'user' ? 'var(--green)' : 'var(--cyan)' }}>
                {msg.role === 'user' ? 'YOU' : 'ZARA'}
              </div>
              <div style={{ fontSize:11, color:'var(--text2)', lineHeight:1.5,
                background:'var(--bg3)', padding:'5px 8px', borderRadius:5,
                borderLeft:`2px solid ${msg.role === 'user' ? 'var(--green)' : 'var(--cyan)'}` }}>
                {msg.text}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function WindowsPanel() {
  const { openWindows, minimizedWindows, addMessage, setZaraState, addToast } = useZaraStore();
  const [windowList, setWindowList] = useState([
    { name: 'Google Chrome', state: 'active', process: 'chrome.exe' },
    { name: 'Visual Studio Code', state: 'active', process: 'code.exe' },
    { name: 'Spotify', state: 'active', process: 'spotify.exe' },
    { name: 'Windows Explorer', state: 'minimized', process: 'explorer.exe' },
    { name: 'Slack', state: 'minimized', process: 'slack.exe' },
    { name: 'Discord', state: 'active', process: 'discord.exe' },
    { name: 'Windows Terminal', state: 'active', process: 'wt.exe' },
  ]);

  const active = windowList.filter(w => w.state === 'active');
  const minimized = windowList.filter(w => w.state === 'minimized');

  const windowCmd = (cmd) => {
    setZaraState('THINKING');
    addMessage('user', cmd);
    setTimeout(() => {
      addMessage('zara', `Window command executed: ${cmd}`);
      addToast(`✓ ${cmd}`);
      setZaraState('STANDBY');
    }, 600);
  };

  return (
    <div style={{ padding:12, display:'flex', flexDirection:'column', gap:8 }}>
      <div style={T.card}>
        <span style={T.label}>Active Windows ({active.length})</span>
        {active.map(w => (
          <WindowItem key={w.name} window={w} onAction={(act) => windowCmd(`${act} ${w.name}`)} />
        ))}
      </div>

      <div style={T.card}>
        <span style={T.label}>Minimized to Taskbar ({minimized.length})</span>
        {minimized.length ? minimized.map(w => (
          <WindowItem key={w.name} window={w} minimized onAction={(act) => windowCmd(`${act} ${w.name}`)} />
        )) : <span style={{ fontSize:11, color:'var(--text3)', ...T.mono }}>No minimized windows</span>}
      </div>

      <div style={T.card}>
        <span style={T.label}>Quick Commands</span>
        <div style={{ display:'flex', flexWrap:'wrap', gap:5 }}>
          {['Minimize all', 'Show desktop', 'Restore all', 'Snap left', 'Snap right', 'Maximize', 'List windows'].map(cmd => (
            <QABtn key={cmd} onClick={() => windowCmd(cmd)}>{cmd}</QABtn>
          ))}
        </div>
      </div>
    </div>
  );
}

function MemoryPanel() {
  const { recentMemories, memoryStats } = useZaraStore();
  const demo = [
    { tag:'preference', text:'User prefers dark mode interfaces', time:'2m ago' },
    { tag:'task', text:'Working on Python data analysis script', time:'15m ago' },
    { tag:'personal', text:'Music app preference: Spotify', time:'1h ago' },
    { tag:'insight', text:'User frequently asks about crypto prices', time:'3h ago' },
    { tag:'learning', text:'Code fix: missing import in sandbox_py', time:'5h ago' },
  ];

  return (
    <div style={{ padding:12, display:'flex', flexDirection:'column', gap:8 }}>
      <div style={{ ...T.card, display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
        {[['Stored', '2,847', 'var(--cyan)'], ['Semantic', '412', 'var(--green)'],
          ['Sessions', '38', 'var(--purple)'], ['Insights', '12', 'var(--amber)']].map(([label, val, color]) => (
          <div key={label} style={{ background:'var(--bg3)', border:'1px solid var(--border)', borderRadius:6, padding:8 }}>
            <span style={{ ...T.label, marginBottom:3 }}>{label}</span>
            <div style={{ ...T.mono, fontSize:18, fontWeight:700, color }}>{val}</div>
          </div>
        ))}
      </div>

      <div style={T.card}>
        <span style={T.label}>Recent Memories</span>
        {demo.map((m, i) => (
          <div key={i} style={{ background:'var(--bg3)', border:'1px solid var(--border)', borderRadius:6, padding:8, marginBottom:5 }}>
            <div style={{ fontSize:9, ...T.mono, color:'var(--purple)', letterSpacing:'0.1em', textTransform:'uppercase', marginBottom:2 }}>{m.tag}</div>
            <div style={{ fontSize:11, color:'var(--text2)', lineHeight:1.5 }}>{m.text}</div>
            <div style={{ fontSize:9, ...T.mono, color:'var(--text3)', marginTop:3, textAlign:'right' }}>{m.time}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function CapabilitiesPanel() {
  const [expanded, setExpanded] = useState(null);

  return (
    <div style={{ padding:12, display:'flex', flexDirection:'column', gap:6 }}>
      <div style={{ fontSize:10, ...T.mono, color:'var(--text2)', lineHeight:1.7,
        background:'var(--surface)', border:'1px solid var(--border)', borderRadius:8, padding:10, marginBottom:4 }}>
        Zara is powered by Claude (Anthropic). All of Claude's core capabilities are available through Zara's voice and text interface.
      </div>

      {CAPABILITY_GROUPS.map((group) => (
        <div key={group.group} style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:8, overflow:'hidden' }}>
          <button
            onClick={() => setExpanded(expanded === group.group ? null : group.group)}
            style={{
              width:'100%', padding:'9px 12px',
              display:'flex', alignItems:'center', justifyContent:'space-between',
              background:'transparent', border:'none', cursor:'pointer',
              color:'var(--text)', textAlign:'left',
            }}
          >
            <div style={{ display:'flex', alignItems:'center', gap:8 }}>
              <div style={{ width:7, height:7, borderRadius:'50%', background:group.color, flexShrink:0 }} />
              <span style={{ fontSize:12, fontWeight:600, color:group.color }}>{group.group}</span>
              <span style={{ fontSize:10, ...T.mono, color:'var(--text3)' }}>{group.items.length}</span>
            </div>
            <span style={{ color:'var(--text3)', fontSize:12 }}>{expanded === group.group ? '▲' : '▼'}</span>
          </button>
          {expanded === group.group && (
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

function ToolsPanel() {
  const { addMessage, setZaraState, addToast, setPendingMessage } = useZaraStore();

  const runTool = (cmd) => {
    setZaraState('THINKING');
    addMessage('user', cmd);
    setTimeout(() => {
      addMessage('zara', `Processing: "${cmd}"`);
      addToast(cmd.substring(0, 50));
      setZaraState('STANDBY');
    }, 700);
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
        {
          label: 'Web Research', color:'var(--cyan)',
          actions: ['Latest AI news', 'Hacker News today', 'Bitcoin price', 'Weather in London', 'GitHub user torvalds', 'Search for quantum computing'],
        },
        {
          label: 'Messaging', color:'var(--green)',
          actions: ['Open WhatsApp', 'Open Telegram', 'Open Discord', 'Open Slack'],
          extra: <QABtn onClick={demoMsgConfirm} style={{ marginTop:6 }}>Demo: Message Confirm</QABtn>,
        },
        {
          label: 'System', color:'var(--amber)',
          actions: ['Take a screenshot', 'System status', 'What is my IP?', 'Time in Tokyo', 'Shorten URL', 'Generate QR code'],
        },
        {
          label: 'Knowledge', color:'var(--purple)',
          actions: ['Define serendipity', 'Synonyms for happy', 'Tell me about France', 'NASA picture today', 'Recipe for carbonara', 'Number fact about 42'],
        },
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
          {[
            '"Send a message to John on WhatsApp saying hi"',
            '"Volume to 40 percent"',
            '"Play Stonebwoy on Spotify"',
            '"Snap Chrome to the left"',
            '"What windows are open?"',
            '"Search for React best practices"',
            '"Take a screenshot"',
            '"Define obfuscation"',
            '"Remind me to call mom in 30 minutes"',
            '"Write a Python script to sort a CSV"',
          ].map(ex => <div key={ex} style={{ color:'var(--text2)' }}>{ex}</div>)}
        </div>
      </div>
    </div>
  );
}

function SettingsPanel() {
  const { gender, setGender, resetGender, honorific,
    alwaysOnTop, setAlwaysOnTop, mediaDucking, setMediaDucking,
    bgDetectionEnabled, setBgDetectionEnabled, apiHealth } = useZaraStore();

  const isElectron = window.electron?.isElectron;

  const handleAlwaysOnTop = (v) => {
    setAlwaysOnTop(v);
    if (isElectron) window.electron.alwaysOnTop(v);
  };

  return (
    <div style={{ padding:12, display:'flex', flexDirection:'column', gap:8 }}>
      {/* User profile */}
      <div style={T.card}>
        <span style={T.label}>User Profile</span>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:6, marginBottom:8 }}>
          {[['Honorific', honorific, 'var(--purple)'], ['Gender', gender === 'unknown' ? 'Detecting' : gender, 'var(--green)']].map(([l, v, c]) => (
            <div key={l} style={{ background:'var(--bg3)', border:'1px solid var(--border)', borderRadius:6, padding:8 }}>
              <span style={T.label}>{l}</span>
              <div style={{ ...T.mono, fontSize:13, color:c }}>{v}</div>
            </div>
          ))}
        </div>
        <div style={{ display:'flex', gap:6 }}>
          <QABtn onClick={() => setGender('male')}>♂ Male</QABtn>
          <QABtn onClick={() => setGender('female')}>♀ Female</QABtn>
          <QABtn onClick={resetGender}>⟳ Reset</QABtn>
        </div>
      </div>

      {/* API health */}
      <div style={T.card}>
        <span style={T.label}>API Health</span>
        <div style={{ display:'flex', flexDirection:'column', gap:5 }}>
          {Object.entries(apiHealth).map(([key, status]) => (
            <div key={key} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'4px 0' }}>
              <span style={{ fontSize:11, ...T.mono, color:'var(--text2)' }}>{key}</span>
              <span style={{ fontSize:10, ...T.mono,
                color: status === 'online' ? 'var(--green)' : status === 'checking' ? 'var(--amber)' : 'var(--text3)' }}>
                {status.toUpperCase()}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Toggles */}
      <div style={T.card}>
        <span style={T.label}>Options</span>
        <Toggle label="Always on Top" value={alwaysOnTop} onChange={handleAlwaysOnTop} />
        <Toggle label="Media Ducking" value={mediaDucking} onChange={setMediaDucking} />
        <Toggle label="Background Detection" value={bgDetectionEnabled} onChange={setBgDetectionEnabled} />
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════
//  SHARED SUB-COMPONENTS
// ══════════════════════════════════════════════════════════════════

function VolumeCard({ volume, isMuted, setVolume }) {
  const bars = Array.from({ length: 20 }, (_, i) => i);
  const litCount = Math.round(volume / 100 * 20);

  const handleVolumeChange = (v) => {
    setVolume(v);
    wsSend({ type: 'volume', level: v });
  };

  return (
    <div style={T.card}>
      <span style={T.label}>Volume Control</span>
      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:6 }}>
        <span style={{ fontSize:11, ...T.mono, color:'var(--text2)' }}>System Audio</span>
        <span style={{ ...T.mono, fontSize:13, color: isMuted ? 'var(--red)' : 'var(--cyan)' }}>
          {isMuted ? 'MUTED' : `${volume}%`}
        </span>
      </div>
      <input
        type="range" min={0} max={100} value={volume}
        onChange={e => handleVolumeChange(+e.target.value)}
        style={{ width:'100%', height:4, accentColor:'var(--cyan)', cursor:'pointer', marginBottom:8 }}
      />
      <div style={{ display:'flex', gap:2, height:16 }}>
        {bars.map(i => (
          <div key={i} style={{
            flex:1, borderRadius:2,
            background: i < litCount ? (i >= 16 ? 'var(--amber)' : 'var(--cyan)') : 'var(--surface2)',
            transition:'background 0.1s',
          }} />
        ))}
      </div>
    </div>
  );
}

function MetricBar({ name, value, critThreshold, warnThreshold }) {
  const color = value > critThreshold ? 'var(--red)' : value > warnThreshold ? 'var(--amber)' : 'var(--cyan)';
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

function WindowItem({ window: w, minimized, onAction }) {
  return (
    <div style={{ display:'flex', alignItems:'center', gap:8, padding:'5px 8px',
      background:'var(--bg3)', border:'1px solid var(--border)',
      borderRadius:6, marginBottom:4, cursor:'pointer',
      transition:'border-color 0.2s' }}
      onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--border2)'}
      onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
    >
      <div style={{ width:7, height:7, borderRadius:2, background: minimized ? 'var(--text3)' : 'var(--cyan)', flexShrink:0 }} />
      <div style={{ fontSize:11, ...T.mono, color: minimized ? 'var(--text2)' : 'var(--text)', flex:1,
        overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{w.name}</div>
      <div style={{ display:'flex', gap:3 }}>
        {minimized
          ? <QABtn onClick={() => onAction('Restore')}>↑</QABtn>
          : <>
              <QABtn onClick={() => onAction('Minimize')}>⊟</QABtn>
              <QABtn onClick={() => onAction('Focus')}>⊞</QABtn>
            </>
        }
      </div>
    </div>
  );
}

function Toggle({ label, value, onChange }) {
  return (
    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'6px 0' }}>
      <span style={{ fontSize:11, ...T.mono, color:'var(--text2)' }}>{label}</span>
      <div
        onClick={() => onChange(!value)}
        style={{ width:32, height:18, borderRadius:9, cursor:'pointer',
          background: value ? 'var(--cyan)' : 'var(--surface2)',
          position:'relative', transition:'background 0.2s', flexShrink:0 }}
      >
        <div style={{ width:14, height:14, borderRadius:'50%', background:'#fff',
          position:'absolute', top:2, left: value ? 16 : 2, transition:'left 0.2s' }} />
      </div>
    </div>
  );
}

function QABtn({ onClick, children, style: extra }) {
  const [hover, setHover] = useState(false);
  return (
    <button onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{ fontSize:10, ...T.mono, cursor:'pointer', padding:'4px 8px', borderRadius:4,
        background: hover ? 'var(--cyan-dim)' : 'var(--surface)',
        border:`1px solid ${hover ? 'var(--border2)' : 'var(--border)'}`,
        color: hover ? 'var(--cyan)' : 'var(--text2)',
        transition:'all 0.15s', whiteSpace:'nowrap', ...extra }}>
      {children}
    </button>
  );
}

function WsStatusDot() {
  const wsConnected = useZaraStore(s => s.wsConnected);
  return (
    <div style={{ display:'flex', alignItems:'center', gap:5 }}>
      <div style={{
        width:6, height:6, borderRadius:'50%',
        background: wsConnected ? 'var(--green)' : 'var(--red)',
        animation: wsConnected ? 'pulseBlink 2s infinite' : 'none',
        flexShrink:0,
      }} />
      <span style={{ fontSize:9, ...T.mono, color:'var(--text3)' }}>
        {wsConnected ? 'BACKEND LIVE' : 'BACKEND OFFLINE'}
      </span>
    </div>
  );
}

// ── Message Confirmation Dialog ───────────────────────────────────
function MessageConfirmDialog() {
  const { pendingMessage, clearPendingMessage, addMessage, addToast, setZaraState } = useZaraStore();
  if (!pendingMessage) return null;

  const confirm = () => {
    clearPendingMessage();
    addMessage('zara', `Message sent to ${pendingMessage.recipient} via ${pendingMessage.app}.`);
    addToast(`✓ Sent to ${pendingMessage.recipient}`);
  };
  const cancel = () => {
    clearPendingMessage();
    addMessage('zara', 'Message cancelled.');
    addToast('Message cancelled');
  };

  return (
    <div style={{ position:'fixed', inset:0, background:'rgba(6,8,16,0.85)', backdropFilter:'blur(4px)',
      zIndex:500, display:'flex', alignItems:'center', justifyContent:'center' }}
      onClick={e => { if (e.target === e.currentTarget) cancel(); }}>
      <div style={{ background:'var(--surface)', border:'1px solid var(--border2)', borderRadius:12,
        padding:24, maxWidth:480, width:'90%', animation:'fadeIn 0.25s ease' }}>
        <div style={{ fontSize:10, ...T.mono, letterSpacing:'0.15em', color:'var(--amber)', textTransform:'uppercase', marginBottom:12 }}>
          ⚡ Confirm Message
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:12 }}>
          <div style={{ width:28, height:28, borderRadius:6, background:'var(--cyan-dim)',
            border:'1px solid var(--border2)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:14 }}>
            {pendingMessage.appIcon}
          </div>
          <span style={{ ...T.mono, fontSize:13, color:'var(--cyan)' }}>{pendingMessage.app}</span>
          <span style={{ ...T.mono, fontSize:11, color:'var(--text3)' }}>→</span>
          <span style={{ ...T.mono, fontSize:13, color:'var(--green)' }}>{pendingMessage.recipient}</span>
        </div>
        <div style={{ background:'var(--bg3)', border:'1px solid var(--border)', borderRadius:8,
          padding:12, fontSize:13, color:'var(--text)', lineHeight:1.6, marginBottom:16,
          borderLeft:'3px solid var(--cyan)' }}>
          {pendingMessage.message}
        </div>
        <div style={{ display:'flex', gap:10 }}>
          <button onClick={cancel} style={{ flex:1, padding:10, borderRadius:8,
            border:'1px solid rgba(255,77,106,0.3)', background:'var(--red-dim)',
            color:'var(--red)', ...T.mono, fontSize:12, cursor:'pointer', textTransform:'uppercase', letterSpacing:'0.05em' }}>
            ✕ Cancel
          </button>
          <button onClick={confirm} style={{ flex:1, padding:10, borderRadius:8,
            border:'1px solid var(--border2)', background:'var(--cyan-dim)',
            color:'var(--cyan)', ...T.mono, fontSize:12, cursor:'pointer', textTransform:'uppercase', letterSpacing:'0.05em' }}>
            ✓ Send It
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Toast Container ───────────────────────────────────────────────
function Toasts() {
  const toasts = useZaraStore(s => s.toasts);
  return (
    <div style={{ position:'fixed', bottom:220, right:340, display:'flex', flexDirection:'column', gap:5, zIndex:400, pointerEvents:'none' }}>
      {toasts.map(t => (
        <div key={t.id} style={{ background:'var(--surface2)', border:'1px solid var(--border2)',
          borderRadius:7, padding:'7px 12px', fontSize:11, ...T.mono, color:'var(--text)',
          animation:'fadeIn 0.25s ease', maxWidth:280 }}>
          {t.text}
        </div>
      ))}
    </div>
  );
}

// ── Bottom Bar: Transcript + Mic + Metrics ────────────────────────
function BottomBar({ onSend }) {
  const { micActive, setMicActive, liveTranscript, transcriptHistory, setZaraState, addMessage } = useZaraStore();
  const [input, setInput] = useState('');

  const toggleMic = () => {
    const next = !micActive;
    setMicActive(next);
    setZaraState(next ? 'LISTENING' : 'STANDBY');
  };

  const send = () => {
    if (!input.trim()) return;
    onSend(input.trim());
    setInput('');
  };

  return (
    <div style={{ display:'grid', gridTemplateColumns:'1fr auto 1fr',
      height:'100%', borderTop:'1px solid var(--border)', background:'var(--bg2)' }}>
      {/* Transcript */}
      <div style={{ padding:'10px 16px', borderRight:'1px solid var(--border)', overflow:'hidden' }}>
        <div style={{ ...T.label }}>Live Transcript</div>
        <div style={{ display:'flex', flexDirection:'column', justifyContent:'flex-end', gap:2, height:'calc(100% - 20px)' }}>
          {[...transcriptHistory.slice(-2), liveTranscript || 'Waiting for speech...'].map((line, i, arr) => (
            <div key={i} style={{ fontSize: i === arr.length - 1 ? 12 : 11, ...T.mono,
              color: i === arr.length - 1 ? 'var(--text)' : 'var(--text3)',
              overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
              opacity: i === arr.length - 1 ? 1 : 0.5 + i * 0.2 }}>
              {line}
            </div>
          ))}
        </div>
      </div>

      {/* Mic + input */}
      <div style={{ display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', gap:6, padding:'8px 20px' }}>
        <button
          onClick={toggleMic}
          style={{ width:48, height:48, borderRadius:'50%',
            border: micActive ? '2px solid var(--red)' : '2px solid var(--border2)',
            background: micActive ? 'var(--red-dim)' : 'var(--surface)',
            cursor:'pointer', display:'flex', alignItems:'center', justifyContent:'center',
            boxShadow: micActive ? '0 0 0 8px rgba(255,77,106,0.15)' : 'none',
            transition:'all 0.2s' }}>
          <svg width={20} height={20} viewBox="0 0 24 24" fill="none" stroke={micActive ? 'var(--red)' : 'var(--text2)'} strokeWidth={1.5} strokeLinecap="round">
            <path d="M12 2a3 3 0 013 3v6a3 3 0 01-6 0V5a3 3 0 013-3z"/>
            <path d="M19 10v1a7 7 0 01-14 0v-1"/><line x1="12" y1="18" x2="12" y2="22"/>
            <line x1="8" y1="22" x2="16" y2="22"/>
          </svg>
        </button>
        {/* Waveform */}
        <div style={{ display:'flex', alignItems:'center', gap:2, height:16 }}>
          {Array.from({length:9}, (_,i) => (
            <div key={i} style={{ width:3, height: micActive ? undefined : 4, borderRadius:2,
              background: micActive ? 'var(--cyan)' : 'var(--text3)',
              animation: micActive ? `waveAnim 0.6s ease-in-out infinite ${i * 0.08}s` : 'none' }} />
          ))}
        </div>
        {/* Text input */}
        <div style={{ display:'flex', gap:5, width:260 }}>
          <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()}
            placeholder="Type a command..."
            style={{ flex:1, background:'rgba(11,14,26,0.95)', border:'1px solid var(--border2)',
              borderRadius:7, padding:'7px 10px', color:'var(--text)', ...T.mono, fontSize:12, outline:'none' }} />
          <button onClick={send} style={{ width:34, height:34, borderRadius:7, background:'var(--cyan-dim)',
            border:'1px solid var(--border2)', cursor:'pointer', display:'flex', alignItems:'center', justifyContent:'center' }}>
            <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="var(--cyan)" strokeWidth={2} strokeLinecap="round">
              <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </div>
        {/* WS connection status */}
        <WsStatusDot />
      </div>

      {/* System metrics */}
      <div style={{ padding:'10px 16px', borderLeft:'1px solid var(--border)' }}>
        <div style={T.label}>System Metrics</div>
        <MetricsSection />
      </div>

      <style>{`
        @keyframes waveAnim { 0%,100%{height:4px} 50%{height:16px} }
      `}</style>
    </div>
  );
}

function MetricsSection() {
  const metrics = useZaraStore(s => s.metrics);
  return (
    <div style={{ display:'flex', gap:14, height:'calc(100% - 20px)', alignItems:'flex-end', paddingBottom:4 }}>
      {[['CPU', metrics.cpu, 80, 60], ['RAM', metrics.ram, 85, 70], ['GPU', metrics.gpu, 90, 75], ['DISK', metrics.disk, 95, 85]].map(([n, v, c, w]) => (
        <div key={n} style={{ flex:1 }}>
          <div style={{ display:'flex', justifyContent:'space-between', marginBottom:3 }}>
            <span style={{ fontSize:9, ...T.mono, color:'var(--text3)' }}>{n}</span>
            <span style={{ fontSize:9, ...T.mono, color: v>c?'var(--red)':v>w?'var(--amber)':'var(--cyan)' }}>{v}%</span>
          </div>
          <div style={{ height:3, background:'var(--surface2)', borderRadius:2, overflow:'hidden' }}>
            <div style={{ height:'100%', width:`${v}%`, borderRadius:2, transition:'width 0.5s',
              background: v>c?'var(--red)':v>w?'var(--amber)':'var(--cyan)' }} />
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Sidebar ───────────────────────────────────────────────────────
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
        const active = activePanel === id;
        return (
          <button key={id} title={label} onClick={() => setActivePanel(id)}
            style={{ width:38, height:38, borderRadius:9, display:'flex', alignItems:'center',
              justifyContent:'center', cursor:'pointer', border:`1px solid ${active ? 'var(--border2)' : 'transparent'}`,
              background: active ? 'var(--cyan-dim)' : 'transparent',
              color: active ? 'var(--cyan)' : 'var(--text3)',
              fontSize:16, transition:'all 0.2s' }}
            onMouseEnter={e => !active && (e.currentTarget.style.background = 'var(--surface)')}
            onMouseLeave={e => !active && (e.currentTarget.style.background = 'transparent')}>
            {icon}
          </button>
        );
      })}
    </nav>
  );
}

// ══════════════════════════════════════════════════════════════════
//  MAIN APP
// ══════════════════════════════════════════════════════════════════
export default function App() {
  const { activePanel, addMessage, setZaraState, addToast,
    setMetrics, setApiHealth, setPendingMessage } = useZaraStore();

  // Simulate metrics polling
  useEffect(() => {
    const id = setInterval(() => {
      setMetrics({
        cpu: Math.round(15 + Math.random() * 45),
        ram: Math.round(48 + Math.random() * 28),
        gpu: Math.round(5 + Math.random() * 35),
        disk: Math.round(20 + Math.random() * 20),
      });
    }, 2500);
    return () => clearInterval(id);
  }, [setMetrics]);

  // Simulate API health checks
  useEffect(() => {
    setTimeout(() => setApiHealth({ groq: 'online', deepgram: 'online' }), 1200);
    setTimeout(() => setApiHealth({ elevenlabs: 'offline' }), 1800);
    setTimeout(() => setApiHealth({ ollama: 'offline' }), 2000);
  }, []);

  const handleSend = useCallback((text) => {
    // Detect gender from input
    const tl = text.toLowerCase();
    if (/\bi('m| am) a (man|guy|male)\b/.test(tl)) {
      useZaraStore.getState().setGender('male');
      wsSend({ type: 'gender', value: 'male' });
      addToast('Honorific updated: Sir');
    } else if (/\bi('m| am) a (woman|girl|female)\b/.test(tl)) {
      useZaraStore.getState().setGender('female');
      wsSend({ type: 'gender', value: 'female' });
      addToast("Honorific updated: Ma'am");
    }

    // Demo message confirmation flow
    const msgMatch = text.match(/send.+to\s+([A-Za-z]+).+saying\s+(.+)/i);
    if (msgMatch) {
      addMessage('user', text);
      const appMatch = text.match(/(whatsapp|telegram|discord|slack|teams|signal|email)/i);
      setPendingMessage({
        app: appMatch ? appMatch[1].charAt(0).toUpperCase() + appMatch[1].slice(1) : 'WhatsApp',
        appIcon: '\u{1F4AC}',
        recipient: msgMatch[1],
        message: msgMatch[2],
      });
      setZaraState('STANDBY');
      return;
    }

    addMessage('user', text);
    setZaraState('THINKING');

    // Send to Electron backend
    if (window.electron?.isElectron) {
      window.electron.sendCommand(text);
    } else {
      // Send via WebSocket bridge to live Python backend
      wsSend({ type: 'command', text });
      // Fallback demo if backend offline
      setTimeout(() => {
        if (useZaraStore.getState().zaraState === 'THINKING') {
          setZaraState('TALKING');
          const h = useZaraStore.getState().honorific;
          addMessage('zara', `Processing your request, ${h}. "${text.substring(0, 60)}${text.length > 60 ? '...' : ''}"`);
          setTimeout(() => setZaraState('STANDBY'), 1800);
        }
      }, 5000);
    }
  }, [addMessage, setZaraState, addToast, setPendingMessage]);

  const PANELS = {
    intelligence: IntelPanel,
    windows: WindowsPanel,
    memory: MemoryPanel,
    capabilities: CapabilitiesPanel,
    tools: ToolsPanel,
    settings: SettingsPanel,
  };
  const Panel = PANELS[activePanel] || IntelPanel;

  return (
    <>
      <style>{GLOBAL_CSS}</style>
      <div style={{ display:'grid', gridTemplateColumns:'56px 1fr 300px', gridTemplateRows:'52px 1fr 180px', height:'100vh', gap:'1px', backgroundColor:'var(--border)' }}>
        {/* Title bar - full width */}
        <div style={{ gridColumn:'1/-1', background:'var(--bg)' }}>
          <TitleBar />
        </div>

        {/* Sidebar */}
        <Sidebar />

        {/* Main sphere canvas */}
        <main style={{ position:'relative', background:'var(--bg)', overflow:'hidden' }}>
          <NeuralSphere />
          {/* Scanlines */}
          <div style={{ position:'absolute', inset:0, backgroundImage:'repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.04) 2px,rgba(0,0,0,0.04) 4px)', pointerEvents:'none', zIndex:2 }} />
          {/* Corners */}
          {[['0','0','2px 0 0 2px'],['0','auto','0 2px 0 0'],['auto','0','0 0 2px 0'],['auto','auto','0 0 0 2px']].map(([t,r,bw], i) => (
            <div key={i} style={{ position:'absolute', width:18, height:18,
              top: t !== 'auto' ? 12 : 'auto', right: r !== 'auto' ? 12 : 'auto',
              bottom: t === 'auto' ? 12 : 'auto', left: r === 'auto' && t === 'auto' ? 12 : r === 'auto' ? 12 : 'auto',
              borderColor:'var(--cyan)', borderStyle:'solid', borderWidth:bw,
              opacity:0.35, pointerEvents:'none', zIndex:3 }} />
          ))}
          {/* State label */}
          <div style={{ position:'absolute', bottom:16, left:'50%', transform:'translateX(-50%)',
            fontFamily:'var(--mono)', fontSize:10, letterSpacing:'0.22em',
            color:'var(--text3)', textTransform:'uppercase', pointerEvents:'none', zIndex:4 }}>
            {useZaraStore.getState().zaraState}
          </div>
        </main>

        {/* Right panel */}
        <aside style={{ background:'var(--bg2)', display:'flex', flexDirection:'column', overflow:'hidden' }}>
          {/* Tab bar */}
          <div style={{ display:'flex', borderBottom:'1px solid var(--border)', flexShrink:0 }}>
            {NAV_ITEMS.map(({ id, label }) => {
              const active = activePanel === id;
              return (
                <button key={id} onClick={() => useZaraStore.getState().setActivePanel(id)}
                  style={{ flex:1, padding:'9px 4px', fontSize:9, fontFamily:'var(--mono)',
                    letterSpacing:'0.07em', textTransform:'uppercase', cursor:'pointer',
                    border:'none', borderBottom:`2px solid ${active ? 'var(--cyan)' : 'transparent'}`,
                    background:'transparent', color: active ? 'var(--cyan)' : 'var(--text3)',
                    transition:'all 0.15s' }}>
                  {label}
                </button>
              );
            })}
          </div>
          <div style={{ flex:1, overflowY:'auto' }}>
            <Panel />
          </div>
        </aside>

        {/* Bottom bar - spans last 2 cols */}
        <div style={{ gridColumn:'2/-1', background:'var(--bg)', minHeight:0 }}>
          <BottomBar onSend={handleSend} />
        </div>
      </div>

      <MessageConfirmDialog />
      <Toasts />
    </>
  );
}

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Layers, Cpu, Database, Code, Package, GraduationCap, Send, Zap, Activity } from 'lucide-react';
import NeuralSphere from './components/NeuralSphere';
import { useZaraStore, wsSend } from './store/zaraStore';
import ContextWing from './components/ContextWing';
import WindowMatrix from './components/WindowMatrix';
import AgentTimeline from './components/AgentTimeline';
import NeuralHeartbeat from './components/NeuralHeartbeat';
import OmniSearch from './components/OmniSearch';
import AutoDebugConsole from './components/AutoDebugConsole';
import SubtitleOverlay from './components/SubtitleOverlay';

const GLOBAL_CSS = `
  @import url('https://rsms.me/inter/inter.css');
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
  
  * { margin: 0; padding: 0; box-sizing: border-box; }
  :root {
    --bg: #010306;
    --glass: rgba(10, 15, 28, 0.7);
    --cyan: #00d4ff;
    --magenta: #ff00ff;
    --border: rgba(0, 212, 255, 0.1);
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
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E");
    opacity: 0.03;
    pointer-events: none;
    z-index: 999;
  }

  .bento-card {
    background: var(--glass);
    backdrop-filter: blur(25px) saturate(180%);
    border: 1px solid var(--border);
    border-radius: 28px;
    padding: 24px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.8);
    overflow: hidden;
    transition: all 0.3s ease;
    display: flex;
    flex-direction: column;
  }

  .message-entry {
    animation: blurEntry 0.5s cubic-bezier(0.4, 0, 0.2, 1);
  }

  @keyframes blurEntry {
    from { opacity: 0; filter: blur(20px); transform: translateY(10px); }
    to { opacity: 1; filter: blur(0px); transform: translateY(0); }
  }
`;

const GlassPanel = ({ area, title, children, icon: Icon, color }) => (
  <motion.div 
    layout 
    initial={{ opacity: 0, scale: 0.95, filter: 'blur(10px)' }}
    animate={{ opacity: 1, scale: 1, filter: 'blur(0px)' }}
    style={{ gridArea: area }} 
    className="bento-card"
  >
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, flexShrink: 0 }}>
      {Icon && <Icon size={14} color={color || 'var(--cyan)'} />}
      {title && <span style={{ fontSize: 9, fontWeight: 700, color: color || 'var(--cyan)', letterSpacing: '0.15em', textTransform: 'uppercase' }}>{title}</span>}
    </div>
    <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
      {children}
    </div>
  </motion.div>
);

function IntelPanel() {
  const { zaraState, metrics, conversation } = useZaraStore();
  const convRef = useRef(null);
  useEffect(() => { if (convRef.current) convRef.current.scrollTop = convRef.current.scrollHeight; }, [conversation]);
  const stateColors = { STANDBY: '#0060ff', LISTENING: '#ff2244', THINKING: '#00d4ff', TALKING: '#00ff9d', EXECUTING: '#ffb547' };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>
       <div style={{ background: 'rgba(255,255,255,0.03)', padding: 12, borderRadius: 12, border: '1px solid var(--border)' }}>
          <div style={{ fontSize: 9, fontFamily: 'var(--mono)', color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase', marginBottom: 4 }}>Neural State</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <motion.div animate={{ scale: [1, 1.2, 1] }} transition={{ repeat: Infinity, duration: 2 }} style={{ width: 8, height: 8, borderRadius: '50%', background: stateColors[zaraState] || 'var(--cyan)' }} />
            <div style={{ fontSize: 20, fontWeight: 800, color: stateColors[zaraState] || 'var(--cyan)', fontFamily: 'var(--mono)' }}>{zaraState}</div>
          </div>
       </div>
       <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <MetricSmall name="CPU" value={metrics?.cpu || 0} color="var(--cyan)" />
          <MetricSmall name="RAM" value={metrics?.ram || 0} color="var(--magenta)" />
          <MetricSmall name="GPU" value={metrics?.gpu || 0} color="#00ff9d" />
          <MetricSmall name="DISK" value={metrics?.disk || 0} color="#ffb547" />
       </div>
       <div ref={convRef} style={{ flex: 1, overflowY: 'auto', borderTop: '1px solid var(--border)', paddingTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {(conversation || []).slice(-10).map((msg, i) => (
            <div key={i} className="message-entry">
               <div style={{ fontSize: 11, color: msg.role === 'user' ? 'var(--cyan)' : 'var(--text)', opacity: 0.8 }}>
                 {msg.text}
               </div>
            </div>
          ))}
       </div>
    </div>
  );
}

function MetricSmall({ name, value, color }) {
  return (
    <div style={{ background: 'rgba(255,255,255,0.02)', padding: 10, borderRadius: 12, border: '1px solid var(--border)' }}>
      <div style={{ fontSize: 8, fontFamily: 'var(--mono)', color: 'rgba(255,255,255,0.3)', marginBottom: 2 }}>{name}</div>
      <div style={{ fontSize: 16, fontWeight: 700, color, fontFamily: 'var(--mono)' }}>{value}%</div>
    </div>
  );
}

function ChatInput({ onSend }) {
  const [text, setText] = useState('');
  const { liveTranscript } = useZaraStore();
  const inputRef = useRef(null);

  const submit = (e) => {
    e?.preventDefault();
    const t = text.trim();
    if (!t) return;
    onSend(t);
    setText('');
  };

  return (
    <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>
       <div style={{ flex: 1, position: 'relative', background: 'rgba(255,255,255,0.02)', borderRadius: 12, border: '1px solid var(--border)', padding: 12 }}>
          <textarea
            ref={inputRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }}
            placeholder="Neural instruction..."
            style={{ 
              width: '100%', height: '100%', background: 'none', border: 'none', outline: 'none',
              color: 'white', fontSize: '15px', resize: 'none',
              fontFamily: 'var(--sans)'
            }}
          />
       </div>
       <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Activity size={10} color="var(--cyan)" />
            <span style={{ fontSize: 10, fontFamily: 'var(--mono)', color: 'rgba(255,255,255,0.4)', letterSpacing: '0.05em' }}>
               {liveTranscript ? liveTranscript : 'Ready'}
            </span>
          </div>
          <button type="submit" style={{ 
            background: 'var(--cyan)', color: '#000', border: 'none', 
            padding: '8px 20px', borderRadius: '12px', fontSize: '11px', 
            fontWeight: 800, cursor: 'pointer', fontFamily: 'var(--mono)',
            display: 'flex', alignItems: 'center', gap: 8
          }}>
            <Send size={12} />
            SEND
          </button>
       </div>
    </form>
  );
}

function ModeButton({ mode, icon: Icon, active, onClick }) {
  return (
    <motion.button
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
      onClick={onClick}
      style={{
        background: active ? 'var(--cyan)' : 'rgba(255,255,255,0.05)',
        border: '1px solid var(--border)',
        borderRadius: '16px',
        padding: '12px 20px',
        color: active ? '#000' : 'white',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        cursor: 'pointer',
        transition: 'all 0.2s',
        boxShadow: active ? '0 0 20px rgba(0, 212, 255, 0.3)' : 'none'
      }}
    >
      <Icon size={16} />
      <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: '0.08em', textTransform: 'uppercase' }}>{mode}</span>
    </motion.button>
  );
}

export default function App() {
  const { zaraState, orbFrame, activeMode, setMode, addMessage, setZaraState } = useZaraStore();

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
        gridTemplateAreas: '"intel core wings" "matrix core wings" "chat chat wings"',
        gridTemplateColumns: '1.2fr 1.8fr 1.2fr',
        gridTemplateRows: '280px 1fr 180px',
        gap: '20px', padding: '20px', height: '100vh', background: 'var(--bg)' 
      }}>
        <GlassPanel area="intel" title="Neural Intelligence" icon={Zap} color="var(--cyan)">
          <IntelPanel />
        </GlassPanel>

        <GlassPanel area="matrix" title="System Matrix" icon={Layers} color="var(--cyan)">
           <div style={{ flex: 1, overflowY: 'auto' }}>
            <WindowMatrix />
          </div>
        </GlassPanel>
        
        <div style={{ gridArea: 'core', position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {orbFrame ? (
            <motion.img
              src={`data:image/png;base64,${orbFrame}`}
              animate={{ scale: zaraState === 'TALKING' ? [1, 1.05, 1] : 1 }}
              transition={{ duration: 0.5, repeat: Infinity }}
              style={{ width: 'min(70vh, 90%)', height: 'min(70vh, 90%)', objectFit: 'contain', filter: 'drop-shadow(0 0 40px rgba(0, 212, 255, 0.2))' }}
            />
          ) : <NeuralSphere />}
          
          <SubtitleOverlay />
          
          {/* Reactive Ambient Glow */}
          <motion.div 
            animate={{ scale: [1, 1.1, 1], opacity: [0.05, 0.15, 0.05] }}
            transition={{ duration: 4, repeat: Infinity }}
            style={{ position: 'absolute', inset: 0, background: 'radial-gradient(circle, rgba(0,212,255,0.1) 0%, transparent 70%)', pointerEvents: 'none' }} 
          />

          <div style={{ position: 'absolute', bottom: 40, width: '100%', display: 'flex', justifyContent: 'center', gap: 16 }}>
            <ModeButton mode="coding" icon={Code} active={activeMode === 'coding'} onClick={() => setMode('coding')} />
            <ModeButton mode="logistics" icon={Package} active={activeMode === 'logistics'} onClick={() => setMode('logistics')} />
            <ModeButton mode="study" icon={GraduationCap} active={activeMode === 'study'} onClick={() => setMode('study')} />
          </div>
        </div>

        <GlassPanel area="wings" title="Context Wing" icon={Database} color="var(--magenta)">
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 12 }}>
            <ContextWing />
            <div style={{ borderTop: '1px solid var(--border)', marginTop: 12, paddingTop: 12 }}>
               <AgentTimeline />
            </div>
          </div>
        </GlassPanel>

        <GlassPanel area="chat">
           <ChatInput onSend={handleSend} />
        </GlassPanel>
      </div>

      <Toasts />
    </>
  );
}

function Toasts() {
  const { toasts, removeToast } = useZaraStore();
  return (
    <div style={{ position:'fixed', bottom: 200, right: 30, display:'flex', flexDirection:'column', gap:8, zIndex:9999 }}>
      <AnimatePresence>
        {toasts.map(t => (
          <motion.div 
            key={t.id} 
            initial={{ x: 50, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 50, opacity: 0 }}
            onClick={() => removeToast(t.id)}
            style={{ 
              background:'rgba(10,15,28,0.95)', border:'1px solid var(--border)', 
              borderRadius:12, padding:'12px 20px', fontSize:11, fontFamily:'var(--mono)', 
              color:'white', cursor:'pointer', borderLeft: `4px solid var(--cyan)`,
              boxShadow: '0 8px 24px rgba(0,0,0,0.4)'
            }}>
            {t.text}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

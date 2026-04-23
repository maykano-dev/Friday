import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Terminal, ShieldCheck, Zap, AlertCircle } from 'lucide-react';
import { useZaraStore } from '../store/zaraStore';

export default function AutoDebugConsole() {
  const { zaraState } = useZaraStore();
  const [logs, setLogs] = useState([]);
  const [visible, setVisible] = useState(false);

  // Mocking/Connecting to real debug events
  useEffect(() => {
    if (zaraState === 'THINKING') {
      const newLog = {
        id: Date.now(),
        type: 'process',
        msg: 'Initiating self-healing protocol...',
        time: new Date().toLocaleTimeString()
      };
      setLogs(prev => [newLog, ...prev].slice(0, 50));
    }
  }, [zaraState]);

  return (
    <div style={{ position: 'fixed', bottom: '80px', right: '20px', zIndex: 500 }}>
       <button 
        onClick={() => setVisible(!visible)}
        style={{
          background: 'rgba(10, 15, 28, 0.8)',
          border: '1px solid rgba(0, 212, 255, 0.2)',
          borderRadius: '12px',
          padding: '8px 12px',
          color: 'var(--cyan)',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          cursor: 'pointer',
          backdropFilter: 'blur(10px)'
        }}
      >
        <Terminal size={14} />
        <span style={{ fontSize: '10px', fontWeight: 700, letterSpacing: '0.1em' }}>AUTO-DEBUG</span>
      </button>

      <AnimatePresence>
        {visible && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            style={{
              position: 'absolute', bottom: '50px', right: 0,
              width: '320px', height: '400px',
              background: 'rgba(5, 8, 15, 0.95)',
              border: '1px solid rgba(0, 212, 255, 0.3)',
              borderRadius: '20px',
              boxShadow: '0 10px 40px rgba(0,0,0,0.5)',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden'
            }}
          >
            <div style={{ padding: '12px 16px', borderBottom: '1px solid rgba(0, 212, 255, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Zap size={14} color="var(--cyan)" />
                <span style={{ fontSize: '10px', fontWeight: 800, letterSpacing: '0.1em', color: 'var(--cyan)' }}>SELF-HEALING CORE</span>
              </div>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: zaraState === 'THINKING' ? '#00ff9d' : '#444', boxShadow: zaraState === 'THINKING' ? '0 0 10px #00ff9d' : 'none' }} />
            </div>

            <div style={{ flex: 1, padding: '16px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {logs.length === 0 ? (
                <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'rgba(255,255,255,0.2)', fontSize: '11px', textAlign: 'center' }}>
                  No active debug sessions.<br/>Zara is stable.
                </div>
              ) : (
                logs.map(log => (
                  <div key={log.id} style={{ display: 'flex', gap: 10 }}>
                    <span style={{ fontSize: '9px', color: 'rgba(255,255,255,0.3)', minWidth: '50px', fontFamily: 'var(--mono)' }}>[{log.time}]</span>
                    <span style={{ fontSize: '11px', color: log.type === 'error' ? '#ff4d6a' : 'var(--cyan)', fontFamily: 'var(--mono)' }}>{log.msg}</span>
                  </div>
                ))
              )}
            </div>

            <div style={{ padding: '10px', background: 'rgba(0, 212, 255, 0.05)', display: 'flex', alignItems: 'center', gap: 8 }}>
              <ShieldCheck size={12} color="#00ff9d" />
              <span style={{ fontSize: '9px', color: '#00ff9d', fontWeight: 600 }}>VERIFIED_EXECUTE ACTIVE</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

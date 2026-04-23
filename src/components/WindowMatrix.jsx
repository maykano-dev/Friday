import { motion } from 'framer-motion';
import { useZaraStore, wsSend } from '../store/zaraStore';
import { Monitor, Maximize2 } from 'lucide-react';

export default function WindowMatrix() {
  const { openWindows } = useZaraStore();

  const handleFocus = (title) => {
    wsSend({ type: 'command', text: `<EXECUTE>{"action": "focus_window", "title": "${title}"}</EXECUTE>` });
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: '8px', padding: '12px' }}>
      {openWindows.map((win, i) => (
        <motion.div
          key={win + i}
          whileHover={{ scale: 1.02, borderColor: 'var(--cyan)' }}
          style={{
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: '10px', padding: '12px', height: '110px',
            position: 'relative', overflow: 'hidden', display: 'flex', flexDirection: 'column'
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
            <Monitor size={12} color="var(--text3)" />
            <button onClick={() => handleFocus(win)} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
              <Maximize2 size={12} color="var(--cyan)" />
            </button>
          </div>
          <div style={{ fontSize: '11px', fontWeight: '600', color: 'var(--text)', lineHeight: '1.4' }}>{win}</div>
          <motion.div 
            animate={{ top: ['-10%', '110%'] }} transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
            style={{ position: 'absolute', left: 0, right: 0, height: '1px', background: 'var(--cyan)', opacity: 0.3 }}
          />
        </motion.div>
      ))}
    </div>
  );
}

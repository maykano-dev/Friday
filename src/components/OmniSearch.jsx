import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, Globe, X } from 'lucide-react';
import { wsSend, useZaraStore } from '../store/zaraStore';

export default function OmniSearch() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const inputRef = useRef(null);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.ctrlKey && e.code === 'Space') {
        e.preventDefault();
        setOpen(true);
      }
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  useEffect(() => {
    if (open && inputRef.current) {
      inputRef.current.focus();
    }
  }, [open]);

  const handleSearch = (e) => {
    e.preventDefault();
    if (!query.trim()) return;
    
    wsSend({ type: 'command', text: `web search for: ${query}` });
    setOpen(false);
    setQuery('');
  };

  return (
    <AnimatePresence>
      {open && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 1000,
          background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(10px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px'
        }}>
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            style={{
              width: '100%', maxWidth: '600px',
              background: 'rgba(10, 15, 28, 0.95)',
              borderRadius: '24px',
              border: '1px solid rgba(0, 212, 255, 0.3)',
              boxShadow: '0 0 50px rgba(0, 212, 255, 0.1)',
              padding: '8px',
              overflow: 'hidden'
            }}
          >
            <form onSubmit={handleSearch} style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px' }}>
              <Globe size={20} color="var(--cyan)" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Omni-Search: Ask anything or search the web..."
                style={{
                  flex: 1, background: 'none', border: 'none', outline: 'none',
                  color: 'white', fontSize: '18px', fontFamily: 'var(--sans)'
                }}
              />
              <button type="submit" style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
                <Search size={20} color="var(--cyan)" />
              </button>
            </form>
            <div style={{ padding: '4px 16px 12px', display: 'flex', gap: '8px' }}>
               <span style={{ fontSize: '10px', color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Press Enter to search, ESC to close</span>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}

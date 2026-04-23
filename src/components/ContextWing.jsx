import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useZaraStore } from '../store/zaraStore';
import { FileText, Code, Image as ImageIcon, ExternalLink } from 'lucide-react';

export default function ContextWing() {
  const cards = useZaraStore(s => s.contextCards);

  return (
    <div style={{ padding: '12px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
      <AnimatePresence initial={false}>
        {cards.map((card, i) => (
          <motion.div
            key={card.timestamp || i}
            initial={{ opacity: 0, x: 50, filter: 'blur(10px)' }}
            animate={{ opacity: 1, x: 0, filter: 'blur(0px)' }}
            exit={{ opacity: 0, scale: 0.95 }}
            style={{
              background: 'rgba(255, 255, 255, 0.03)',
              border: '1px solid rgba(0, 212, 255, 0.1)',
              borderRadius: '12px',
              padding: '12px',
              backdropFilter: 'blur(10px)',
              boxShadow: '0 4px 15px rgba(0,0,0,0.3)'
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              {card.card_type === 'CODE' ? <Code size={14} color="var(--cyan)" /> : <FileText size={14} color="var(--purple)" />}
              <span style={{ fontSize: '10px', color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>{card.label}</span>
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text)', whiteSpace: 'pre-wrap', maxHeight: '150px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {card.content}
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

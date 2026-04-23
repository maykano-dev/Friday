import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useZaraStore } from '../store/zaraStore';

export default function SubtitleOverlay() {
  const { liveTranscript, zaraState } = useZaraStore();

  if (!liveTranscript || zaraState === 'STANDBY') return null;

  return (
    <div style={{
      position: 'absolute',
      bottom: '120px',
      left: '50%',
      transform: 'translateX(-50%)',
      width: '80%',
      maxWidth: '800px',
      pointerEvents: 'none',
      zIndex: 100,
      textAlign: 'center'
    }}>
      <AnimatePresence mode="wait">
        <motion.div
          key={liveTranscript}
          initial={{ opacity: 0, y: 10, filter: 'blur(10px)' }}
          animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
          exit={{ opacity: 0, y: -10, filter: 'blur(10px)' }}
          transition={{ duration: 0.3 }}
          style={{
            background: 'rgba(0, 0, 0, 0.4)',
            backdropFilter: 'blur(20px)',
            padding: '12px 24px',
            borderRadius: '16px',
            border: '1px solid rgba(0, 212, 255, 0.2)',
            color: 'white',
            fontSize: '18px',
            fontWeight: 500,
            lineHeight: 1.4,
            boxShadow: '0 10px 30px rgba(0,0,0,0.3)',
            display: 'inline-block'
          }}
        >
          {liveTranscript}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

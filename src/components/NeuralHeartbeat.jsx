import React from 'react';
import { motion } from 'framer-motion';
import { useZaraStore } from '../store/zaraStore';

const SCANLINE_CSS = `
  @keyframes scanline {
    0% { transform: translateY(-100%); }
    100% { transform: translateY(100%); }
  }
`;

export default function NeuralHeartbeat() {
  const { metrics, zaraState } = useZaraStore();
  const speed = zaraState === 'THINKING' ? 0.8 : 3.0;

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: -1, overflow: 'hidden', pointerEvents: 'none' }}>
      <style>{SCANLINE_CSS}</style>
      
      {/* Central Pulse */}
      <motion.div
        animate={{
          scale: [1, 1.1, 1],
          opacity: zaraState === 'THINKING' ? [0.2, 0.4, 0.2] : [0.05, 0.1, 0.05],
        }}
        transition={{ duration: speed, repeat: Infinity, ease: "easeInOut" }}
        style={{
          width: '100vw', height: '100vh',
          background: `radial-gradient(circle at 50% 50%, rgba(0, 212, 255, 0.15) 0%, transparent 60%)`,
          filter: 'blur(80px)',
        }}
      />

      {/* Digital Scanline */}
      <div style={{
        position: 'absolute', inset: 0,
        background: 'linear-gradient(to bottom, transparent, rgba(0, 212, 255, 0.05) 50%, transparent)',
        height: '100px',
        width: '100%',
        animation: 'scanline 4s linear infinite',
        opacity: zaraState === 'THINKING' ? 0.8 : 0.2,
      }} />

      {/* Reactive Grid */}
      <div style={{
        position: 'absolute', inset: 0,
        backgroundImage: 'linear-gradient(rgba(0, 212, 255, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 212, 255, 0.03) 1px, transparent 1px)',
        backgroundSize: '40px 40px',
        opacity: 0.5,
      }} />
    </div>
  );
}

import { useZaraStore } from '../store/zaraStore';

const isElectron = typeof window !== 'undefined' && window.electron?.isElectron;

export default function TitleBar() {
  const { zaraState, gender, honorific, apiHealth } = useZaraStore();

  const stateColors = {
    STANDBY: '#0060ff',
    LISTENING: '#ff2244',
    THINKING: '#00d4ff',
    TALKING: '#00ff9d',
    EXECUTING: '#ffb547',
  };

  const dot = stateColors[zaraState] || '#0060ff';

  const handleMin = () => window.electron?.minimize();
  const handleMax = () => window.electron?.maximize();
  const handleClose = () => window.electron?.close();

  return (
    <header style={{
      height: 52,
      background: '#0b0e1a',
      borderBottom: '1px solid rgba(0,212,255,0.12)',
      display: 'flex',
      alignItems: 'center',
      padding: '0 16px',
      gap: 12,
      WebkitAppRegion: 'drag', // Electron draggable
      flexShrink: 0,
      zIndex: 100,
      position: 'relative',
    }}>
      {/* Logo */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        fontFamily: "'Space Mono', monospace",
        fontSize: 17, fontWeight: 700,
        color: '#00d4ff', letterSpacing: '0.12em',
        WebkitAppRegion: 'no-drag',
      }}>
        <div style={{
          width: 9, height: 9, borderRadius: '50%',
          background: dot,
          boxShadow: `0 0 8px ${dot}`,
          transition: 'background 0.4s, box-shadow 0.4s',
          animation: 'pulseDot 2.2s ease-in-out infinite',
        }} />
        ZARA
      </div>

      {/* State chip */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 5,
        fontFamily: "'Space Mono', monospace",
        fontSize: 10, letterSpacing: '0.1em',
        color: dot, background: `${dot}18`,
        border: `1px solid ${dot}40`,
        padding: '3px 9px', borderRadius: 20,
        transition: 'all 0.3s',
      }}>
        <span style={{ width: 5, height: 5, borderRadius: '50%', background: dot, display: 'inline-block' }} />
        {zaraState}
      </div>

      {/* API health chips */}
      {Object.entries(apiHealth).map(([key, status]) => (
        <div key={key} style={{
          fontFamily: "'Space Mono', monospace",
          fontSize: 9, letterSpacing: '0.08em',
          color: status === 'online' ? '#00ff9d' : status === 'checking' ? '#ffb547' : '#4a567a',
          background: '#141b2d',
          border: '1px solid rgba(0,212,255,0.1)',
          padding: '3px 7px', borderRadius: 4,
          textTransform: 'uppercase',
        }}>
          {key}: {status}
        </div>
      ))}

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Honorific badge */}
      <div style={{
        fontFamily: "'Space Mono', monospace",
        fontSize: 10, color: '#b47dff',
        background: 'rgba(180,125,255,0.1)',
        border: '1px solid rgba(180,125,255,0.25)',
        padding: '3px 8px', borderRadius: 4,
      }}>
        {gender === 'unknown' ? '⚥ DETECTING' : `${gender === 'male' ? '♂' : '♀'} ${honorific.toUpperCase()}`}
      </div>

      {/* Clock */}
      <Clock />

      {/* Window controls (Electron only) */}
      {isElectron && (
        <div style={{ display: 'flex', gap: 6, WebkitAppRegion: 'no-drag', marginLeft: 8 }}>
          {[
            { label: '−', action: handleMin, hover: '#444' },
            { label: '□', action: handleMax, hover: '#444' },
            { label: '×', action: handleClose, hover: '#c0392b' },
          ].map(({ label, action, hover }) => (
            <button
              key={label}
              onClick={action}
              style={{
                width: 24, height: 24, borderRadius: 4,
                background: 'transparent',
                border: '1px solid rgba(255,255,255,0.1)',
                color: '#7b8ab8',
                fontFamily: 'monospace', fontSize: 12,
                cursor: 'pointer', display: 'flex',
                alignItems: 'center', justifyContent: 'center',
                transition: 'all 0.15s',
              }}
              onMouseEnter={(e) => { e.target.style.background = hover; e.target.style.color = '#fff'; }}
              onMouseLeave={(e) => { e.target.style.background = 'transparent'; e.target.style.color = '#7b8ab8'; }}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      <style>{`
        @keyframes pulseDot {
          0%,100% { transform:scale(1); opacity:1; }
          50% { transform:scale(1.4); opacity:0.7; }
        }
      `}</style>
    </header>
  );
}

function Clock() {
  const [time, setTime] = React.useState('');
  React.useEffect(() => {
    const tick = () => {
      const n = new Date();
      setTime(`${String(n.getHours()).padStart(2,'0')}:${String(n.getMinutes()).padStart(2,'0')}:${String(n.getSeconds()).padStart(2,'0')}`);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <div style={{
      fontFamily: "'Space Mono', monospace",
      fontSize: 11, color: '#4a567a',
      background: '#141b2d',
      border: '1px solid rgba(0,212,255,0.1)',
      padding: '3px 8px', borderRadius: 4,
    }}>
      {time}
    </div>
  );
}

import React from 'react';

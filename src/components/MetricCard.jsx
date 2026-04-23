import { motion } from 'framer-motion';

export default function MetricCard({ name, value, history, color }) {
  // history is an array of metric objects { cpu, ram, gpu, disk, ... }
  // We want to extract the specific metric by name
  const metricKey = name.toLowerCase();
  const data = (history || []).map(h => h[metricKey] || 0);
  
  // Create points for the polyline
  // Viewbox is 0 0 100 40
  // x goes from 0 to 100, y goes from 40 (0%) to 0 (100%)
  const points = data.map((v, i) => {
    const x = (i / (Math.max(1, data.length - 1))) * 100;
    const y = 40 - (v / 100) * 40;
    return `${x},${y}`;
  }).join(' ');

  return (
    <motion.div 
      layout
      style={{ 
        background: 'rgba(20, 27, 45, 0.4)', 
        backdropFilter: 'blur(15px)',
        border: '1px solid rgba(0, 212, 255, 0.12)',
        borderRadius: '12px',
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px'
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 10, color, fontWeight: '700', letterSpacing: '0.1em' }}>{name.toUpperCase()}</span>
        <span style={{ fontSize: 18, fontWeight: 800, color: '#fff' }}>{value}%</span>
      </div>
      <div style={{ height: '40px', width: '100%', marginTop: '4px' }}>
        <svg width="100%" height="40" preserveAspectRatio="none" viewBox="0 0 100 40">
          <motion.polyline 
            points={points} 
            fill="none" 
            stroke={color} 
            strokeWidth="2" 
            initial={{ pathLength: 0 }} 
            animate={{ pathLength: 1 }} 
            transition={{ duration: 0.8, ease: "easeOut" }}
          />
          {/* Subtle glow layer */}
          <motion.polyline 
            points={points} 
            fill="none" 
            stroke={color} 
            strokeWidth="4" 
            style={{ opacity: 0.2, filter: 'blur(3px)' }}
          />
        </svg>
      </div>
    </motion.div>
  );
}

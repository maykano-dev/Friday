import { motion } from 'framer-motion';
import { useZaraStore } from '../store/zaraStore';
import { CheckCircle2, Circle, Loader2, AlertCircle } from 'lucide-react';

export default function AgentTimeline() {
  const { agentTasks } = useZaraStore();

  const getIcon = (status) => {
    switch (status) {
      case 'completed': return <CheckCircle2 size={14} color="var(--green)" />;
      case 'running': return <Loader2 size={14} color="var(--cyan)" className="animate-spin" />;
      case 'failed': return <AlertCircle size={14} color="var(--red)" />;
      default: return <Circle size={14} color="var(--text3)" />;
    }
  };

  return (
    <div style={{ padding: '12px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
      {agentTasks.length === 0 ? (
        <div style={{ fontSize: '11px', color: 'var(--text3)', fontFamily: 'var(--mono)', textAlign: 'center', padding: '20px' }}>
          No active agent workflows.
        </div>
      ) : (
        agentTasks.map((task, i) => (
          <motion.div
            key={task.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: '8px',
              padding: '10px',
              display: 'flex',
              gap: '12px',
              alignItems: 'flex-start'
            }}
          >
            <div style={{ marginTop: '2px' }}>{getIcon(task.status)}</div>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                <span style={{ fontSize: '10px', fontWeight: '700', color: 'var(--cyan)', textTransform: 'uppercase', fontFamily: 'var(--mono)' }}>
                  {task.role}
                </span>
                <span style={{ fontSize: '9px', color: 'var(--text3)', fontFamily: 'var(--mono)' }}>
                  {new Date(task.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text)', lineHeight: '1.4' }}>
                {task.instruction}
              </div>
              {task.status === 'completed' && (
                <motion.div 
                  initial={{ opacity: 0 }} 
                  animate={{ opacity: 1 }}
                  style={{ fontSize: '10px', color: 'var(--text2)', marginTop: '6px', fontStyle: 'italic', borderTop: '1px solid var(--border)', paddingTop: '6px' }}
                >
                  "Done."
                </motion.div>
              )}
            </div>
          </motion.div>
        ))
      )}
      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        .animate-spin { animation: spin 2s linear infinite; }
      `}</style>
    </div>
  );
}

import React, { useState, useEffect } from 'react';
import ConceptPreviewBanner from './ConceptPreviewBanner';

const styles = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: '20px',
    color: '#e2e8f0',
    fontFamily: 'var(--font-mono, monospace)',
  },
  card: {
    background: 'rgba(10, 15, 30, 0.85)',
    border: '1px solid rgba(0, 240, 255, 0.2)',
    borderRadius: '12px',
    padding: '20px',
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
    backdropFilter: 'blur(10px)',
    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
  },
  cardTitle: {
    fontFamily: 'var(--font-display, sans-serif)',
    fontSize: '15px',
    fontWeight: 700,
    color: 'var(--neon-cyan, #00f0ff)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderBottom: '1px solid rgba(0, 240, 255, 0.15)',
    paddingBottom: '10px',
  },
  badge: (color) => ({
    fontSize: '10px',
    padding: '3px 8px',
    borderRadius: '4px',
    background: `${color || '#00f0ff'}22`,
    color: color || '#00f0ff',
    border: `1px solid ${color || '#00f0ff'}44`,
    fontWeight: 600,
  }),
  nodeGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
    gap: '14px',
  },
  nodeCard: {
    background: '#040812',
    border: '1px solid rgba(0, 240, 255, 0.15)',
    borderRadius: '8px',
    padding: '14px',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  progressBar: (pct, color) => ({
    width: '100%',
    height: '6px',
    background: 'rgba(255,255,255,0.1)',
    borderRadius: '3px',
    overflow: 'hidden',
  }),
  progressFill: (pct, color) => ({
    width: `${pct}%`,
    height: '100%',
    background: color || '#00f0ff',
    transition: 'width 0.4s ease',
  }),
  metricRow: {
    display: 'flex',
    justifyContent: 'space-between',
    fontSize: '12px',
  }
};

export default function FederatedLearning() {
  const [round, setRound] = useState(48);
  const [globalLoss, setGlobalLoss] = useState(0.0241);
  const [privacyBudget, setPrivacyBudget] = useState(0.42); // Epsilon
  const [isAggregating, setIsAggregating] = useState(false);

  const [nodes, setNodes] = useState([
    { id: 'NODE-01', name: 'Mobile Wallet (iOS)', samples: 14200, localLoss: 0.028, status: 'TRAINING', progress: 85 },
    { id: 'NODE-02', name: 'POS Terminal (Retail)', samples: 8900, localLoss: 0.022, status: 'READY', progress: 100 },
    { id: 'NODE-03', name: 'Web Node (Browser)', samples: 21500, localLoss: 0.019, status: 'TRAINING', progress: 62 },
    { id: 'NODE-04', name: 'Banking Edge Gateway', samples: 45000, localLoss: 0.015, status: 'READY', progress: 100 },
  ]);

  // Simulate federated learning rounds
  useEffect(() => {
    const interval = setInterval(() => {
      setIsAggregating(true);

      setTimeout(() => {
        setRound(r => r + 1);
        setGlobalLoss(l => Math.max(0.008, Number((l * 0.985).toFixed(4))));
        setPrivacyBudget(e => Number((e + 0.005).toFixed(3)));

        setNodes(prev => prev.map(n => ({
          ...n,
          localLoss: Number((n.localLoss * (0.97 + Math.random() * 0.04)).toFixed(4)),
          progress: Math.floor(Math.random() * 40) + 60,
          status: Math.random() > 0.3 ? 'READY' : 'TRAINING',
        })));

        setIsAggregating(false);
      }, 800);

    }, 4500);

    return () => clearInterval(interval);
  }, []);

  return (
    <div style={styles.container}>
      <ConceptPreviewBanner label="Federated Learning" />
      {/* Header Banner */}
      <div style={{
        padding: '14px 20px',
        background: 'linear-gradient(90deg, rgba(0,240,255,0.12) 0%, rgba(168,85,247,0.12) 100%)',
        border: '1px solid rgba(0, 240, 255, 0.3)',
        borderRadius: '10px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div>
          <span style={{ color: '#00f0ff', fontWeight: 'bold', fontSize: '15px' }}>⚡ PRIVACY-PRESERVING FEDERATED LEARNING PROTOCOL</span>
          <div style={{ color: '#94a3b8', fontSize: '12px', marginTop: '4px' }}>
            FedAvg / FedProx Distributed Training · Differential Privacy ($\epsilon$-Noise Injection) · SMPC Gradient Aggregation
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <span style={styles.badge('#00ff88')}>ROUND #{round}</span>
          <span style={styles.badge(isAggregating ? '#a855f7' : '#00f0ff')}>
            {isAggregating ? 'AGGREGATING GRADIENTS...' : 'CLIENT TRAIN ACTIVE'}
          </span>
        </div>
      </div>

      {/* Main Stats Strip */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '14px' }}>
        <div style={styles.card}>
          <div style={{ fontSize: '11px', color: '#94a3b8' }}>GLOBAL MODEL LOSS</div>
          <div style={{ fontSize: '24px', color: '#00ff88', fontWeight: 'bold' }}>{globalLoss}</div>
          <div style={{ fontSize: '10px', color: '#64748b' }}>FedAvg Convergence Rate: -1.5%/round</div>
        </div>

        <div style={styles.card}>
          <div style={{ fontSize: '11px', color: '#94a3b8' }}>DIFFERENTIAL PRIVACY (ε)</div>
          <div style={{ fontSize: '24px', color: '#a855f7', fontWeight: 'bold' }}>ε = {privacyBudget}</div>
          <div style={{ fontSize: '10px', color: '#64748b' }}>δ = 10⁻⁵ Gaussian Noise Scale</div>
        </div>

        <div style={styles.card}>
          <div style={{ fontSize: '11px', color: '#94a3b8' }}>TOTAL PARTICIPATING SAMPLES</div>
          <div style={{ fontSize: '24px', color: '#00f0ff', fontWeight: 'bold' }}>
            {nodes.reduce((a, b) => a + b.samples, 0).toLocaleString()}
          </div>
          <div style={{ fontSize: '10px', color: '#64748b' }}>Zero Raw Data Transferred</div>
        </div>

        <div style={styles.card}>
          <div style={{ fontSize: '11px', color: '#94a3b8' }}>POST-QUANTUM KEY ENCRYPTION</div>
          <div style={{ fontSize: '24px', color: '#eab308', fontWeight: 'bold' }}>Dilithium5</div>
          <div style={{ fontSize: '10px', color: '#64748b' }}>Gradient Delta Signed & Sealed</div>
        </div>
      </div>

      {/* Client Nodes Grid */}
      <div style={styles.card}>
        <div style={styles.cardTitle}>
          <span>📱 Distributed Edge Client Nodes</span>
          <span style={{ fontSize: '12px', color: '#94a3b8' }}>4/4 Nodes Active in FedAvg Pool</span>
        </div>

        <div style={styles.nodeGrid}>
          {nodes.map(node => (
            <div key={node.id} style={styles.nodeCard}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ color: '#00f0ff', fontWeight: 'bold', fontSize: '13px' }}>{node.id}</span>
                <span style={styles.badge(node.status === 'READY' ? '#00ff88' : '#a855f7')}>{node.status}</span>
              </div>
              <div style={{ color: '#e2e8f0', fontSize: '12px', fontWeight: 600 }}>{node.name}</div>

              <div style={{ marginTop: '6px' }}>
                <div style={styles.metricRow}>
                  <span style={{ color: '#94a3b8' }}>Local Samples:</span>
                  <span style={{ color: '#38bdf8' }}>{node.samples.toLocaleString()}</span>
                </div>
                <div style={styles.metricRow}>
                  <span style={{ color: '#94a3b8' }}>Local Loss:</span>
                  <span style={{ color: '#00ff88' }}>{node.localLoss}</span>
                </div>
              </div>

              <div style={{ marginTop: '8px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: '#64748b', marginBottom: '4px' }}>
                  <span>Epoch Progress</span>
                  <span>{node.progress}%</span>
                </div>
                <div style={styles.progressBar()}>
                  <div style={styles.progressFill(node.progress, node.status === 'READY' ? '#00ff88' : '#a855f7')} />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

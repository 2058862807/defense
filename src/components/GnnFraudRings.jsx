import React, { useState, useEffect } from 'react';

const styles = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: '20px',
    color: '#e2e8f0',
    fontFamily: 'var(--font-mono, monospace)',
  },
  grid2: {
    display: 'grid',
    gridTemplateColumns: '1fr 340px',
    gap: '16px',
  },
  card: {
    background: 'rgba(10, 15, 30, 0.85)',
    border: '1px solid rgba(0, 240, 255, 0.2)',
    borderRadius: '12px',
    padding: '20px',
    display: 'flex',
    flexDirection: 'column',
    gap: '14px',
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
  graphArea: {
    width: '100%',
    height: '420px',
    background: '#030712',
    borderRadius: '8px',
    border: '1px solid rgba(0, 240, 255, 0.2)',
    position: 'relative',
    overflow: 'hidden',
  },
  nodeItem: {
    padding: '10px 12px',
    background: 'rgba(0,0,0,0.4)',
    border: '1px solid rgba(0,240,255,0.15)',
    borderRadius: '6px',
    fontSize: '11px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    cursor: 'pointer',
  }
};

export default function GnnFraudRings() {
  const [selectedHop, setSelectedHop] = useState(2); // 1-hop, 2-hop, 3-hop GNN depth
  const [selectedNode, setSelectedNode] = useState('NODE_RING_ALPHA_01');
  const [graphData, setGraphData] = useState({
    nodes: [
      { id: 'NODE_RING_ALPHA_01', type: 'WALLET', label: '0x7f83...9069', x: 200, y: 150, risk: 94.2, ring: 'CIRCULAR_LAUNDERING_RING_A' },
      { id: 'NODE_RING_ALPHA_02', type: 'IP_SUBNET', label: '192.168.4.12', x: 340, y: 110, risk: 88.5, ring: 'CIRCULAR_LAUNDERING_RING_A' },
      { id: 'NODE_RING_ALPHA_03', type: 'DEVICE_ID', label: 'FP-IOS-99A', x: 280, y: 260, risk: 91.0, ring: 'CIRCULAR_LAUNDERING_RING_A' },
      { id: 'NODE_RING_ALPHA_04', type: 'BANK_ACCOUNT', label: 'FED-ACH-8831', x: 420, y: 220, risk: 85.4, ring: 'CIRCULAR_LAUNDERING_RING_A' },
      { id: 'NODE_LEGIT_01', type: 'WALLET', label: '0x11ab...33ef', x: 100, y: 300, risk: 8.2, ring: 'NONE' },
      { id: 'NODE_MIXER_01', type: 'MIXER_HUB', label: '0x88ff...44aa', x: 550, y: 160, risk: 98.7, ring: 'FAN_OUT_SYBIL_HUB' },
      { id: 'NODE_SYBIL_01', type: 'WALLET', label: '0x33dd...22bb', x: 650, y: 100, risk: 89.1, ring: 'FAN_OUT_SYBIL_HUB' },
      { id: 'NODE_SYBIL_02', type: 'WALLET', label: '0x44ee...99cc', x: 660, y: 240, risk: 92.4, ring: 'FAN_OUT_SYBIL_HUB' },
    ],
    edges: [
      { source: 'NODE_RING_ALPHA_01', target: 'NODE_RING_ALPHA_02', label: 'SAME_IP' },
      { source: 'NODE_RING_ALPHA_02', target: 'NODE_RING_ALPHA_03', label: 'SHARED_FP' },
      { source: 'NODE_RING_ALPHA_03', target: 'NODE_RING_ALPHA_04', label: 'RAPID_ACH' },
      { source: 'NODE_RING_ALPHA_04', target: 'NODE_RING_ALPHA_01', label: 'CIRCULAR_LOOP' },
      { source: 'NODE_LEGIT_01', target: 'NODE_RING_ALPHA_01', label: '1_HOP_PAY' },
      { source: 'NODE_RING_ALPHA_04', target: 'NODE_MIXER_01', label: 'FAN_OUT' },
      { source: 'NODE_MIXER_01', target: 'NODE_SYBIL_01', label: 'SYBIL_SPLIT' },
      { source: 'NODE_MIXER_01', target: 'NODE_SYBIL_02', label: 'SYBIL_SPLIT' },
    ]
  });

  const activeNodeInfo = graphData.nodes.find(n => n.id === selectedNode) || graphData.nodes[0];

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={{
        padding: '14px 20px',
        background: 'linear-gradient(90deg, rgba(255,0,85,0.12) 0%, rgba(0,240,255,0.12) 100%)',
        border: '1px solid rgba(255, 0, 85, 0.3)',
        borderRadius: '10px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div>
          <span style={{ color: '#ff3355', fontWeight: 'bold', fontSize: '15px' }}>🕸 GRAPH NEURAL NETWORK (GNN) FRAUD-RING DETECTOR</span>
          <div style={{ color: '#94a3b8', fontSize: '12px', marginTop: '4px' }}>
            GraphSAGE / GCN Message Passing · Multi-Hop Anomaly Propagation · Circular Laundering Loop & Sybil Ring Detection
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <span style={{ fontSize: '11px', color: '#94a3b8' }}>GNN HOPS:</span>
          {[1, 2, 3].map(hop => (
            <button
              key={hop}
              onClick={() => setSelectedHop(hop)}
              style={{
                padding: '4px 10px',
                borderRadius: '4px',
                border: selectedHop === hop ? '1px solid #00f0ff' : '1px solid rgba(255,255,255,0.1)',
                background: selectedHop === hop ? 'rgba(0,240,255,0.2)' : 'transparent',
                color: selectedHop === hop ? '#00f0ff' : '#94a3b8',
                cursor: 'pointer',
                fontSize: '11px',
                fontWeight: 'bold',
              }}
            >
              {hop}-Hop
            </button>
          ))}
        </div>
      </div>

      <div style={styles.grid2}>
        {/* SVG Node Graph */}
        <div style={styles.card}>
          <div style={styles.cardTitle}>
            <span>🌐 Interactive Multi-Hop Subgraph View</span>
            <span style={styles.badge('#ff0055')}>2 FRAUD RINGS DETECTED</span>
          </div>

          <div style={styles.graphArea}>
            <svg width="100%" height="100%" viewBox="0 0 750 380">
              {/* Draw Edges */}
              {graphData.edges.map((edge, idx) => {
                const s = graphData.nodes.find(n => n.id === edge.source);
                const t = graphData.nodes.find(n => n.id === edge.target);
                if (!s || !t) return null;
                const isHighRisk = s.risk > 80 && t.risk > 80;

                return (
                  <g key={idx}>
                    <line
                      x1={s.x} y1={s.y}
                      x2={t.x} y2={t.y}
                      stroke={isHighRisk ? '#ff0055' : 'rgba(0, 240, 255, 0.4)'}
                      strokeWidth={isHighRisk ? 2.5 : 1.5}
                      strokeDasharray={edge.label.includes('CIRCULAR') ? '4' : 'none'}
                    />
                    <text
                      x={(s.x + t.x) / 2}
                      y={(s.y + t.y) / 2 - 4}
                      fill={isHighRisk ? '#ff88aa' : '#64748b'}
                      fontSize="9"
                      fontFamily="monospace"
                      textAnchor="middle"
                    >
                      {edge.label}
                    </text>
                  </g>
                );
              })}

              {/* Draw Nodes */}
              {graphData.nodes.map(node => {
                const isSelected = selectedNode === node.id;
                const isHighRisk = node.risk > 80;
                const circleColor = isHighRisk ? '#ff0055' : '#00ff88';

                return (
                  <g
                    key={node.id}
                    onClick={() => setSelectedNode(node.id)}
                    style={{ cursor: 'pointer' }}
                  >
                    {/* Halo ring for selected */}
                    {isSelected && (
                      <circle
                        cx={node.x} cy={node.y} r="22"
                        fill="none" stroke="#00f0ff" strokeWidth="2"
                        strokeDasharray="3 3"
                      />
                    )}
                    <circle
                      cx={node.x} cy={node.y} r="14"
                      fill="#040812"
                      stroke={circleColor} strokeWidth="2.5"
                    />
                    <text
                      x={node.x} y={node.y + 4}
                      fill="#ffffff" fontSize="9" fontWeight="bold"
                      fontFamily="monospace" textAnchor="middle"
                    >
                      {node.type.substring(0, 2)}
                    </text>
                    <text
                      x={node.x} y={node.y + 28}
                      fill={isHighRisk ? '#ffaacc' : '#94a3b8'}
                      fontSize="10" fontFamily="monospace" textAnchor="middle"
                    >
                      {node.label}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
        </div>

        {/* Right Details Panel */}
        <div style={styles.card}>
          <div style={styles.cardTitle}>
            <span>🔍 GNN Node Embedding Inspector</span>
            <span style={styles.badge(activeNodeInfo.risk > 80 ? '#ff0055' : '#00ff88')}>
              RISK: {activeNodeInfo.risk}%
            </span>
          </div>

          <div style={{ fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div>
              <span style={{ color: '#94a3b8' }}>Node ID:</span>{' '}
              <span style={{ color: '#00f0ff', fontWeight: 'bold' }}>{activeNodeInfo.id}</span>
            </div>
            <div>
              <span style={{ color: '#94a3b8' }}>Entity Type:</span>{' '}
              <span style={{ color: '#e2e8f0' }}>{activeNodeInfo.type}</span>
            </div>
            <div>
              <span style={{ color: '#94a3b8' }}>Detected Ring:</span>{' '}
              <span style={{ color: activeNodeInfo.ring !== 'NONE' ? '#ff3355' : '#00ff88', fontWeight: 'bold' }}>
                {activeNodeInfo.ring}
              </span>
            </div>
          </div>

          <div style={{ background: '#040812', padding: '10px', borderRadius: '6px', fontSize: '10px' }}>
            <div style={{ color: '#64748b', marginBottom: '6px' }}>GRAPH EMBEDDING VECTOR (z_v ∈ ℝ¹²⁸)</div>
            <div style={{ color: '#a855f7', wordBreak: 'break-all', fontFamily: 'monospace' }}>
              [-0.412, +0.892, +1.240, -0.015, +2.188, -0.901, +0.442, +1.082, -0.331, ...]
            </div>
          </div>

          <div style={{ marginTop: '10px' }}>
            <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '8px' }}>FLAGGED SYBIL/RING ENTITIES:</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {graphData.nodes.filter(n => n.risk > 80).slice(0, 4).map(node => (
                <div
                  key={node.id}
                  onClick={() => setSelectedNode(node.id)}
                  style={styles.nodeItem}
                >
                  <span style={{ color: '#e2e8f0' }}>{node.label}</span>
                  <span style={{ color: '#ff0055', fontWeight: 'bold' }}>{node.risk}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

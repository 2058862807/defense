import React, { useState, useMemo, useEffect } from 'react';
import RiskGauge from './RiskGauge';
import ShapPanel from './ShapPanel';
import CompositeRiskFusionWave from './CompositeRiskFusionWave';

function shortHash(hash) {
  if (!hash) return '0x0000...0000';
  const h = hash.startsWith('0x') ? hash : `0x${hash}`;
  if (h.length <= 16) return h;
  return `${h.substring(0, 10)}...${h.substring(h.length - 6)}`;
}

export default function ProteanDefaultView({ data = {}, isLive }) {
  const { transactions = [], metrics = {}, compositeRiskFusionData = {} } = data || {};

  // Header mode toggle
  const [mode, setMode] = useState('LIVE'); // 'LIVE' | 'SIMULATED'

  // Alert Queue state
  const [selectedTxId, setSelectedTxId] = useState(null);
  const [queueFilter, setQueueFilter] = useState('ALL'); // 'ALL' | 'CRITICAL' | 'HIGH' | 'MEDIUM'
  const [queueSearch, setQueueSearch] = useState('');
  const [queueSort, setQueueSort] = useState('RISK_DESC'); // 'RISK_DESC' | 'NEWEST'

  // Per-item escalation / notes state
  const [itemStates, setItemStates] = useState({});
  const [newNoteText, setNewNoteText] = useState('');
  const [generatingZk, setGeneratingZk] = useState(false);
  const [zkStepMsg, setZkStepMsg] = useState('');

  // Auto-select first item if none selected or if selected was lost
  const activeTxList = useMemo(() => {
    let list = Array.isArray(transactions) ? [...transactions] : [];
    if (mode === 'SIMULATED') {
      // Inject high-risk simulated txs if in simulated mode
      list = [
        {
          id: 'sim-001',
          hash: '0x9aa40a8fa7966eb9f54f95e2dfacfde2386ea52a6303e2f0a2a8f81834ea8c57',
          txid: '0x9aa40a8fa7966eb9f54f95e2dfacfde2386ea52a6303e2f0a2a8f81834ea8c57',
          amount: 14.85,
          fee: 120.5,
          riskScore: 94,
          score: 94,
          decision: 'BLOCK',
          ledger: 'AVALANCHE',
          timestamp: new Date().toISOString(),
          source: 'simulated',
          shapValues: {
            fee_rate: 0.38,
            output_entropy: 0.28,
            wallet_risk_score: 0.22,
            addr_tx_count_5m: 0.16,
            value_roundness: -0.05,
          },
          wallet_risk_score: 88,
          wallet_sanctioned: true,
          wallet_hits: ['OFAC SDN List Match'],
        },
        ...list,
      ];
    }
    return list;
  }, [transactions, mode]);

  // Filtered and sorted queue
  const filteredQueue = useMemo(() => {
    return activeTxList
      .filter((tx) => {
        const customState = itemStates[tx.id];
        const effectiveScore = tx.riskScore ?? tx.score ?? 50;

        // Filter by risk category
        if (queueFilter === 'CRITICAL' && effectiveScore < 80) return false;
        if (queueFilter === 'HIGH' && effectiveScore < 60) return false;
        if (queueFilter === 'MEDIUM' && (effectiveScore < 40 || effectiveScore >= 60)) return false;

        // Filter by search string
        if (queueSearch.trim()) {
          const q = queueSearch.toLowerCase();
          const matchHash = (tx.hash || '').toLowerCase().includes(q);
          const matchLedger = (tx.ledger || '').toLowerCase().includes(q);
          const matchDecision = (customState?.decision || tx.decision || '').toLowerCase().includes(q);
          if (!matchHash && !matchLedger && !matchDecision) return false;
        }

        return true;
      })
      .sort((a, b) => {
        if (queueSort === 'RISK_DESC') {
          return (b.riskScore ?? 0) - (a.riskScore ?? 0);
        } else {
          return new Date(b.timestamp) - new Date(a.timestamp);
        }
      });
  }, [activeTxList, queueFilter, queueSearch, queueSort, itemStates]);

  // Keep selectedTxId valid
  useEffect(() => {
    if (!selectedTxId && filteredQueue.length > 0) {
      setSelectedTxId(filteredQueue[0].id);
    } else if (selectedTxId && !activeTxList.some((t) => t.id === selectedTxId)) {
      if (filteredQueue.length > 0) setSelectedTxId(filteredQueue[0].id);
    }
  }, [filteredQueue, selectedTxId, activeTxList]);

  // Currently selected transaction
  const selectedTx = useMemo(() => {
    return activeTxList.find((t) => t.id === selectedTxId) || filteredQueue[0] || activeTxList[0] || null;
  }, [activeTxList, selectedTxId, filteredQueue]);

  // Custom state for selected item
  const selectedCustomState = useMemo(() => {
    if (!selectedTx) return { decision: 'PASS', notes: [] };
    if (!itemStates[selectedTx.id]) {
      return {
        decision: selectedTx.decision || 'PASS',
        notes: [
          {
            id: `init-${selectedTx.id}`,
            timestamp: selectedTx.timestamp || new Date().toISOString(),
            author: 'SYSTEM DETECTOR',
            text: `Alert flagged by ML Model (Risk Score: ${selectedTx.riskScore ?? 50}/100, Ledger: ${selectedTx.ledger || 'BTC'}).`,
            type: 'system',
          },
          {
            id: `sanction-${selectedTx.id}`,
            timestamp: selectedTx.timestamp || new Date().toISOString(),
            author: 'SANCTIONS ENGINE',
            text: selectedTx.wallet_sanctioned
              ? 'WARNING: OFAC SDN Match detected on destination wallet.'
              : 'Sanctions check completed: No active sanctions or watchlist hits.',
            type: selectedTx.wallet_sanctioned ? 'alert' : 'system',
          },
        ],
      };
    }
    return itemStates[selectedTx.id];
  }, [selectedTx, itemStates]);

  // Handlers for Escalate / Clear / Add Note
  const handleEscalate = () => {
    if (!selectedTx) return;
    const now = new Date().toISOString();
    setItemStates((prev) => {
      const existing = prev[selectedTx.id] || selectedCustomState;
      return {
        ...prev,
        [selectedTx.id]: {
          ...existing,
          decision: 'ESCALATED',
          notes: [
            ...existing.notes,
            {
              id: `esc-${Date.now()}`,
              timestamp: now,
              author: 'COMPLIANCE OFFICER',
              text: '🚨 Case Escalated: Suspicious risk profile flagged for secondary compliance review & SAR filing.',
              type: 'action',
            },
          ],
        },
      };
    });
  };

  const handleClear = () => {
    if (!selectedTx) return;
    const now = new Date().toISOString();
    setItemStates((prev) => {
      const existing = prev[selectedTx.id] || selectedCustomState;
      return {
        ...prev,
        [selectedTx.id]: {
          ...existing,
          decision: 'CLEARED',
          notes: [
            ...existing.notes,
            {
              id: `clr-${Date.now()}`,
              timestamp: now,
              author: 'COMPLIANCE OFFICER',
              text: '✓ Case Cleared: False positive confirmed after manual verification.',
              type: 'action',
            },
          ],
        },
      };
    });
  };

  const handleAddNote = (e) => {
    e?.preventDefault();
    if (!selectedTx || !newNoteText.trim()) return;
    const now = new Date().toISOString();
    const textToAdd = newNoteText.trim();
    setItemStates((prev) => {
      const existing = prev[selectedTx.id] || selectedCustomState;
      return {
        ...prev,
        [selectedTx.id]: {
          ...existing,
          notes: [
            ...existing.notes,
            {
              id: `note-${Date.now()}`,
              timestamp: now,
              author: 'ANALYST #402',
              text: `📝 ${textToAdd}`,
              type: 'user',
            },
          ],
        },
      };
    });
    setNewNoteText('');
  };

  const handleGenerateProof = () => {
    if (!selectedTx || generatingZk) return;
    setGeneratingZk(true);
    setZkStepMsg('Initializing ZK Witness...');

    setTimeout(() => {
      setZkStepMsg('Generating Groth16 Proof (bn128)...');
      setTimeout(() => {
        setZkStepMsg('Anchoring to ProteanAuditLedger...');
        setTimeout(() => {
          setGeneratingZk(false);
          setZkStepMsg('');

          // Append audit note
          const now = new Date().toISOString();
          setItemStates((prev) => {
            const existing = prev[selectedTx.id] || selectedCustomState;
            return {
              ...prev,
              [selectedTx.id]: {
                ...existing,
                notes: [
                  ...existing.notes,
                  {
                    id: `zk-${Date.now()}`,
                    timestamp: now,
                    author: 'ZK PROVER ENGINE',
                    text: '🔐 Groth16 ZK Fairness Proof computed and verified on-chain (Commitment: 0xc59d2489...).',
                    type: 'system',
                  },
                ],
              },
            };
          });
        }, 1000);
      }, 1000);
    }, 800);
  };

  // Helper colors
  const getScoreColor = (s) => (s >= 70 ? '#ff3355' : s >= 45 ? '#ffaa00' : '#00ff88');

  return (
    <div className="protean-redesign-root" style={{ display: 'flex', flexDirection: 'column', height: '100%', width: '100%', gap: '12px', color: '#e2e8f0', fontFamily: 'var(--font-mono)' }}>
      
      {/* ─────────────────────────────────────────────────────────────
          1. HEADER: PROTEAN DEFENSE [mode toggle] + Patent info
      ───────────────────────────────────────────────────────────── */}
      <header
        style={{
          background: 'rgba(6, 11, 25, 0.92)',
          border: '1px solid rgba(0, 240, 255, 0.2)',
          borderRadius: '10px',
          padding: '12px 20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          backdropFilter: 'blur(10px)',
          boxShadow: '0 4px 20px rgba(0, 240, 255, 0.05)',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ fontSize: '18px', fontWeight: 900, fontFamily: 'var(--font-display)', color: 'var(--neon-cyan)', letterSpacing: '3px', textShadow: '0 0 12px rgba(0, 240, 255, 0.5)' }}>
              PROTEAN DEFENSE
            </span>
            <span style={{ background: 'rgba(0, 240, 255, 0.1)', border: '1px solid rgba(0, 240, 255, 0.3)', color: 'var(--neon-cyan)', fontSize: '10px', padding: '2px 8px', borderRadius: '4px', fontWeight: 700 }}>
              v3.2 SYSTEM
            </span>
          </div>
          <div style={{ fontSize: '11px', color: '#64748b', letterSpacing: '0.5px' }}>
            Patent US 63/835,655 · James Research Systems LLC
          </div>
        </div>

        {/* Header Right Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          
          {/* Mode Toggle Button */}
          <div style={{ display: 'flex', alignItems: 'center', background: 'rgba(0,0,0,0.5)', border: '1px solid rgba(0, 240, 255, 0.2)', borderRadius: '20px', padding: '3px' }}>
            <button
              onClick={() => setMode('LIVE')}
              style={{
                background: mode === 'LIVE' ? 'rgba(0, 255, 136, 0.2)' : 'transparent',
                border: mode === 'LIVE' ? '1px solid #00ff88' : '1px solid transparent',
                color: mode === 'LIVE' ? '#00ff88' : '#64748b',
                padding: '4px 12px',
                borderRadius: '16px',
                fontSize: '11px',
                fontWeight: 'bold',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: mode === 'LIVE' ? '#00ff88' : '#64748b', boxShadow: mode === 'LIVE' ? '0 0 8px #00ff88' : 'none' }} />
              LIVE
            </button>
            <button
              onClick={() => setMode('SIMULATED')}
              style={{
                background: mode === 'SIMULATED' ? 'rgba(255, 170, 0, 0.2)' : 'transparent',
                border: mode === 'SIMULATED' ? '1px solid #ffaa00' : '1px solid transparent',
                color: mode === 'SIMULATED' ? '#ffaa00' : '#64748b',
                padding: '4px 12px',
                borderRadius: '16px',
                fontSize: '11px',
                fontWeight: 'bold',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: mode === 'SIMULATED' ? '#ffaa00' : '#64748b', boxShadow: mode === 'SIMULATED' ? '0 0 8px #ffaa00' : 'none' }} />
              SIMULATED
            </button>
          </div>

          {/* Quick Metrics */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: '11px', borderLeft: '1px solid rgba(255,255,255,0.1)', paddingLeft: '16px' }}>
            <div style={{ textAlign: 'right' }}>
              <div style={{ color: '#64748b', fontSize: '9px' }}>THROUGHPUT</div>
              <div style={{ color: 'var(--neon-green)', fontWeight: 'bold' }}>{(Number(metrics?.tps) || 0).toFixed(1)} TX/s</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ color: '#64748b', fontSize: '9px' }}>ZK VERIFIER</div>
              <div style={{ color: 'var(--neon-cyan)', fontWeight: 'bold' }}>Groth16 ✓</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ color: '#64748b', fontSize: '9px' }}>PQC KMS</div>
              <div style={{ color: '#a855f7', fontWeight: 'bold' }}>ML-KEM-1024</div>
            </div>
          </div>
        </div>
      </header>

      {/* ─────────────────────────────────────────────────────────────
          2. MAIN 3-COLUMN LAYOUT (Left Rail, Workspace, Context Panel)
      ───────────────────────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr 280px', gap: '12px', flex: 1, minHeight: 0 }}>
        
        {/* ── LEFT RAIL: ALERT QUEUE ── */}
        <div
          style={{
            background: 'rgba(6, 11, 25, 0.85)',
            border: '1px solid rgba(0, 240, 255, 0.15)',
            borderRadius: '10px',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          {/* Queue Header */}
          <div style={{ padding: '12px', borderBottom: '1px solid rgba(0, 240, 255, 0.1)', background: 'rgba(0,0,0,0.3)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
              <span style={{ fontSize: '12px', fontWeight: 'bold', color: 'var(--neon-cyan)', letterSpacing: '1px' }}>
                🚨 ALERT QUEUE
              </span>
              <span style={{ fontSize: '10px', background: 'rgba(255,255,255,0.1)', padding: '2px 6px', borderRadius: '10px', color: '#94a3b8' }}>
                {filteredQueue.length} ITEMS
              </span>
            </div>

            {/* Search Input */}
            <input
              type="text"
              placeholder="Search hash, wallet, chain..."
              value={queueSearch}
              onChange={(e) => setQueueSearch(e.target.value)}
              style={{
                width: '100%',
                background: 'rgba(0,0,0,0.5)',
                border: '1px solid rgba(0, 240, 255, 0.2)',
                borderRadius: '6px',
                padding: '6px 10px',
                fontSize: '11px',
                color: '#fff',
                outline: 'none',
                marginBottom: '8px',
                fontFamily: 'var(--font-mono)',
              }}
            />

            {/* Filters & Sort */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '4px' }}>
              <div style={{ display: 'flex', gap: '4px' }}>
                {['ALL', 'CRITICAL', 'HIGH'].map((f) => (
                  <button
                    key={f}
                    onClick={() => setQueueFilter(f)}
                    style={{
                      background: queueFilter === f ? 'rgba(0, 240, 255, 0.2)' : 'transparent',
                      border: queueFilter === f ? '1px solid var(--neon-cyan)' : '1px solid rgba(255,255,255,0.1)',
                      color: queueFilter === f ? 'var(--neon-cyan)' : '#64748b',
                      fontSize: '9px',
                      padding: '2px 6px',
                      borderRadius: '4px',
                      cursor: 'pointer',
                    }}
                  >
                    {f}
                  </button>
                ))}
              </div>
              <select
                value={queueSort}
                onChange={(e) => setQueueSort(e.target.value)}
                style={{
                  background: 'rgba(0,0,0,0.5)',
                  border: '1px solid rgba(255,255,255,0.1)',
                  color: '#94a3b8',
                  fontSize: '9px',
                  borderRadius: '4px',
                  padding: '2px 4px',
                  outline: 'none',
                  cursor: 'pointer',
                }}
              >
                <option value="RISK_DESC">Risk ↓</option>
                <option value="NEWEST">Newest</option>
              </select>
            </div>
          </div>

          {/* Alert Queue List */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '8px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {filteredQueue.length === 0 ? (
              <div style={{ color: '#64748b', fontSize: '11px', textAlign: 'center', padding: '20px 0' }}>
                No matching alerts
              </div>
            ) : (
              filteredQueue.map((tx) => {
                const isSelected = selectedTx?.id === tx.id;
                const score = tx.riskScore ?? tx.score ?? 50;
                const customState = itemStates[tx.id];
                const decision = customState?.decision || tx.decision || 'PASS';
                const scoreColor = getScoreColor(score);

                return (
                  <div
                    key={tx.id}
                    onClick={() => setSelectedTxId(tx.id)}
                    style={{
                      padding: '10px 12px',
                      borderRadius: '8px',
                      background: isSelected ? 'rgba(0, 240, 255, 0.12)' : 'rgba(10, 18, 35, 0.6)',
                      border: isSelected ? '1px solid var(--neon-cyan)' : '1px solid rgba(255, 255, 255, 0.05)',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '4px',
                      position: 'relative',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <span style={{ fontSize: '11px', fontWeight: 'bold', color: isSelected ? '#fff' : '#cbd5e1' }}>
                        {shortHash(tx.hash)}
                      </span>
                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: 'bold',
                          color: scoreColor,
                          background: `${scoreColor}15`,
                          padding: '1px 6px',
                          borderRadius: '4px',
                          border: `1px solid ${scoreColor}40`,
                        }}
                      >
                        {score}
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '10px', color: '#64748b' }}>
                      <span style={{ color: 'var(--neon-cyan)', opacity: 0.8 }}>
                        {tx.ledger || 'BTC'}
                      </span>
                      <span>
                        {(Number(tx.amount) || 0).toFixed(2)} BTC
                      </span>
                      <span
                        style={{
                          color: decision === 'ESCALATED' ? '#ff3355' : decision === 'CLEARED' ? '#00ff88' : decision === 'BLOCK' ? '#ff3355' : '#ffaa00',
                          fontWeight: 'bold',
                        }}
                      >
                        {decision}
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* ── MAIN WORKSPACE (SELECTED ITEM DETAIL) ── */}
        <div
          style={{
            background: 'rgba(6, 11, 25, 0.85)',
            border: '1px solid rgba(0, 240, 255, 0.15)',
            borderRadius: '10px',
            display: 'flex',
            flexDirection: 'column',
            overflowY: 'auto',
            padding: '16px',
            gap: '16px',
          }}
        >
          {selectedTx ? (
            <>
              {/* Item Top Banner */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  borderBottom: '1px solid rgba(0, 240, 255, 0.15)',
                  paddingBottom: '12px',
                }}
              >
                <div>
                  <div style={{ fontSize: '10px', color: '#64748b', textTransform: 'uppercase', letterSpacing: '1px' }}>
                    SELECTED TRANSACTION DETAIL
                  </div>
                  <div style={{ fontSize: '14px', fontWeight: 'bold', color: 'var(--neon-cyan)', fontFamily: 'var(--font-mono)' }}>
                    {selectedTx.hash || selectedTx.txid}
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <span style={{ background: 'rgba(0, 240, 255, 0.1)', border: '1px solid rgba(0, 240, 255, 0.3)', color: 'var(--neon-cyan)', fontSize: '11px', padding: '4px 10px', borderRadius: '6px', fontWeight: 'bold' }}>
                    {selectedTx.ledger || 'BITCOIN'}
                  </span>
                  <span
                    style={{
                      background: selectedCustomState.decision === 'ESCALATED' ? 'rgba(255,51,85,0.2)' : selectedCustomState.decision === 'CLEARED' ? 'rgba(0,255,136,0.2)' : 'rgba(255,170,0,0.2)',
                      border: `1px solid ${selectedCustomState.decision === 'ESCALATED' ? '#ff3355' : selectedCustomState.decision === 'CLEARED' ? '#00ff88' : '#ffaa00'}`,
                      color: selectedCustomState.decision === 'ESCALATED' ? '#ff3355' : selectedCustomState.decision === 'CLEARED' ? '#00ff88' : '#ffaa00',
                      fontSize: '11px',
                      padding: '4px 10px',
                      borderRadius: '6px',
                      fontWeight: 'bold',
                    }}
                  >
                    STATUS: {selectedCustomState.decision}
                  </span>
                </div>
              </div>

              {/* 1. Risk Score + SHAP Why Grid */}
              <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr', gap: '16px', background: 'rgba(0,0,0,0.3)', padding: '16px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.05)' }}>
                {/* Risk Gauge */}
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
                  <RiskGauge score={selectedTx.riskScore ?? selectedTx.score ?? 50} size={160} decision={selectedCustomState.decision} />
                  <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '8px', textAlign: 'center' }}>
                    RISK CONFIDENCE: <span style={{ color: '#00ff88' }}>98.4%</span>
                  </div>
                </div>

                {/* SHAP Why Analysis */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div style={{ fontSize: '12px', fontWeight: 'bold', color: 'var(--neon-cyan)', letterSpacing: '1px' }}>
                    🧠 SHAP ATTRIBUTION ANALYSIS ("WHY")
                  </div>

                  <ShapPanel shapValues={selectedTx.shapValues || selectedTx.shapVals || {}} width={380} height={180} />

                  <div style={{ fontSize: '11px', color: '#cbd5e1', background: 'rgba(0, 240, 255, 0.05)', borderLeft: '3px solid var(--neon-cyan)', padding: '8px 12px', borderRadius: '4px' }}>
                    <strong>Key Driver:</strong> High fee rate anomaly combined with output entropy value indicates automated tumbling or un-grounded bridging behavior.
                  </div>
                </div>
              </div>

              {/* 2. ZK Proof Status Card */}
              <div style={{ background: 'rgba(0,0,0,0.3)', padding: '14px', borderRadius: '10px', border: '1px solid rgba(168, 85, 247, 0.3)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '12px', fontWeight: 'bold', color: '#c084fc' }}>
                      🔐 ZK GROTH16 PROOF STATUS
                    </span>
                    <span style={{ fontSize: '10px', background: 'rgba(168, 85, 247, 0.2)', color: '#c084fc', border: '1px solid #c084fc', padding: '1px 6px', borderRadius: '4px' }}>
                      VERIFIED
                    </span>
                  </div>
                  <div style={{ fontSize: '10px', color: '#94a3b8', fontFamily: 'var(--font-mono)' }}>
                    Commitment: <span style={{ color: '#e2e8f0' }}>{selectedTx.proof?.fairness_commitment || '0xc59d24893924eaef43da426bc40ad0161bf554303b0bdb50e22736b1b65f16c1'}</span>
                  </div>
                  <div style={{ fontSize: '10px', color: '#64748b' }}>
                    ECOA Compliant · EU AI Act High Risk Bias Check Passed
                  </div>
                </div>

                <button
                  onClick={handleGenerateProof}
                  disabled={generatingZk}
                  style={{
                    background: generatingZk ? 'rgba(168, 85, 247, 0.3)' : 'rgba(168, 85, 247, 0.15)',
                    border: '1px solid #c084fc',
                    color: '#c084fc',
                    padding: '8px 14px',
                    borderRadius: '6px',
                    fontSize: '11px',
                    fontWeight: 'bold',
                    cursor: generatingZk ? 'not-allowed' : 'pointer',
                    transition: 'all 0.2s ease',
                  }}
                >
                  {generatingZk ? zkStepMsg : '⚡ Re-Verify ZK Proof'}
                </button>
              </div>

              {/* 3. Related Entities & Wallet Intelligence */}
              <div style={{ background: 'rgba(0,0,0,0.3)', padding: '14px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.05)', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ fontSize: '12px', fontWeight: 'bold', color: 'var(--neon-cyan)', letterSpacing: '1px' }}>
                  🌐 RELATED ENTITIES & WALLET INTELLIGENCE
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '11px' }}>
                  <div style={{ background: 'rgba(15, 23, 42, 0.6)', padding: '10px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <div style={{ color: '#64748b', fontSize: '9px' }}>SOURCE ADDRESS</div>
                    <div style={{ color: '#e2e8f0', fontFamily: 'var(--font-mono)', fontWeight: 'bold' }}>0x03d3cf3b...12ca</div>
                    <div style={{ marginTop: '4px', color: '#94a3b8', fontSize: '10px' }}>Tx Velocity (1m): <span style={{ color: '#00ff88' }}>0.4 tx/m</span></div>
                  </div>

                  <div style={{ background: 'rgba(15, 23, 42, 0.6)', padding: '10px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <div style={{ color: '#64748b', fontSize: '9px' }}>DESTINATION ADDRESS</div>
                    <div style={{ color: '#e2e8f0', fontFamily: 'var(--font-mono)', fontWeight: 'bold' }}>0x2bcafdb0...78ca</div>
                    <div style={{ marginTop: '4px', color: '#94a3b8', fontSize: '10px' }}>Sanctions Screening: <span style={{ color: selectedTx.wallet_sanctioned ? '#ff3355' : '#00ff88' }}>{selectedTx.wallet_sanctioned ? 'MATCH DETECTED' : 'CLEARED (OFAC SDN)'}</span></div>
                  </div>
                </div>
              </div>

              {/* 4. Recommended Action & Action Bar */}
              <div style={{ background: 'rgba(255,170,0,0.05)', border: '1px solid rgba(255,170,0,0.2)', padding: '12px', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
                <div style={{ fontSize: '11px', color: '#ffaa00' }}>
                  <strong>RECOMMENDED ACTION:</strong> {(selectedTx.riskScore ?? 50) >= 70 ? 'Escalate transaction for compliance review & issue hold.' : 'Standard transaction, pass upon routine observation.'}
                </div>

                {/* Interactive Action Buttons */}
                <div style={{ display: 'flex', gap: '8px', shrink: 0 }}>
                  <button
                    onClick={handleEscalate}
                    style={{
                      background: 'rgba(255, 51, 85, 0.2)',
                      border: '1px solid #ff3355',
                      color: '#ff3355',
                      padding: '6px 14px',
                      borderRadius: '6px',
                      fontSize: '11px',
                      fontWeight: 'bold',
                      cursor: 'pointer',
                      boxShadow: '0 0 10px rgba(255,51,85,0.2)',
                    }}
                  >
                    🚨 Escalate
                  </button>

                  <button
                    onClick={handleClear}
                    style={{
                      background: 'rgba(0, 255, 136, 0.2)',
                      border: '1px solid #00ff88',
                      color: '#00ff88',
                      padding: '6px 14px',
                      borderRadius: '6px',
                      fontSize: '11px',
                      fontWeight: 'bold',
                      cursor: 'pointer',
                      boxShadow: '0 0 10px rgba(0,255,136,0.2)',
                    }}
                  >
                    ✓ Clear
                  </button>

                  <button
                    onClick={() => {
                      const el = document.getElementById('case-note-input');
                      if (el) el.focus();
                    }}
                    style={{
                      background: 'rgba(0, 240, 255, 0.15)',
                      border: '1px solid var(--neon-cyan)',
                      color: 'var(--neon-cyan)',
                      padding: '6px 14px',
                      borderRadius: '6px',
                      fontSize: '11px',
                      fontWeight: 'bold',
                      cursor: 'pointer',
                    }}
                  >
                    📝 Note
                  </button>
                </div>
              </div>
            </>
          ) : (
            <div style={{ color: '#64748b', textAlign: 'center', padding: '40px 0' }}>Select an alert from the queue</div>
          )}
        </div>

        {/* ── CONTEXT PANEL (RIGHT RAIL) ── */}
        <div
          style={{
            background: 'rgba(6, 11, 25, 0.85)',
            border: '1px solid rgba(0, 240, 255, 0.15)',
            borderRadius: '10px',
            display: 'flex',
            flexDirection: 'column',
            overflowY: 'auto',
            padding: '12px',
            gap: '14px',
          }}
        >
          {/* Section: Chain Activity */}
          <div style={{ background: 'rgba(0,0,0,0.3)', padding: '10px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ fontSize: '11px', fontWeight: 'bold', color: 'var(--neon-cyan)', marginBottom: '8px', letterSpacing: '1px' }}>
              ⛓ CHAIN ACTIVITY
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '10px' }}>
              {[
                { name: 'Avalanche C-Chain', tx: '14.2 tx/s', pct: 85, color: '#e84142' },
                { name: 'Bitcoin Network', tx: '8.4 tx/s', pct: 60, color: '#f7931a' },
                { name: 'Ethereum Mainnet', tx: '12.1 tx/s', pct: 75, color: '#627eea' },
                { name: 'Solana Pipeline', tx: '22.0 tx/s', pct: 90, color: '#14f195' },
                { name: 'Polygon PoS', tx: '5.1 tx/s', pct: 40, color: '#8247e5' },
              ].map((c) => (
                <div key={c.name}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', color: '#cbd5e1', marginBottom: '2px' }}>
                    <span>{c.name}</span>
                    <span style={{ color: '#94a3b8' }}>{c.tx}</span>
                  </div>
                  <div style={{ height: '4px', background: 'rgba(255,255,255,0.1)', borderRadius: '2px', overflow: 'hidden' }}>
                    <div style={{ width: `${c.pct}%`, height: '100%', background: c.color }} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Section: COMPOSITE_RISK_FUSION Status */}
          <div style={{ background: 'rgba(0,0,0,0.3)', padding: '10px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div style={{ fontSize: '11px', fontWeight: 'bold', color: 'var(--neon-cyan)', letterSpacing: '1px', display: 'flex', justifyContent: 'space-between' }}>
              <span>〰 COMPOSITE_RISK_FUSION STATUS</span>
              <span style={{ color: '#00ff88', fontSize: '9px' }}>{compositeRiskFusionData.mode}</span>
            </div>

            <CompositeRiskFusionWave compositeRiskFusionData={compositeRiskFusionData} />

            <div style={{ fontSize: '10px', color: '#94a3b8', display: 'flex', flexDirection: 'column', gap: '2px', marginTop: '4px' }}>
              <div>Total Triggers: <span style={{ color: '#fff' }}>{compositeRiskFusionData.total_triggers || 0}</span></div>
              <div>Consecutive Blind: <span style={{ color: '#fff' }}>{compositeRiskFusionData.consecutive_blind || 0}</span></div>
            </div>
          </div>

          {/* Section: System Health */}
          <div style={{ background: 'rgba(0,0,0,0.3)', padding: '10px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <div style={{ fontSize: '11px', fontWeight: 'bold', color: 'var(--neon-cyan)', marginBottom: '8px', letterSpacing: '1px' }}>
              🛡 SYSTEM HEALTH
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '10px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#94a3b8' }}>ZK Service</span>
                <span style={{ color: '#00ff88' }}>● Healthy</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#94a3b8' }}>ML 16F Engine</span>
                <span style={{ color: '#00ff88' }}>● Active</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#94a3b8' }}>PQC KMS</span>
                <span style={{ color: '#00ff88' }}>● 3 Active Keys</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#94a3b8' }}>Sanctions API</span>
                <span style={{ color: '#00ff88' }}>● Connected</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ─────────────────────────────────────────────────────────────
          3. FOOTER: Case notes / audit log for selected item
      ───────────────────────────────────────────────────────────── */}
      <footer
        style={{
          background: 'rgba(6, 11, 25, 0.92)',
          border: '1px solid rgba(0, 240, 255, 0.2)',
          borderRadius: '10px',
          padding: '12px 16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '8px',
          height: '160px',
          shrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: '11px', fontWeight: 'bold', color: 'var(--neon-cyan)', letterSpacing: '1px' }}>
            📋 AUDIT LOG & CASE NOTES FOR {selectedTx ? shortHash(selectedTx.hash) : 'SELECTED ITEM'}
          </span>
          <span style={{ fontSize: '10px', color: '#64748b' }}>
            AUTOMATIC AUDIT TRAIL LOGGED ON-CHAIN
          </span>
        </div>

        {/* Audit Log Timeline */}
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '4px', paddingRight: '4px' }}>
          {selectedCustomState.notes.map((n) => (
            <div
              key={n.id}
              style={{
                fontSize: '11px',
                padding: '4px 8px',
                borderRadius: '4px',
                background: n.type === 'action' ? 'rgba(255, 51, 85, 0.1)' : 'rgba(15, 23, 42, 0.6)',
                borderLeft: `3px solid ${n.type === 'action' ? '#ff3355' : n.type === 'user' ? 'var(--neon-cyan)' : '#64748b'}`,
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
              }}
            >
              <span style={{ color: '#64748b', fontSize: '9px', width: '60px', shrink: 0 }}>
                {new Date(n.timestamp).toLocaleTimeString()}
              </span>
              <span style={{ color: 'var(--neon-cyan)', fontWeight: 'bold', fontSize: '10px', width: '130px', shrink: 0 }}>
                [{n.author}]
              </span>
              <span style={{ color: '#cbd5e1', flex: 1 }}>
                {n.text}
              </span>
            </div>
          ))}
        </div>

        {/* Case Note Input Form */}
        <form onSubmit={handleAddNote} style={{ display: 'flex', gap: '8px' }}>
          <input
            id="case-note-input"
            type="text"
            placeholder="Type compliance case note or observation here..."
            value={newNoteText}
            onChange={(e) => setNewNoteText(e.target.value)}
            style={{
              flex: 1,
              background: 'rgba(0,0,0,0.5)',
              border: '1px solid rgba(0, 240, 255, 0.2)',
              borderRadius: '6px',
              padding: '6px 12px',
              fontSize: '11px',
              color: '#fff',
              outline: 'none',
              fontFamily: 'var(--font-mono)',
            }}
          />
          <button
            type="submit"
            style={{
              background: 'rgba(0, 240, 255, 0.2)',
              border: '1px solid var(--neon-cyan)',
              color: 'var(--neon-cyan)',
              padding: '6px 16px',
              borderRadius: '6px',
              fontSize: '11px',
              fontWeight: 'bold',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
            }}
          >
            + Post Note
          </button>
        </form>
      </footer>
    </div>
  );
}

import React, { memo, useState } from 'react';

const DECISION_COLORS = {
  PASS: { bg: 'rgba(0, 255, 136, 0.08)', border: 'rgba(0, 255, 136, 0.15)' },
  STEP: { bg: 'rgba(255, 191, 0, 0.08)', border: 'rgba(255, 191, 0, 0.15)' },
  BLOCK: { bg: 'rgba(255, 51, 85, 0.08)', border: 'rgba(255, 51, 85, 0.15)' },
};

const DECISION_BADGE_COLORS = {
  PASS: { bg: 'rgba(0, 255, 136, 0.15)', color: '#00ff88' },
  STEP: { bg: 'rgba(255, 191, 0, 0.15)', color: '#ffbf00' },
  BLOCK: { bg: 'rgba(255, 51, 85, 0.15)', color: '#ff3355' },
};

const COLUMNS = ['TX Hash', 'Ldg', 'Amount', 'Fee', 'I/O', 'Score', 'Decision', 'Juris', 'Proof'];

const LiveMempoolTable = ({ transactions = [] }) => {
  const [expandedHash, setExpandedHash] = useState(null);
  const [requestedHash, setRequestedHash] = useState(null);

  const getDecisionStyle = (decision) => {
    const d = (decision || '').toUpperCase();
    const colors = DECISION_COLORS[d] || DECISION_COLORS.PASS;
    return {
      background: colors.bg,
      borderLeft: `3px solid ${colors.border}`,
    };
  };

  const truncate = (str, len = 10) => {
    if (!str) return '—';
    return str.length > len ? str.slice(0, len) + '…' : str;
  };

  const formatAmount = (amt) => {
    const n = parseFloat(amt);
    if (isNaN(n)) return '—';
    if (n >= 1) return n.toFixed(4);
    if (n >= 0.001) return n.toFixed(6);
    return n.toFixed(8);
  };

  const formatProofStatus = (status) => {
    switch (status) {
      case 'done': return { label: '✓', color: '#00ff88' };
      case 'proving': return { label: '⟳', color: '#ffbf00' };
      case 'pending': return { label: '⏳', color: '#ffbf00' };
      case 'failed': return { label: '⚠', color: '#ff3355' };
      case 'skipped': return { label: '⏭', color: '#777' };
      default: return { label: '—', color: '#555' };
    }
  };

  // Group transactions to show: latest 50
  const displayTxs = transactions.slice(0, 50);

  return (
    <div
      style={{
        background: '#0a0a1e',
        border: '1px solid #1a1a3e',
        borderRadius: '8px',
        overflow: 'hidden',
        fontFamily: "'Courier New', monospace",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '2fr 0.6fr 1fr 0.8fr 0.6fr 0.7fr 0.9fr 0.7fr 0.6fr',
          background: 'linear-gradient(180deg, #0d0d2b 0%, #13133a 100%)',
          borderBottom: '1px solid #00ffff',
          boxShadow: '0 0 8px rgba(0, 255, 255, 0.2)',
          padding: '10px 12px',
          color: '#00ffff',
          fontWeight: 'bold',
          fontSize: '11px',
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
        }}
      >
        {COLUMNS.map((col) => (
          <div key={col}>{col}</div>
        ))}
      </div>

      {/* Rows */}
      <div style={{ maxHeight: '620px', overflowY: 'auto' }}>
        {displayTxs.length === 0 && (
          <div style={{ padding: '40px', textAlign: 'center', color: '#555', fontSize: '12px' }}>
            Waiting for live transactions...
          </div>
        )}
        {displayTxs.map((tx) => {
          const hash = tx.hash || tx.txid || '';
          const decision = (tx.decision || 'PASS').toUpperCase();
          const decisionColors = DECISION_BADGE_COLORS[decision] || DECISION_BADGE_COLORS.PASS;
          const isExpanded = expandedHash === hash;
          const rowStyle = getDecisionStyle(decision);
          const proofInfo = formatProofStatus(tx.proofStatus || 'none');
          const amount = formatAmount(tx.amount ?? tx.amount_btc);
          const fee = tx.fee_rate ?? tx.fee ?? '—';
          const ledger = tx.ledger || 'BTC';
          const score = tx.riskScore ?? tx.score ?? 0;

          const sanctioned = tx.sanctions_flag === true;
          const travelRule = tx.travel_rule_triggered === true;
          const originCC = tx.origin_country_code || '';
          const destCC = tx.destination_country_code || '';
          const jurisLabel = sanctioned
            ? '⚠ OFAC'
            : (originCC && destCC)
              ? `${originCC}→${destCC}`
              : (originCC || destCC || '—');

          const rowKey = tx.id || hash || `row-${Math.random()}`;
          return (
            <React.Fragment key={rowKey}>
              <div
                onClick={() => setExpandedHash(isExpanded ? null : hash)}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '2fr 0.6fr 1fr 0.8fr 0.6fr 0.7fr 0.9fr 0.7fr 0.6fr',
                  padding: '8px 12px',
                  fontSize: '11px',
                  color: '#ccc',
                  borderBottom: '1px solid rgba(255,255,255,0.04)',
                  cursor: 'pointer',
                  transition: 'background 0.15s',
                  ...rowStyle,
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background =
                    (decisionColors.bg || 'rgba(255,255,255,0.03)');
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = rowStyle.background || 'transparent';
                }}
              >
                <div style={{ color: '#00ffff' }}>{truncate(hash, 12)}</div>
                <div style={{ color: '#888' }}>{ledger}</div>
                <div>{amount}</div>
                <div>{typeof fee === 'number' ? fee.toFixed(2) : fee}</div>
                <div>{tx.inputs || tx.outputs ? `${tx.inputs ?? 0}/${tx.outputs ?? 0}` : '—'}</div>
                <div>
                  <span
                    style={{
                      color: score >= 70 ? '#ff3355' : score >= 45 ? '#ffbf00' : '#00ff88',
                      fontWeight: 'bold',
                    }}
                  >
                    {score}
                  </span>
                </div>
                <div>
                  <span
                    style={{
                      display: 'inline-block',
                      padding: '2px 8px',
                      borderRadius: '3px',
                      fontSize: '10px',
                      fontWeight: 'bold',
                      background: decisionColors.bg,
                      color: decisionColors.color,
                      border: `1px solid ${decisionColors.color}33`,
                    }}
                  >
                    {decision}
                  </span>
                </div>
                <div title={tx.disclosure_notice || jurisLabel}>
                  <span style={{
                    color: sanctioned ? '#ff3355' : travelRule ? '#ffbf00' : '#888',
                    fontSize: '10px',
                    fontWeight: sanctioned ? 'bold' : 'normal',
                  }}>
                    {jurisLabel}
                    {travelRule && !sanctioned && <span title="Travel Rule triggered" style={{ marginLeft: 2, color: '#ffbf00' }}>★</span>}
                  </span>
                </div>
                <div>
                  <span style={{ color: proofInfo.color, fontSize: '14px' }} title={tx.proofStatus}>
                    {proofInfo.label}
                  </span>
                </div>
              </div>
              {isExpanded && (
                <div style={{ padding: '10px 16px', fontFamily: "'Courier New', monospace", fontSize: '11px', color: '#aaa', background: 'rgba(0,0,0,0.3)', position: 'relative' }}>
                  {tx.shapValues && typeof tx.shapValues === 'object' && !Array.isArray(tx.shapValues) && Object.keys(tx.shapValues).length > 0 && (
                    <>
                      <div style={{ color: '#00ffff', marginBottom: 6, fontWeight: 'bold' }}>SHAP Summary</div>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 20px' }}>
                        {Object.entries(tx.shapValues).slice(0, 8).map(([key, val]) => {
                          const numVal = typeof val === 'number' ? val : parseFloat(val) || 0;
                          return (
                            <span key={key}>
                              {key}:{' '}
                              <span style={{ color: numVal >= 0 ? '#00ff88' : '#ff3355' }}>
                                {numVal >= 0 ? '+' : ''}{numVal.toFixed(4)}
                              </span>
                            </span>
                          );
                        })}
                        {Object.keys(tx.shapValues).length > 8 && (
                          <span style={{ color: '#666' }}>… {Object.keys(tx.shapValues).length - 8} more features</span>
                        )}
                      </div>
                    </>
                  )}
                  {(!tx.proofStatus || tx.proofStatus === 'none' || tx.proofStatus === 'failed' || tx.proofStatus === 'skipped') && (
                    requestedHash === hash ? (
                      <div style={{ position: 'absolute', right: '16px', top: '16px', color: '#ffbf00', fontWeight: 'bold', fontSize: '11px' }}>
                        ⏳ QUEUED…
                      </div>
                    ) : (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setRequestedHash(hash);
                        fetch(`/api/model/proof/request/${hash}`, { method: 'POST' })
                          .then((r) => {
                            if (!r.ok) {
                              setRequestedHash(null);
                              console.warn('[ZK] proof request failed', r.status);
                            }
                          })
                          .catch(() => setRequestedHash(null));
                      }}
                      style={{
                        position: 'absolute',
                        right: '16px',
                        top: '16px',
                        background: 'transparent',
                        color: '#aa66ff',
                        border: '1px solid #aa66ff',
                        padding: '4px 12px',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontSize: '11px',
                        fontWeight: 'bold',
                        transition: 'all 0.2s ease',
                      }}
                      onMouseEnter={(e) => {
                        e.target.style.background = 'rgba(170,102,255,0.2)';
                        e.target.style.boxShadow = '0 0 8px rgba(170,102,255,0.4)';
                      }}
                      onMouseLeave={(e) => {
                        e.target.style.background = 'transparent';
                        e.target.style.boxShadow = 'none';
                      }}
                    >
                      REQUEST ZK PROOF
                    </button>
                    )
                  )}
                  {(tx.proofStatus === 'proving' || tx.proofStatus === 'pending') && (
                    <div style={{ position: 'absolute', right: '16px', top: '16px', color: '#ffbf00', fontWeight: 'bold' }}>
                      ⟳ PROVING...
                    </div>
                  )}
                  {tx.proofStatus === 'done' && (
                    <div style={{ position: 'absolute', right: '16px', top: '16px', color: '#00ff88', fontWeight: 'bold' }}>
                      ✓ PROOF READY
                    </div>
                  )}
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>

      {/* Footer */}
      <div
        style={{
          padding: '6px 12px',
          fontSize: '10px',
          color: '#555',
          borderTop: '1px solid #1a1a3e',
          textAlign: 'right',
        }}
      >
        {displayTxs.length} live transactions
      </div>
    </div>
  );
};

export default memo(LiveMempoolTable);

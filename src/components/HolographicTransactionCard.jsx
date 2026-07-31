import React, { memo, useState, useMemo } from 'react';

function truncateHash(hash, start = 8, end = 6) {
  if (!hash) return '0x0000...0000';
  const h = hash.startsWith('0x') ? hash : `0x${hash}`;
  if (h.length <= start + end + 3) return h;
  return `${h.substring(0, start + 2)}...${h.substring(h.length - end)}`;
}

function getDecisionColor(decision) {
  switch (decision) {
    case 'PASS': return '#00ff88';
    case 'STEP': return '#ffaa00';
    case 'BLOCK': return '#ff3355';
    default: return '#00ff88';
  }
}

function getScoreColor(score) {
  if (score <= 44) return '#00ff88';
  if (score <= 69) return '#ffaa00';
  return '#ff3355';
}

const SHAP_FEATURE_KEYS = [
  'input_count', 'output_count', 'amount_btc', 'fee_rate',
  'unique_inputs', 'unique_outputs', 'iou_ratio', 'dust_output_count',
  'output_entropy', 'output_value_gini', 'fee_ratio_pct', 'weight_efficiency',
  'value_roundness', 'addr_tx_count_1m', 'addr_tx_count_5m', 'is_seen_address',
];

const styles = {
  card: {
    background: 'rgba(10, 22, 40, 0.75)',
    /* backdrop-filter removed for Firefox perf */
    
    border: '1px solid rgba(0, 240, 255, 0.15)',
    borderRadius: '12px',
    padding: '16px',
    position: 'relative',
    overflow: 'hidden',
    cursor: 'pointer',
    transition: 'all 0.3s ease',
    animation: 'slideIn 0.4s ease-out forwards',
  },
  leftBorder: {
    position: 'absolute',
    left: 0,
    top: '8px',
    bottom: '8px',
    width: '3px',
    borderRadius: '0 3px 3px 0',
    transition: 'all 0.3s ease',
  },
  topRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: '10px',
  },
  hashContainer: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  hashText: {
    fontFamily: "'JetBrains Mono', 'Courier New', monospace",
    fontSize: '13px',
    color: 'rgba(0, 240, 255, 0.9)',
    letterSpacing: '0.5px',
  },
  ledgerBadge: {
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: '10px',
    padding: '2px 6px',
    borderRadius: '4px',
    background: 'rgba(0, 240, 255, 0.1)',
    color: 'rgba(0, 240, 255, 0.6)',
    border: '1px solid rgba(0, 240, 255, 0.15)',
  },
  badgesRow: {
    display: 'flex',
    gap: '6px',
    alignItems: 'center',
  },
  riskBadge: {
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: '11px',
    fontWeight: 'bold',
    padding: '3px 8px',
    borderRadius: '4px',
    border: '1px solid',
    minWidth: '36px',
    textAlign: 'center',
  },
  decisionBadge: {
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: '10px',
    fontWeight: 'bold',
    padding: '3px 8px',
    borderRadius: '4px',
    letterSpacing: '1px',
    border: '1px solid',
    minWidth: '52px',
    textAlign: 'center',
  },
  infoRow: {
    display: 'flex',
    gap: '16px',
    flexWrap: 'wrap',
    marginBottom: '6px',
  },
  infoItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
  },
  infoLabel: {
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: '11px',
    color: 'rgba(255, 255, 255, 0.35)',
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
  },
  infoValue: {
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: '12px',
    color: 'rgba(255, 255, 255, 0.8)',
  },
  timestamp: {
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: '10px',
    color: 'rgba(255, 255, 255, 0.25)',
    marginTop: '4px',
  },
  expandIcon: {
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: '14px',
    color: 'rgba(0, 240, 255, 0.4)',
    transition: 'transform 0.3s ease',
    marginLeft: 'auto',
  },
  expandPanel: {
    marginTop: '12px',
    paddingTop: '12px',
    borderTop: '1px solid rgba(0, 240, 255, 0.1)',
    animation: 'expandIn 0.3s ease-out',
    overflow: 'hidden',
  },
  shapTitle: {
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: '10px',
    color: 'rgba(0, 240, 255, 0.5)',
    textTransform: 'uppercase',
    letterSpacing: '1px',
    marginBottom: '8px',
  },
  shapBarsContainer: {
    display: 'flex',
    alignItems: 'flex-end',
    gap: '3px',
    height: '60px',
    paddingBottom: '16px',
    position: 'relative',
  },
  shapBarWrapper: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'flex-end',
    height: '100%',
    position: 'relative',
  },
  shapBar: {
    width: '100%',
    borderRadius: '2px 2px 0 0',
    minHeight: '2px',
    transition: 'height 0.6s cubic-bezier(0.34, 1.56, 0.64, 1)',
    position: 'relative',
  },
  shapLabel: {
    position: 'absolute',
    bottom: '-14px',
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: '7px',
    color: 'rgba(255, 255, 255, 0.25)',
    textAlign: 'center',
    width: '100%',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  shapValue: {
    position: 'absolute',
    top: '-14px',
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: '7px',
    textAlign: 'center',
    width: '100%',
    fontWeight: 'bold',
  },
  centerLine: {
    position: 'absolute',
    left: 0,
    right: 0,
    top: '50%',
    height: '1px',
    background: 'rgba(0, 240, 255, 0.08)',
  },
};

const HolographicTransactionCard = ({ transaction = {}, index = 0 }) => {
  const [expanded, setExpanded] = useState(false);

  const tx = transaction || {};
  const {
    hash = '',
    amount = '0.00',
    fee = '0.00',
    inputs = 0,
    outputs = 0,
    riskScore = 0,
    decision = 'PASS',
    shapValues = {},
    ledger = 'mainnet',
    timestamp = '',
    sanctions_flag = false,
    travel_rule_triggered = false,
    origin_country_code = '',
    destination_country_code = '',
    disclosure_notice = null,
  } = tx;

  const clampedScore = Math.max(0, Math.min(99, riskScore));
  const decisionColor = getDecisionColor(decision);
  const scoreColor = getScoreColor(clampedScore);
  const truncatedHash = truncateHash(hash);

  const shapEntries = useMemo(() => {
    const safeShap = (shapValues && typeof shapValues === 'object') ? shapValues : {};
    return SHAP_FEATURE_KEYS.map((key, i) => {
      const rawVal = safeShap[key];
      const val = rawVal !== undefined ? parseFloat(rawVal) || 0 : 0;
      return { key, value: val, index: i };
    });
  }, [shapValues]);

  const maxAbsShap = useMemo(() => {
    return Math.max(0.01, ...shapEntries.map(s => Math.abs(s.value)));
  }, [shapEntries]);

  const formattedTime = useMemo(() => {
    if (!timestamp) return '';
    try {
      const d = new Date(timestamp);
      return d.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return String(timestamp);
    }
  }, [timestamp]);

  const handleToggle = () => setExpanded(prev => !prev);

  const baseDelay = 0.05;
  const delay = index * baseDelay;

  return (
    <div
      style={{
        ...styles.card,
        animationDelay: `${delay}s`,
        opacity: 0,
        animationFillMode: 'forwards',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = `${decisionColor}55`;
        e.currentTarget.style.boxShadow = `0 0 20px ${decisionColor}22, 0 0 40px ${decisionColor}11`;
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'rgba(0, 240, 255, 0.15)';
        e.currentTarget.style.boxShadow = 'none';
      }}
      onClick={handleToggle}
    >
      {/* Left border glow */}
      <div
        style={{
          ...styles.leftBorder,
          background: decisionColor,
          boxShadow: `0 0 10px ${decisionColor}, 0 0 20px ${decisionColor}66`,
        }}
      />

      {/* Top row: hash + badges */}
      <div style={styles.topRow}>
        <div style={styles.hashContainer}>
          <span style={styles.hashText}>{truncatedHash}</span>
          <span style={styles.ledgerBadge}>{ledger}</span>
        </div>
        <div style={styles.badgesRow}>
          <div
            style={{
              ...styles.riskBadge,
              color: scoreColor,
              borderColor: `${scoreColor}55`,
              background: `${scoreColor}11`,
            }}
          >
            {clampedScore}
          </div>
          <div
            style={{
              ...styles.decisionBadge,
              color: decisionColor,
              borderColor: `${decisionColor}55`,
              background: `${decisionColor}15`,
            }}
          >
            {decision}
          </div>
          {sanctions_flag && (
            <div
              title={disclosure_notice || 'Sanctioned jurisdiction'}
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '9px',
                fontWeight: 'bold',
                padding: '2px 5px',
                borderRadius: '3px',
                background: 'rgba(255,51,85,0.2)',
                color: '#ff3355',
                border: '1px solid #ff335588',
                letterSpacing: '0.5px',
              }}
            >
              OFAC
            </div>
          )}
          {travel_rule_triggered && !sanctions_flag && (
            <div
              title="Travel Rule triggered (FATF Rec. 16)"
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '9px',
                fontWeight: 'bold',
                padding: '2px 5px',
                borderRadius: '3px',
                background: 'rgba(255,191,0,0.15)',
                color: '#ffbf00',
                border: '1px solid #ffbf0055',
                letterSpacing: '0.5px',
              }}
            >
              TR
            </div>
          )}
          {(origin_country_code || destination_country_code) && (
            <div
              title={`${origin_country_code || '?'} → ${destination_country_code || '?'}`}
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '9px',
                padding: '2px 5px',
                borderRadius: '3px',
                background: 'rgba(0,240,255,0.08)',
                color: 'rgba(0,240,255,0.5)',
                border: '1px solid rgba(0,240,255,0.15)',
              }}
            >
              {origin_country_code || '??'}→{destination_country_code || '??'}
            </div>
          )}
          <span style={{ ...styles.expandIcon, transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)' }}>
            ▼
          </span>
        </div>
      </div>

      {/* Info row */}
      <div style={styles.infoRow}>
        <div style={styles.infoItem}>
          <span style={styles.infoLabel}>Amount</span>
          <span style={styles.infoValue}>{amount} BTC</span>
        </div>
        <div style={styles.infoItem}>
          <span style={styles.infoLabel}>Fee</span>
          <span style={styles.infoValue}>{fee} sat/vB</span>
        </div>
        <div style={styles.infoItem}>
          <span style={styles.infoLabel}>In/Out</span>
          <span style={styles.infoValue}>{inputs}/{outputs}</span>
        </div>
      </div>

      {/* Timestamp */}
      {formattedTime && <div style={styles.timestamp}>{formattedTime}</div>}

      {/* Expandable SHAP panel */}
      {expanded && (
        <div style={styles.expandPanel}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <div style={styles.shapTitle}>SHAP Feature Contributions</div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                fetch(`/api/model/proof/request/${hash}`, { method: 'POST' });
              }}
              style={{
                background: 'transparent',
                color: '#aa66ff',
                border: '1px solid #aa66ff',
                padding: '4px 10px',
                borderRadius: '4px',
                cursor: 'pointer',
                fontSize: '10px',
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
          </div>
          <div style={styles.shapBarsContainer}>
            <div style={styles.centerLine} />
            {shapEntries.map((entry) => {
              const normalizedHeight = Math.abs(entry.value) / maxAbsShap;
              const barHeight = Math.max(4, normalizedHeight * 48);
              const isPositive = entry.value >= 0;
              const barColor = isPositive ? '#00ff88' : '#ff3355';
              const barGlow = isPositive
                ? '0 0 4px rgba(0, 255, 136, 0.3)'
                : '0 0 4px rgba(255, 51, 85, 0.3)';

              return (
                <div key={entry.key} style={styles.shapBarWrapper}>
                  <div
                    style={{
                      ...styles.shapBar,
                      height: `${barHeight}px`,
                      background: barColor,
                      boxShadow: barGlow,
                      opacity: 0.85,
                      alignSelf: isPositive ? 'flex-start' : 'flex-end',
                    }}
                  />
                  <div
                    style={{
                      ...styles.shapValue,
                      color: barColor,
                      top: isPositive ? '-12px' : 'auto',
                      bottom: isPositive ? 'auto' : `${barHeight + 2}px`,
                    }}
                  >
                    {entry.value >= 0 ? '+' : ''}{entry.value.toFixed(2)}
                  </div>
                  <div style={styles.shapLabel}>
                    {entry.key.replace(/([A-Z])/g, ' $1').replace(/^./, s => s.toUpperCase()).substring(0, 8)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <style>{`
        @keyframes slideIn {
          from {
            opacity: 0;
            transform: translateX(40px);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }
        @keyframes expandIn {
          from {
            opacity: 0;
            max-height: 0;
          }
          to {
            opacity: 1;
            max-height: 200px;
          }
        }
      `}</style>
    </div>
  );
};

export default memo(HolographicTransactionCard);

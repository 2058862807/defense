import React, { memo, useState, useEffect, useRef } from 'react';

const ProofBlockchain = ({ proofs = [] }) => {
  const [expandedId, setExpandedId] = useState(null);
  const [visible, setVisible] = useState([]);
  const containerRef = useRef(null);

  // Sequential fade-in animation
  useEffect(() => {
    if (!proofs.length) {
      setVisible([]);
      return;
    }
    setVisible([]);
    const timers = [];
    proofs.forEach((_, i) => {
      const timer = setTimeout(() => {
        setVisible((prev) => [...prev, i]);
      }, i * 200);
      timers.push(timer);
    });
    return () => timers.forEach(clearTimeout);
  }, [proofs]);

  // Determine chain verification status - pending proofs are in-flight, not compromised
  const hasFailed = proofs.some((p) => p && p.status === 'failed');
  const hasPending = proofs.some((p) => p && p.status === 'pending');
  const doneCount = proofs.filter((p) => p && (p.status === 'done' || p.verified)).length;
  const chainVerified = proofs.length > 0 && !hasFailed && !hasPending && doneCount === proofs.length;
  const chainProving = proofs.length > 0 && !hasFailed && hasPending;

  const truncateHash = (hash) => {
    if (!hash) return '—';
    return hash.length > 12 ? hash.slice(0, 6) + '…' + hash.slice(-4) : hash;
  };

  const truncateCommitment = (comm) => {
    if (!comm) return '—';
    return comm.length > 16 ? comm.slice(0, 16) + '…' : comm;
  };

  const formatTime = (ts) => {
    if (!ts) return '—';
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString('en-US', { hour12: false }) + ' ' + d.toLocaleDateString('en-US');
    } catch {
      return String(ts);
    }
  };

  const getDecisionStyle = (decision) => {
    const d = (decision || '').toUpperCase();
    switch (d) {
      case 'BLOCK':
        return { bg: 'rgba(255,51,85,0.2)', color: '#ff3355', label: 'BLOCK' };
      case 'STEP':
        return { bg: 'rgba(255,191,0,0.2)', color: '#ffbf00', label: 'STEP' };
      default:
        return { bg: 'rgba(0,255,136,0.2)', color: '#00ff88', label: 'PASS' };
    }
  };

  return (
    <div
      ref={containerRef}
      style={{
        padding: '20px',
        background: '#0a0a1e',
        borderRadius: '12px',
        border: '1px solid #1a1a3e',
        fontFamily: "'Courier New', monospace",
      }}
    >
      {/* Chain verification indicator */}
      <div
        style={{
          textAlign: 'center',
          padding: '12px 20px',
          marginBottom: '24px',
          background: chainVerified
            ? 'rgba(0, 255, 136, 0.06)'
            : chainProving
            ? 'rgba(255, 191, 0, 0.06)'
            : 'rgba(255, 51, 85, 0.06)',
          border: `1px solid ${
            chainVerified
              ? 'rgba(0,255,136,0.3)'
              : chainProving
              ? 'rgba(255,191,0,0.3)'
              : 'rgba(255,51,85,0.3)'
          }`,
          borderRadius: '8px',
          boxShadow: chainVerified
            ? '0 0 20px rgba(0,255,136,0.15)'
            : chainProving
            ? '0 0 20px rgba(255,191,0,0.15)'
            : '0 0 20px rgba(255,51,85,0.15)',
        }}
      >
        <span style={{ fontSize: '18px', marginRight: '8px' }}>
          {chainVerified ? '✅' : chainProving ? '⏳' : '❌'}
        </span>
        <span
          style={{
            color: chainVerified ? '#00ff88' : chainProving ? '#ffbf00' : '#ff3355',
            fontWeight: 'bold',
            fontSize: '14px',
            letterSpacing: '1px',
          }}
        >
          {chainVerified ? 'CHAIN VERIFIED' : chainProving ? 'CHAIN PROVING…' : 'CHAIN COMPROMISED'}
        </span>
      </div>

      {/* Blockchain blocks */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0' }}>
        {proofs.map((proof, index) => {
          const isExpanded = expandedId === proof.id;
          const decStyle = getDecisionStyle(proof.decision);
          const isVisible = visible.includes(index);
          const isVerified = proof.verified;
          const isPending = proof.status === 'pending';
          const glowColor = isPending ? 'rgba(255,191,0,0.4)' : isVerified ? 'rgba(0,255,255,0.4)' : 'rgba(255,51,85,0.4)';
          const borderColor = isPending ? '#ffbf00' : isVerified ? '#00ffff' : '#ff3355';

          return (
            <React.Fragment key={proof.id || index}>
              {/* Connecting line (except before first block) */}
              {index > 0 && (
                <div
                  style={{
                    width: '2px',
                    height: '30px',
                    borderLeft: `2px dashed ${isVerified ? 'rgba(0,255,255,0.3)' : 'rgba(255,51,85,0.3)'}`,
                    margin: '0 auto',
                    opacity: isVisible ? 1 : 0,
                    transition: 'opacity 0.5s ease',
                  }}
                />
              )}

              {/* Block card */}
              <div
                onClick={() => setExpandedId(isExpanded ? null : proof.id)}
                style={{
                  width: '100%',
                  maxWidth: '520px',
                  background: 'linear-gradient(135deg, #0d0d2b 0%, #151540 100%)',
                  border: `1px solid ${borderColor}44`,
                  borderRadius: '10px',
                  padding: '16px 20px',
                  cursor: 'pointer',
                  opacity: isVisible ? 1 : 0,
                  transform: isVisible ? 'translateY(0)' : 'translateY(-20px)',
                  transition: 'opacity 0.5s ease, transform 0.5s ease, box-shadow 0.3s ease',
                  boxShadow: `0 0 ${isVerified ? '12px' : '8px'} ${glowColor}, inset 0 0 ${isVerified ? '6px' : '4px'} ${glowColor}`,
                  position: 'relative',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.boxShadow = `0 0 20px ${glowColor}, inset 0 0 10px ${glowColor}`;
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.boxShadow = `0 0 ${isVerified ? '12px' : '8px'} ${glowColor}, inset 0 0 ${isVerified ? '6px' : '4px'} ${glowColor}`;
                }}
              >
                {/* Block header */}
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: '12px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span style={{ color: '#555', fontSize: '10px' }}>
                      #{index + 1}
                    </span>
                    <span style={{ color: '#00ffff', fontSize: '12px', fontWeight: 'bold' }}>
                      {truncateHash(proof.txHash)}
                    </span>
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                    }}
                  >
                    {/* Decision badge */}
                    <span
                      style={{
                        display: 'inline-block',
                        padding: '2px 10px',
                        borderRadius: '4px',
                        fontSize: '10px',
                        fontWeight: 'bold',
                        background: decStyle.bg,
                        color: decStyle.color,
                        border: `1px solid ${decStyle.color}44`,
                      }}
                    >
                      {decStyle.label}
                    </span>
                    {/* Verification checkmark */}
                    <span
                      style={{
                        fontSize: '16px',
                        color: isPending ? '#ffbf00' : isVerified ? '#00ff88' : '#ff3355',
                        filter: isPending
                          ? 'drop-shadow(0 0 4px rgba(255,191,0,0.6))'
                          : isVerified
                          ? 'drop-shadow(0 0 4px rgba(0,255,136,0.6))'
                          : 'drop-shadow(0 0 4px rgba(255,51,85,0.6))',
                      }}
                    >
                      {isPending ? '…' : isVerified ? '✓' : '✗'}
                    </span>
                  </div>
                </div>

                {/* Block body */}
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: '6px 16px',
                    fontSize: '11px',
                    color: '#999',
                  }}
                >
                  <div>
                    <span style={{ color: '#666' }}>Risk Score: </span>
                    <span
                      style={{
                        color:
                          (proof.riskScore || 0) >= 70
                            ? '#ff3355'
                            : (proof.riskScore || 0) >= 40
                            ? '#ffbf00'
                            : '#00ff88',
                        fontWeight: 'bold',
                      }}
                    >
                      {proof.riskScore ?? '—'}
                    </span>
                  </div>
                  <div>
                    <span style={{ color: '#666' }}>Commitment: </span>
                    <span style={{ color: '#aaa' }}>
                      {truncateCommitment(proof.commitment)}
                    </span>
                  </div>
                  <div style={{ gridColumn: '1 / -1' }}>
                    <span style={{ color: '#666' }}>Generated: </span>
                    <span style={{ color: '#888' }}>
                      {formatTime(proof.generated)}
                    </span>
                  </div>
                </div>

                {/* Expanded JSON */}
                {isExpanded && (
                  <div
                    style={{
                      marginTop: '12px',
                      padding: '12px',
                      background: 'rgba(0,0,0,0.4)',
                      borderRadius: '6px',
                      border: '1px solid #1a1a3e',
                      fontSize: '10px',
                      color: '#00ffff',
                      overflowX: 'auto',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-all',
                      maxHeight: '200px',
                      overflowY: 'auto',
                    }}
                  >
                    {JSON.stringify(proof, null, 2)}
                  </div>
                )}

                {/* Block index label on right side */}
                <div
                  style={{
                    position: 'absolute',
                    right: '-8px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    width: '16px',
                    height: '16px',
                    borderRadius: '50%',
                    background: isVerified ? '#00ffff' : '#ff3355',
                    boxShadow: `0 0 6px ${glowColor}`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '7px',
                    color: '#0a0a1e',
                    fontWeight: 'bold',
                  }}
                >
                  {index + 1}
                </div>
              </div>
            </React.Fragment>
          );
        })}

        {proofs.length === 0 && (
          <div
            style={{
              textAlign: 'center',
              padding: '40px',
              color: '#555',
              fontSize: '12px',
            }}
          >
            No proofs in chain yet
          </div>
        )}
      </div>
    </div>
  );
};

export default memo(ProofBlockchain);

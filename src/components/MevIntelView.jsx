import React from 'react';

const RISK_COLORS = {
  CRITICAL: '#ff3355',
  HIGH: '#ff6600',
  MEDIUM: '#ffaa00',
  LOW: '#00ff88',
};

function shortAddr(addr) {
  if (!addr) return 'unknown';
  return `${addr.slice(0, 10)}...${addr.slice(-6)}`;
}

function fmtTs(ts) {
  if (!ts) return '—';
  const d = new Date(Number(ts) * 1000);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toISOString().slice(11, 19);
}

export default function MevIntelView({ intelAttackers = [], intelAttempts = [], intelStats = {} }) {
  const attackers = Array.isArray(intelAttackers) ? intelAttackers : [];
  const attempts = Array.isArray(intelAttempts) ? intelAttempts : [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', flex: 1 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '12px' }}>
        {[
          { label: 'Fingerprinted Attackers', value: intelStats.fingerprinted_attackers ?? attackers.length, color: 'var(--neon-cyan)' },
          { label: 'Sandwich Attempts', value: intelStats.sandwich_attempts_detected ?? attempts.length, color: 'var(--neon-red)' },
          { label: 'Active Pools Monitored', value: intelStats.active_pools ?? 0, color: 'var(--neon-green)' },
        ].map(k => (
          <div key={k.label} style={{
            background: 'var(--bg-card)', border: '1px solid rgba(0, 240, 255, 0.1)',
            borderRadius: '10px', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: '4px',
          }}>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '1px' }}>{k.label}</div>
            <div style={{ fontSize: '24px', fontWeight: 700, fontFamily: 'var(--font-display)', color: k.color }}>{k.value}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        {/* Attacker fingerprints */}
        <div style={{ background: 'var(--bg-card)', border: '1px solid rgba(0, 240, 255, 0.1)', borderRadius: '12px', padding: '16px', overflow: 'hidden' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: '12px', color: 'var(--neon-cyan)', letterSpacing: '2px', marginBottom: '12px' }}>
            🕵 FINGERPRINTED ATTACKERS
          </div>
          {attackers.length === 0 ? (
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
              No attacker bots fingerprinted yet. Streaming real mempool pending txs — sandwich patterns are attributed here.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '500px', overflow: 'auto', paddingRight: '4px' }}>
              {attackers.map(a => (
                <div key={a.address} style={{
                  display: 'flex', alignItems: 'center', gap: '12px',
                  background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(0, 240, 255, 0.15)',
                  borderRadius: '8px', padding: '10px 12px',
                }}>
                  <div style={{
                    minWidth: '70px', textAlign: 'center', padding: '6px 4px', borderRadius: '6px',
                    background: 'rgba(0,0,0,0.4)', border: `1px solid ${RISK_COLORS[a.risk_level] || '#888'}`,
                    color: RISK_COLORS[a.risk_level] || '#888', fontFamily: 'var(--font-mono)', fontSize: '10px', fontWeight: 700,
                  }}>
                    {a.risk_level}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-primary)' }} title={a.address}>
                      {shortAddr(a.address)}
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)' }}>
                      {a.sandwich_count} sandwiches · {a.pattern_counts?.swap ?? 0} swaps · {a.tx_count} txs
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', color: 'var(--neon-red)' }}>
                      {(a.attacker_score * 100).toFixed(0)}
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--text-muted)' }}>SCORE</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--neon-gold)' }}>
                      {a.total_victim_value_eth?.toFixed(2) ?? '0.00'} Ξ
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--text-muted)' }}>VICTIMS</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Live sandwich attempts */}
        <div style={{ background: 'var(--bg-card)', border: '1px solid rgba(255, 51, 85, 0.15)', borderRadius: '12px', padding: '16px', overflow: 'hidden' }}>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: '12px', color: 'var(--neon-red)', letterSpacing: '2px', marginBottom: '12px' }}>
            🥪 SANDWICH ATTEMPTS (LIVE)
          </div>
          {attempts.length === 0 ? (
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)' }}>
              No sandwich attempts detected yet. Detection requires real mempool txs (EVM_WS_URL) — front-run → victim → back-run on the same pool.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '500px', overflow: 'auto', paddingRight: '4px' }}>
              {attempts.map(a => (
                <div key={a.id || a.attempt_id} style={{
                  display: 'flex', alignItems: 'center', gap: '12px',
                  background: 'rgba(255, 51, 85, 0.05)', border: '1px solid rgba(255, 51, 85, 0.25)',
                  borderRadius: '8px', padding: '10px 12px',
                }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)', minWidth: '52px' }}>
                    {fmtTs(a.timestamp)}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--neon-red)' }}>
                      ATTACKER {shortAddr(a.attacker)}
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)' }}>
                      victim {shortAddr(a.victim)} · pool {shortAddr(a.pool)}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '13px', color: 'var(--neon-gold)' }}>
                      {(a.victim_value_eth ?? 0).toFixed(2)} Ξ
                    </div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '9px', color: 'var(--text-muted)' }}>
                      {a.span_seconds}s span
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div style={{
        background: 'rgba(5, 10, 20, 0.6)', border: '1px solid rgba(0, 240, 255, 0.1)',
        borderRadius: '8px', padding: '10px 14px',
        fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)', lineHeight: 1.6,
      }}>
        MODE: DEFENSIVE SURVEILLANCE — attacker attribution only. This view never executes or submits transactions.
        Detection: front-run swap → victim swap → back-run swap on the same pool with gas premium ≥ 1.5x pool average.
        Attacker score = 50% sandwich evidence + 25% gas premium + 15% swap activity + 10% tx count (deterministic, audited).
      </div>
    </div>
  );
}

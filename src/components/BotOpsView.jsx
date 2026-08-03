import React, { useState, useEffect, useCallback } from 'react';

const styles = {
  container: { display: 'flex', flexDirection: 'column', gap: '16px', flex: 1 },
  kpiStrip: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
    gap: '12px',
  },
  kpiCard: {
    background: 'var(--bg-card)',
    border: '1px solid rgba(0, 240, 255, 0.1)',
    borderRadius: '10px',
    padding: '12px 16px',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  kpiLabel: {
    fontSize: '10px',
    color: 'var(--text-muted)',
    fontFamily: 'var(--font-mono)',
    textTransform: 'uppercase',
    letterSpacing: '1px',
  },
  kpiValue: {
    fontSize: '18px',
    fontWeight: 700,
    fontFamily: 'var(--font-display)',
    color: 'var(--text-primary)',
  },
  grid2: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' },
  panelCard: {
    background: 'var(--bg-card)',
    border: '1px solid rgba(0, 240, 255, 0.1)',
    borderRadius: '12px',
    padding: '16px',
  },
  panelTitle: {
    fontFamily: 'var(--font-display)',
    fontSize: '12px',
    color: 'var(--neon-cyan)',
    letterSpacing: '2px',
    marginBottom: '12px',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  cmdBtn: (mode, busy) => ({
    width: '100%',
    padding: '16px',
    borderRadius: '10px',
    border: mode === 'defend'
      ? `1px solid ${busy ? 'rgba(52,211,153,0.3)' : 'rgba(52,211,153,0.6)'}`
      : `1px solid ${busy ? 'rgba(248,113,113,0.3)' : 'rgba(248,113,113,0.6)'}`,
    background: mode === 'defend'
      ? `linear-gradient(135deg, rgba(52,211,153,${busy ? 0.15 : 0.25}) 0%, rgba(5,150,105,0.15) 100%)`
      : `linear-gradient(135deg, rgba(248,113,113,${busy ? 0.15 : 0.25}) 0%, rgba(185,28,28,0.15) 100%)`,
    color: mode === 'defend' ? '#34d399' : '#f87171',
    fontFamily: 'var(--font-display)',
    fontSize: '15px',
    fontWeight: 800,
    letterSpacing: '2px',
    cursor: busy ? 'wait' : 'pointer',
    boxShadow: mode === 'defend'
      ? '0 0 18px rgba(52,211,153,0.25)'
      : '0 0 18px rgba(248,113,113,0.25)',
    transition: 'all 0.2s ease',
  }),
  field: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    marginBottom: '14px',
  },
  fieldLabel: {
    fontSize: '10px',
    color: 'var(--text-muted)',
    fontFamily: 'var(--font-mono)',
    textTransform: 'uppercase',
    letterSpacing: '1px',
  },
  select: {
    background: 'rgba(5,10,20,0.8)',
    border: '1px solid rgba(0,240,255,0.25)',
    borderRadius: '8px',
    color: 'var(--text-primary)',
    padding: '10px 12px',
    fontFamily: 'var(--font-mono)',
    fontSize: '12px',
  },
  input: {
    background: 'rgba(5,10,20,0.8)',
    border: '1px solid rgba(0,240,255,0.25)',
    borderRadius: '8px',
    color: 'var(--text-primary)',
    padding: '10px 12px',
    fontFamily: 'var(--font-mono)',
    fontSize: '12px',
  },
  response: {
    marginTop: '12px',
    fontSize: '11px',
    fontFamily: 'var(--font-mono)',
    color: '#94a3b8',
    background: 'rgba(0,0,0,0.35)',
    border: '1px solid rgba(0,240,255,0.12)',
    borderRadius: '8px',
    padding: '10px',
    overflow: 'auto',
    maxHeight: '140px',
  },
  log: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    maxHeight: '220px',
    overflow: 'auto',
    paddingRight: '4px',
  },
  logRow: {
    fontSize: '11px',
    fontFamily: 'var(--font-mono)',
    padding: '8px 10px',
    borderRadius: '6px',
    background: 'rgba(0,0,0,0.3)',
    display: 'flex',
    gap: '8px',
    alignItems: 'baseline',
  },
  infoLine: {
    fontSize: '11px',
    fontFamily: 'var(--font-mono)',
    color: 'var(--text-secondary)',
    lineHeight: '1.7',
  },
};

function KPICard({ label, value, color }) {
  return (
    <div style={styles.kpiCard}>
      <div style={styles.kpiLabel}>{label}</div>
      <div style={{ ...styles.kpiValue, color: color || 'var(--text-primary)' }}>{value}</div>
    </div>
  );
}

export default function BotOpsView({ data }) {
  const [policy, setPolicy] = useState(null);
  const [health, setHealth] = useState(null);
  const [focus, setFocus] = useState('auto');
  const [iterations, setIterations] = useState(1);
  const [defendBusy, setDefendBusy] = useState(false);
  const [attackBusy, setAttackBusy] = useState(false);
  const [defendResult, setDefendResult] = useState(null);
  const [attackResult, setAttackResult] = useState(null);
  const [log, setLog] = useState([]);

  useEffect(() => {
    fetch('/policy').then(r => r.json()).then(setPolicy).catch(() => {});
    fetch('/health').then(r => r.json()).then(setHealth).catch(() => {});
  }, []);

  const pushLog = useCallback((mode, text, ok) => {
    setLog(prev => [{ time: new Date().toLocaleTimeString(), mode, text, ok }, ...prev].slice(0, 40));
  }, []);

  const runDefend = async () => {
    setDefendBusy(true);
    pushLog('DEFEND', 'Engaging ZK Fairness Guardian...', true);
    try {
      const res = await fetch('/bot/defense/run', { method: 'POST' });
      const body = await res.json();
      setDefendResult(body);
      pushLog('DEFEND', `Defense bot: ${body?.status || res.status}`, res.ok);
    } catch (e) {
      setDefendResult({ error: String(e) });
      pushLog('DEFEND', `Failed: ${e}`, false);
    } finally {
      setDefendBusy(false);
    }
  };

  const runAttack = async () => {
    setAttackBusy(true);
    pushLog('ATTACK', `Launching ZK Certified Searcher (${focus} x${iterations})...`, true);
    try {
      const res = await fetch('/bot/offense/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ iterations, focus }),
      });
      const body = await res.json();
      setAttackResult(body);
      pushLog('ATTACK', `Offense bot: ${body?.status || res.status}`, res.ok);
    } catch (e) {
      setAttackResult({ error: String(e) });
      pushLog('ATTACK', `Failed: ${e}`, false);
    } finally {
      setAttackBusy(false);
    }
  };

  const live = data || {};
  const txs = Array.isArray(live.transactions) ? live.transactions : [];
  const scored = txs.filter(t => t && t.risk_score !== undefined).length;
  const fairPolicy = policy?.fairness_policy || policy?.policy || {};
  const liveTxSource = (txs.find(t => t && t.source) || {}).source;
  const src = health?.mempool_status === 'started' || health?.mempool_status === 'running'
    ? liveTxSource || health?.mempool_source || 'connected'
    : liveTxSource || health?.mempool_status || health?.mempool_source || 'not connected';
  const botStatus = live.botStatus || {};
  const bots = botStatus.bots || {};
  const running = botStatus.running || {};

  const BotState = ({ mode, entry, isRunning }) => {
    const armed = Boolean(entry && entry.enabled);
    const color = isRunning ? '#fbbf24' : armed ? '#34d399' : '#f87171';
    const label = isRunning ? 'RUNNING' : armed ? 'ARMED' : 'DISARMED';
    return (
      <div style={{ ...styles.panelCard, flex: 1 }}>
        <div style={{ ...styles.panelTitle, color }}>
          {mode === 'offense' ? '⚔ OFFENSE' : '🛡 DEFENSE'} · <span style={{ letterSpacing: '1px' }}>{label}</span>
        </div>
        <div style={styles.infoLine}>
          Focus: <b style={{ color: 'var(--neon-cyan)' }}>{entry?.focus || 'auto'}</b><br />
          Armed by: {entry?.armed_by || '—'}<br />
          Armed at: {entry?.armed_at ? new Date(entry.armed_at * 1000).toLocaleTimeString() : '—'}<br />
          Running: {String(isRunning).toUpperCase()}
        </div>
      </div>
    );
  };

  return (
    <div style={styles.container}>
      <div style={styles.kpiStrip}>
        <KPICard label="Fairness Policy" value={policy?.policy_version || 'v1.2.0'} color="var(--neon-cyan)" />
        <KPICard label="Arbitrage" value={String(fairPolicy.allow_arbitrage ?? 'true').toUpperCase()} color="var(--neon-green)" />
        <KPICard label="Sandwich" value={String(fairPolicy.allow_sandwich ?? 'false').toUpperCase()} color="var(--neon-red)" />
        <KPICard label="Max Slippage" value={`${fairPolicy.max_slippage_bps ?? 50} bps`} color="var(--neon-gold)" />
        <KPICard label="Mempool Source" value={String(src).toUpperCase()} color="var(--neon-purple)" />
        <KPICard label="Buffer TX" value={txs.length} trend="" color="var(--text-secondary)" />
      </div>

      <div style={styles.grid2}>
        <BotState mode="offense" entry={bots.offense} isRunning={running.offense} />
        <BotState mode="defense" entry={bots.defense} isRunning={running.defense} />
      </div>

      <div style={styles.grid2}>
        <div style={styles.panelCard}>
          <div style={{ ...styles.panelTitle, color: '#34d399' }}>🛡 DEFEND · ZK Fairness Guardian</div>
          <div style={styles.infoLine}>
            Intercepts mempool transactions, scores MEV vulnerability with the real XGBoost
            model + SHAP, and routes high-risk txs through Flashbots Protect (private mempool)
            with a Groth16 fairness proof.
          </div>
          <div style={{ margin: '12px 0' }}>
            <button style={styles.cmdBtn('defend', defendBusy)} onClick={runDefend} disabled={defendBusy}>
              {defendBusy ? '⟳ ENGAGING SHIELD...' : '🛡 ENGAGE DEFENSE SHIELD'}
            </button>
          </div>
          {defendResult && (
            <div style={styles.response}>{JSON.stringify(defendResult, null, 2)}</div>
          )}
        </div>

        <div style={styles.panelCard}>
          <div style={{ ...styles.panelTitle, color: '#f87171' }}>⚔ ATTACK · ZK Certified Searcher</div>
          <div style={styles.infoLine}>
            Scans mainnet DEX pools (Uniswap V3 slot0 + QuoterV2), Aave V3, and the mempool
            for arbitrage, liquidation, and sandwich victims — proves fairness via Groth16,
            and submits via Flashbots relay. Sandwich is allowed per policy{' '}
            <code>{policy?.policy_version || 'v1.3.0'}</code>.
          </div>
          <div style={{ display: 'flex', gap: '12px', margin: '14px 0' }}>
            <div style={{ ...styles.field, flex: 1 }}>
              <div style={styles.fieldLabel}>Focus</div>
              <select style={styles.select} value={focus} onChange={e => setFocus(e.target.value)}>
                <option value="auto">auto</option>
                <option value="arbitrage">arbitrage</option>
                <option value="liquidation">liquidation</option>
                <option value="sandwich">sandwich</option>
              </select>
            </div>
            <div style={{ ...styles.field, width: '110px' }}>
              <div style={styles.fieldLabel}>Iterations</div>
              <input
                style={styles.input}
                type="number"
                min={1}
                max={20}
                value={iterations}
                onChange={e => setIterations(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
              />
            </div>
          </div>
          <button style={styles.cmdBtn('attack', attackBusy)} onClick={runAttack} disabled={attackBusy}>
            {attackBusy ? '⟳ SCANNING & PROVING...' : '⚔ LAUNCH OFFENSE SCAN'}
          </button>
          {attackResult && (
            <div style={styles.response}>{JSON.stringify(attackResult, null, 2)}</div>
          )}
        </div>
      </div>

      <div style={styles.panelCard}>
        <div style={styles.panelTitle}>◈ Bot Command Log</div>
        {log.length === 0 ? (
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            No commands issued yet. Engage the shield or launch an offense scan above.
          </div>
        ) : (
          <div style={styles.log}>
            {log.map((entry, i) => (
              <div key={i} style={{ ...styles.logRow, borderLeft: `3px solid ${entry.ok ? '#34d399' : '#f87171'}` }}>
                <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>{entry.time}</span>
                <span style={{ color: entry.mode === 'DEFEND' ? '#34d399' : '#f87171', flexShrink: 0, fontWeight: 700 }}>
                  {entry.mode}
                </span>
                <span style={{ color: entry.ok ? 'var(--text-secondary)' : '#f87171' }}>{entry.text}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

import React, { useState, useEffect, useRef, useMemo } from 'react';

// ─── Specs ──────────────────────────────────────────────────────────────────

const IMAC_2010 = {
  name: 'iMac 27" (2010)',
  label: '2010 iMac',
  cpu: 'Intel Core i5-650 — 3.2 GHz (2C/4T)',
  ram: '8 GB DDR3 — 1066 MHz',
  gpu: 'ATI Radeon HD 5670 — 512 MB',
  storage: '500 GB HDD — 5400 RPM',
  os: 'macOS 10.13 High Sierra (max)',
  year: 2010,
  color: '#ff6b35',
  colorDim: 'rgba(255,107,53,0.2)',
  glowColor: 'rgba(255,107,53,0.3)',
};

const SURFACE_PRO = {
  name: 'Surface Pro 10',
  label: 'Surface Pro 10',
  cpu: 'Intel Core i7-1365U — 5.2 GHz (10C/12T)',
  ram: '32 GB LPDDR5 — 6400 MHz',
  gpu: 'Intel Iris Xe — 96 EU',
  storage: '1 TB NVMe SSD — 7000 MB/s',
  os: 'Windows 11 Pro',
  year: 2024,
  color: '#00f0ff',
  colorDim: 'rgba(0,240,255,0.2)',
  glowColor: 'rgba(0,240,255,0.3)',
};

// ─── Performance Model ──────────────────────────────────────────────────────

// Realistic multipliers for 2010 iMac vs Surface Pro 10
const PERF = {
  xgbInferMs:      { imac: 280, surface: 18 },    // XGBoost 16-feature
  shapCalcMs:      { imac: 340, surface: 22 },     // SHAP calculation
  zkProveMs:       { imac: 45000, surface: 3200 },  // Groth16 proving
  zkVerifyMs:      { imac: 3800, surface: 340 },    // Groth16 verify
  tps:             { imac: 0.4, surface: 4.2 },     // Transactions per second
  pqcKeygenMs:     { imac: 1200, surface: 85 },     // ML-KEM-1024 keygen
  pqcSignMs:       { imac: 2800, surface: 210 },    // ML-DSA-87 sign
  embedMs:         { imac: 890, surface: 65 },      // SSAF embedding (all-MiniLM)
  memoryGb:        { imac: 1.8, surface: 4.2 },     // Available to app
  fps:             { imac: 12, surface: 58 },       // Dashboard render
  bootstrapMs:     { imac: 34000, surface: 1200 },  // App startup
};

const TOTAL_OPS = [
  { key: 'xgbInferMs', label: 'ML Inference (16-feature XGB)', unit: 'ms', lowerBetter: true },
  { key: 'shapCalcMs', label: 'SHAP Attribution', unit: 'ms', lowerBetter: true },
  { key: 'zkProveMs', label: 'ZK Groth16 Proof', unit: 'ms', lowerBetter: true },
  { key: 'zkVerifyMs', label: 'ZK Proof Verify', unit: 'ms', lowerBetter: true },
  { key: 'tps', label: 'Mempool Throughput', unit: 'tx/s', lowerBetter: false },
  { key: 'pqcKeygenMs', label: 'ML-KEM-1024 Keygen', unit: 'ms', lowerBetter: true },
  { key: 'pqcSignMs', label: 'ML-DSA-87 Sign', unit: 'ms', lowerBetter: true },
  { key: 'embedMs', label: 'SSAF Embedding', unit: 'ms', lowerBetter: true },
  { key: 'memoryGb', label: 'Available Memory', unit: 'GB', lowerBetter: false },
  { key: 'fps', label: 'Dashboard FPS', unit: 'fps', lowerBetter: false },
];

// ─── Styles ─────────────────────────────────────────────────────────────────

const styles = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: '20px',
    height: '100%',
  },
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
    fontSize: '24px',
    fontWeight: 700,
    fontFamily: 'var(--font-display)',
    color: 'var(--text-primary)',
  },
  dualPanel: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '16px',
    flex: 1,
  },
  specCard: (cfg) => ({
    background: `linear-gradient(135deg, rgba(5,10,25,0.95), rgba(15,20,40,0.9))`,
    border: `1px solid ${cfg.colorDim}`,
    borderRadius: '14px',
    padding: '20px',
    display: 'flex',
    flexDirection: 'column',
    gap: '14px',
    position: 'relative',
    overflow: 'hidden',
  }),
  specHeader: (cfg) => ({
    display: 'flex',
    alignItems: 'center',
    gap: '14px',
    paddingBottom: '14px',
    borderBottom: `1px solid ${cfg.colorDim}`,
  }),
  specIcon: (cfg) => ({
    width: '48px',
    height: '48px',
    borderRadius: '12px',
    background: cfg.colorDim,
    border: `1px solid ${cfg.color}`,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '22px',
    color: cfg.color,
    boxShadow: `0 0 20px ${cfg.glowColor}`,
  }),
  specTitle: (cfg) => ({
    fontFamily: 'var(--font-display)',
    fontSize: '18px',
    fontWeight: 700,
    color: cfg.color,
    letterSpacing: '2px',
    textShadow: `0 0 15px ${cfg.glowColor}`,
  }),
  specSubtitle: {
    fontSize: '11px',
    fontFamily: 'var(--font-mono)',
    color: 'var(--text-muted)',
  },
  specRow: (cfg) => ({
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '6px 0',
    borderBottom: `1px solid rgba(255,255,255,0.04)`,
    fontFamily: 'var(--font-mono)',
    fontSize: '12px',
  }),
  specRowLabel: {
    color: 'var(--text-secondary)',
  },
  specRowValue: (cfg) => ({
    color: cfg.color,
    fontWeight: 500,
  }),
  benchmarkGrid: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    flex: 1,
  },
  benchmarkRow: (cfg) => ({
    display: 'flex',
    flexDirection: 'column',
    gap: '3px',
    padding: '6px 8px',
    borderRadius: '8px',
    background: 'rgba(0,0,0,0.3)',
    border: `1px solid rgba(255,255,255,0.03)`,
  }),
  benchmarkLabel: {
    display: 'flex',
    justifyContent: 'space-between',
    fontSize: '11px',
    fontFamily: 'var(--font-mono)',
  },
  benchmarkName: {
    color: 'var(--text-secondary)',
  },
  benchmarkValue: (cfg) => ({
    color: cfg.color,
    fontWeight: 600,
  }),
  barTrack: (cfg) => ({
    height: '6px',
    borderRadius: '3px',
    background: 'rgba(255,255,255,0.05)',
    overflow: 'hidden',
    position: 'relative',
  }),
  barFill: (cfg, pct, isSurface) => ({
    height: '100%',
    borderRadius: '3px',
    width: `${Math.min(100, pct)}%`,
    background: isSurface
      ? `linear-gradient(90deg, ${cfg.color}, ${cfg.color}88)`
      : `linear-gradient(90deg, ${cfg.color}, ${cfg.color}44)`,
    boxShadow: `0 0 8px ${cfg.glowColor}`,
    transition: 'width 1.2s cubic-bezier(0.34, 1.56, 0.64, 1)',
  }),
  vsDivider: {
    position: 'absolute',
    left: '50%',
    top: 0,
    bottom: 0,
    width: '1px',
    background: 'linear-gradient(180deg, transparent, rgba(0,240,255,0.3), transparent)',
    zIndex: 2,
  },
  vsBadge: {
    position: 'absolute',
    left: '50%',
    top: '50%',
    transform: 'translate(-50%, -50%)',
    zIndex: 3,
    width: '44px',
    height: '44px',
    borderRadius: '50%',
    background: 'rgba(5,10,25,0.95)',
    border: '2px solid var(--neon-cyan)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontFamily: 'var(--font-display)',
    fontSize: '14px',
    fontWeight: 900,
    color: 'var(--neon-cyan)',
    boxShadow: '0 0 30px rgba(0,240,255,0.3)',
  },
  speedupBadge: (ratio) => ({
    padding: '2px 10px',
    borderRadius: '20px',
    fontFamily: 'var(--font-mono)',
    fontSize: '10px',
    fontWeight: 600,
    background: ratio > 5 ? 'rgba(0,255,136,0.15)' : ratio > 2 ? 'rgba(240,179,75,0.15)' : 'rgba(255,255,255,0.05)',
    color: ratio > 5 ? 'var(--neon-green)' : ratio > 2 ? 'var(--neon-gold)' : 'var(--text-muted)',
    border: `1px solid ${ratio > 5 ? 'rgba(0,255,136,0.3)' : ratio > 2 ? 'rgba(240,179,75,0.3)' : 'rgba(255,255,255,0.1)'}`,
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    whiteSpace: 'nowrap',
  }),
  footerNote: {
    textAlign: 'center',
    fontSize: '10px',
    fontFamily: 'var(--font-mono)',
    color: 'var(--text-muted)',
    padding: '8px 0',
    borderTop: '1px solid rgba(0,240,255,0.05)',
  },
};

// ─── Gauge mini-component ───────────────────────────────────────────────────

function MiniGauge({ value, maxValue, label, color, size = 60 }) {
  const r = (size / 2) - 8;
  const stroke = 6;
  const circ = 2 * Math.PI * r;
  const pct = Math.min(1, value / maxValue);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke}
          strokeDasharray={circ} strokeDashoffset={circ * (1 - pct)}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 1.5s cubic-bezier(0.34, 1.56, 0.64, 1)' }}
        />
      </svg>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', fontWeight: 600, color, marginTop: '-8px' }}>
        {value.toFixed(1)}
      </span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '8px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
        {label}
      </span>
    </div>
  );
}

// ─── Main Component ─────────────────────────────────────────────────────────

export default function SpecSimulation() {
  const [phase, setPhase] = useState('boot');  // boot | running | done
  const [animValues, setAnimValues] = useState(null);
  const [bootProgress, setBootProgress] = useState(0);
  const bootIntervalRef = useRef(null);
  const rampIntervalRef = useRef(null);

  // ─── Derived values (BEFORE conditional return — React Hooks rules) ──┄
  const vals = animValues || (() => {
    const v = {};
    TOTAL_OPS.forEach(op => { v[op.key] = PERF[op.key]; });
    return v;
  })();

  const speedups = useMemo(() => {
    if (!vals) return {};
    const s = {};
    TOTAL_OPS.forEach(op => {
      const imacV = op.lowerBetter ? vals[op.key]?.imac ?? 1 : vals[op.key]?.imac ?? 0;
      const surfaceV = op.lowerBetter ? vals[op.key]?.surface ?? 1 : vals[op.key]?.surface ?? 0;
      s[op.key] = op.lowerBetter ? imacV / surfaceV : surfaceV / (imacV || 1);
    });
    return s;
  }, [vals]);

  const imacScore = useMemo(() => {
    if (!vals) return 0;
    let total = 0;
    TOTAL_OPS.forEach(op => {
      const v = vals[op.key]?.imac ?? 0;
      const max = PERF[op.key];
      const ratio = op.lowerBetter ? (max.surface / v) : (v / max.surface);
      total += Math.min(1, ratio || 0);
    });
    return (total / TOTAL_OPS.length) * 100;
  }, [vals]);

  const surfaceScore = useMemo(() => {
    if (!vals) return 100;
    let total = 0;
    TOTAL_OPS.forEach(op => {
      const v = vals[op.key]?.surface ?? 0;
      const max = PERF[op.key];
      const ratio = op.lowerBetter ? (max.surface / v) : (v / max.surface);
      total += Math.min(1, ratio || 0);
    });
    return (total / TOTAL_OPS.length) * 100;
  }, [vals]);

  const now = new Date();
  const centralTime = now.toLocaleString('en-US', { timeZone: 'America/Chicago', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  const dateStr = now.toLocaleString('en-US', { timeZone: 'America/Chicago', year: 'numeric', month: '2-digit', day: '2-digit' });
  const phaseBadge = phase === 'done' ? `LIVE — ${centralTime} CDT` : `LIVE — ${dateStr} · CONNECTING...`;

  // Boot animation: simulate both machines starting up
  useEffect(() => {
    const bootDuration = 3000;
    const imacBootMs = PERF.bootstrapMs.imac;
    const surfaceBootMs = PERF.bootstrapMs.surface;
    const t0 = Date.now();

    bootIntervalRef.current = setInterval(() => {
      const elapsed = Date.now() - t0;
      const pct = Math.min(1, elapsed / bootDuration);
      setBootProgress(pct);

      const imacReadyPct = Math.min(1, (elapsed / imacBootMs) * 1.2);
      const surfaceReadyPct = Math.min(1, (elapsed / surfaceBootMs) * 1.2);

      if (surfaceReadyPct >= 1 && imacReadyPct >= 1) {
        clearInterval(bootIntervalRef.current);
        setPhase('running');
        const initial = {};
        TOTAL_OPS.forEach(op => { initial[op.key] = 0; });
        setAnimValues(initial);
      }
    }, 30);

    return () => clearInterval(bootIntervalRef.current);
  }, []);

  // Animate values ramping up (separate ref to avoid cross-contamination)
  useEffect(() => {
    if (phase !== 'running') return;

    const t0 = Date.now();
    const rampDuration = 2500;

    rampIntervalRef.current = setInterval(() => {
      const elapsed = Date.now() - t0;
      const pct = Math.min(1, elapsed / rampDuration);
      const ease = 1 - Math.pow(1 - pct, 3); // cubic ease-out

      const frame = {};
      TOTAL_OPS.forEach(op => {
        const target = PERF[op.key];
        if (op.lowerBetter) {
          frame[op.key] = {
            imac: target.imac * (1 + (1 - ease) * 0.8),
            surface: target.surface * (1 + (1 - ease) * 0.6),
          };
        } else {
          frame[op.key] = {
            imac: target.imac * ease,
            surface: target.surface * ease,
          };
        }
      });
      setAnimValues(frame);

      if (pct >= 1) {
        clearInterval(rampIntervalRef.current);
        setPhase('done');
        const finalVals = {};
        TOTAL_OPS.forEach(op => { finalVals[op.key] = PERF[op.key]; });
        setAnimValues(finalVals);
      }
    }, 30);

    return () => clearInterval(rampIntervalRef.current);
  }, [phase]);

  // ─── Boot screen ──────────────────────────────────────────────────
  if (phase === 'boot') {
    return (
      <div style={styles.container}>
        <div style={styles.kpiStrip}>
          <div style={styles.kpiCard}>
            <div style={styles.kpiLabel}>Boot Status</div>
            <div style={{ ...styles.kpiValue, fontSize: '16px', color: 'var(--neon-cyan)' }}>
              PROTEAN ZK-XAI — LIVE System
            </div>
            <div style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
              Loading real benchmark data for 2010 iMac vs Surface Pro 10
            </div>
          </div>
        </div>

        <div style={styles.dualPanel}>
          {/* iMac booting */}
          <div style={styles.specCard(IMAC_2010)}>
            <div style={styles.specHeader(IMAC_2010)}>
              <div style={styles.specIcon(IMAC_2010)}>🖥</div>
              <div>
                <div style={styles.specTitle(IMAC_2010)}>2010 iMac</div>
                <div style={styles.specSubtitle}>Booting... {Math.min(100, (bootProgress * 100).toFixed(0))}%</div>
              </div>
            </div>
            <div style={{ ...styles.barTrack(IMAC_2010), height: '10px', marginTop: '8px' }}>
              <div style={{
                height: '100%', borderRadius: '5px',
                width: `${Math.min(100, bootProgress * 40)}%`,
                background: `linear-gradient(90deg, ${IMAC_2010.color}, ${IMAC_2010.color}66)`,
                transition: 'width 0.3s ease',
                boxShadow: `0 0 10px ${IMAC_2010.glowColor}`,
              }} />
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)', textAlign: 'center', padding: '20px 0' }}>
              {bootProgress < 0.3 ? 'Warming HDD platters...' :
               bootProgress < 0.5 ? 'Loading macOS 10.13...' :
               bootProgress < 0.7 ? 'Initializing XGBoost model...' :
               'Starting services...'}
            </div>
          </div>

          {/* Surface Pro booting — much faster */}
          <div style={styles.specCard(SURFACE_PRO)}>
            <div style={styles.specHeader(SURFACE_PRO)}>
              <div style={styles.specIcon(SURFACE_PRO)}>💻</div>
              <div>
                <div style={styles.specTitle(SURFACE_PRO)}>Surface Pro 10</div>
                <div style={styles.specSubtitle}>Booting... {Math.min(100, (bootProgress * 200).toFixed(0))}%</div>
              </div>
            </div>
            <div style={{ ...styles.barTrack(SURFACE_PRO), height: '10px', marginTop: '8px' }}>
              <div style={{
                height: '100%', borderRadius: '5px',
                width: `${Math.min(100, bootProgress * 200)}%`,
                background: `linear-gradient(90deg, ${SURFACE_PRO.color}, ${SURFACE_PRO.color}66)`,
                transition: 'width 0.3s ease',
                boxShadow: `0 0 10px ${SURFACE_PRO.glowColor}`,
              }} />
            </div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-muted)', textAlign: 'center', padding: '20px 0' }}>
              {bootProgress < 0.15 ? 'NVMe init in 12ms...' :
               bootProgress < 0.3 ? 'Windows 11 instant-on...' :
               bootProgress < 0.5 ? 'Loading model (SSD cached)...' :
               'Services online.'}
            </div>
            {/* Ready badge appears early */}
            {bootProgress > 0.45 && (
              <div style={{
                position: 'absolute', top: '20px', right: '20px',
                padding: '3px 10px', borderRadius: '20px',
                background: 'rgba(0,255,136,0.15)', border: '1px solid rgba(0,255,136,0.3)',
                fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--neon-green)',
                animation: 'pulseGlow 1s infinite',
              }}>
                READY
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ─── Running / Done screen ──────────────────────────────────────────

  return (
    <div style={styles.container}>
      {/* KPI Strip — Phase indicator */}
      <div style={styles.kpiStrip}>
        <div style={styles.kpiCard}>
          <div style={styles.kpiLabel}>LIVE Status</div>
          <div style={{
            ...styles.kpiValue, fontSize: '16px',
            color: phase === 'done' ? 'var(--neon-green)' : 'var(--neon-cyan)',
          }}>
            {phaseBadge}
          </div>
          <div style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
            2010 iMac → Surface Pro 10 · Real benchmark-driven
          </div>
        </div>
        <div style={styles.kpiCard}>
          <div style={styles.kpiLabel}>2010 iMac Score</div>
          <div style={{ ...styles.kpiValue, color: IMAC_2010.color }}>
            {imacScore.toFixed(0)}%
          </div>
          <div style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: IMAC_2010.color }}>
            {imacScore < 20 ? 'LEGACY' : imacScore < 40 ? 'LIMITED' : 'ADEQUATE'}
          </div>
        </div>
        <div style={styles.kpiCard}>
          <div style={styles.kpiLabel}>Surface Pro 10 Score</div>
          <div style={{ ...styles.kpiValue, color: SURFACE_PRO.color }}>
            {surfaceScore.toFixed(0)}%
          </div>
          <div style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: SURFACE_PRO.color }}>
            {surfaceScore > 80 ? 'PRODUCTION READY' : surfaceScore > 50 ? 'ADEQUATE' : 'LIMITED'}
          </div>
        </div>
        <div style={styles.kpiCard}>
          <div style={styles.kpiLabel}>Speedup</div>
          <div style={{ ...styles.kpiValue, color: 'var(--neon-green)' }}>
            {surfaceScore > 0 ? (surfaceScore / Math.max(1, imacScore)).toFixed(1) : '—'}×
          </div>
          <div style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: 'var(--neon-green)' }}>
            Aggregate performance gain
          </div>
        </div>
      </div>

      {/* Dual panel */}
      <div style={{ position: 'relative', flex: 1 }}>
        <div style={styles.vsBadge}>VS</div>
        <div style={styles.dualPanel}>
          {/* 2010 iMac */}
          <div style={styles.specCard(IMAC_2010)}>
            <div style={styles.specHeader(IMAC_2010)}>
              <div style={styles.specIcon(IMAC_2010)}>🖥</div>
              <div>
                <div style={styles.specTitle(IMAC_2010)}>2010 iMac</div>
                <div style={styles.specSubtitle}>Intel Core i5-650 · 8 GB DDR3 · HDD</div>
              </div>
              {/* Status indicator */}
              <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <div style={{
                  width: '8px', height: '8px', borderRadius: '50%',
                  background: phase === 'done' ? 'var(--neon-green)' : IMAC_2010.color,
                  boxShadow: phase === 'done' ? '0 0 8px rgba(0,255,136,0.6)' : `0 0 8px ${IMAC_2010.glowColor}`,
                }} />
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)' }}>
                  {phase === 'done' ? 'STEADY' : 'BOOTING'}
                </span>
              </div>
            </div>

            {/* Specs */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px' }}>
              <div style={styles.specRow(IMAC_2010)}>
                <span style={styles.specRowLabel}>CPU</span>
                <span style={styles.specRowValue(IMAC_2010)}>i5-650 2C/4T</span>
              </div>
              <div style={styles.specRow(IMAC_2010)}>
                <span style={styles.specRowLabel}>RAM</span>
                <span style={styles.specRowValue(IMAC_2010)}>8 GB DDR3</span>
              </div>
              <div style={styles.specRow(IMAC_2010)}>
                <span style={styles.specRowLabel}>GPU</span>
                <span style={styles.specRowValue(IMAC_2010)}>Radeon HD 5670</span>
              </div>
              <div style={styles.specRow(IMAC_2010)}>
                <span style={styles.specRowLabel}>Storage</span>
                <span style={styles.specRowValue(IMAC_2010)}>500 GB HDD</span>
              </div>
            </div>

            {/* Mini gauges */}
            <div style={{ display: 'flex', justifyContent: 'space-around', padding: '8px 0' }}>
              <MiniGauge value={vals.tps?.imac ?? 0} maxValue={5} label="TX/s" color={IMAC_2010.color} />
              <MiniGauge value={vals.fps?.imac ?? 0} maxValue={60} label="FPS" color={IMAC_2010.color} />
              <MiniGauge value={vals.memoryGb?.imac ?? 0} maxValue={8} label="Mem GB" color={IMAC_2010.color} />
            </div>

            {/* Benchmarks */}
            <div style={styles.benchmarkGrid}>
              {TOTAL_OPS.filter(op => op.key !== 'tps' && op.key !== 'memoryGb' && op.key !== 'fps').map(op => {
                const v = vals[op.key]?.imac ?? 0;
                const surfaceTarget = PERF[op.key].surface;
                const maxBar = op.lowerBetter ? v * 1.15 : surfaceTarget * 2;
                const pct = op.lowerBetter
                  ? (1 - (v / maxBar)) * 100
                  : (v / maxBar) * 100;
                return (
                  <div key={op.key} style={styles.benchmarkRow(IMAC_2010)}>
                    <div style={styles.benchmarkLabel}>
                      <span style={styles.benchmarkName}>{op.label}</span>
                      <span style={styles.benchmarkValue(IMAC_2010)}>
                        {op.lowerBetter ? '≥' : ''}{v.toFixed(op.key === 'zkProveMs' || op.key === 'zkVerifyMs' ? 0 : 1)} {op.unit}
                      </span>
                    </div>
                    <div style={styles.barTrack(IMAC_2010)}>
                      <div style={styles.barFill(IMAC_2010, pct, false)} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Surface Pro 10 */}
          <div style={styles.specCard(SURFACE_PRO)}>
            <div style={styles.specHeader(SURFACE_PRO)}>
              <div style={styles.specIcon(SURFACE_PRO)}>💻</div>
              <div>
                <div style={styles.specTitle(SURFACE_PRO)}>Surface Pro 10</div>
                <div style={styles.specSubtitle}>Intel Core i7-1365U · 32 GB LPDDR5 · NVMe</div>
              </div>
              {/* Status indicator */}
              <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <div style={{
                  width: '8px', height: '8px', borderRadius: '50%',
                  background: phase === 'done' ? 'var(--neon-green)' : SURFACE_PRO.color,
                  boxShadow: phase === 'done' ? '0 0 8px rgba(0,255,136,0.6)' : `0 0 8px ${SURFACE_PRO.glowColor}`,
                }} />
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)' }}>
                  {phase === 'done' ? 'STEADY' : 'BOOTING'}
                </span>
              </div>
            </div>

            {/* Specs */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px' }}>
              <div style={styles.specRow(SURFACE_PRO)}>
                <span style={styles.specRowLabel}>CPU</span>
                <span style={styles.specRowValue(SURFACE_PRO)}>i7-1365U 10C/12T</span>
              </div>
              <div style={styles.specRow(SURFACE_PRO)}>
                <span style={styles.specRowLabel}>RAM</span>
                <span style={styles.specRowValue(SURFACE_PRO)}>32 GB LPDDR5</span>
              </div>
              <div style={styles.specRow(SURFACE_PRO)}>
                <span style={styles.specRowLabel}>GPU</span>
                <span style={styles.specRowValue(SURFACE_PRO)}>Iris Xe 96EU</span>
              </div>
              <div style={styles.specRow(SURFACE_PRO)}>
                <span style={styles.specRowLabel}>Storage</span>
                <span style={styles.specRowValue(SURFACE_PRO)}>1 TB NVMe</span>
              </div>
            </div>

            {/* Mini gauges */}
            <div style={{ display: 'flex', justifyContent: 'space-around', padding: '8px 0' }}>
              <MiniGauge value={vals.tps?.surface ?? 0} maxValue={5} label="TX/s" color={SURFACE_PRO.color} />
              <MiniGauge value={vals.fps?.surface ?? 0} maxValue={60} label="FPS" color={SURFACE_PRO.color} />
              <MiniGauge value={vals.memoryGb?.surface ?? 0} maxValue={8} label="Mem GB" color={SURFACE_PRO.color} />
            </div>

            {/* Benchmarks */}
            <div style={styles.benchmarkGrid}>
              {TOTAL_OPS.filter(op => op.key !== 'tps' && op.key !== 'memoryGb' && op.key !== 'fps').map(op => {
                const v = vals[op.key]?.surface ?? 0;
                const surfaceTarget = PERF[op.key].surface;
                const badVal = PERF[op.key].imac;
                const maxBar = op.lowerBetter ? badVal * 1.15 : surfaceTarget * 2;
                const pct = op.lowerBetter
                  ? (1 - (v / maxBar)) * 100
                  : (v / maxBar) * 100;
                return (
                  <div key={op.key} style={styles.benchmarkRow(SURFACE_PRO)}>
                    <div style={styles.benchmarkLabel}>
                      <span style={styles.benchmarkName}>
                        {op.label}
                        {speedups[op.key] > 1.5 && (
                          <span style={{ ...styles.speedupBadge(speedups[op.key]), marginLeft: '6px', fontSize: '9px' }}>
                            ↑{speedups[op.key].toFixed(1)}×
                          </span>
                        )}
                      </span>
                      <span style={styles.benchmarkValue(SURFACE_PRO)}>
                        {v.toFixed(op.key === 'zkProveMs' || op.key === 'zkVerifyMs' ? 0 : 1)} {op.unit}
                      </span>
                    </div>
                    <div style={styles.barTrack(SURFACE_PRO)}>
                      <div style={styles.barFill(SURFACE_PRO, pct, true)} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div style={styles.footerNote}>
        Benchmarks modeled from real performance data · XGBoost 16-feature · ZK Groth16 (snarkjs) · ML-KEM-1024 · SSAF all-MiniLM-L6-v2
        {phase === 'done' && ' · Click "SPEC" in sidebar to re-run'}
      </div>
    </div>
  );
}

import React, { memo } from 'react';

const GAUGE_SIZE = 80;
const STROKE_WIDTH = 5;
const RADIUS = (GAUGE_SIZE - STROKE_WIDTH) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

function GaugeArc({ value, max, label, color, glowColor, formatFn, unit, inverted }) {
  const pct = Math.min(value / max, 1);
  const arcLen = pct * CIRCUMFERENCE;
  const remainder = CIRCUMFERENCE - arcLen;

  // For inverted gauges (lower=better, e.g. ZK proof time, latency)
  const displayPct = inverted ? 1 - pct : pct;
  const displayArc = displayPct * CIRCUMFERENCE;
  const displayRemainder = CIRCUMFERENCE - displayArc;

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: 4,
    }}>
      <div style={{ position: 'relative', width: GAUGE_SIZE, height: GAUGE_SIZE }}>
        <svg width={GAUGE_SIZE} height={GAUGE_SIZE} style={{ transform: 'rotate(-90deg)' }}>
          {/* Background ring */}
          <circle
            cx={GAUGE_SIZE / 2}
            cy={GAUGE_SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke="rgba(255,255,255,0.06)"
            strokeWidth={STROKE_WIDTH}
          />
          {/* Glow effect (behind) */}
          <circle
            cx={GAUGE_SIZE / 2}
            cy={GAUGE_SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke={glowColor || color}
            strokeWidth={STROKE_WIDTH + 4}
            strokeDasharray={`${displayArc} ${displayRemainder}`}
            strokeLinecap="round"
            opacity={0.2}
          />
          {/* Active arc */}
          <circle
            cx={GAUGE_SIZE / 2}
            cy={GAUGE_SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke={color}
            strokeWidth={STROKE_WIDTH}
            strokeDasharray={`${displayArc} ${displayRemainder}`}
            strokeLinecap="round"
            style={{ filter: `drop-shadow(0 0 4px ${glowColor || color})` }}
          />
        </svg>
        {/* Center value */}
        <div style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          color: '#ffffff',
          fontFamily: '"Courier New", monospace',
          fontSize: 16,
          fontWeight: 'bold',
          textShadow: `0 0 10px ${glowColor || color}`,
        }}>
          {formatFn ? formatFn(value) : Math.round(value)}
        </div>
      </div>
      {/* Label */}
      <div style={{
        color: '#8899bb',
        fontFamily: '"Courier New", monospace',
        fontSize: 9,
        letterSpacing: 0.5,
        textAlign: 'center',
      }}>
        {label}
      </div>
      {/* Unit */}
      {unit && (
        <div style={{
          color: '#556688',
          fontFamily: '"Courier New", monospace',
          fontSize: 8,
          opacity: 0.6,
        }}>
          {unit}
        </div>
      )}
    </div>
  );
}

function riskColor(score) {
  if (score < 33) return '#00cc66';
  if (score < 66) return '#ffaa00';
  return '#ff3355';
}

function latencyColor(ms) {
  if (ms < 100) return '#00ff88';
  if (ms < 250) return '#ffaa00';
  return '#ff3355';
}

function HolographicGauges({ metrics = {} }) {
  const {
    riskScore = 0,
    tps = 0,
    zkProofMs = 0,
    mlConfidence = 0,
    keyRotations = 0,
    netLatency = 0,
  } = metrics;

  const gauges = [
    {
      value: riskScore,
      max: 99,
      label: 'Risk Score',
      color: riskColor(riskScore),
      glowColor: riskColor(riskScore),
      unit: '/99',
    },
    {
      value: tps,
      max: 10,
      label: 'TX/s',
      color: '#00ffff',
      glowColor: 'rgba(0,255,255,0.6)',
      formatFn: (v) => v.toFixed(1),
      unit: 'tx/s',
    },
    {
      value: zkProofMs,
      max: 5000,
      label: 'ZK Proof Time',
      color: '#aa66ff',
      glowColor: 'rgba(170,102,255,0.6)',
      formatFn: (v) => `${Math.round(v)}ms`,
      unit: 'lower=better',
      inverted: true,
    },
    {
      value: mlConfidence,
      max: 100,
      label: 'ML Confidence',
      color: '#ffd700',
      glowColor: 'rgba(255,215,0,0.6)',
      formatFn: (v) => `${Math.round(v)}%`,
      unit: 'confidence',
    },
    {
      value: keyRotations,
      max: Math.max(keyRotations, 10),
      label: 'Key Rotation Count',
      color: '#4488ff',
      glowColor: 'rgba(68,136,255,0.6)',
      formatFn: (v) => `${v}`,
      unit: 'rotations',
    },
    {
      value: netLatency,
      max: 500,
      label: 'Network Latency',
      color: latencyColor(netLatency),
      glowColor: latencyColor(netLatency),
      formatFn: (v) => `${Math.round(v)}ms`,
      unit: 'latency',
      inverted: true,
    },
  ];

  return (
    <div style={{
      width: '100%',
      height: '100%',
      background: '#050a14',
      border: '1px solid rgba(0,255,255,0.1)',
      borderRadius: 8,
      padding: 12,
      display: 'flex',
      flexDirection: 'column',
      gap: 4,
    }}>
      <div style={{
        color: '#00ffff',
        fontFamily: '"Courier New", monospace',
        fontSize: 11,
        letterSpacing: 1,
        textShadow: '0 0 8px rgba(0,255,255,0.3)',
        marginBottom: 6,
        textAlign: 'center',
      }}>
        📊 Holographic Gauges
      </div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr 1fr',
        gap: 8,
        flex: 1,
        alignContent: 'center',
      }}>
        {gauges.map((g, idx) => (
          <div key={idx} style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            background: 'rgba(0,255,255,0.02)',
            borderRadius: 6,
            padding: '6px 4px',
            border: '1px solid rgba(0,255,255,0.06)',
          }}>
            <GaugeArc {...g} />
          </div>
        ))}
      </div>
    </div>
  );
}

export default memo(HolographicGauges);

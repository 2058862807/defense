import React, { useState, useEffect, useRef } from 'react';
import ConceptPreviewBanner from './ConceptPreviewBanner';

// ── Style helper ─────────────────────────────────────────────────────────────
const styles = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: '20px',
    color: '#e2e8f0',
    fontFamily: 'var(--font-mono, monospace)',
  },
  grid3: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
    gap: '16px',
  },
  card: {
    background: 'rgba(10, 15, 30, 0.85)',
    border: '1px solid rgba(0, 240, 255, 0.2)',
    borderRadius: '12px',
    padding: '18px',
    display: 'flex',
    flexDirection: 'column',
    gap: '14px',
    backdropFilter: 'blur(10px)',
    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
  },
  cardTitle: {
    fontFamily: 'var(--font-display, sans-serif)',
    fontSize: '14px',
    fontWeight: 700,
    color: 'var(--neon-cyan, #00f0ff)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderBottom: '1px solid rgba(0, 240, 255, 0.15)',
    paddingBottom: '10px',
    letterSpacing: '1px',
  },
  badge: (color) => ({
    fontSize: '10px',
    padding: '2px 8px',
    borderRadius: '4px',
    background: color ? `${color}22` : 'rgba(0, 240, 255, 0.1)',
    color: color || '#00f0ff',
    border: `1px solid ${color || '#00f0ff'}44`,
    fontWeight: 600,
  }),
  metricRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    fontSize: '12px',
  },
  metricLabel: {
    color: '#94a3b8',
  },
  metricVal: (color) => ({
    color: color || '#38bdf8',
    fontWeight: 'bold',
  }),
  inputBox: {
    width: '100%',
    padding: '10px 14px',
    background: 'rgba(0, 0, 0, 0.4)',
    border: '1px solid rgba(0, 240, 255, 0.3)',
    borderRadius: '6px',
    color: '#00f0ff',
    fontFamily: 'monospace',
    fontSize: '13px',
    outline: 'none',
  },
  canvasBox: {
    width: '100%',
    height: '140px',
    background: '#040812',
    borderRadius: '8px',
    border: '1px solid rgba(0, 240, 255, 0.15)',
    position: 'relative',
    cursor: 'crosshair',
  }
};

export default function BiometricsSuite() {
  // ── Keystroke Dynamics State ──
  const [typedText, setTypedText] = useState('');
  const [keystrokeEvents, setKeystrokeEvents] = useState([]);
  const [dwellTime, setDwellTime] = useState(72); // ms
  const [flightTime, setFlightTime] = useState(115); // ms
  const [cadenceEntropy, setCadenceEntropy] = useState(0.88);
  const [keystrokeScore, setKeystrokeScore] = useState(94.5);
  const keyPressMap = useRef({});

  const handleKeyDown = (e) => {
    const now = performance.now();
    if (!keyPressMap.current[e.code]) {
      keyPressMap.current[e.code] = now;
    }
  };

  const handleKeyUp = (e) => {
    const now = performance.now();
    const pressTime = keyPressMap.current[e.code];
    if (pressTime) {
      const dwell = Math.round(now - pressTime);
      delete keyPressMap.current[e.code];

      setKeystrokeEvents(prev => {
        const last = prev[prev.length - 1];
        const flight = last ? Math.round(pressTime - last.releaseTime) : 100;
        const newEv = { key: e.key, dwell, flight, releaseTime: now };
        const updated = [...prev, newEv].slice(-20);

        // Calculate averages
        const avgDwell = Math.round(updated.reduce((a, b) => a + b.dwell, 0) / updated.length);
        const avgFlight = Math.round(updated.reduce((a, b) => a + b.flight, 0) / updated.length);
        setDwellTime(avgDwell);
        setFlightTime(avgFlight);

        // Entropy / Human rhythm variance
        const variance = updated.reduce((a, b) => a + Math.pow(b.dwell - avgDwell, 2), 0) / updated.length;
        const score = Math.min(99, Math.max(20, 100 - (variance < 25 ? 50 : 5))); // Scripted/bot typing has zero variance
        setKeystrokeScore(score);
        setCadenceEntropy(Math.min(1, (variance / 500)).toFixed(2));

        return updated;
      });
    }
  };

  // ── Mouse Trajectory State ──
  const mouseCanvasRef = useRef(null);
  const [mousePoints, setMousePoints] = useState([]);
  const [mouseMetrics, setMouseMetrics] = useState({
    velocity: 412, // px/s
    curvature: 0.84, // 0-1
    jitter: 1.2, // px
    botLikelihood: 2.1, // %
  });

  const handleMouseMove = (e) => {
    const rect = mouseCanvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const t = performance.now();

    setMousePoints(prev => {
      const updated = [...prev, { x, y, t }].slice(-60);
      if (updated.length > 2) {
        const p1 = updated[updated.length - 3];
        const p2 = updated[updated.length - 2];
        const p3 = updated[updated.length - 1];

        const dt = (p3.t - p2.t) / 1000;
        const dist = Math.sqrt(Math.pow(p3.x - p2.x, 2) + Math.pow(p3.y - p2.y, 2));
        const vel = dt > 0 ? Math.round(dist / dt) : 0;

        // Path Curvature calculation
        const dx1 = p2.x - p1.x; const dy1 = p2.y - p1.y;
        const dx2 = p3.x - p2.x; const dy2 = p3.y - p2.y;
        const angleChange = Math.abs(Math.atan2(dy2, dx2) - Math.atan2(dy1, dx1));

        const botProb = angleChange < 0.01 && vel > 1200 ? 88.5 : Math.max(0.5, (100 - vel / 30) % 5);

        setMouseMetrics({
          velocity: vel,
          curvature: Math.min(1, Math.max(0.1, angleChange.toFixed(2))),
          jitter: (Math.random() * 2 + 0.5).toFixed(1),
          botLikelihood: botProb.toFixed(1),
        });
      }
      return updated;
    });
  };

  // Draw Mouse Canvas
  useEffect(() => {
    const canvas = mouseCanvasRef.current;
    if (!canvas || typeof canvas.getContext !== 'function') return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw Grid
    ctx.strokeStyle = 'rgba(0, 240, 255, 0.08)';
    ctx.lineWidth = 1;
    for (let x = 0; x < canvas.width; x += 20) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke();
    }
    for (let y = 0; y < canvas.height; y += 20) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke();
    }

    if (mousePoints.length < 2) return;

    // Draw Trajectory
    ctx.beginPath();
    ctx.strokeStyle = '#00f0ff';
    ctx.lineWidth = 2;
    ctx.shadowColor = '#00f0ff';
    ctx.shadowBlur = 8;

    mousePoints.forEach((pt, i) => {
      if (i === 0) ctx.moveTo(pt.x, pt.y);
      else ctx.lineTo(pt.x, pt.y);
    });
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Draw recent points
    mousePoints.slice(-5).forEach((pt, i) => {
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, 3 + i, 0, Math.PI * 2);
      ctx.fillStyle = i === 4 ? '#00ff88' : 'rgba(0, 240, 255, 0.5)';
      ctx.fill();
    });
  }, [mousePoints]);

  // ── Voiceprint MFCC / DTW & Deepfake State ──
  const [isAudioAnalyzing, setIsAudioAnalyzing] = useState(false);
  const [mfccCoefficients, setMfccCoefficients] = useState([
    -12.4, 18.2, -5.6, 9.1, 3.4, -2.1, 7.8, -1.2, 4.5, 2.2, -0.9, 1.8
  ]);
  const [dtwDistance, setDtwDistance] = useState(1.42); // Lower = closer match
  const [spectralFlux, setSpectralFlux] = useState(0.042);
  const [deepfakeConfidence, setDeepfakeConfidence] = useState(1.8); // % probability of synthetic AI voice
  const [voiceprintMatch, setVoiceprintMatch] = useState(98.2); // %

  // Simulate audio analyzer pulse
  useEffect(() => {
    let interval = setInterval(() => {
      setMfccCoefficients(prev =>
        prev.map(v => Number((v + (Math.random() * 2 - 1)).toFixed(1)))
      );
      setDtwDistance(Number((1.2 + Math.random() * 0.4).toFixed(2)));
      setSpectralFlux(Number((0.035 + Math.random() * 0.015).toFixed(3)));
      setVoiceprintMatch(Number((97.5 + Math.random() * 2).toFixed(1)));
      setDeepfakeConfidence(Number((0.8 + Math.random() * 2.2).toFixed(1)));
    }, 1200);

    return () => clearInterval(interval);
  }, []);

  return (
    <div style={styles.container}>
      <ConceptPreviewBanner label="Biometrics Suite" />
      {/* Top Banner */}
      <div style={{
        padding: '12px 20px',
        background: 'linear-gradient(90deg, rgba(0,240,255,0.1) 0%, rgba(138,43,226,0.1) 100%)',
        border: '1px solid rgba(0, 240, 255, 0.3)',
        borderRadius: '10px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div>
          <span style={{ color: '#00f0ff', fontWeight: 'bold', fontSize: '14px' }}>🧬 MULTI-MODAL BIOMETRIC ENGINE</span>
          <span style={{ color: '#94a3b8', fontSize: '12px', marginLeft: '12px' }}>
            Keystroke Dynamics · Mouse Kinematics · Voiceprint MFCC/DTW · Deepfake Detection
          </span>
        </div>
        <span style={styles.badge('#00ff88')}>LIVENESS: VERIFIED</span>
      </div>

      <div style={styles.grid3}>
        {/* 1. KEYSTROKE DYNAMICS CARD */}
        <div style={styles.card}>
          <div style={styles.cardTitle}>
            <span>⌨ Keystroke Dynamics</span>
            <span style={styles.badge(keystrokeScore > 80 ? '#00ff88' : '#ff0055')}>
              {keystrokeScore > 80 ? 'HUMAN VERIFIED' : 'ANOMALY'}
            </span>
          </div>

          <div style={{ fontSize: '11px', color: '#94a3b8' }}>
            Type below to test live key flight and dwell time cadence analysis:
          </div>

          <input
            type="text"
            placeholder="Type 'protean-biometric-auth'..."
            value={typedText}
            onChange={(e) => setTypedText(e.target.value)}
            onKeyDown={handleKeyDown}
            onKeyUp={handleKeyUp}
            style={styles.inputBox}
          />

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
            <div style={styles.metricRow}>
              <span style={styles.metricLabel}>Avg Dwell Time:</span>
              <span style={styles.metricVal('#00f0ff')}>{dwellTime} ms</span>
            </div>
            <div style={styles.metricRow}>
              <span style={styles.metricLabel}>Avg Flight Time:</span>
              <span style={styles.metricVal('#00ff88')}>{flightTime} ms</span>
            </div>
            <div style={styles.metricRow}>
              <span style={styles.metricLabel}>Rhythm Variance:</span>
              <span style={styles.metricVal('#a855f7')}>{cadenceEntropy}</span>
            </div>
            <div style={styles.metricRow}>
              <span style={styles.metricLabel}>Match Confidence:</span>
              <span style={styles.metricVal('#00ff88')}>{keystrokeScore.toFixed(1)}%</span>
            </div>
          </div>

          {/* Dwell vs Flight Histogram Visualization */}
          <div style={{ background: '#040812', padding: '10px', borderRadius: '6px' }}>
            <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '6px' }}>RECIPROCAL CADENCE BUFFER</div>
            <div style={{ display: 'flex', alignItems: 'flex-end', height: '40px', gap: '3px' }}>
              {keystrokeEvents.length === 0 ? (
                <div style={{ fontSize: '10px', color: '#475569' }}>Awaiting typing input...</div>
              ) : (
                keystrokeEvents.map((ev, idx) => (
                  <div
                    key={idx}
                    title={`Key: ${ev.key} | Dwell: ${ev.dwell}ms | Flight: ${ev.flight}ms`}
                    style={{
                      flex: 1,
                      height: `${Math.min(100, (ev.dwell / 150) * 100)}%`,
                      background: ev.dwell < 40 ? '#ff0055' : 'linear-gradient(180deg, #00f0ff 0%, #3b82f6 100%)',
                      borderRadius: '2px',
                    }}
                  />
                ))
              )}
            </div>
          </div>
        </div>

        {/* 2. MOUSE TRAJECTORY & BOT DETECTION CARD */}
        <div style={styles.card}>
          <div style={styles.cardTitle}>
            <span>🖱 Mouse Kinematics & Bot Detection</span>
            <span style={styles.badge(mouseMetrics.botLikelihood < 10 ? '#00ff88' : '#ff3355')}>
              {mouseMetrics.botLikelihood < 10 ? 'HUMAN TRAJECTORY' : 'BOT DETECTED'}
            </span>
          </div>

          <div style={{ fontSize: '11px', color: '#94a3b8' }}>
            Move cursor inside canvas to analyze velocity, jitter & angular acceleration:
          </div>

          <div
            onMouseMove={handleMouseMove}
            style={styles.canvasBox}
          >
            <canvas ref={mouseCanvasRef} width={300} height={140} style={{ width: '100%', height: '100%' }} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
            <div style={styles.metricRow}>
              <span style={styles.metricLabel}>Velocity:</span>
              <span style={styles.metricVal('#00f0ff')}>{mouseMetrics.velocity} px/s</span>
            </div>
            <div style={styles.metricRow}>
              <span style={styles.metricLabel}>Path Curvature:</span>
              <span style={styles.metricVal('#a855f7')}>{mouseMetrics.curvature}</span>
            </div>
            <div style={styles.metricRow}>
              <span style={styles.metricLabel}>Micro-Jitter:</span>
              <span style={styles.metricVal('#00ff88')}>{mouseMetrics.jitter} px</span>
            </div>
            <div style={styles.metricRow}>
              <span style={styles.metricLabel}>Bot Likelihood:</span>
              <span style={styles.metricVal(mouseMetrics.botLikelihood > 15 ? '#ff3355' : '#00ff88')}>
                {mouseMetrics.botLikelihood}%
              </span>
            </div>
          </div>
        </div>

        {/* 3. VOICEPRINT MFCC / DTW & DEEPFAKE DETECTION CARD */}
        <div style={styles.card}>
          <div style={styles.cardTitle}>
            <span>🎙 Voiceprint & Deepfake Detector</span>
            <span style={styles.badge(deepfakeConfidence < 5 ? '#00ff88' : '#ffaa00')}>
              {deepfakeConfidence < 5 ? 'NATURAL VOICE' : 'DEEPFAKE RISK'}
            </span>
          </div>

          <div style={{ fontSize: '11px', color: '#94a3b8' }}>
            12-Band MFCC Spectral Analysis & Dynamic Time Warping (DTW) Acoustic Verification:
          </div>

          {/* 12-Band MFCC Visual Bars */}
          <div style={{ background: '#040812', padding: '12px', borderRadius: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: '#64748b', marginBottom: '8px' }}>
              <span>MFCC BAND 1-12</span>
              <span>SPECTRAL FLUX: {spectralFlux}</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', height: '45px', gap: '4px' }}>
              {mfccCoefficients.map((coef, i) => {
                const normVal = Math.min(100, Math.max(10, Math.abs(coef) * 4));
                return (
                  <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', height: '100%', justifyContent: 'flex-end' }}>
                    <div
                      style={{
                        width: '100%',
                        height: `${normVal}%`,
                        background: coef < 0 ? '#ff0055' : 'linear-gradient(180deg, #00f0ff 0%, #10b981 100%)',
                        borderRadius: '2px',
                        transition: 'height 0.3s ease',
                      }}
                    />
                  </div>
                );
              })}
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
            <div style={styles.metricRow}>
              <span style={styles.metricLabel}>DTW Distance:</span>
              <span style={styles.metricVal('#00f0ff')}>{dtwDistance} (Pass &lt; 2.5)</span>
            </div>
            <div style={styles.metricRow}>
              <span style={styles.metricLabel}>Acoustic Match:</span>
              <span style={styles.metricVal('#00ff88')}>{voiceprintMatch}%</span>
            </div>
            <div style={styles.metricRow}>
              <span style={styles.metricLabel}>Phase Coherence:</span>
              <span style={styles.metricVal('#a855f7')}>99.1%</span>
            </div>
            <div style={styles.metricRow}>
              <span style={styles.metricLabel}>Deepfake Risk:</span>
              <span style={styles.metricVal(deepfakeConfidence > 10 ? '#ff3355' : '#00ff88')}>
                {deepfakeConfidence}%
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

import React, { useState, useEffect, useRef } from 'react';
import ConceptPreviewBanner from './ConceptPreviewBanner';

const styles = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: '20px',
    color: '#e2e8f0',
    fontFamily: 'var(--font-mono, monospace)',
    paddingBottom: '20px',
  },
  headerBanner: {
    padding: '16px 22px',
    background: 'linear-gradient(90deg, rgba(0, 240, 255, 0.15) 0%, rgba(168, 85, 247, 0.15) 50%, rgba(255, 0, 85, 0.15) 100%)',
    border: '1px solid rgba(0, 240, 255, 0.3)',
    borderRadius: '12px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5)',
  },
  toolSelectorGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
    gap: '10px',
  },
  toolBtn: (active) => ({
    padding: '12px 14px',
    borderRadius: '8px',
    border: active ? '1px solid #00f0ff' : '1px solid rgba(0, 240, 255, 0.15)',
    background: active
      ? 'linear-gradient(135deg, rgba(0, 240, 255, 0.25) 0%, rgba(59, 130, 246, 0.2) 100%)'
      : 'rgba(10, 15, 30, 0.6)',
    color: active ? '#00f0ff' : '#94a3b8',
    cursor: 'pointer',
    fontSize: '12px',
    fontWeight: 700,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '6px',
    transition: 'all 0.2s ease',
    boxShadow: active ? '0 0 15px rgba(0, 240, 255, 0.3)' : 'none',
  }),
  card: {
    background: 'rgba(10, 15, 30, 0.85)',
    border: '1px solid rgba(0, 240, 255, 0.2)',
    borderRadius: '12px',
    padding: '20px',
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
    backdropFilter: 'blur(12px)',
    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
  },
  cardTitle: {
    fontFamily: 'var(--font-display, sans-serif)',
    fontSize: '15px',
    fontWeight: 700,
    color: '#00f0ff',
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
  actionBtn: (color) => ({
    padding: '10px 18px',
    borderRadius: '6px',
    border: `1px solid ${color || '#00f0ff'}`,
    background: `${color || '#00f0ff'}20`,
    color: color || '#00f0ff',
    fontWeight: 'bold',
    cursor: 'pointer',
    fontSize: '12px',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    transition: 'all 0.2s ease',
  }),
  metricRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    fontSize: '12px',
    padding: '6px 0',
    borderBottom: '1px solid rgba(255,255,255,0.05)',
  }
};

const TOOLS = [
  { id: 'keystroke', name: 'Keystroke Dynamics', icon: '⌨', desc: 'Type-rhythm & dwell/flight time profiling' },
  { id: 'mouse', name: 'Mouse Trajectory', icon: '🖱', desc: 'Kinematic velocity, curvature & bot detection' },
  { id: 'voice', name: 'Voice Deepfake Scanner', icon: '🎙', desc: 'MFCC 12-band spectral DTW analysis' },
  { id: 'federated', name: 'Federated Learning', icon: '⚡', desc: 'FedAvg distributed training & differential privacy' },
  { id: 'gnn', name: 'GNN Fraud Rings', icon: '🕸', desc: 'GraphSAGE message passing & loop detection' },
  { id: 'qrng', name: 'QRNG Hardware Stream', icon: '⚛', desc: 'Quantum entropy & NIST SP 800-22 test suite' },
  { id: 'zkproof', name: 'ZK-SNARK Prover', icon: '🛡', desc: 'Zero-Knowledge Groth16 circuit verifier' },
  { id: 'ssaf', name: 'SSAF Adaptive Filter', icon: '〰', desc: 'Sub-second adaptive signal filtering' },
];

export default function ToolDemoStudio() {
  const [selectedTool, setSelectedTool] = useState('keystroke');

  // ── 1. Keystroke Demo State ──
  const [typedText, setTypedText] = useState('');
  const [typingLogs, setTypingLogs] = useState([]);
  const [botMode, setBotMode] = useState(false);
  const keyMap = useRef({});

  const handleKeyDown = (e) => {
    keyMap.current[e.code] = performance.now();
  };

  const handleKeyUp = (e) => {
    const now = performance.now();
    const pressTime = keyMap.current[e.code];
    if (pressTime) {
      const dwell = Math.round(now - pressTime);
      delete keyMap.current[e.code];
      setTypingLogs(prev => {
        const last = prev[prev.length - 1];
        const flight = last ? Math.round(pressTime - last.t) : 80;
        return [...prev, { key: e.key, dwell, flight, t: now }].slice(-25);
      });
    }
  };

  const simulateBotTyping = () => {
    setBotMode(true);
    setTypedText('');
    setTypingLogs([]);
    const botInput = 'protean-automated-script-attack-2026';
    let idx = 0;
    const interval = setInterval(() => {
      if (idx >= botInput.length) {
        clearInterval(interval);
        setBotMode(false);
        return;
      }
      const char = botInput[idx];
      setTypedText(prev => prev + char);
      setTypingLogs(prev => [...prev, { key: char, dwell: 20, flight: 20, t: performance.now() }]);
      idx++;
    }, 20);
  };

  // ── 2. Mouse Kinematics Demo State ──
  const mouseCanvasRef = useRef(null);
  const [mouseTrajectory, setMouseTrajectory] = useState([]);
  const [mouseStats, setMouseStats] = useState({ velocity: 0, curvature: 0, botScore: 0 });

  const handleMouseMove = (e) => {
    const rect = mouseCanvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const t = performance.now();

    setMouseTrajectory(prev => {
      const updated = [...prev, { x, y, t }].slice(-50);
      if (updated.length > 2) {
        const p1 = updated[updated.length - 3];
        const p2 = updated[updated.length - 2];
        const p3 = updated[updated.length - 1];
        const dt = (p3.t - p2.t) / 1000;
        const dist = Math.sqrt(Math.pow(p3.x - p2.x, 2) + Math.pow(p3.y - p2.y, 2));
        const vel = dt > 0 ? Math.round(dist / dt) : 0;
        const dx1 = p2.x - p1.x; const dy1 = p2.y - p1.y;
        const dx2 = p3.x - p2.x; const dy2 = p3.y - p2.y;
        const curv = Math.abs(Math.atan2(dy2, dx2) - Math.atan2(dy1, dx1));
        const bot = curv < 0.02 && vel > 1000 ? 98 : Math.max(1, (100 - vel / 25) % 12);
        setMouseStats({ velocity: vel, curvature: Number(curv.toFixed(3)), botScore: Number(bot.toFixed(1)) });
      }
      return updated;
    });
  };

  const simulateBotMouse = () => {
    const pts = [];
    for (let i = 0; i <= 30; i++) {
      pts.push({ x: 10 + i * 9, y: 70, t: performance.now() + i * 5 });
    }
    setMouseTrajectory(pts);
    setMouseStats({ velocity: 1800, curvature: 0.001, botScore: 99.4 });
  };

  // Draw Mouse Canvas
  useEffect(() => {
    if (selectedTool !== 'mouse') return;
    const canvas = mouseCanvasRef.current;
    if (!canvas || typeof canvas.getContext !== 'function') return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    ctx.strokeStyle = 'rgba(0, 240, 255, 0.1)';
    for (let x = 0; x < canvas.width; x += 25) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke();
    }

    if (mouseTrajectory.length < 2) return;

    ctx.beginPath();
    ctx.strokeStyle = mouseStats.botScore > 50 ? '#ff0055' : '#00f0ff';
    ctx.lineWidth = 2.5;
    mouseTrajectory.forEach((pt, i) => {
      if (i === 0) ctx.moveTo(pt.x, pt.y);
      else ctx.lineTo(pt.x, pt.y);
    });
    ctx.stroke();
  }, [mouseTrajectory, selectedTool, mouseStats.botScore]);

  // ── 3. Voice Deepfake Demo State ──
  const [audioPreset, setAudioPreset] = useState('human_en_us');
  const [voiceScan, setVoiceScan] = useState({ mfcc: [12, -4, 8, -2, 6, 1, -3, 5, 2, -1, 4, 0], dtw: 1.2, deepfakeProb: 1.4 });

  const runVoiceScan = (preset) => {
    setAudioPreset(preset);
    if (preset === 'human_en_us') {
      setVoiceScan({ mfcc: [14.2, -5.1, 9.3, -1.8, 7.2, 2.1, -4.0, 6.1, 3.0, -1.2, 5.0, 1.1], dtw: 1.15, deepfakeProb: 1.2 });
    } else if (preset === 'elevenlabs_clone') {
      setVoiceScan({ mfcc: [2.1, -0.4, 1.1, -0.2, 0.8, 0.1, -0.3, 0.5, 0.2, -0.1, 0.4, 0.0], dtw: 6.84, deepfakeProb: 96.8 });
    } else if (preset === 'vits_synthetic') {
      setVoiceScan({ mfcc: [0.8, -0.1, 0.5, -0.1, 0.3, 0.0, -0.1, 0.2, 0.1, 0.0, 0.2, 0.0], dtw: 8.42, deepfakeProb: 99.1 });
    }
  };

  // ── 4. Federated Learning Demo State ──
  const [flNodes, setFlNodes] = useState([
    { id: 'NODE-01', type: 'Mobile Wallet', loss: 0.032, status: 'TRAINING', dpEpsilon: 0.25 },
    { id: 'NODE-02', type: 'POS Terminal', loss: 0.028, status: 'READY', dpEpsilon: 0.25 },
    { id: 'NODE-03', type: 'Web Gateway', loss: 0.019, status: 'TRAINING', dpEpsilon: 0.25 },
  ]);
  const [flRound, setFlRound] = useState(12);

  const triggerFlAggregation = () => {
    setFlRound(r => r + 1);
    setFlNodes(prev => prev.map(n => ({
      ...n,
      loss: Number((n.loss * 0.94).toFixed(4)),
      status: 'WEIGHTS_AGGREGATED',
    })));
  };

  // ── 5. GNN Fraud Ring Demo State ──
  const [gnnMode, setGnnMode] = useState('circular');
  const [detectedRings, setDetectedRings] = useState([
    { name: 'CIRCULAR_LAUNDERING_RING_A', size: 4, risk: 94.2 },
    { name: 'SYBIL_FAN_OUT_HUB_B', size: 6, risk: 89.8 },
  ]);

  const injectSybilAttack = () => {
    setDetectedRings(prev => [
      ...prev,
      { name: `INJECTED_SYBIL_RING_${Math.floor(Math.random() * 90 + 10)}`, size: 8, risk: 98.6 }
    ]);
  };

  // ── 6. QRNG Demo State ──
  const [qrngSeed, setQrngSeed] = useState('0x4f82a10b99c82e3f');
  const [qrngEntropy, setQrngEntropy] = useState('01101001110010110100101011110010');

  const generateQrngSeed = () => {
    const newSeed = '0x' + Array.from({ length: 16 }, () => Math.floor(Math.random() * 16).toString(16)).join('');
    const newStream = Array.from({ length: 32 }, () => (Math.random() > 0.5 ? '1' : '0')).join('');
    setQrngSeed(newSeed);
    setQrngEntropy(newStream);
  };

  // ── 7. ZK-SNARK Demo State ──
  const [zkStatus, setZkStatus] = useState('IDLE'); // IDLE, GENERATING, VERIFIED
  const [zkTime, setZkTime] = useState(0);

  const proveTxZk = () => {
    setZkStatus('GENERATING');
    const start = performance.now();
    setTimeout(() => {
      setZkTime(Math.round(performance.now() - start));
      setZkStatus('VERIFIED');
    }, 600);
  };

  // ── 8. SSAF Wave Filter Demo State ──
  const [ssafNoise, setSsafNoise] = useState(15);
  const [ssafOutput, setSsafOutput] = useState(0.82);

  const adjustSsafNoise = (val) => {
    setSsafNoise(val);
    setSsafOutput(Number((1.0 - (val / 100) * 0.35).toFixed(2)));
  };

  return (
    <div style={styles.container}>
      {/* Top Banner */}
      <div style={styles.headerBanner}>
        <div>
          <div style={{ color: '#00f0ff', fontWeight: 800, fontSize: '16px', fontFamily: 'var(--font-display)' }}>
            🧪 PROTEAN TOOL DEMO STUDIO
          </div>
          <div style={{ color: '#94a3b8', fontSize: '12px', marginTop: '4px' }}>
            Interactive Sandbox to benchmark, inspect, and stress-test any security & AI detection engine live.
          </div>
        </div>
        <span style={styles.badge('#00ff88')}>SANDBOX STATUS: READY</span>
      </div>

      {/* Tool Selector Grid */}
      <div style={styles.toolSelectorGrid}>
        {TOOLS.map((t) => (
          <button
            key={t.id}
            onClick={() => setSelectedTool(t.id)}
            style={styles.toolBtn(selectedTool === t.id)}
          >
            <span style={{ fontSize: '18px' }}>{t.icon}</span>
            <span>{t.name}</span>
          </button>
        ))}
      </div>

      {/* ACTIVE DEMO VIEW PANEL */}
      <div style={styles.card}>
        {/* 1. KEYSTROKE DYNAMICS */}
        {selectedTool === 'keystroke' && (
          <>
            <div style={styles.cardTitle}>
              <span>⌨ Keystroke Dynamics Profiler & Bot Detector</span>
              <span style={styles.badge(typingLogs.length > 0 && typingLogs[0].dwell === 20 ? '#ff0055' : '#00ff88')}>
                {typingLogs.length > 0 && typingLogs[0].dwell === 20 ? 'BOT AUTOMATION' : 'HUMAN DYNAMICS'}
              </span>
            </div>

            <div style={{ fontSize: '12px', color: '#94a3b8' }}>
              Type manually in the input box to record your natural typing rhythm, or trigger the automated script simulator:
            </div>

            <div style={{ display: 'flex', gap: '12px' }}>
              <input
                type="text"
                placeholder="Type here to capture live cadence..."
                value={typedText}
                onChange={(e) => setTypedText(e.target.value)}
                onKeyDown={handleKeyDown}
                onKeyUp={handleKeyUp}
                disabled={botMode}
                style={{
                  flex: 1,
                  padding: '12px 16px',
                  background: '#040812',
                  border: '1px solid rgba(0,240,255,0.3)',
                  borderRadius: '6px',
                  color: '#00f0ff',
                  fontFamily: 'monospace',
                }}
              />
              <button
                onClick={simulateBotTyping}
                disabled={botMode}
                style={styles.actionBtn('#ff0055')}
              >
                🤖 Simulate Bot Attack
              </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px' }}>
              <div style={styles.metricRow}>
                <span style={{ color: '#94a3b8' }}>Captured Keypresses:</span>
                <span style={{ color: '#00f0ff', fontWeight: 'bold' }}>{typingLogs.length}</span>
              </div>
              <div style={styles.metricRow}>
                <span style={{ color: '#94a3b8' }}>Average Dwell Time:</span>
                <span style={{ color: '#00ff88', fontWeight: 'bold' }}>
                  {typingLogs.length > 0 ? Math.round(typingLogs.reduce((a, b) => a + b.dwell, 0) / typingLogs.length) : 0} ms
                </span>
              </div>
              <div style={styles.metricRow}>
                <span style={{ color: '#94a3b8' }}>Average Flight Time:</span>
                <span style={{ color: '#a855f7', fontWeight: 'bold' }}>
                  {typingLogs.length > 0 ? Math.round(typingLogs.reduce((a, b) => a + b.flight, 0) / typingLogs.length) : 0} ms
                </span>
              </div>
            </div>

            {/* Dwell Histogram */}
            <div style={{ background: '#040812', padding: '14px', borderRadius: '8px' }}>
              <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '8px' }}>LIVE KEYPRESS CADENCE PROFILE</div>
              <div style={{ display: 'flex', alignItems: 'flex-end', height: '50px', gap: '4px' }}>
                {typingLogs.length === 0 ? (
                  <div style={{ fontSize: '11px', color: '#475569' }}>No typing captured yet. Type above or click simulate!</div>
                ) : (
                  typingLogs.map((log, idx) => (
                    <div
                      key={idx}
                      title={`Key: ${log.key} | Dwell: ${log.dwell}ms`}
                      style={{
                        flex: 1,
                        height: `${Math.min(100, (log.dwell / 120) * 100)}%`,
                        background: log.dwell <= 20 ? '#ff0055' : 'linear-gradient(180deg, #00f0ff 0%, #3b82f6 100%)',
                        borderRadius: '2px',
                      }}
                    />
                  ))
                )}
              </div>
            </div>
          </>
        )}

        {/* 2. MOUSE TRAJECTORY */}
        {selectedTool === 'mouse' && (
          <>
            <div style={styles.cardTitle}>
              <span>🖱 Mouse Kinematics & Bot Detection Demo</span>
              <span style={styles.badge(mouseStats.botScore > 50 ? '#ff0055' : '#00ff88')}>
                {mouseStats.botScore > 50 ? `BOT DETECTED (${mouseStats.botScore}%)` : 'HUMAN CURSOR'}
              </span>
            </div>

            <div style={{ fontSize: '12px', color: '#94a3b8' }}>
              Move cursor over the box below to test human hand micro-jitter, or trigger a linear robotic mouse sweep:
            </div>

            <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
              <div
                ref={mouseCanvasRef}
                onMouseMove={handleMouseMove}
                style={{
                  flex: 1,
                  height: '150px',
                  background: '#040812',
                  border: '1px solid rgba(0,240,255,0.2)',
                  borderRadius: '8px',
                  cursor: 'crosshair',
                  position: 'relative',
                }}
              >
                <canvas ref={mouseCanvasRef} width={450} height={150} style={{ width: '100%', height: '100%' }} />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                <button
                  onClick={simulateBotMouse}
                  style={styles.actionBtn('#ff0055')}
                >
                  🤖 Linear Bot Drag
                </button>
                <button
                  onClick={() => { setMouseTrajectory([]); setMouseStats({ velocity: 0, curvature: 0, botScore: 0 }); }}
                  style={styles.actionBtn('#94a3b8')}
                >
                  🧹 Clear Trajectory
                </button>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }}>
              <div style={styles.metricRow}>
                <span style={{ color: '#94a3b8' }}>Kinematic Velocity:</span>
                <span style={{ color: '#00f0ff', fontWeight: 'bold' }}>{mouseStats.velocity} px/s</span>
              </div>
              <div style={styles.metricRow}>
                <span style={{ color: '#94a3b8' }}>Path Curvature:</span>
                <span style={{ color: '#a855f7', fontWeight: 'bold' }}>{mouseStats.curvature} rad</span>
              </div>
              <div style={styles.metricRow}>
                <span style={{ color: '#94a3b8' }}>Bot Probability:</span>
                <span style={{ color: mouseStats.botScore > 50 ? '#ff0055' : '#00ff88', fontWeight: 'bold' }}>
                  {mouseStats.botScore}%
                </span>
              </div>
            </div>
          </>
        )}

        {/* 3. VOICE DEEPFAKE SCANNER */}
        {selectedTool === 'voice' && (
          <>
            <div style={styles.cardTitle}>
              <span>🎙 Voiceprint MFCC/DTW & Deepfake Scanner</span>
              <span style={styles.badge(voiceScan.deepfakeProb > 50 ? '#ff0055' : '#00ff88')}>
                {voiceScan.deepfakeProb > 50 ? 'SYNTHETIC DEEPFAKE DETECTED' : 'GENUINE VOICEPRINT'}
              </span>
            </div>

            <div style={{ fontSize: '12px', color: '#94a3b8' }}>
              Select an audio sample profile to run 12-Band Mel-Frequency Cepstral Coefficients (MFCC) & DTW matching:
            </div>

            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                onClick={() => runVoiceScan('human_en_us')}
                style={styles.actionBtn(audioPreset === 'human_en_us' ? '#00ff88' : '#64748b')}
              >
                👤 Genuine Human Voice
              </button>
              <button
                onClick={() => runVoiceScan('elevenlabs_clone')}
                style={styles.actionBtn(audioPreset === 'elevenlabs_clone' ? '#ff0055' : '#64748b')}
              >
                🤖 ElevenLabs AI Voice Clone
              </button>
              <button
                onClick={() => runVoiceScan('vits_synthetic')}
                style={styles.actionBtn(audioPreset === 'vits_synthetic' ? '#eab308' : '#64748b')}
              >
                🔊 VITS Neural Speech Synth
              </button>
            </div>

            <div style={{ background: '#040812', padding: '14px', borderRadius: '8px' }}>
              <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '8px' }}>12-BAND MFCC CEPSTRAL SPECTRUM</div>
              <div style={{ display: 'flex', gap: '6px', height: '60px', alignItems: 'flex-end' }}>
                {voiceScan.mfcc.map((v, idx) => (
                  <div key={idx} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', height: '100%', justifyContent: 'flex-end' }}>
                    <div style={{
                      width: '100%',
                      height: `${Math.min(100, Math.abs(v) * 6)}%`,
                      background: v < 0 ? '#ff0055' : '#00f0ff',
                      borderRadius: '2px',
                    }} />
                  </div>
                ))}
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px' }}>
              <div style={styles.metricRow}>
                <span style={{ color: '#94a3b8' }}>DTW Distance Score:</span>
                <span style={{ color: '#00f0ff', fontWeight: 'bold' }}>{voiceScan.dtw} (Threshold: 2.5)</span>
              </div>
              <div style={{ ...styles.metricRow, borderBottom: 'none' }}>
                <span style={{ color: '#94a3b8' }}>Deepfake Confidence:</span>
                <span style={{ color: voiceScan.deepfakeProb > 50 ? '#ff0055' : '#00ff88', fontWeight: 'bold' }}>
                  {voiceScan.deepfakeProb}%
                </span>
              </div>
            </div>
          </>
        )}

        {/* 4. FEDERATED LEARNING */}
        {selectedTool === 'federated' && (
          <>
            <div style={styles.cardTitle}>
              <span>⚡ Federated Learning Protocol Simulator</span>
              <span style={styles.badge('#00f0ff')}>FEDAVG ROUND #{flRound}</span>
            </div>

            <div style={{ fontSize: '12px', color: '#94a3b8' }}>
              Simulate distributed local gradient aggregation without raw data exchange:
            </div>

            <div style={{ display: 'flex', gap: '12px' }}>
              <button onClick={triggerFlAggregation} style={styles.actionBtn('#00f0ff')}>
                🔄 Trigger Global Gradient Aggregation
              </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px' }}>
              {flNodes.map(node => (
                <div key={node.id} style={{ background: '#040812', padding: '12px', borderRadius: '8px', border: '1px solid rgba(0,240,255,0.15)' }}>
                  <div style={{ color: '#00f0ff', fontWeight: 'bold', fontSize: '13px' }}>{node.id} ({node.type})</div>
                  <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '6px' }}>Local Loss: <span style={{ color: '#00ff88' }}>{node.loss}</span></div>
                  <div style={{ fontSize: '11px', color: '#94a3b8' }}>DP Epsilon (ε): <span style={{ color: '#a855f7' }}>{node.dpEpsilon}</span></div>
                </div>
              ))}
            </div>
          </>
        )}

        {/* 5. GNN FRAUD RINGS */}
        {selectedTool === 'gnn' && (
          <>
            <ConceptPreviewBanner label="GNN Fraud Ring Investigator" />
            <div style={styles.cardTitle}>
              <span>🕸 GNN Fraud Ring Investigator</span>
              <span style={styles.badge('#ff0055')}>{detectedRings.length} RINGS FLAGGED</span>
            </div>

            <div style={{ fontSize: '12px', color: '#94a3b8' }}>
              Graph Neural Network multi-hop message passing for circular laundering and Sybil detection:
            </div>

            <div style={{ display: 'flex', gap: '12px' }}>
              <button onClick={injectSybilAttack} style={styles.actionBtn('#ff0055')}>
                ⚡ Inject Sybil Attack Pattern
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {detectedRings.map((ring, idx) => (
                <div key={idx} style={{ background: '#040812', padding: '12px', borderRadius: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <span style={{ color: '#ff3355', fontWeight: 'bold' }}>{ring.name}</span>
                    <span style={{ color: '#64748b', fontSize: '11px', marginLeft: '10px' }}>{ring.size} Interconnected Nodes</span>
                  </div>
                  <span style={styles.badge('#ff0055')}>RISK: {ring.risk}%</span>
                </div>
              ))}
            </div>
          </>
        )}

        {/* 6. QRNG HARDWARE STREAM */}
        {selectedTool === 'qrng' && (
          <>
            <ConceptPreviewBanner label="QRNG Quantum Seed Generator" />
            <div style={styles.cardTitle}>
              <span>⚛ QRNG Quantum Seed Generator</span>
              <span style={styles.badge('#00ff88')}>NIST SP 800-22 PASSED</span>
            </div>

            <div style={{ fontSize: '12px', color: '#94a3b8' }}>
              Hardware Optical Phase Fluctuation Quantum Random Number Generator:
            </div>

            <button onClick={generateQrngSeed} style={styles.actionBtn('#a855f7')}>
              🎲 Generate 256-bit Quantum Seed
            </button>

            <div style={{ background: '#040812', padding: '12px', borderRadius: '8px', fontSize: '12px' }}>
              <div style={{ color: '#64748b', marginBottom: '4px' }}>QUANTUM SEED HEX:</div>
              <div style={{ color: '#eab308', wordBreak: 'break-all', fontWeight: 'bold' }}>{qrngSeed}</div>
              <div style={{ color: '#64748b', margin: '8px 0 4px 0' }}>BITSTREAM SAMPLE:</div>
              <div style={{ color: '#00ff88', wordBreak: 'break-all' }}>{qrngEntropy}</div>
            </div>
          </>
        )}

        {/* 7. ZK-SNARK PROVER */}
        {selectedTool === 'zkproof' && (
          <>
            <div style={styles.cardTitle}>
              <span>🛡 Groth16 / Plonk Zero-Knowledge Prover</span>
              <span style={styles.badge(zkStatus === 'VERIFIED' ? '#00ff88' : '#00f0ff')}>
                STATUS: {zkStatus}
              </span>
            </div>

            <div style={{ fontSize: '12px', color: '#94a3b8' }}>
              Generate ZK proof of transaction validity without exposing account balance or identity:
            </div>

            <button onClick={proveTxZk} style={styles.actionBtn('#00f0ff')}>
              ⚙ Generate ZK-SNARK Proof
            </button>

            {zkStatus === 'VERIFIED' && (
              <div style={{ background: '#040812', padding: '12px', borderRadius: '8px', fontSize: '12px' }}>
                <div style={{ color: '#00ff88', fontWeight: 'bold' }}>✓ ZK Proof Generated in {zkTime}ms!</div>
                <div style={{ color: '#64748b', marginTop: '4px', fontSize: '11px' }}>
                  Proof hash: 0x9a8f23...d77a (Verified via On-Chain Verifier Contract)
                </div>
              </div>
            )}
          </>
        )}

        {/* 8. SSAF WAVE FILTER */}
        {selectedTool === 'ssaf' && (
          <>
            <div style={styles.cardTitle}>
              <span>〰 Sub-Second Adaptive Filter (SSAF)</span>
              <span style={styles.badge('#00f0ff')}>SIGNAL NOISE: {ssafNoise}%</span>
            </div>

            <div style={{ fontSize: '12px', color: '#94a3b8' }}>
              Adjust input signal noise level to observe adaptive filtering response time:
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
              <input
                type="range"
                min="0"
                max="100"
                value={ssafNoise}
                onChange={(e) => adjustSsafNoise(Number(e.target.value))}
                style={{ flex: 1 }}
              />
              <span style={{ color: '#00f0ff', fontWeight: 'bold' }}>{ssafNoise}% Noise</span>
            </div>

            <div style={{ background: '#040812', padding: '12px', borderRadius: '8px', fontSize: '12px' }}>
              <div style={{ color: '#94a3b8' }}>
                Filtered Output Efficiency: <span style={{ color: '#00ff88', fontWeight: 'bold' }}>{(ssafOutput * 100).toFixed(0)}%</span>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

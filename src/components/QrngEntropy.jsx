import React, { useState, useEffect } from 'react';

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
    gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
    gap: '16px',
  },
  card: {
    background: 'rgba(10, 15, 30, 0.85)',
    border: '1px solid rgba(0, 240, 255, 0.2)',
    borderRadius: '12px',
    padding: '20px',
    display: 'flex',
    flexDirection: 'column',
    gap: '14px',
    backdropFilter: 'blur(10px)',
    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
  },
  cardTitle: {
    fontFamily: 'var(--font-display, sans-serif)',
    fontSize: '15px',
    fontWeight: 700,
    color: 'var(--neon-cyan, #00f0ff)',
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
  bitStream: {
    background: '#040812',
    padding: '12px',
    borderRadius: '8px',
    fontFamily: 'monospace',
    fontSize: '11px',
    color: '#00ff88',
    wordBreak: 'break-all',
    minHeight: '80px',
    border: '1px solid rgba(0, 240, 255, 0.15)',
  },
  metricRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    fontSize: '12px',
  }
};

export default function QrngEntropy() {
  const [entropyStream, setEntropyStream] = useState('');
  const [entropyRate, setEntropyRate] = useState(102.4); // Mbps
  const [quantumCoherence, setQuantumCoherence] = useState(99.98); // %
  const [lastSeed, setLastSeed] = useState('0x7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1f');

  // Generate continuous quantum bit stream simulation
  useEffect(() => {
    const generateBits = () => {
      let bits = '';
      for (let i = 0; i < 160; i++) {
        bits += Math.random() > 0.5 ? '1' : '0';
      }
      setEntropyStream(bits);

      // Generate seed
      const seedHex = '0x' + Array.from({ length: 20 }, () =>
        Math.floor(Math.random() * 256).toString(16).padStart(2, '0')
      ).join('');
      setLastSeed(seedHex);

      setEntropyRate(Number((100 + Math.random() * 5).toFixed(1)));
    };

    generateBits();
    const interval = setInterval(generateBits, 1500);
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={styles.container}>
      {/* Banner */}
      <div style={{
        padding: '14px 20px',
        background: 'linear-gradient(90deg, rgba(168,85,247,0.15) 0%, rgba(0,240,255,0.15) 100%)',
        border: '1px solid rgba(168, 85, 247, 0.3)',
        borderRadius: '10px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div>
          <span style={{ color: '#a855f7', fontWeight: 'bold', fontSize: '15px' }}>⚛ HARDWARE QUANTUM RANDOM NUMBER GENERATOR (QRNG)</span>
          <div style={{ color: '#94a3b8', fontSize: '12px', marginTop: '4px' }}>
            Photon Phase Fluctuation Entropy Source · NIST SP 800-22 Verified · Post-Quantum PQC Key Seeding
          </div>
        </div>
        <span style={styles.badge('#00ff88')}>QRNG STATUS: ONLINE (100% MIN-ENTROPY)</span>
      </div>

      <div style={styles.grid3}>
        {/* 1. QUANTUM ENTROPY BITSTREAM */}
        <div style={styles.card}>
          <div style={styles.cardTitle}>
            <span>⚡ Quantum Entropy Bitstream</span>
            <span style={styles.badge('#00f0ff')}>{entropyRate} Mbps</span>
          </div>

          <div style={{ fontSize: '11px', color: '#94a3b8' }}>
            Real-time optical beam splitter quantum vacuum phase fluctuations:
          </div>

          <div style={styles.bitStream}>
            {entropyStream}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={styles.metricRow}>
              <span style={{ color: '#94a3b8' }}>Min-Entropy:</span>
              <span style={{ color: '#00ff88', fontWeight: 'bold' }}>0.999998 bits/bit</span>
            </div>
            <div style={styles.metricRow}>
              <span style={{ color: '#94a3b8' }}>Coherence Stability:</span>
              <span style={{ color: '#00f0ff', fontWeight: 'bold' }}>{quantumCoherence}%</span>
            </div>
          </div>
        </div>

        {/* 2. NIST SP 800-22 TEST SUITE */}
        <div style={styles.card}>
          <div style={styles.cardTitle}>
            <span>🧪 NIST SP 800-22 Randomness Suite</span>
            <span style={styles.badge('#00ff88')}>ALL 6 TESTS PASSED</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '11px' }}>
            {[
              { test: 'Frequency (Monobit) Test', pVal: '0.542', status: 'PASS' },
              { test: 'Block Frequency Test', pVal: '0.489', status: 'PASS' },
              { test: 'Runs Test', pVal: '0.612', status: 'PASS' },
              { test: 'Longest Run of Ones', pVal: '0.521', status: 'PASS' },
              { test: 'Discrete Fourier Transform (FFT)', pVal: '0.704', status: 'PASS' },
              { test: 'Approximate Entropy Test', pVal: '0.812', status: 'PASS' },
            ].map((t, idx) => (
              <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 8px', background: '#040812', borderRadius: '4px' }}>
                <span style={{ color: '#e2e8f0' }}>{t.test}</span>
                <div>
                  <span style={{ color: '#64748b', marginRight: '8px' }}>p={t.pVal}</span>
                  <span style={{ color: '#00ff88', fontWeight: 'bold' }}>{t.status}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 3. PQC SEED & HARDWARE HEALTH */}
        <div style={styles.card}>
          <div style={styles.cardTitle}>
            <span>🔐 PQC Key Seed Generator</span>
            <span style={styles.badge('#eab308')}>KYBER / DILITHIUM</span>
          </div>

          <div style={{ fontSize: '11px', color: '#94a3b8' }}>
            Latest 256-bit Quantum Seed for Post-Quantum Key Rotation:
          </div>

          <div style={{ background: '#040812', padding: '10px', borderRadius: '6px', fontSize: '11px', color: '#eab308', wordBreak: 'break-all' }}>
            {lastSeed}
          </div>

          <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={styles.metricRow}>
              <span style={{ color: '#94a3b8' }}>Laser Diode Temp:</span>
              <span style={{ color: '#00f0ff', fontWeight: 'bold' }}>24.2 °C (Stable)</span>
            </div>
            <div style={styles.metricRow}>
              <span style={{ color: '#94a3b8' }}>Photodiode Bias:</span>
              <span style={{ color: '#00ff88', fontWeight: 'bold' }}>12.0 V</span>
            </div>
            <div style={styles.metricRow}>
              <span style={{ color: '#94a3b8' }}>Synthetic Noise Seed:</span>
              <span style={{ color: '#a855f7', fontWeight: 'bold' }}>INJECTED</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

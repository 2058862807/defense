import React, { memo, useMemo } from 'react';

const MODE_CONFIG = {
  COMPETITIVE: {
    color: '#ff4400',
    waveColor1: '#ff4400',
    waveColor2: '#ff8800',
    amplitude: 40,
    frequency: 0.035,
    complexity: 3,
    label: 'COMPETITIVE MODE',
    subtitle: 'Aggressive scanning — sharp peaks',
  },
  DEFERENTIAL: {
    color: '#4466ff',
    waveColor1: '#4466ff',
    waveColor2: '#8844ff',
    amplitude: 25,
    frequency: 0.018,
    complexity: 2,
    label: 'DEFERENTIAL MODE',
    subtitle: 'Smooth monitoring — gentle curves',
  },
  ATTRIBUTION_BLIND: {
    color: '#00ffff',
    waveColor1: '#00ffff',
    waveColor2: '#ffffff',
    amplitude: 50,
    frequency: 0.05,
    complexity: 6,
    label: 'ATTRIBUTION-BLIND MODE',
    subtitle: 'Chaotic scanning — maximum entropy',
  },
  NO_SSAF: {
    color: '#00cc66',
    waveColor1: '#00cc66',
    waveColor2: '#00cc66',
    amplitude: 2,
    frequency: 0.005,
    complexity: 1,
    label: 'NO SSAF MODE',
    subtitle: 'Flat line — no attribution control',
  },
};

function generateWavePoints(width, height, config, time) {
  const points = [];
  const { amplitude, frequency, complexity } = config;
  for (let x = 0; x <= width; x += 2) {
    let y = height / 2;
    for (let c = 1; c <= complexity; c++) {
      const f = frequency * c;
      const a = amplitude / c;
      y += a * Math.sin(x * f + time * (0.02 + c * 0.01) + c * 1.5);
    }
    // Add some random noise for attribution-blind
    if (config.complexity >= 6) {
      y += (Math.random() - 0.5) * 8;
    }
    points.push({ x, y });
  }
  return points;
}

function WavePath({ width, height, mode, time }) {
  const config = MODE_CONFIG[mode] || MODE_CONFIG.NO_SSAF;
  const points = useMemo(() => generateWavePoints(width, height, config, time), [width, height, config, time]);

  const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');

  // Bottom fill
  const fillD = pathD + ` L ${width} ${height} L 0 ${height} Z`;

  return (
    <svg width={width} height={height} style={{ display: 'block', position: 'absolute', top: 0, left: 0 }}>
      <defs>
        <linearGradient id={`wave-grad-${mode}`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor={config.waveColor1} stopOpacity="0.6" />
          <stop offset="50%" stopColor={config.waveColor2} stopOpacity="0.4" />
          <stop offset="100%" stopColor={config.waveColor1} stopOpacity="0.6" />
        </linearGradient>
        <linearGradient id={`fill-grad-${mode}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={config.waveColor1} stopOpacity="0.2" />
          <stop offset="100%" stopColor={config.waveColor1} stopOpacity="0" />
        </linearGradient>
        <filter id={`wave-glow-${mode}`}>
          <feGaussianBlur stdDeviation="2" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      {/* Fill under wave */}
      <path d={fillD} fill={`url(#fill-grad-${mode})`} opacity={0.3} />
      {/* Glow line */}
      <path
        d={pathD}
        fill="none"
        stroke={config.waveColor1}
        strokeWidth={3}
        opacity={0.3}
        filter={`url(#wave-glow-${mode})`}
      />
      {/* Main wave line */}
      <path
        d={pathD}
        fill="none"
        stroke={config.waveColor1}
        strokeWidth={1.5}
        opacity={0.8}
      />
    </svg>
  );
}

function SsafWave({ ssafData = { mode: 'NO_SSAF', magnitude: 0, score: 0 } }) {
  const containerRef = React.useRef(null);
  const [dimensions, setDimensions] = React.useState({ width: 600, height: 200 });
  const [time, setTime] = React.useState(0);
  const mode = ssafData.mode || 'NO_SSAF';

  // Handle resize
  React.useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setDimensions({
          width: entry.contentRect.width || 600,
          height: entry.contentRect.height || 200,
        });
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Animation loop — throttled to ~10fps for Firefox
  React.useEffect(() => {
    let running = true;
    const INTERVAL = 100;
    const id = setInterval(() => {
      if (!running) return;
      setTime((t) => t + 1);
    }, INTERVAL);
    return () => { clearInterval(id); running = false; };
  }, []);

  const config = MODE_CONFIG[mode] || MODE_CONFIG.NO_SSAF;

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height: '100%',
        minHeight: 200,
        background: '#050a14',
        border: '1px solid rgba(0,255,255,0.1)',
        borderRadius: 8,
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      {/* Wave canvas */}
      <div style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        transition: 'all 0.8s ease-in-out',
      }}>
        <WavePath
          width={dimensions.width}
          height={dimensions.height}
          mode={mode}
          time={time}
        />
      </div>

      {/* Mode label */}
      <div style={{
        position: 'absolute',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        textAlign: 'center',
        zIndex: 10,
        pointerEvents: 'none',
        transition: 'all 0.6s ease-in-out',
      }}>
        <div style={{
          color: config.color,
          fontFamily: '"Courier New", monospace',
          fontSize: 18,
          fontWeight: 'bold',
          letterSpacing: 3,
          textShadow: `0 0 20px ${config.color}44, 0 0 40px ${config.color}22`,
          transition: 'all 0.6s ease-in-out',
        }}>
          {config.label}
        </div>
        <div style={{
          color: config.color,
          fontFamily: '"Courier New", monospace',
          fontSize: 11,
          opacity: 0.6,
          marginTop: 6,
          letterSpacing: 1,
          transition: 'all 0.6s ease-in-out',
        }}>
          {config.subtitle}
        </div>
        <div style={{
          display: 'flex',
          gap: 24,
          justifyContent: 'center',
          marginTop: 10,
          transition: 'all 0.6s ease-in-out',
        }}>
          <span style={{
            color: config.color,
            fontFamily: '"Courier New", monospace',
            fontSize: 10,
            opacity: 0.5,
            letterSpacing: 1,
          }}>
            MAG: {(ssafData.magnitude || 0).toFixed(2)}
          </span>
          <span style={{
            color: config.color,
            fontFamily: '"Courier New", monospace',
            fontSize: 10,
            opacity: 0.5,
            letterSpacing: 1,
          }}>
            SCORE: {(ssafData.score || 0).toFixed(1)}
          </span>
        </div>
      </div>

      {/* Decorative corner markers */}
      <div style={{
        position: 'absolute',
        top: 6,
        left: 8,
        color: config.color,
        fontSize: 8,
        fontFamily: '"Courier New", monospace',
        opacity: 0.3,
        transition: 'color 0.6s ease-in-out',
      }}>▤ SSAF</div>
    </div>
  );
}

export default memo(SsafWave);

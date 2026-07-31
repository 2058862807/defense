import React, { useMemo } from 'react';

const RING_CONFIG = [
  {
    id: 'kyber',
    label: 'Kyber-1024 Active Keys',
    keyCount: 3,
    radius: 70,
    speed: 0.008,
    color: '#00ffff',
    glowColor: 'rgba(0,255,255,0.3)',
    nodeBg: 'rgba(0,255,255,0.1)',
    status: 'ML-KEM-1024 ✓',
  },
  {
    id: 'mldsa',
    label: 'ML-DSA-87 Signing Keys',
    keyCount: 2,
    radius: 50,
    speed: 0.012,
    color: '#aa66ff',
    glowColor: 'rgba(170,102,255,0.3)',
    nodeBg: 'rgba(170,102,255,0.1)',
    status: 'ML-DSA-87 ✓',
  },
  {
    id: 'history',
    label: 'Rotation History',
    keyCount: 5,
    radius: 90,
    speed: 0.005,
    color: '#ffd700',
    glowColor: 'rgba(255,215,0,0.2)',
    nodeBg: 'rgba(255,215,0,0.05)',
    status: 'Rotation Chain ✓',
  },
];

function KeyRing({ config, time }) {
  const angle = time * config.speed;

  const nodes = useMemo(() => {
    const arr = [];
    for (let i = 0; i < config.keyCount; i++) {
      const a = (i / config.keyCount) * 2 * Math.PI + angle;
      const x = config.radius * Math.cos(a);
      const y = config.radius * Math.sin(a);
      const opacity = config.id === 'history' ? 1 - (i / config.keyCount) * 0.6 : 1;
      arr.push({ x, y, opacity, idx: i });
    }
    return arr;
  }, [config.keyCount, config.radius, config.id, angle]);

  const isHistory = config.id === 'history';

  return (
    <div style={{
      position: 'absolute',
      top: '50%',
      left: '50%',
      width: 0,
      height: 0,
      transform: `rotate(${angle * 0.5}deg)`,
    }}>
      {/* Ring orbit */}
      <div style={{
        position: 'absolute',
        left: -config.radius,
        top: -config.radius,
        width: config.radius * 2,
        height: config.radius * 2,
        borderRadius: '50%',
        border: `1px solid ${config.color}`,
        opacity: 0.35,
        boxShadow: `0 0 12px ${config.glowColor}, inset 0 0 12px ${config.glowColor}`,
      }} />

      {/* Key nodes */}
      {nodes.map((node) => (
        <div
          key={`${config.id}-${node.idx}`}
          style={{
            position: 'absolute',
            left: node.x - 10,
            top: node.y - 10,
            width: 20,
            height: 20,
            borderRadius: '50%',
            background: config.nodeBg,
            border: `1.5px solid ${config.color}`,
            opacity: node.opacity,
            boxShadow: `0 0 10px ${config.glowColor}, 0 0 20px ${config.glowColor}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 8,
            color: config.color,
            fontFamily: '"Courier New", monospace',
            transform: `rotate(${-angle * 0.5}deg)`,
            transition: isHistory ? 'opacity 0.3s' : 'none',
          }}
        >
          K
        </div>
      ))}
    </div>
  );
}

function KmsHub() {
  const [pulse, setPulse] = React.useState(0);

  React.useEffect(() => {
    let running = true;
    let t = 0;
    let last = 0;
    const THROTTLE = 100; // ~10fps (Firefox perf fix)
    const anim = (now) => {
      if (!running) return;
      if (now - last >= THROTTLE) {
        last = now;
        t += 0.03 * (THROTTLE / 16.67);
        setPulse(0.5 + 0.5 * Math.sin(t * 2));
      }
      requestAnimationFrame(anim);
    };
    requestAnimationFrame(anim);
    return () => { running = false; };
  }, []);

  return (
    <div style={{
      position: 'absolute',
      top: '50%',
      left: '50%',
      transform: 'translate(-50%, -50%)',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      zIndex: 10,
    }}>
      {/* Glow rings */}
      <div style={{
        width: 40 + pulse * 20,
        height: 40 + pulse * 20,
        borderRadius: '50%',
        background: `radial-gradient(circle, rgba(0,255,255,${0.15 + pulse * 0.2}), transparent)`,
        position: 'absolute',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        transition: 'all 0.05s linear',
      }} />
      <div style={{
        width: 24,
        height: 24,
        borderRadius: '50%',
        background: '#0d1b2a',
        border: '2px solid #00ffff',
        boxShadow: `0 0 ${12 + pulse * 12}px rgba(0,255,255,${0.4 + pulse * 0.3}), 0 0 30px rgba(0,255,255,${0.1 + pulse * 0.1})`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 7,
        color: '#00ffff',
        fontFamily: '"Courier New", monospace',
        fontWeight: 'bold',
        letterSpacing: 0.5,
        zIndex: 1,
      }}>
        KMS
      </div>
    </div>
  );
}

export default function QknVisualization({ qknData = { keys: [], rotations: 0, chainHead: '' } }) {
  const [time, setTime] = React.useState(0);

  React.useEffect(() => {
    let running = true;
    let last = 0;
    const THROTTLE = 100; // ~10fps (Firefox perf fix)
    const anim = (now) => {
      if (!running) return;
      if (now - last >= THROTTLE) {
        last = now;
        setTime((t) => t + 1);
      }
      requestAnimationFrame(anim);
    };
    requestAnimationFrame(anim);
    return () => { running = false; };
  }, []);

  return (
    <div style={{
      width: '100%',
      height: '100%',
      background: 'radial-gradient(circle at center, #0a1628 0%, #050a14 100%)',
      border: '1px solid rgba(0,255,255,0.12)',
      borderRadius: 8,
      overflow: 'hidden',
      position: 'relative',
    }}>
      {/* Title */}
      <div style={{
        position: 'absolute',
        top: 10,
        left: 14,
        color: '#00ffff',
        fontFamily: '"Courier New", monospace',
        fontSize: 11,
        letterSpacing: 1,
        textShadow: '0 0 8px rgba(0,255,255,0.3)',
        zIndex: 20,
      }}>
        🔐 QKN Key Network
      </div>

      {/* Key rings */}
      {RING_CONFIG.map((config) => (
        <KeyRing key={config.id} config={config} time={time} />
      ))}

      {/* Central KMS */}
      <KmsHub />

      {/* Status indicators */}
      <div style={{
        position: 'absolute',
        bottom: 10,
        left: 14,
        right: 14,
        display: 'flex',
        justifyContent: 'space-between',
        zIndex: 20,
      }}>
        {RING_CONFIG.map((config) => (
          <div
            key={config.id}
            style={{
              color: config.color,
              fontFamily: '"Courier New", monospace',
              fontSize: 8,
              opacity: 0.7,
              textShadow: `0 0 6px ${config.glowColor}`,
            }}
          >
            {config.status}
          </div>
        ))}
      </div>

      {/* Key count badges */}
      <div style={{
        position: 'absolute',
        top: 30,
        right: 10,
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
        zIndex: 20,
      }}>
        {RING_CONFIG.map((config) => (
          <div
            key={config.id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              background: 'rgba(0,0,0,0.5)',
              padding: '2px 8px',
              borderRadius: 4,
              border: `1px solid ${config.color}33`,
            }}
          >
            <div style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: config.color,
              boxShadow: `0 0 6px ${config.color}`,
            }} />
            <span style={{
              color: config.color,
              fontFamily: '"Courier New", monospace',
              fontSize: 8,
              opacity: 0.8,
            }}>
              {config.label.split(' ')[0]} {config.keyCount}
            </span>
          </div>
        ))}
      </div>

      {/* Data from props */}
      <div style={{
        position: 'absolute',
        top: 30,
        left: 14,
        color: '#6688aa',
        fontFamily: '"Courier New", monospace',
        fontSize: 8,
        zIndex: 20,
        opacity: 0.6,
      }}>
        Rotations: {qknData.rotations || 0}
      </div>
    </div>
  );
}

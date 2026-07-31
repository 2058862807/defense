import React, { memo, useMemo } from 'react';

const styles = {
  container: {
    position: 'relative',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  svg: {
    transform: 'rotate(-90deg)',
  },
  centerContent: {
    position: 'absolute',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    pointerEvents: 'none',
  },
  scoreText: {
    fontFamily: "'JetBrains Mono', 'Courier New', monospace",
    fontWeight: 'bold',
    lineHeight: 1,
    textShadow: '0 0 20px currentColor, 0 0 40px currentColor',
    transition: 'color 0.4s ease',
  },
  decisionText: {
    fontFamily: "'JetBrains Mono', 'Courier New', monospace",
    fontWeight: 'bold',
    fontSize: '12px',
    letterSpacing: '2px',
    marginTop: '2px',
    textShadow: '0 0 10px currentColor',
    transition: 'color 0.4s ease',
  },
  needle: {
    position: 'absolute',
    bottom: '50%',
    left: '50%',
    transformOrigin: 'bottom center',
    transition: 'transform 0.8s cubic-bezier(0.34, 1.56, 0.64, 1)',
    filter: 'drop-shadow(0 0 6px currentColor)',
    zIndex: 2,
  },
  centerDot: {
    position: 'absolute',
    borderRadius: '50%',
    zIndex: 3,
    boxShadow: '0 0 15px currentColor, 0 0 30px currentColor',
    transition: 'background 0.4s ease, box-shadow 0.4s ease',
  },
  outerGlow: {
    position: 'absolute',
    borderRadius: '50%',
    zIndex: 0,
    transition: 'all 0.6s ease',
  },
};

function getScoreColor(score) {
  if (score <= 44) return '#00ff88';
  if (score <= 69) return '#ffaa00';
  return '#ff3355';
}

function getScoreGradient(score) {
  if (score <= 44) return { start: '#00cc6a', end: '#00ff88' };
  if (score <= 69) return { start: '#ff8800', end: '#ffcc00' };
  return { start: '#ff2244', end: '#ff5577' };
}

function getDecisionColor(decision) {
  switch (decision) {
    case 'PASS': return '#00ff88';
    case 'STEP': return '#ffaa00';
    case 'BLOCK': return '#ff3355';
    default: return '#00ff88';
  }
}

function getSegmentColor(index, totalSegments) {
  const fraction = index / totalSegments;
  if (fraction < 0.45) return '#00ff88';
  if (fraction < 0.70) return '#ffaa00';
  return '#ff3355';
}

function polarToCartesian(cx, cy, r, angleDeg) {
  const angleRad = ((angleDeg - 90) * Math.PI) / 180;
  return {
    x: cx + r * Math.cos(angleRad),
    y: cy + r * Math.sin(angleRad),
  };
}

function describeArc(cx, cy, r, startAngle, endAngle) {
  const start = polarToCartesian(cx, cy, r, endAngle);
  const end = polarToCartesian(cx, cy, r, startAngle);
  const largeArcFlag = endAngle - startAngle > 180 ? 1 : 0;
  return [
    'M', start.x, start.y,
    'A', r, r, 0, largeArcFlag, 0, end.x, end.y,
  ].join(' ');
}

const RiskGauge = ({ score = 0, size = 200, decision = 'PASS' }) => {
  const clampedScore = Math.max(0, Math.min(99, score));
  const center = size / 2;
  const radius = (size - 20) / 2;
  const strokeWidth = Math.max(6, size * 0.045);
  const innerRadius = radius - strokeWidth / 2;

  const scoreColor = getScoreColor(clampedScore);
  const decisionColor = getDecisionColor(decision);
  const gradient = getScoreGradient(clampedScore);

  // Map score (0-99) to angle: start at -205deg, end at 25deg -> total arc = 230deg
  const arcStartAngle = -205;
  const arcEndAngle = 25;
  const arcRange = arcEndAngle - arcStartAngle;
  const needleAngle = arcStartAngle + (clampedScore / 99) * arcRange;

  // Small segments for the rainbow arc
  const segments = useMemo(() => {
    const segs = [];
    const numSegs = 36;
    const segArc = arcRange / numSegs;
    for (let i = 0; i < numSegs; i++) {
      const sa = arcStartAngle + i * segArc;
      const ea = sa + segArc - 0.3;
      segs.push({
        start: sa,
        end: ea,
        color: getSegmentColor(i, numSegs),
      });
    }
    return segs;
  }, []);

  const needleLength = radius * 0.65;
  const glowSize = size + 60;

  // Pulse animation when score changes - use key to re-trigger
  const pulseKey = `pulse-${clampedScore}-${decision}`;

  return (
    <div style={{ ...styles.container, width: size, height: size }} key={pulseKey}>
      {/* Outer glow */}
      <div
        style={{
          ...styles.outerGlow,
          width: glowSize,
          height: glowSize,
          top: (size - glowSize) / 2,
          left: (size - glowSize) / 2,
          background: `radial-gradient(circle, ${scoreColor}22 0%, transparent 70%)`,
          animation: `gaugePulse 2s ease-in-out infinite`,
        }}
      />

      {/* SVG arc */}
      <svg width={size} height={size} style={styles.svg}>
        <defs>
          <linearGradient id={`gaugeGrad-${clampedScore}`} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={gradient.start} />
            <stop offset="100%" stopColor={gradient.end} />
          </linearGradient>
          <filter id={`glow-${clampedScore}`}>
            <feGaussianBlur stdDeviation="2" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Background arc (subtle) */}
        <path
          d={describeArc(center, center, innerRadius, arcStartAngle, arcEndAngle)}
          stroke="rgba(255,255,255,0.05)"
          strokeWidth={strokeWidth}
          fill="none"
          strokeLinecap="round"
        />

        {/* Colored segments */}
        {segments.map((seg, i) => (
          <path
            key={i}
            d={describeArc(center, center, innerRadius, seg.start, seg.end)}
            stroke={seg.color}
            strokeWidth={strokeWidth}
            fill="none"
            strokeLinecap="round"
            style={{
              opacity: 0.3 + (seg.color === '#00ff88' ? 0.3 : seg.color === '#ffaa00' ? 0.2 : 0.1),
              filter: `drop-shadow(0 0 2px ${seg.color})`,
            }}
          />
        ))}

        {/* Active arc up to score */}
        <path
          d={describeArc(center, center, innerRadius, arcStartAngle, arcStartAngle + (clampedScore / 99) * arcRange)}
          stroke={`url(#gaugeGrad-${clampedScore})`}
          strokeWidth={strokeWidth + 2}
          fill="none"
          strokeLinecap="round"
          style={{
            filter: `drop-shadow(0 0 6px ${scoreColor}) drop-shadow(0 0 12px ${scoreColor})`,
            transition: 'all 0.6s ease',
          }}
        />

        {/* Tick marks */}
        {[0, 25, 50, 75, 99].map((val) => {
          const ang = arcStartAngle + (val / 99) * arcRange;
          const innerP = polarToCartesian(center, center, innerRadius - strokeWidth / 2 - 4, ang);
          const outerP = polarToCartesian(center, center, innerRadius + strokeWidth / 2 + 4, ang);
          const tickColor = getScoreColor(val);
          return (
            <line
              key={val}
              x1={innerP.x}
              y1={innerP.y}
              x2={outerP.x}
              y2={outerP.y}
              stroke={tickColor}
              strokeWidth="2"
              style={{
                opacity: 0.6,
                filter: `drop-shadow(0 0 2px ${tickColor})`,
              }}
            />
          );
        })}

        {/* Label arcs for 0, 50, 99 */}
        <text x={center - radius + 8} y={center + 4} fill="rgba(255,255,255,0.25)" fontSize="10" fontFamily="'JetBrains Mono', monospace" transform={`rotate(90, ${center}, ${center})`}>
          0
        </text>
        <text x={center + 4} y={center - radius + 14} fill="rgba(255,255,255,0.25)" fontSize="10" fontFamily="'JetBrains Mono', monospace" textAnchor="middle">
          50
        </text>
        <text x={center + radius - 18} y={center + 4} fill="rgba(255,255,255,0.25)" fontSize="10" fontFamily="'JetBrains Mono', monospace" transform={`rotate(90, ${center}, ${center})`}>
          99
        </text>
      </svg>

      {/* Center dot */}
      <div
        style={{
          ...styles.centerDot,
          width: size * 0.07,
          height: size * 0.07,
          background: scoreColor,
          boxShadow: `0 0 15px ${scoreColor}, 0 0 30px ${scoreColor}`,
        }}
      />

      {/* Center text */}
      <div style={styles.centerContent}>
        <div
          style={{
            ...styles.scoreText,
            fontSize: `${size * 0.18}px`,
            color: scoreColor,
          }}
        >
          {clampedScore}
        </div>
        <div
          style={{
            ...styles.decisionText,
            color: decisionColor,
            fontSize: `${Math.max(10, size * 0.065)}px`,
          }}
        >
          {decision}
        </div>
      </div>

      {/* Inline keyframes */}
      <style>{`
        @keyframes gaugePulse {
          0%, 100% { transform: scale(1); opacity: 0.6; }
          50% { transform: scale(1.05); opacity: 1; }
        }
        @keyframes needlePulse {
          0%, 100% { opacity: 0.8; }
          50% { opacity: 1; }
        }
      `}</style>
    </div>
  );
};

export default memo(RiskGauge);

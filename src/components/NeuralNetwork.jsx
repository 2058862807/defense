import React, { memo, useRef, useEffect, useState, useMemo } from 'react';
import * as d3 from 'd3';
import ConceptPreviewBanner from './ConceptPreviewBanner';

const FEATURE_LABELS = [
  'input_count', 'output_count', 'amount_btc', 'fee_rate',
  'unique_inputs', 'unique_outputs', 'iou_ratio', 'dust_output_count',
  'output_entropy', 'output_value_gini', 'fee_ratio_pct', 'weight_efficiency',
  'value_roundness', 'addr_tx_count_1m', 'addr_tx_count_5m', 'is_seen_address',
];

function NeuralNetwork({ shapValues = {}, riskScore = 0, width = 700, height = 500 }) {
  const svgRef = useRef(null);
  const [particles, setParticles] = useState([]);
  const animRef = useRef(null);

  const edgeData = useMemo(() => {
    const edges = [];
    const centerX = 160;
    const centerY = height / 2;
    const radius = Math.min(centerX - 40, height / 2 - 60);

    for (let i = 0; i < 16; i++) {
      const angle = (i / 16) * 2 * Math.PI - Math.PI / 2;
      const x = centerX + radius * Math.cos(angle);
      const y = centerY + radius * Math.sin(angle);

      const key = FEATURE_LABELS[i];
      const shap = shapValues[key] !== undefined ? shapValues[key] : 0;
      const absShap = Math.abs(shap);
      const width_px = 0.5 + absShap * 3;
      const color = shap >= 0 ? '#00ff88' : '#ff3355';

      edges.push({
        id: i,
        x1: x,
        y1: y,
        x2: width - 80,
        y2: height / 2,
        label: FEATURE_LABELS[i] || `f${i}`,
        shap,
        absShap,
        strokeWidth: Math.min(width_px, 8),
        color,
        featureX: x,
        featureY: y,
      });
    }
    return edges;
  }, [shapValues, width, height]);

  useEffect(() => {
    if (!svgRef.current) return;

    const svg = d3.select(svgRef.current);

    // Clear
    svg.selectAll('*').remove();

    const defs = svg.append('defs');

    // Glow filter
    const filter = defs.append('filter').attr('id', 'neon-glow');
    filter.append('feGaussianBlur').attr('stdDeviation', '2').attr('result', 'blur');
    const merge = filter.append('feMerge');
    merge.append('feMergeNode').attr('in', 'blur');
    merge.append('feMergeNode').attr('in', 'SourceGraphic');

    // Grid background
    svg.append('rect')
      .attr('width', width)
      .attr('height', height)
      .attr('fill', '#0a0e1a');

    // Grid lines
    const gridGroup = svg.append('g').attr('opacity', 0.08);
    for (let x = 0; x < width; x += 40) {
      gridGroup.append('line')
        .attr('x1', x).attr('y1', 0)
        .attr('x2', x).attr('y2', height)
        .attr('stroke', '#00ffff').attr('strokeWidth', 0.5);
    }
    for (let y = 0; y < height; y += 40) {
      gridGroup.append('line')
        .attr('x1', 0).attr('y1', y)
        .attr('x2', width).attr('y2', y)
        .attr('stroke', '#00ffff').attr('strokeWidth', 0.5);
    }

    // Edges
    edgeData.forEach((edge) => {
      const edgeGroup = svg.append('g');

      // Glow line underneath
      edgeGroup.append('line')
        .attr('x1', edge.x1).attr('y1', edge.y1)
        .attr('x2', edge.x2).attr('y2', edge.y2)
        .attr('stroke', edge.color)
        .attr('strokeWidth', edge.strokeWidth + 3)
        .attr('opacity', 0.15)
        .attr('filter', 'url(#neon-glow)');

      // Main line
      edgeGroup.append('line')
        .attr('x1', edge.x1).attr('y1', edge.y1)
        .attr('x2', edge.x2).attr('y2', edge.y2)
        .attr('stroke', edge.color)
        .attr('strokeWidth', edge.strokeWidth)
        .attr('opacity', 0.7);

      // SHAP value label on edge
      const mx = (edge.x1 + edge.x2) / 2;
      const my = (edge.y1 + edge.y2) / 2;
      edgeGroup.append('text')
        .attr('x', mx + 5).attr('y', my - 5)
        .attr('fill', edge.color)
        .attr('fontSize', 8)
        .attr('fontFamily', '"Courier New", monospace')
        .attr('opacity', 0.6)
        .text(edge.shap.toFixed(3));
    });

    // Feature nodes (input layer - circle arrangement)
    edgeData.forEach((edge) => {
      const nodeGroup = svg.append('g');

      // Outer glow ring
      nodeGroup.append('circle')
        .attr('cx', edge.featureX).attr('cy', edge.featureY)
        .attr('r', 16)
        .attr('fill', 'none')
        .attr('stroke', '#00ffff')
        .attr('strokeWidth', 0.5)
        .attr('opacity', 0.3);

      // Node circle
      nodeGroup.append('circle')
        .attr('cx', edge.featureX).attr('cy', edge.featureY)
        .attr('r', 6)
        .attr('fill', '#0d1b2a')
        .attr('stroke', edge.color)
        .attr('strokeWidth', 2)
        .attr('filter', 'url(#neon-glow)');

      // Label
      nodeGroup.append('text')
        .attr('x', edge.featureX).attr('y', edge.featureY + 18)
        .attr('textAnchor', 'middle')
        .attr('fill', '#88bbdd')
        .attr('fontSize', 8)
        .attr('fontFamily', '"Courier New", monospace')
        .attr('opacity', 0.8)
        .text(edge.label);
    });

    // Output node
    const outputX = width - 80;
    const outputY = height / 2;

    // Output glow rings
    for (let r = 20; r <= 40; r += 10) {
      svg.append('circle')
        .attr('cx', outputX).attr('cy', outputY)
        .attr('r', r)
        .attr('fill', 'none')
        .attr('stroke', '#ff6600')
        .attr('strokeWidth', 0.5)
        .attr('opacity', 0.2 + (40 - r) / 100);
    }

    // Output node
    svg.append('circle')
      .attr('cx', outputX).attr('cy', outputY)
      .attr('r', 14)
      .attr('fill', '#1a0d00')
      .attr('stroke', '#ff6600')
      .attr('strokeWidth', 2.5)
      .attr('filter', 'url(#neon-glow)');

    // RISK SCORE label
    svg.append('text')
      .attr('x', outputX).attr('y', outputY - 30)
      .attr('textAnchor', 'middle')
      .attr('fill', '#ff8800')
      .attr('fontSize', 9)
      .attr('fontFamily', '"Courier New", monospace')
      .attr('fontWeight', 'bold')
      .attr('letterSpacing', '1')
      .text('RISK SCORE');

    // Score value
    svg.append('text')
      .attr('x', outputX).attr('y', outputY + 4)
      .attr('textAnchor', 'middle')
      .attr('fill', '#ffaa00')
      .attr('fontSize', 22)
      .attr('fontFamily', '"Courier New", monospace')
      .attr('fontWeight', 'bold')
      .attr('filter', 'url(#neon-glow)')
      .text(Math.round(riskScore));

    svg.append('text')
      .attr('x', outputX).attr('y', outputY + 22)
      .attr('textAnchor', 'middle')
      .attr('fill', '#ff8800')
      .attr('fontSize', 7)
      .attr('fontFamily', '"Courier New", monospace')
      .attr('opacity', 0.6)
      .text('/ 99');
  }, [edgeData, riskScore, width, height]);

  // Particle animation — throttled to ~15fps for Firefox
  useEffect(() => {
    let running = true;
    const particleList = [];
    const INTERVAL = 66; // ~15fps
    let spawnCounter = 0;

    const tick = () => {
      if (!running) return;
      // Spawn roughly same rate as before: 0.08 per frame at 60fps = ~1 per 12.5 frames
      // At 15fps, spawn ~1 per 3 ticks
      for (let s = 0; s < 5; s++) {
        if (Math.random() < 0.08) {
          const edgeIdx = Math.floor(Math.random() * edgeData.length);
          if (!edgeData[edgeIdx]) return;
          const edge = edgeData[edgeIdx];
          particleList.push({
            id: Date.now() + Math.random(),
            edgeId: edge.id,
            x1: edge.x1, y1: edge.y1,
            x2: edge.x2, y2: edge.y2,
            color: edge.color,
            progress: 0,
          });
        }
      }

      for (let i = particleList.length - 1; i >= 0; i--) {
        particleList[i].progress += 0.08; // 4x per tick to match 60fps rate
        if (particleList[i].progress >= 1) {
          particleList.splice(i, 1);
        }
      }

      setParticles([...particleList]);
    };

    const id = setInterval(tick, INTERVAL);
    return () => { running = false; clearInterval(id); };
  }, [edgeData]);

  return (
    <div style={{
      background: '#0a0e1a',
      border: '1px solid rgba(0,255,255,0.15)',
      borderRadius: 8,
      overflow: 'hidden',
      position: 'relative',
    }}>
      <div style={{ padding: '8px' }}>
        <ConceptPreviewBanner label="Neural Inference Topology" />
      </div>
      <div style={{
        padding: '10px 16px',
        borderBottom: '1px solid rgba(0,255,255,0.1)',
        color: '#00ffff',
        fontFamily: '"Courier New", monospace',
        fontSize: 13,
        letterSpacing: 1,
        textShadow: '0 0 8px rgba(0,255,255,0.3)',
      }}>
        🕸️ Neural Inference Topology
      </div>
      <svg ref={svgRef} width={width} height={height} style={{ display: 'block' }}>
        {/* Particles rendered via React overlay below */}
      </svg>
      {/* Particle overlay */}
      <svg
        width={width}
        height={height}
        style={{
          position: 'absolute',
          top: 38,
          left: 0,
          pointerEvents: 'none',
        }}
      >
        {particles.map((p) => {
          const x = p.x1 + (p.x2 - p.x1) * p.progress;
          const y = p.y1 + (p.y2 - p.y1) * p.progress;
          const opacity = 1 - p.progress;
          return (
            <g key={p.id}>
              <circle
                cx={x}
                cy={y}
                r={3}
                fill={p.color}
                opacity={opacity}
              />
              <circle
                cx={x}
                cy={y}
                r={6}
                fill={p.color}
                opacity={opacity * 0.3}
              />
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export default memo(NeuralNetwork);

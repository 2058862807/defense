import React, { memo, useRef, useEffect, useState } from 'react';
import * as d3 from 'd3';

const FEATURES = [
  'input_count',
  'output_count',
  'amount_btc',
  'fee_rate',
  'unique_inputs',
  'unique_outputs',
  'iou_ratio',
  'dust_output_count',
  'output_entropy',
  'output_value_gini',
  'fee_ratio_pct',
  'weight_efficiency',
  'value_roundness',
  'addr_tx_count_1m',
  'addr_tx_count_5m',
  'is_seen_address',
];

const BAR_HEIGHT = 18;
const BAR_GAP = 6;
const LABEL_WIDTH = 160;
const MARGIN = { top: 50, right: 20, bottom: 20, left: LABEL_WIDTH + 10 };

const ShapPanel = ({ shapValues = {}, width = 500, height = 400 }) => {
  const svgRef = useRef(null);
  const [tooltip, setTooltip] = useState(null);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;

    // Clear previous
    d3.select(svg).selectAll('*').remove();

    const chartWidth = width - MARGIN.left - MARGIN.right;
    const chartHeight = height - MARGIN.top - MARGIN.bottom;

    // Build data array
    const data = FEATURES.map((name) => {
      const val = shapValues[name] ?? 0;
      return { name, value: val, absVal: Math.abs(val) };
    });

    const maxAbs = Math.max(...data.map((d) => d.absVal), 0.0001);

    // Scale
    const xScale = d3.scaleLinear().domain([0, maxAbs]).range([0, chartWidth]);

    // Root group
    const g = d3
      .select(svg)
      .attr('width', width)
      .attr('height', height)
      .append('g')
      .attr('transform', `translate(${MARGIN.left},${MARGIN.top})`);

    // Title
    g.append('text')
      .attr('x', chartWidth / 2)
      .attr('y', -20)
      .attr('text-anchor', 'middle')
      .attr('fill', '#00ffff')
      .attr('font-size', '16px')
      .attr('font-weight', 'bold')
      .attr('font-family', "'Courier New', monospace")
      .text('SHAP Feature Attribution');

    // Zero line
    g.append('line')
      .attr('x1', 0)
      .attr('y1', 0)
      .attr('x2', 0)
      .attr('y2', FEATURES.length * (BAR_HEIGHT + BAR_GAP))
      .attr('stroke', '#444')
      .attr('stroke-width', 1)
      .attr('stroke-dasharray', '3,3');

    // Draw bars
    data.forEach((d, i) => {
      const y = i * (BAR_HEIGHT + BAR_GAP);
      const barWidth = xScale(d.absVal);
      const isPos = d.value >= 0;
      const color = isPos ? '#00ff88' : '#ff3355';
      const xPos = isPos ? 0 : -barWidth;

      const barGroup = g
        .append('g')
        .attr('class', 'shap-bar-group')
        .style('cursor', 'pointer');

      // Bar
      barGroup
        .append('rect')
        .attr('x', isPos ? 0 : -barWidth)
        .attr('y', y)
        .attr('width', barWidth)
        .attr('height', BAR_HEIGHT)
        .attr('fill', color)
        .attr('opacity', 0.85)
        .attr('rx', 2)
        .attr('ry', 2);

      // Label
      barGroup
        .append('text')
        .attr('x', -8)
        .attr('y', y + BAR_HEIGHT / 2)
        .attr('text-anchor', 'end')
        .attr('dominant-baseline', 'middle')
        .attr('fill', '#aaa')
        .attr('font-size', '11px')
        .attr('font-family', "'Courier New', monospace")
        .text(d.name);

      // Value text at end of bar
      barGroup
        .append('text')
        .attr('x', isPos ? barWidth + 4 : -barWidth - 4)
        .attr('y', y + BAR_HEIGHT / 2)
        .attr('text-anchor', isPos ? 'start' : 'end')
        .attr('dominant-baseline', 'middle')
        .attr('fill', color)
        .attr('font-size', '10px')
        .attr('font-family', "'Courier New', monospace")
        .text(d.value.toFixed(4));

      // Mouse events for tooltip
      barGroup
        .on('mouseenter', () => {
          setTooltip({
            x: MARGIN.left + (isPos ? barWidth : -barWidth),
            y: MARGIN.top + y,
            feature: d.name,
            value: d.value,
            direction: isPos ? '↑ increases risk' : '↓ decreases risk',
          });
        })
        .on('mouseleave', () => setTooltip(null));
    });
  }, [shapValues, width, height]);

  return (
    <div style={{ position: 'relative', display: 'inline-block' }}>
      <svg ref={svgRef}></svg>
      {tooltip && (
        <div
          style={{
            position: 'absolute',
            left: Math.min(tooltip.x + 10, width - 220),
            top: Math.max(tooltip.y - 30, 0),
            background: 'rgba(10, 10, 30, 0.95)',
            border: '1px solid #00ffff',
            borderRadius: '4px',
            padding: '6px 10px',
            color: '#eee',
            fontFamily: "'Courier New', monospace",
            fontSize: '11px',
            pointerEvents: 'none',
            zIndex: 100,
            whiteSpace: 'nowrap',
            boxShadow: '0 0 12px rgba(0, 255, 255, 0.3)',
          }}
        >
          <div style={{ color: '#00ffff', fontWeight: 'bold', marginBottom: 2 }}>
            {tooltip.feature}
          </div>
          <div>
            Value: <span style={{ color: tooltip.value >= 0 ? '#00ff88' : '#ff3355' }}>
              {tooltip.value.toFixed(4)}
            </span>
          </div>
          <div style={{ color: tooltip.value >= 0 ? '#00ff88' : '#ff3355', fontSize: '10px' }}>
            {tooltip.direction}
          </div>
        </div>
      )}
    </div>
  );
};

export default memo(ShapPanel);

import React from 'react';

/**
 * Unmissable banner marking a view as illustrative, not live telemetry.
 * Always rendered - never gated behind a prop that could hide it - because
 * the point is that nobody in a demo/screen-share can mistake this panel
 * for real data.
 */
export default function ConceptPreviewBanner({ label = 'Concept Preview' }) {
  return (
    <div
      role="alert"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        padding: '10px 16px',
        background: 'repeating-linear-gradient(45deg, #7a1f00, #7a1f00 10px, #5c1700 10px, #5c1700 20px)',
        border: '2px solid #ff8a00',
        borderRadius: '8px',
        color: '#ffe8cc',
        fontFamily: 'var(--font-mono, monospace)',
        fontSize: '12px',
        fontWeight: 700,
        letterSpacing: '0.5px',
        textTransform: 'uppercase',
      }}
    >
      <span style={{ fontSize: '16px' }}>⚠️</span>
      <span>{label} — illustrative UI, not live data. Not part of the built/deployed product.</span>
    </div>
  );
}

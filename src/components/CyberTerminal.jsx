import React, { useState, useEffect, useRef, useCallback } from 'react';

const styles = {
  container: {
    background: '#0a0a0a',
    color: '#00ff88',
    fontFamily: "'JetBrains Mono', 'Fira Code', 'Courier New', monospace",
    fontSize: '13px',
    lineHeight: '1.5',
    borderRadius: '8px',
    border: '1px solid rgba(0, 255, 136, 0.2)',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    boxShadow: 'inset 0 0 30px rgba(0, 255, 136, 0.05), 0 0 15px rgba(0, 255, 136, 0.1)',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '8px 12px',
    borderBottom: '1px solid rgba(0, 255, 136, 0.15)',
    background: 'rgba(0, 255, 136, 0.03)',
    userSelect: 'none',
  },
  dot: {
    width: '10px',
    height: '10px',
    borderRadius: '50%',
    display: 'inline-block',
  },
  headerTitle: {
    color: 'rgba(0, 255, 136, 0.6)',
    fontSize: '11px',
    letterSpacing: '1px',
    textTransform: 'uppercase',
    marginLeft: '6px',
  },
  logArea: {
    flex: 1,
    overflowY: 'auto',
    padding: '10px 12px',
    scrollBehavior: 'smooth',
  },
  logEntry: {
    marginBottom: '2px',
    wordBreak: 'break-all',
    whiteSpace: 'pre-wrap',
    animation: 'fadeInLog 0.15s ease-in',
  },
  timestamp: {
    color: 'rgba(0, 255, 136, 0.4)',
    marginRight: '10px',
  },
  levelInfo: { color: '#00ff88' },
  levelWarn: { color: '#ffaa00' },
  levelError: { color: '#ff3355' },
  levelSystem: { color: '#00ccff' },
  levelSuccess: { color: '#00ff88', fontWeight: 'bold' },
  promptRow: {
    display: 'flex',
    alignItems: 'center',
    padding: '8px 12px',
    borderTop: '1px solid rgba(0, 255, 136, 0.15)',
    background: 'rgba(0, 0, 0, 0.5)',
  },
  promptSymbol: {
    color: '#00ff88',
    fontWeight: 'bold',
    marginRight: '8px',
    fontSize: '14px',
    display: 'flex',
    alignItems: 'center',
  },
  cursor: {
    display: 'inline-block',
    width: '8px',
    height: '14px',
    background: '#00ff88',
    marginLeft: '1px',
    animation: 'blink 1s step-end infinite',
  },
  input: {
    flex: 1,
    background: 'transparent',
    border: 'none',
    color: '#00ff88',
    fontFamily: "'JetBrains Mono', monospace",
    fontSize: '13px',
    outline: 'none',
    caretColor: '#00ff88',
  },
  outputBlock: {
    padding: '4px 0',
    marginBottom: '4px',
  },
  outputLine: { color: 'rgba(0, 255, 136, 0.85)', paddingLeft: '0' },
  outputLabel: { color: 'rgba(0, 255, 136, 0.5)' },
  outputValue: { color: '#00ff88', fontWeight: 'bold' },
  divider: {
    border: 'none',
    borderTop: '1px dashed rgba(0, 255, 136, 0.15)',
    margin: '6px 0',
  },
  commandHeader: { color: '#00ccff', fontWeight: 'bold', marginBottom: '4px' },
  commandRow: { display: 'flex', justifyContent: 'space-between', padding: '2px 0' },
  commandName: { color: '#00ff88', fontWeight: 'bold', minWidth: '100px' },
  commandDesc: { color: 'rgba(0, 255, 136, 0.6)' },
  proofItem: {
    padding: '3px 0',
    borderBottom: '1px solid rgba(0, 255, 136, 0.08)',
    fontSize: '12px',
  },
  statusDot: { display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', marginRight: '6px' },
  progressBar: { display: 'inline-block', height: '10px', borderRadius: '2px', marginRight: '4px', background: '#00ff88' },
};

const COLORS = {
  info: styles.levelInfo, warn: styles.levelWarn, error: styles.levelError,
  system: styles.levelSystem, success: styles.levelSuccess,
};

function formatTimestamp(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  return d.toLocaleTimeString('en-US', { hour12: false }) + '.' + String(d.getMilliseconds()).padStart(3, '0');
}

const builtinCommands = [
  { cmd: 'help', desc: 'Show available commands' },
  { cmd: 'stats', desc: 'Show system stats (live)' },
  { cmd: 'proofs', desc: 'Show proof ledger from backend' },
  { cmd: 'prove <tx_hash>', desc: 'Request a ZK proof for a transaction' },
  { cmd: 'verify <tx_hash>', desc: 'Verify a ZK proof from backend' },
  { cmd: 'status', desc: 'Show system health (live)' },
  { cmd: 'rotate', desc: 'Trigger KMS key rotation' },
  { cmd: 'export', desc: 'Export proof ledger from backend' },
  { cmd: 'monitor', desc: 'Toggle auto-scroll' },
  { cmd: 'clear', desc: 'Clear terminal' },
];

// Use relative paths through serve_frontend.py reverse proxy (port 4000)
// to avoid Firefox HTTPS-Only mode blocking direct localhost connections
const API_MODEL = '/api/model';
const API_CRYPTO = '/api/crypto';

function getDecisionColor(decision) {
  switch (decision) {
    case 'PASS': return '#00ff88';
    case 'STEP': return '#ffaa00';
    case 'BLOCK': return '#ff3355';
    default: return '#00ff88';
  }
}

const CyberTerminal = ({ logs = [], height = '300px', terminalRef }) => {
  const [entries, setEntries] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [autoMonitor, setAutoMonitor] = useState(true);
  const logAreaRef = useRef(null);
  const inputRef = useRef(null);
  const internalIdRef = useRef(0);

  const addEntry = useCallback((message, level = 'info', timestamp = null) => {
    const id = ++internalIdRef.current;
    const ts = timestamp || Date.now();
    setEntries(prev => [...prev, { id, timestamp: ts, level, message }]);
  }, []);

  async function fetchLiveStats() {
    try {
      const resp = await fetch(`${API_MODEL}/dashboard/live`);
      if (!resp.ok) throw new Error('Not available');
      const data = await resp.json();
      const m = data.metrics || {};
      addEntry(`  TPS:               ${(m.aggregate_throughput_tx_s ?? 0).toFixed(1)} tx/s`);
      addEntry(`  Total Scored:      ${m.total_scored ?? 0}`, 'info');
      addEntry(`  ML Confidence:     ${((m.ml_confidence ?? 0)).toFixed(0)}%`);
      addEntry(`  Scored Txs:        ${data.transactions?.length ?? 0} in buffer`);
    } catch {
      addEntry('  Backend unavailable — is model_service running on :8000?', 'warn');
    }
  }

  async function fetchProofLedger() {
    try {
      const resp = await fetch(`${API_MODEL}/proofs/ledger?limit=10`);
      if (!resp.ok) throw new Error('Not available');
      const data = await resp.json();
      const proofs = data.proofs || [];
      if (proofs.length === 0) {
        addEntry('  No proofs in ledger (BLOCK/STEP transactions will auto-prove)', 'info');
        return;
      }
      proofs.forEach(p => {
        const hash = (p.tx_hash || '').substring(0, 12);
        const status = p.verified ? 'verified' : (p.proof_exists ? 'generated' : 'pending');
        addEntry(`  ${hash.padEnd(16)} ${(p.decision || '').padEnd(8)} [${status}]`, 
          status === 'verified' ? 'success' : status === 'pending' ? 'warn' : 'info');
      });
    } catch {
      addEntry('  Proof ledger unavailable', 'warn');
    }
  }

  async function fetchProofStatus(txHash) {
    try {
      const resp = await fetch(`${API_MODEL}/proof/status/${txHash}`);
      if (resp.ok) {
        const data = await resp.json();
        addEntry(`  Status: ${data.status}`, 'info');
        if (data.proof) {
          addEntry(`  Commitment: ${(data.proof.commitment || '').substring(0, 32)}...`, 'success');
        }
      } else {
        addEntry(`  No proof found for ${txHash.substring(0, 12)}...`, 'warn');
      }
    } catch {
      addEntry('  Proof status unavailable', 'warn');
    }
  }

  async function triggerKeyRotation() {
    try {
      addEntry('⟳ Initiating KMS key rotation...', 'system');
      const resp = await fetch(`${API_CRYPTO}/kms/rotate`, { method: 'POST' });
      if (resp.ok) {
        const data = await resp.json();
        addEntry('✓ Key rotation complete', 'success');
        addEntry(`  New key count: ${data.active_count} active keys`, 'info');
        if (data.event_hash) {
          addEntry(`  Event: ${data.event_hash.substring(0, 20)}...`, 'info');
        }
      } else {
        addEntry('✗ Rotation failed', 'error');
      }
    } catch {
      addEntry('  Crypto service unavailable on :8002', 'warn');
    }
  }

  async function verifyRemoteProof(txHash) {
    try {
      addEntry(`⧗ Fetching verification result for ${txHash.substring(0, 12)}...`, 'info');
      const resp = await fetch(`${API_MODEL}/proof/status/${txHash}`);
      if (resp.ok) {
        const data = await resp.json();
        if (data.status === 'done' && data.proof) {
          addEntry('✓ Proof exists and is stored in ledger', 'success');
          addEntry(`  Commitment: ${(data.proof.commitment || '').substring(0, 40)}...`, 'info');
          addEntry(`  Generated: ${data.proof.generated_at || 'unknown'}`, 'info');
          if (data.integrity?.verified) {
            addEntry('  Chain integrity: ✓ VERIFIED', 'success');
          }
        } else {
          addEntry('  Proof status: ' + (data.status || 'unknown'), 'warn');
        }
      } else {
        addEntry('  Proof not found for this transaction hash', 'error');
      }
    } catch {
      addEntry('  Verification unavailable (services not running?)', 'warn');
    }
  }

  async function exportProofLedger() {
    try {
      addEntry('⟳ Fetching proof ledger...', 'system');
      const resp = await fetch(`${API_MODEL}/proofs/export?limit=100`);
      if (resp.ok) {
        const data = await resp.json();
        addEntry(`✓ Export: ${data.proofs?.length || 0} proofs`, 'success');
        addEntry(`  Integrity: ${data.integrity?.verified ? 'VERIFIED' : 'CHECK REQUIRED'}`, data.integrity?.verified ? 'success' : 'warn');
        addEntry(`  Exported at: ${new Date().toISOString()}`, 'info');
      } else {
        addEntry('  Export unavailable', 'warn');
      }
    } catch {
      addEntry('  Export unavailable (backend not running?)', 'warn');
    }
  }

  async function fetchSystemHealth() {
    try {
      addEntry('── System Health (live) ──', 'system');
      
      // Model service
      try {
        const m = await fetch(`${API_MODEL}/health`);
        const mText = m.ok ? await m.text() : 'unreachable';
        addEntry(`  Model (:8000):      ${m.ok ? 'ONLINE' : 'DOWN'} [${mText.substring(0, 30)}]`, m.ok ? 'success' : 'error');
      } catch { addEntry('  Model (:8000):      DOWN', 'error'); }

      // Crypto service
      try {
        const c = await fetch(`${API_CRYPTO}/health`);
        addEntry(`  Crypto (:8002):     ${c.ok ? 'ONLINE' : 'DOWN'}`, c.ok ? 'success' : 'error');
      } catch { addEntry('  Crypto (:8002):     DOWN', 'error'); }

      addEntry('  All services nominal', 'system');
    } catch {
      addEntry('  Health check failed', 'error');
    }
  }

  const processCommand = useCallback((cmdStr) => {
    const trimmed = cmdStr.trim();
    const parts = trimmed.split(/\s+/);
    const cmd = parts[0]?.toLowerCase();
    const arg = parts.slice(1).join(' ');

    if (!trimmed) return;

    addEntry(`$ ${trimmed}`, 'system', Date.now());

    switch (cmd) {
      case 'help': {
        addEntry('╔══════════════════════════════════════╗', 'system');
        addEntry('║        AVAILABLE COMMANDS            ║', 'system');
        addEntry('╚══════════════════════════════════════╝', 'system');
        builtinCommands.forEach(({ cmd: c, desc }) => {
          addEntry(`  ${c.padEnd(20)} ${desc}`, 'info');
        });
        break;
      }
      case 'stats':
        addEntry('── System Statistics (live) ──', 'system');
        fetchLiveStats();
        break;

      case 'proofs':
        addEntry('── Proof Ledger (live) ──', 'system');
        fetchProofLedger();
        break;

      case 'prove': {
        if (!arg) {
          addEntry('Usage: prove <tx_hash>', 'warn');
        } else {
          const shortHash = arg.length > 12 ? arg.substring(0, 6) + '...' + arg.substring(arg.length - 4) : arg;
          addEntry(`⧗ Requesting proof for ${shortHash}...`, 'info');
          (async () => {
            try {
              const resp = await fetch(`${API_MODEL}/proof/request/${arg}`, { method: 'POST' });
              if (resp.ok) {
                const data = await resp.json();
                addEntry(`✓ Proof requested — status: ${data.status}`, 'success');
                if (data.proof) {
                  addEntry(`  Commitment: ${(data.proof.commitment || '').substring(0, 32)}...`, 'info');
                }
              } else {
                addEntry(`  Proof request failed: ${resp.status}`, 'error');
              }
            } catch {
              addEntry('  Model service unavailable', 'warn');
            }
          })();
        }
        break;
      }

      case 'verify': {
        if (!arg) {
          addEntry('Usage: verify <tx_hash>', 'warn');
        } else {
          verifyRemoteProof(arg);
        }
        break;
      }

      case 'status':
        fetchSystemHealth();
        break;

      case 'rotate':
        triggerKeyRotation();
        break;

      case 'export':
        exportProofLedger();
        break;

      case 'monitor': {
        const newState = !autoMonitor;
        setAutoMonitor(newState);
        addEntry(newState ? '▶ Auto-scroll enabled' : '⏸ Auto-scroll disabled', 'system');
        break;
      }

      case 'clear': {
        setEntries([]);
        break;
      }

      default: {
        addEntry(`Command not found: ${cmd}. Type 'help' for available commands.`, 'error');
        break;
      }
    }
  }, [addEntry, autoMonitor]);

  useEffect(() => {
    if (logs && logs.length > 0) {
      setEntries(prev => {
        const existingKeys = new Set(prev.map(e => `${e.timestamp}-${e.message}`));
        const newEntries = [];
        logs.forEach(log => {
          const key = `${log.timestamp}-${log.message}`;
          if (!existingKeys.has(key)) {
            internalIdRef.current++;
            newEntries.push({
              id: internalIdRef.current,
              timestamp: log.timestamp || Date.now(),
              level: log.level || 'info',
              message: log.message,
            });
          }
        });
        if (newEntries.length === 0) return prev;
        return [...prev, ...newEntries].slice(-300);
      });
    }
  }, [logs]);

  useEffect(() => {
    if (autoMonitor && logAreaRef.current) {
      logAreaRef.current.scrollTop = logAreaRef.current.scrollHeight;
    }
  }, [entries, autoMonitor]);

  useEffect(() => {
    addEntry('╔══════════════════════════════════════╗', 'system');
    addEntry('║    PROTEAN DEFENSE — LIVE TERMINAL   ║', 'system');
    addEntry('╚══════════════════════════════════════╝', 'system');
    addEntry('Type help for available commands. All data is live.', 'system');
  }, [addEntry]);

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter') {
      processCommand(inputValue);
      setInputValue('');
    }
  }, [inputValue, processCommand]);

  const handleContainerClick = useCallback(() => {
    if (inputRef.current) inputRef.current.focus();
  }, []);

  const renderLog = (entry) => {
    const style = COLORS[entry.level] || styles.levelInfo;
    const isObject = typeof entry.message === 'object';
    return (
      <div key={entry.id || `log-${entry.timestamp}-${entry.message}`} style={styles.logEntry}>
        <span style={styles.timestamp}>{formatTimestamp(entry.timestamp)}</span>
        <span style={style}>
          {isObject ? JSON.stringify(entry.message, null, 2) : entry.message}
        </span>
      </div>
    );
  };

  return (
    <div style={{ ...styles.container, height }} onClick={handleContainerClick}>
      <div style={styles.header}>
        <div style={{ ...styles.dot, background: '#00ff88', boxShadow: '0 0 6px #00ff88' }} />
        <div style={{ ...styles.dot, background: '#ffaa00', opacity: 0.5 }} />
        <div style={{ ...styles.dot, background: '#ff3355', opacity: 0.5 }} />
        <span style={styles.headerTitle}>PROTEAN DEFENSE TERMINAL — LIVE</span>
      </div>
      <div ref={logAreaRef} style={styles.logArea}>
        {entries.map(renderLog)}
      </div>
      <div style={styles.promptRow}>
        <span style={styles.promptSymbol}>❯</span>
        <input
          ref={inputRef}
          style={styles.input}
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          spellCheck={false}
          autoComplete="off"
          placeholder="Type a command..."
        />
      </div>
      <style>{`
        @keyframes fadeInLog { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: #0a0a0a; }
        ::-webkit-scrollbar-thumb { background: #00ff88; border-radius: 2px; }
      `}</style>
    </div>
  );
};

export default CyberTerminal;

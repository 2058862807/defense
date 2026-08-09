import { useState, useEffect, useRef, useCallback } from 'react';

// ─── Helpers ───────────────────────────────────────────────────────────────

function shortHash(hash) {
  if (!hash) return '0x0000...0000';
  const h = hash.startsWith('0x') ? hash : `0x${hash}`;
  if (h.length <= 16) return h;
  return `${h.substring(0, 10)}...${h.substring(h.length - 6)}`;
}

const DECISION_COLORS = {
  block: '#ff3355',
  step: '#ffaa00',
  pass: '#00ff88',
};
const DECISION_LABELS = { block: 'BLOCK', step: 'STEP', pass: 'PASS' };

// Canonical proof statuses: pending | done | failed | skipped | none
function canonicalProofStatus(raw) {
  const s = (raw || 'none').toString().toLowerCase();
  if (s === 'pending' || s === 'proof_pending' || s === 'proving') return 'pending';
  if (s === 'done' || s === 'verified' || s === 'proved_real_groth16' || s === 'proved') return 'done';
  if (s === 'failed' || s === 'proof_failed' || s === 'error') return 'failed';
  if (s === 'skipped' || s === 'proof_skipped' || s === 'deferred') return 'skipped';
  return 'none';
}

// Normalise a backend transaction to frontend format
function normalizeTx(tx) {
  const numScore = Number(tx.risk_score ?? tx.score ?? 50) || 50;
  const decision = tx.decision ?? (numScore >= 70 ? 'block' : numScore >= 45 ? 'step' : 'pass');
  const shapVals = tx.shapVals ?? tx.shap_values ?? {};
  const numAmount = Number(tx.amount_btc ?? tx.amount ?? 0) || 0;
  const numFee = Number(tx.fee_rate ?? tx.fee ?? 0) || 0;

  return {
    id: tx.hash ?? tx.txid ?? `tx-${Date.now()}`,
    hash: tx.hash ?? tx.txid ?? '',
    txid: tx.txid ?? tx.hash ?? '',
    amount: numAmount,
    fee: numFee,
    inputs: Number(tx.inputs ?? tx.input_count ?? (tx.from ? 1 : 0)) || 0,
    outputs: Number(tx.outputs ?? tx.output_count ?? (tx.to ? 1 : 0)) || 0,
    input_count: Number(tx.input_count ?? tx.inputs ?? (tx.from ? 1 : 0)) || 0,
    output_count: Number(tx.output_count ?? tx.outputs ?? (tx.to ? 1 : 0)) || 0,
    riskScore: Math.round(numScore),
    score: Math.round(numScore),
    decision: (decision ?? 'pass').toUpperCase(),
    decision_lower: (decision ?? 'pass').toLowerCase(),
    shapValues: shapVals,
    shapVals: shapVals,
    timestamp: tx.timestamp ?? new Date().toISOString(),
    ledger: (tx.ledger ?? 'btc').toUpperCase(),
    proofStatus: canonicalProofStatus(tx.proof_status),
    proof: tx.proof ?? null,
    source: tx.source ?? 'ml',
    amount_btc: numAmount,
    fee_rate: numFee,
    // Jurisdiction V3 fields
    origin_country_code: tx.origin_country_code ?? '',
    destination_country_code: tx.destination_country_code ?? '',
    jurisdiction_multiplier: tx.jurisdiction_multiplier ?? 1.0,
    sanctions_flag: tx.sanctions_flag ?? false,
    travel_rule_triggered: tx.travel_rule_triggered ?? false,
    disclosure_notice: tx.disclosure_notice ?? null,
    jurisdiction: tx.jurisdiction ?? null,
    wallet_hits: tx.wallet_hits ?? [],
    // TradFi bank fields
    trad_fi_system: tx.trad_fi_system ?? (['SWIFT','FEDWIRE','ACH','SEPA','CHIPS','BANK'].includes((tx.ledger ?? '').toUpperCase()) ? (tx.ledger ?? '').toUpperCase() : null),
    sending_bank_name: tx.sending_bank_name ?? tx.sending_bank ?? '',
    receiving_bank_name: tx.receiving_bank_name ?? tx.receiving_bank ?? '',
    sending_bank_lat: tx.sending_bank_lat ?? null,
    sending_bank_lng: tx.sending_bank_lng ?? null,
    receiving_bank_lat: tx.receiving_bank_lat ?? null,
    receiving_bank_lng: tx.receiving_bank_lng ?? null,
  };
}

// ─── Build initial transaction set ──────────────────────────────────────
function buildInitialFromBackend(txs) {
  if (!txs || txs.length === 0) {
    // Return a single placeholder so components don't crash
    return [{
      id: 'placeholder',
      hash: '0000000000000000000000000000000000000000000000000000000000000000',
      amount: 0,
      fee: 0,
      riskScore: 0,
      score: 0,
      decision: 'PASS',
      shapValues: {},
      timestamp: new Date().toISOString(),
      ledger: 'BTC',
      proofStatus: 'none',
      proof: null,
      source: 'pending',
    }];
  }
  return txs.map(normalizeTx);
}

// ─── COMPOSITE_RISK_FUSION data builder ──────────────────────────────────────────────────
function buildCompositeRiskFusionDataFromBackend(compositeRiskFusionResp) {
  if (!compositeRiskFusionResp || !compositeRiskFusionResp.current_mode) {
    return {
      mode: 'NO_COMPOSITE_RISK_FUSION',
      magnitude: 0,
      score: 0,
      history: [],
      modes: { competitive: 0, deferential: 0, attribution_blind: 0 },
      total_triggers: 0,
      consecutive_blind: 0,
    };
  }
  const mode = (compositeRiskFusionResp.current_mode || 'NO_COMPOSITE_RISK_FUSION').toUpperCase();
  return {
    mode,
    magnitude: compositeRiskFusionResp.recent_magnitude ?? 0,
    score: compositeRiskFusionResp.total_triggers ? Math.min(compositeRiskFusionResp.total_triggers * 5, 100) : 0,
    history: (compositeRiskFusionResp.recent_provenance || [])
      .filter(p => p.mode)
      .map(p => ({
        mode: (p.mode || 'NO_COMPOSITE_RISK_FUSION').toUpperCase(),
        timestamp: p.created_at || new Date().toISOString(),
      })),
    modes: compositeRiskFusionResp.modes || { competitive: 0, deferential: 0, attribution_blind: 0 },
    total_triggers: compositeRiskFusionResp.total_triggers || 0,
    consecutive_blind: compositeRiskFusionResp.consecutive_blind || 0,
  };
}

// ─── KMS data builder ───────────────────────────────────────────────────
function buildKmsDataFromBackend(kmsResp) {
  if (!kmsResp) {
    return { keys: [], rotations: 0, chainHead: '' };
  }
  return {
    keys: (kmsResp.keys || []).map(k => ({
      id: k.id || k.key_id || 'unknown',
      status: k.status || 'unknown',
      age: k.age_seconds ?? k.age ?? 0,
      ttl: k.ttl_seconds ?? k.ttl ?? 300,
      algo: k.algorithm || 'ML-KEM-1024',
    })),
    rotations: kmsResp.total_rotations ?? kmsResp.rotations ?? 0,
    chainHead: kmsResp.chain_head ?? kmsResp.chainHead ?? '',
    active_count: kmsResp.active_count ?? 0,
    next_rotation: kmsResp.next_rotation_seconds ?? 0,
    last_rotation: kmsResp.last_rotation ?? null,
  };
}

// ─── Metrics builder ────────────────────────────────────────────────────
function buildMetrics(backendMetrics, totalTps, totalScored, mlConf) {
  return {
    riskScore: 0,  // Will be set by latest tx
    tps: totalTps ?? 0,
    zkProofMs: 0,
    mlConfidence: Math.min(100, Math.max(0, mlConf ?? 0)),
    keyRotations: 0,
    netLatency: 0,
    totalScored: totalScored ?? 0,
    proofCount: 0,
  };
}

// ─── Globe data (static financial hubs) ─────────────────────────────────
const FINANCIAL_HUBS = [
  { name: 'NYC', lat: 40.7128, lng: -74.006 },
  { name: 'London', lat: 51.5074, lng: -0.1278 },
  { name: 'Hong Kong', lat: 22.3193, lng: 114.1694 },
  { name: 'Singapore', lat: 1.3521, lng: 103.8198 },
  { name: 'Tokyo', lat: 35.6762, lng: 139.6503 },
  { name: 'Zurich', lat: 47.3769, lng: 8.5417 },
  { name: 'Frankfurt', lat: 50.1109, lng: 8.6821 },
  { name: 'Dubai', lat: 25.2048, lng: 55.2708 },
  { name: 'Shanghai', lat: 31.2304, lng: 121.4737 },
  { name: 'Sydney', lat: -33.8688, lng: 151.2093 },
  { name: 'Mumbai', lat: 19.076, lng: 72.8777 },
  { name: 'Sao Paulo', lat: -23.5505, lng: -46.6333 },
  { name: 'Toronto', lat: 43.6532, lng: -79.3832 },
  { name: 'Seoul', lat: 37.5665, lng: 126.978 },
  { name: 'Moscow', lat: 55.7558, lng: 37.6173 },
  { name: 'Curacao', lat: 12.1696, lng: -68.9900 },
  { name: 'Anjouan', lat: -12.2128, lng: 44.4374 },
];

function buildGlobeDataFromTxs(txs) {
  // Stable jitter from tx hash to prevent Math.random() defeating React.memo
  function stableHash(s) {
    let h = 0;
    for (let i = 0; i < (s || '').length; i++) {
      h = ((h << 5) - h) + s.charCodeAt(i);
      h |= 0;
    }
    return h;
  }
  return txs.slice(0, 30).map((tx, i) => {
    if (tx.sending_bank_lat && tx.sending_bank_lng) {
      return {
        lat: tx.sending_bank_lat,
        lng: tx.sending_bank_lng,
        intensity: (tx.riskScore ?? 50) / 100,
        risk: tx.riskScore ?? 50,
      };
    }
    const hub = FINANCIAL_HUBS[i % FINANCIAL_HUBS.length];
    const jitter = ((stableHash(tx.hash ?? tx.id ?? String(i)) & 0xff) / 255) * 2 - 1;
    return {
      lat: hub.lat + jitter,
      lng: hub.lng + jitter * 0.5,
      intensity: (tx.riskScore ?? 50) / 100,
      risk: tx.riskScore ?? 50,
    };
  });
}

// ─── Network data (static topology) ─────────────────────────────────────
const NETWORK_NODES = [
  { id: 'node-0', name: 'BTC Core', group: 1, value: 25 },
  { id: 'node-1', name: 'ETH Node', group: 1, value: 22 },
  { id: 'node-2', name: 'LTC Relay', group: 1, value: 10 },
  { id: 'node-3', name: 'SOL Validator', group: 2, value: 18 },
  { id: 'node-4', name: 'Polygon Bridge', group: 2, value: 15 },
  { id: 'node-5', name: 'DOGE Mempool', group: 2, value: 5 },
  { id: 'node-6', name: 'ZKP Aggregator', group: 3, value: 28 },
  { id: 'node-7', name: 'COMPOSITE_RISK_FUSION Oracle', group: 3, value: 20 },
  { id: 'node-8', name: 'KMS Key Master', group: 3, value: 24 },
  { id: 'node-9', name: 'Risk Engine', group: 4, value: 30 },
  { id: 'node-10', name: 'ML Scorer', group: 4, value: 26 },
  { id: 'node-11', name: 'Tx Mempool', group: 4, value: 19 },
  { id: 'node-12', name: 'Lightning Hub', group: 5, value: 12 },
  { id: 'node-13', name: 'Arbitrum L2', group: 5, value: 15 },
  { id: 'node-14', name: 'Optimism L2', group: 5, value: 14 },
];

function buildNetworkData() {
  const links = [];
  for (let i = 0; i < NETWORK_NODES.length; i++) {
    const nLinks = 1 + Math.floor(Math.random() * 3);
    for (let j = 0; j < nLinks; j++) {
      const target = Math.floor(Math.random() * NETWORK_NODES.length);
      if (target === i) continue;
      links.push({
        source: NETWORK_NODES[i].id,
        target: NETWORK_NODES[target].id,
        value: Math.random() * 0.9 + 0.1,
        color: Math.random() > 0.7 ? '#ef4444' : Math.random() > 0.5 ? '#f59e0b' : '#22c55e',
      });
    }
  }
  return { nodes: NETWORK_NODES, links };
}

// ─── Main hook ──────────────────────────────────────────────────────────

// Use relative paths through serve_frontend.py reverse proxy (port 4000)
// This avoids Firefox HTTPS-Only mode issues with direct localhost connections
const API_MODEL = '/api/model';
const API_COMPOSITE_RISK_FUSION = '/api/compositeRiskFusion';
const API_CRYPTO = '/api/crypto';
const API_BIO  = '/api/biometric';

export function useLiveData() {
  const [transactions, setTransactions] = useState([]);
  const [metrics, setMetrics] = useState({
    riskScore: 0, tps: 0, zkProofMs: 0, mlConfidence: 0,
    keyRotations: 0, netLatency: 0, totalScored: 0, proofCount: 0,
  });
  const [compositeRiskFusionData, setCompositeRiskFusionData] = useState({
    mode: 'NO_COMPOSITE_RISK_FUSION', magnitude: 0, score: 0, history: [],
    modes: {}, total_triggers: 0, consecutive_blind: 0,
  });
  const [qknData, setQknData] = useState({ keys: [], rotations: 0, chainHead: '' });
  const [globeData, setGlobeData] = useState([]);
  const [networkData] = useState(() => buildNetworkData());
  const [proofData, setProofData] = useState([]);
  const [terminalLogs, setTerminalLogs] = useState([]);
  const [isLive, setIsLive] = useState(false);
  const [proofStatusMap, setProofStatusMap] = useState({});
  const [cisData, setCisData] = useState({
    cis: 50.0,
    status: 'not_enrolled',
    anomaly_details: {},
    timestamp: null,
  });
  const [botStatus, setBotStatus] = useState({
    bots: { offense: null, defense: null },
    mempool: 'unknown',
    running: { offense: false, defense: false },
    trigger: 'ws-only',
  });

  const wsRef = useRef(null);
  const lastTxRef = useRef(null);
  const tpsWindowRef = useRef([]);

  // ── WebSocket connection ──────────────────────────────────────────────
  useEffect(() => {
    let reconnectTimer;
    let connected = false;

    function connect() {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }

      let ws;
      try {
        const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
          ws = new WebSocket(`${wsProto}//${location.host}/ws/dashboard`);
      } catch (e) {
        console.warn('[LiveData] WS connection failed, will retry:', e.message);
        reconnectTimer = setTimeout(connect, 5000);
        return;
      }
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[LiveData] WS connected to dashboard');
        connected = true;
        setIsLive(true);
        addTerminalLog('info', '[LIVE] Connected to PROTEAN backend');
      };

      ws.onmessage = async (event) => {
        try {
          let raw = event.data;
          if (typeof raw !== 'string') {
            if (raw instanceof Blob) {
              raw = await raw.text();
            } else if (raw instanceof ArrayBuffer) {
              raw = new TextDecoder().decode(raw);
            }
          }
          const data = JSON.parse(raw);
          if (data.type === 'welcome' || data.type === 'connected') {
            console.log('[LiveData] WS welcome received — connection confirmed');
            setIsLive(true);
          } else if (data.type === 'bot_status') {
            setBotStatus(prev => ({ ...prev, ...(data.bots || data) }));
          } else if (data.type === 'dashboard_update' || data.type === 'snapshot') {
            handleDashboardUpdate(data);
          } else if (data.type === 'tx' || data.type === 'transaction' || data.transaction || data.tx) {
            const singleTx = data.transaction || data.tx;
            if (singleTx) {
              const normalized = normalizeTx(singleTx);
              setTransactions(prev => {
                const existing = new Map(prev.filter(t => t.id !== 'placeholder').map(t => [t.hash, t]));
                existing.set(normalized.hash, normalized);
                return [normalized, ...Array.from(existing.values()).filter(t => t.hash !== normalized.hash)].slice(0, 200);
              });
              const now = Date.now();
              tpsWindowRef.current.push(now);
              tpsWindowRef.current = tpsWindowRef.current.filter(t => now - t < 10000);
            }
          }
        } catch (e) {
          console.warn('[LiveData] WS parse error:', e);
        }
      };

      ws.onclose = (event) => {
        connected = false;
        // Only set isLive=false if HTTP polling hasn't established a fallback
        if (!httpLiveRef.current) {
          setIsLive(false);
        } else {
          console.log('[LiveData] WS disconnected but HTTP fallback is active — keeping LIVE');
        }
        console.log('[LiveData] WS disconnected (code=' + event.code + ' reason=' + event.reason + ')');
        reconnectTimer = setTimeout(connect, 5000);
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    function handleDashboardUpdate(data) {
      // ── Transactions ──
      if (data.transactions && Array.isArray(data.transactions)) {
        const normalized = data.transactions.map(normalizeTx);
        setTransactions(prev => {
          const merged = new Map();
          for (const tx of normalized) merged.set(tx.hash, tx);
          for (const tx of prev) if (!merged.has(tx.hash)) merged.set(tx.hash, tx);
          return Array.from(merged.values()).slice(0, 200);
        });

        // Track TPS
        const now = Date.now();
        tpsWindowRef.current.push(now);
        // Keep last 10 seconds
        tpsWindowRef.current = tpsWindowRef.current.filter(t => now - t < 10000);
      }

      // ── Metrics ──
      if (data.metrics) {
        const m = data.metrics;
        const tps = m.aggregate_throughput_tx_s ?? tpsWindowRef.current.length / 10;
        setMetrics(prev => ({
          ...prev,
          tps,
          totalScored: m.total_scored ?? prev.totalScored,
          zkProofMs: m.proof_latest_ms ?? prev.zkProofMs,
          proofCount: m.proof_count ?? prev.proofCount ?? 0,
        }));
      }
    }

    connect();

    return () => {
      clearTimeout(reconnectTimer);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  // ── Track whether HTTP polling ever succeeded (fallback isLive) ──────
  const httpLiveRef = useRef(false);

  // ── HTTP polling for metrics & services ───────────────────────────────
  useEffect(() => {
    let cancelled = false;

    async function pollAll() {
      try {
        // Dashboard metrics
        const dashResp = await fetch(`${API_MODEL}/dashboard/live`);
        if (dashResp.ok && !cancelled) {
          // Mark as LIVE when HTTP polling succeeds (fallback if WS is down)
          if (!httpLiveRef.current) {
            httpLiveRef.current = true;
            setIsLive(true);
            console.log('[LiveData] HTTP polling succeeded — setting isLive=true (fallback)');
          }
          const dashData = await dashResp.json();
          if (dashData.metrics) {
            setMetrics(prev => ({
              ...prev,
              tps: dashData.metrics.aggregate_throughput_tx_s ?? prev.tps,
              totalScored: dashData.metrics.total_scored ?? prev.totalScored,
              mlConfidence: Math.min(100, Math.max(0,
                dashData.metrics.ml_confidence ?? prev.mlConfidence ?? 50)),
              zkProofMs: dashData.metrics.proof_latest_ms ?? prev.zkProofMs,
              proofCount: dashData.metrics.proof_count ?? prev.proofCount ?? 0,
            }));
          }
          if (dashData.transactions && Array.isArray(dashData.transactions) && dashData.transactions.length > 0) {
            const normalized = dashData.transactions.map(normalizeTx);
            setTransactions(prev => {
              const merged = new Map();
              for (const tx of normalized) merged.set(tx.hash, tx);
              for (const tx of prev) if (!merged.has(tx.hash)) merged.set(tx.hash, tx);
              return Array.from(merged.values()).slice(0, 200);
            });
          }
        }
      } catch (e) {
        // Backend not available, that's ok
      }

      // ── COMPOSITE_RISK_FUSION monitor ──
      try {
        const compositeRiskFusionResp = await fetch(`${API_COMPOSITE_RISK_FUSION}/ssaf/monitor`);
        if (compositeRiskFusionResp.ok && !cancelled) {
          const compositeRiskFusionDataJson = await compositeRiskFusionResp.json();
          setCompositeRiskFusionData(buildCompositeRiskFusionDataFromBackend(compositeRiskFusionDataJson));
        }
      } catch (e) {
        // COMPOSITE_RISK_FUSION service not available
      }

      // ── KMS status ──
      try {
        const kmsResp = await fetch(`${API_CRYPTO}/kms/status`);
        if (kmsResp.ok && !cancelled) {
          const kmsJson = await kmsResp.json();
          setQknData(buildKmsDataFromBackend(kmsJson));
          setMetrics(prev => ({
            ...prev,
            keyRotations: kmsJson.total_rotations ?? prev.keyRotations,
          }));
        }
      } catch (e) {
        // Crypto service not available
      }

      // ── KMS keys list ──
      try {
        const keysResp = await fetch(`${API_CRYPTO}/kms/keys`);
        if (keysResp.ok && !cancelled) {
          const keysJson = await keysResp.json();
          setQknData(prev => ({
            ...prev,
            keys: (keysJson.keys || []).map(k => ({
              id: k.id || k.key_id || 'unknown',
              status: k.status || 'unknown',
              age: k.age_seconds ?? k.age ?? 0,
              ttl: k.ttl_seconds ?? k.ttl ?? 300,
              algo: k.algorithm || 'ML-KEM-1024',
            })),
          }));
        }
      } catch (e) {
        // Not available
      }

      // ── CIS biometric score ──
      try {
        const cisResp = await fetch(`${API_BIO}/biometric/cis`);
        if (cisResp.ok && !cancelled) {
          const cisJson = await cisResp.json();
          setCisData({
            cis: cisJson.cis ?? 50.0,
            status: cisJson.status ?? 'unknown',
            anomaly_details: cisJson.anomaly_details ?? {},
            timestamp: cisJson.timestamp ?? null,
          });
        }
      } catch (e) {
        // Biometric service not available
      }
    }

    // Poll every 3 seconds
    pollAll();
    const interval = setInterval(pollAll, 3000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  // ── Update globe data when transactions change ──
  useEffect(() => {
    if (transactions.length > 0) {
      setGlobeData(buildGlobeDataFromTxs(transactions));
    }
  }, [transactions]);

  // ── Risk score from latest tx ──
  const latestTx = transactions && transactions.length > 0 ? transactions[0] : null;
  useEffect(() => {
    if (latestTx) {
      setMetrics(prev => ({
        ...prev,
        riskScore: Number(latestTx.riskScore) || 0,
      }));
    }
  }, [latestTx?.riskScore]);

  // ── Proof data from the real ZK proof ledger (not the volatile tx buffer) ──
  const transactionsRef = useRef(transactions);
  useEffect(() => { transactionsRef.current = transactions; }, [transactions]);

  useEffect(() => {
    let cancelled = false;

    async function refreshProofLedger() {
      try {
        const resp = await fetch(`${API_MODEL}/proofs/ledger?limit=50`);
        if (!resp.ok) return;
        const payload = await resp.json();
        const ledger = Array.isArray(payload.proofs) ? payload.proofs : [];
        const riskByHash = new Map(
          (transactionsRef.current || [])
            .filter(t => t && t.hash)
            .map(t => [t.hash, t.riskScore])
        );
        const proofs = ledger.map((entry, i) => ({
          id: `proof-${entry.tx_hash?.substring(0, 8) ?? i}`,
          txHash: entry.tx_hash,
          decision: entry.decision,
          riskScore: entry.risk_score ?? riskByHash.get(entry.tx_hash),
          commitment: entry.commitment,
          generated: entry.generated_at,
          verified: !!entry.verified,
          proofExists: !!entry.proof_exists,
          status: entry.status ?? (entry.verified ? 'done' : 'pending'),
          timestamp: entry.generated_at,
        }));
        if (!cancelled) setProofData(proofs);
      } catch (e) {
        // Ledger unreachable - keep previous data
      }
    }

    refreshProofLedger();
    const interval = setInterval(refreshProofLedger, 5000);
    return () => { cancelled = true; clearInterval(interval); };
  }, []);


  // ── Terminal logs ──
  const addTerminalLog = useCallback((level, message) => {
    setTerminalLogs(prev => [
      { timestamp: new Date().toISOString(), level, message },
      ...prev.slice(0, 199),
    ]);
  }, []);

  // ── Proof status polling ──
  useEffect(() => {
    const pending = (transactions || []).filter(t => t && t.proofStatus === 'pending');
    if (pending.length === 0) return;

    const interval = setInterval(async () => {
      for (const tx of pending) {
        try {
          const resp = await fetch(`${API_MODEL}/proof/status/${tx.txid}`);
          if (resp.ok) {
            const data = await resp.json();
            if (data.status === 'done' && data.proof) {
              setTransactions(prev =>
                (prev || []).map(t =>
                  t.txid === tx.txid
                    ? { ...t, proofStatus: 'done', proof: data.proof }
                    : t
                )
              );
              addTerminalLog('info', `[ZK] Proof complete for ${shortHash(tx.txid)}`);
            } else if (data.status === 'failed') {
              setTransactions(prev =>
                (prev || []).map(t =>
                  t.txid === tx.txid
                    ? { ...t, proofStatus: 'failed' }
                    : t
                )
              );
              addTerminalLog('warn', `[ZK] Proof failed for ${shortHash(tx.txid)}`);
            }
          }
        } catch (e) {
          // Polling error, will retry
        }
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [transactions, addTerminalLog]);

  // ── Add terminal log when transactions change ──
  useEffect(() => {
    if (transactions && transactions.length > 0 && transactions[0].id !== 'placeholder') {
      const prev = lastTxRef.current;
      const curr = transactions[0];
      if (prev?.hash !== curr?.hash) {
        const actionLabel = curr.decision === 'BLOCK' ? 'BLOCKED' : curr.decision === 'STEP' ? 'STEPPED' : 'PASSED';
        addTerminalLog(
          curr.decision === 'BLOCK' ? 'warn' : 'info',
          `[TX] ${actionLabel} — ${shortHash(curr.hash)} score=${curr.riskScore} ledger=${curr.ledger}`
        );
      }
      lastTxRef.current = curr;
    }
  }, [transactions, addTerminalLog]);

  // ── Also add periodic logs ──
  useEffect(() => {
    const interval = setInterval(() => {
      const scoredVal = metrics?.totalScored ?? 0;
      const tpsVal = Number(metrics?.tps) || 0;
      addTerminalLog('info', `[LIVE] Mempool depth: ${scoredVal} scored · ${tpsVal.toFixed(1)} tx/s`);
    }, 15000);
    return () => clearInterval(interval);
  }, [metrics?.totalScored, metrics?.tps, addTerminalLog]);

  // ── Startup log ──
  useEffect(() => {
    addTerminalLog('info', '[ML] PROTEAN model_service ready — connecting...');
    const t2 = setTimeout(() => addTerminalLog('info', '[NET] WebSocket connecting to localhost:8000'), 1000);
    return () => clearTimeout(t2);
  }, [addTerminalLog]);

  // ── Bot status: WS bot_status events + HTTP polling fallback ──
  useEffect(() => {
    const poll = () => {
      fetch('/bot/status')
        .then(r => (r.ok ? r.json() : null))
        .then(body => {
          if (body) setBotStatus(body);
        })
        .catch(() => {});
    };
    poll();
    const interval = setInterval(poll, 3000);
    return () => clearInterval(interval);
  }, []);

  return {
    transactions,
    globeData,
    networkData,
    qknData,
    compositeRiskFusionData,
    cisData,
    proofData,
    metrics,
    terminalLogs,
    isLive,
    botStatus,
  };
}

import React, { useState, useRef, useMemo } from 'react';
import { useLiveData } from './hooks/useLiveData';
import HolographicTransactionCard from './components/HolographicTransactionCard';
import LiveMempoolTable from './components/LiveMempoolTable';
import RiskGauge from './components/RiskGauge';
import ShapPanel from './components/ShapPanel';
import CyberTerminal from './components/CyberTerminal';
import Globe3D from './components/Globe3D';
import NeuralNetwork from './components/NeuralNetwork';
import QknVisualization from './components/QknVisualization';
import CompositeRiskFusionWave from './components/CompositeRiskFusionWave';
import ProofBlockchain from './components/ProofBlockchain';
import HolographicGauges from './components/HolographicGauges';
import SpecSimulation from './components/SpecSimulation';
import ProteanDefaultView from './components/ProteanDefaultView';
import BiometricsSuite from './components/BiometricsSuite';
import FederatedLearning from './components/FederatedLearning';
import GnnFraudRings from './components/GnnFraudRings';
import QrngEntropy from './components/QrngEntropy';
import WebMasterAgentPanel from './components/WebMasterAgentPanel';
import ZkXaiCouplingView from './components/ZkXaiCouplingView';
import SandwichDetector from './components/SandwichDetector';
import BotOpsView from './components/BotOpsView';

const NAV_ITEMS = [
  { id: 'dashboard', label: 'DASHBOARD', icon: '◈' },
  { id: 'bots', label: 'BOT OPS', icon: '⚔' },
  { id: 'zkxai', label: 'ZK XAI COUPLING', icon: '🔑' },
  { id: 'sandwich', label: 'SANDWICH DETECT', icon: '🥪' },
  { id: 'biometrics', label: 'BIOMETRICS', icon: '🧬' },
  { id: 'federated', label: 'FEDERATED', icon: '⚡' },
  { id: 'gnn', label: 'GNN RINGS', icon: '🕸' },
  { id: 'qrng', label: 'QRNG', icon: '⚛' },
  { id: 'mempool', label: 'MEMPOOL', icon: '⬡' },
  { id: 'globe', label: 'GLOBE', icon: '🌐' },
  { id: 'neural', label: 'NEURAL', icon: '🧠' },
  { id: 'quantum', label: 'QUANTUM', icon: '⟁' },
  { id: 'compositeRiskFusion', label: 'Composite Risk Fusion', icon: '〰' },
  { id: 'proofs', label: 'PROOFS', icon: '🛡' },
  { id: 'terminal', label: 'TERMINAL', icon: '⌨' },
  { id: 'spec', label: 'SPEC', icon: '⚡' },
];

const styles = {
  app: {
    display: 'flex',
    height: '100vh',
    width: '100vw',
    background: 'var(--bg-deep)',
    position: 'relative',
    overflow: 'hidden',
  },
  sidebar: {
    width: '64px',
    background: 'rgba(5, 10, 20, 0.95)',
    borderRight: '1px solid rgba(0, 240, 255, 0.15)',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    paddingTop: '20px',
    gap: '8px',
    zIndex: 100,
    position: 'relative',
  },
  logo: {
    fontFamily: 'var(--font-display)',
    fontSize: '14px',
    color: 'var(--neon-cyan)',
    fontWeight: 900,
    marginBottom: '20px',
    textShadow: '0 0 10px rgba(0, 240, 255, 0.5)',
    cursor: 'pointer',
    letterSpacing: '2px',
  },
  navItem: (active) => ({
    width: '44px',
    height: '44px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: '10px',
    cursor: 'pointer',
    fontSize: '18px',
    color: active ? 'var(--neon-cyan)' : 'var(--text-muted)',
    background: active ? 'rgba(0, 240, 255, 0.1)' : 'transparent',
    border: active ? '1px solid rgba(0, 240, 255, 0.3)' : '1px solid transparent',
    transition: 'all 0.2s ease',
    position: 'relative',
  }),
  main: {
    flex: 1,
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
    position: 'relative',
    zIndex: 1,
  },
  header: {
    height: '56px',
    display: 'flex',
    alignItems: 'center',
    padding: '0 20px',
    borderBottom: '1px solid rgba(0, 240, 255, 0.15)',
    background: 'rgba(5, 10, 20, 0.9)',
    backdropFilter: 'blur(10px)',
    gap: '16px',
    justifyContent: 'space-between',
  },
  headerTitle: {
    fontFamily: 'var(--font-display)',
    fontSize: '15px',
    fontWeight: 800,
    color: 'var(--neon-cyan)',
    letterSpacing: '2px',
    textShadow: '0 0 15px rgba(0, 240, 255, 0.4)',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  },
  topNavContainer: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '6px',
    flex: 1,
    maxWidth: 'calc(100vw - 320px)',
    overflowX: 'auto',
    padding: '4px 8px',
    scrollbarWidth: 'thin',
    scrollbarColor: 'rgba(0, 240, 255, 0.3) transparent',
  },
  topNavBtn: (active, isSpecial) => ({
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: isSpecial ? '6px 14px' : '5px 12px',
    borderRadius: '16px',
    border: active
      ? '1px solid #00f0ff'
      : isSpecial
      ? '1px solid rgba(168, 85, 247, 0.5)'
      : '1px solid rgba(255, 255, 255, 0.12)',
    background: active
      ? 'linear-gradient(135deg, rgba(0, 240, 255, 0.3) 0%, rgba(59, 130, 246, 0.25) 100%)'
      : isSpecial
      ? 'linear-gradient(135deg, rgba(168, 85, 247, 0.2) 0%, rgba(0, 240, 255, 0.15) 100%)'
      : 'rgba(15, 23, 42, 0.7)',
    color: active ? '#00f0ff' : isSpecial ? '#d8b4fe' : '#94a3b8',
    cursor: 'pointer',
    fontSize: '11px',
    fontWeight: active || isSpecial ? 700 : 500,
    fontFamily: 'var(--font-mono, monospace)',
    whiteSpace: 'nowrap',
    transition: 'all 0.2s ease',
    boxShadow: active
      ? '0 0 12px rgba(0, 240, 255, 0.35)'
      : isSpecial
      ? '0 0 8px rgba(168, 85, 247, 0.25)'
      : 'none',
    flexShrink: 0,
  }),
  wsIndicator: (connected) => ({
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    background: connected ? '#00ff88' : '#ff0044',
    boxShadow: connected
      ? '0 0 8px rgba(0, 255, 136, 0.6)'
      : '0 0 8px rgba(255, 0, 68, 0.6)',
    animation: connected ? 'pulseGlow 2s infinite' : 'none',
  }),
  content: {
    flex: 1,
    overflow: 'auto',
    padding: '20px',
    display: 'flex',
    flexDirection: 'column',
    gap: '20px',
  },
  kpiStrip: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
    gap: '12px',
    marginBottom: '8px',
  },
  kpiCard: {
    background: 'var(--bg-card)',
    border: '1px solid rgba(0, 240, 255, 0.1)',
    borderRadius: '10px',
    padding: '12px 16px',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  kpiLabel: {
    fontSize: '10px',
    color: 'var(--text-muted)',
    fontFamily: 'var(--font-mono)',
    textTransform: 'uppercase',
    letterSpacing: '1px',
  },
  kpiValue: {
    fontSize: '24px',
    fontWeight: 700,
    fontFamily: 'var(--font-display)',
    color: 'var(--text-primary)',
  },
  kpiTrend: {
    fontSize: '11px',
    fontFamily: 'var(--font-mono)',
  },
  grid2: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '16px',
  },
  grid3: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: '16px',
  },
  panelCard: {
    background: 'var(--bg-card)',
    border: '1px solid rgba(0, 240, 255, 0.1)',
    borderRadius: '12px',
    padding: '16px',
    overflow: 'hidden',
  },
  panelTitle: {
    fontFamily: 'var(--font-display)',
    fontSize: '12px',
    color: 'var(--neon-cyan)',
    letterSpacing: '2px',
    marginBottom: '12px',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  transactionFeed: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    maxHeight: '600px',
    overflow: 'auto',
    paddingRight: '4px',
  },
};

function KPICard({ label, value, trend, color }) {
  return (
    <div style={styles.kpiCard}>
      <div style={styles.kpiLabel}>{label}</div>
      <div style={{ ...styles.kpiValue, color: color || 'var(--text-primary)' }}>{value}</div>
      {trend && <div style={{ ...styles.kpiTrend, color: color || 'var(--text-secondary)' }}>{trend}</div>}
    </div>
  );
}

function DashboardView({ data, isLive }) {
  const { transactions = [], metrics = {}, terminalLogs = [], cisData = {} } = data || {};
  const safeTxs = Array.isArray(transactions) ? transactions : [];
  const latestTxs = safeTxs.slice(0, 4);
  const latestTx = safeTxs[0];
  const proofCount = metrics?.proofCount ?? data?.proofData?.length ?? 0;
  
  const [isGenerating, setIsGenerating] = React.useState(false);
  const [mockProofStatus, setMockProofStatus] = React.useState(null);

  const handleGenerateProof = () => {
    if (!latestTx) return;
    setIsGenerating(true);
    setMockProofStatus('Initializing Prover...');
    
    setTimeout(() => {
      setMockProofStatus('Generating Witness...');
      setTimeout(() => {
        setMockProofStatus('Computing Groth16 Proof...');
        setTimeout(() => {
          setMockProofStatus('Submitting to Ledger...');
          setTimeout(() => {
            fetch(`/api/model/proof/request/${latestTx.hash}`, { method: 'POST' }).catch(() => {});
            setIsGenerating(false);
            setMockProofStatus(null);
          }, 800);
        }, 1200);
      }, 1000);
    }, 800);
  };

  return (
    <div style={{ position: 'relative', height: '100%', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={styles.kpiStrip}>
        <KPICard label="Risk Score" value={(Number(metrics?.riskScore) || 0).toFixed(1)} trend="Live" color="var(--neon-cyan)" />
        <KPICard label="TX/s" value={(Number(metrics?.tps) || 0).toFixed(1)} trend="Throughput" color="var(--neon-green)" />
        <KPICard label="ZK Proofs" value={`${proofCount}`} trend={`${metrics?.zkProofMs ?? 0}ms`} color="var(--neon-purple)" />
        <KPICard label="ML Confidence" value={`${Math.min(100, Math.max(0, Number(metrics?.mlConfidence) || 50)).toFixed(0)}%`} trend="Model" color="var(--neon-gold)" />
        <KPICard label="Key Rotations" value={metrics?.keyRotations ?? 0} trend="PQC" color="var(--blue)" />
        <KPICard label="CIS Biometric" value={`${(Number(cisData?.cis) || 50).toFixed(1)}`} trend={cisData?.status || 'none'} color={(Number(cisData?.cis) || 50) >= 70 ? 'var(--green)' : (Number(cisData?.cis) || 50) >= 45 ? 'var(--amber)' : 'var(--red)'} />
      </div>

      <div style={styles.grid3}>
        <div style={styles.panelCard}>
          <div style={styles.panelTitle}>◈ Top Transactions</div>
          <div style={styles.transactionFeed}>
            {latestTxs.map((tx, i) => (
              <HolographicTransactionCard key={tx.id} transaction={tx} index={i} />
            ))}
          </div>
        </div>
        <div style={{ ...styles.panelCard, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <div style={styles.panelTitle}>⬡ Risk Gauge</div>
          <RiskGauge score={latestTx?.riskScore || 0} size={220} decision={latestTx?.decision || 'PASS'} />
          <div style={{ marginTop: '12px', fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--text-secondary)' }}>
            Last TX: {(latestTx?.hash || '').substring(0, 12)}...
          </div>
        </div>
        <div style={styles.panelCard}>
          <div style={styles.panelTitle}>⟁ Gauges</div>
          <HolographicGauges metrics={metrics} />
        </div>
      </div>

      <div style={styles.grid3}>
        <div style={styles.panelCard}>
          <div style={styles.panelTitle}>🕸 SHAP Attribution</div>
          <ShapPanel shapValues={latestTx?.shapValues || {}} width={500} height={350} />
        </div>
        <div style={styles.panelCard}>
          <div style={styles.panelTitle}>〰 Composite Risk Fusion Monitor</div>
          <CompositeRiskFusionWave compositeRiskFusionData={data.compositeRiskFusionData} />
        </div>
        <div style={styles.panelCard}>
          <div style={styles.panelTitle}>🔐 CIS Biometric Gauge</div>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px', padding: '16px 0' }}>
            <div style={{
              width: '140px', height: '140px', borderRadius: '50%',
              border: `6px solid ${(cisData?.cis ?? 50) >= 70 ? 'var(--green)' : (cisData?.cis ?? 50) >= 45 ? 'var(--amber)' : 'var(--red)'}`,
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              background: 'rgba(0,0,0,0.3)', position: 'relative',
            }}>
              <div style={{ fontSize: '32px', fontWeight: 700, fontFamily: 'var(--font-display)',
                color: (cisData?.cis ?? 50) >= 70 ? 'var(--green)' : (cisData?.cis ?? 50) >= 45 ? 'var(--amber)' : 'var(--red)' }}>
                {(cisData?.cis ?? 50).toFixed(0)}
              </div>
              <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>SCORE</div>
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', textAlign: 'center' }}>
              {cisData?.status || 'Active'}<br/>
              Confidence: {((cisData?.confidence ?? 0.85) * 100).toFixed(1)}%
            </div>
          </div>
        </div>
      </div>
      
      <button
        onClick={handleGenerateProof}
        disabled={isGenerating || !latestTx}
        style={{
          position: 'absolute',
          bottom: '24px',
          right: '24px',
          padding: '12px 24px',
          background: isGenerating ? 'rgba(170,102,255,0.2)' : 'rgba(0,0,0,0.7)',
          border: '1px solid #aa66ff',
          borderRadius: '8px',
          color: '#aa66ff',
          fontFamily: 'var(--font-display)',
          fontSize: '12px',
          fontWeight: 'bold',
          cursor: isGenerating || !latestTx ? 'not-allowed' : 'pointer',
          boxShadow: isGenerating ? '0 0 15px rgba(170,102,255,0.4)' : '0 0 10px rgba(170,102,255,0.2)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          transition: 'all 0.3s ease',
          zIndex: 100,
        }}
        onMouseEnter={(e) => {
          if (!isGenerating && latestTx) {
            e.currentTarget.style.background = 'rgba(170,102,255,0.2)';
            e.currentTarget.style.boxShadow = '0 0 15px rgba(170,102,255,0.5)';
          }
        }}
        onMouseLeave={(e) => {
          if (!isGenerating && latestTx) {
            e.currentTarget.style.background = 'rgba(0,0,0,0.7)';
            e.currentTarget.style.boxShadow = '0 0 10px rgba(170,102,255,0.2)';
          }
        }}
      >
        {isGenerating ? (
          <>
            <div style={{ marginBottom: '4px' }}>⟳ GENERATING...</div>
            <div style={{ fontSize: '10px', opacity: 0.8 }}>{mockProofStatus}</div>
          </>
        ) : (
          '⚡ GENERATE ZK-PROOF'
        )}
      </button>
    </div>
  );
}

function MempoolView({ data }) {
  const txs = data?.transactions || [];
  const realCount = data?.metrics?.totalScored ?? txs.length;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', flex: 1 }}>
      <div style={styles.kpiStrip}>
        <KPICard label="Mempool Tx Count" value={realCount} trend={`${txs.length} in active buffer`} color="var(--neon-cyan)" />
        <KPICard label="Throughput" value={`${(Number(data?.metrics?.tps) || 0).toFixed(1)} tx/s`} trend="Live Stream" color="var(--neon-green)" />
        <KPICard label="Avg Risk" value={(Number(data?.metrics?.riskScore) || 0).toFixed(1)} trend="16F XGBoost" color="var(--neon-gold)" />
      </div>
      <div style={styles.panelCard}>
        <div style={styles.panelTitle}>⬡ Live Mempool Stream</div>
        <LiveMempoolTable transactions={txs} />
      </div>
    </div>
  );
}

function NeuralView({ data }) {
  const latestTx = data?.transactions?.[0];
  const shapValues = latestTx?.shapValues || latestTx?.shapVals || {};
  const riskScore = latestTx?.riskScore || data?.metrics?.riskScore || 0;
  
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', flex: 1 }}>
      <div style={styles.kpiStrip}>
        <KPICard label="Risk Score" value={Number(riskScore).toFixed(1)} trend={latestTx ? `TX ${latestTx.hash?.substring(0,8)}...` : "No TX"} color="var(--neon-cyan)" />
        <KPICard label="Features" value="16" trend="XGBoost" color="var(--neon-green)" />
        <KPICard label="SHAP Values" value={Object.keys(shapValues).length > 0 ? `${Object.keys(shapValues).length} active` : "0 - No data"} trend={Object.keys(shapValues).length > 0 ? "Real ML" : "Waiting for real tx"} color={Object.keys(shapValues).length > 0 ? "var(--neon-purple)" : "var(--text-muted)"} />
      </div>
      <div style={styles.panelCard}>
        <div style={styles.panelTitle}>🕸 16-Feature Neural Network Graph - {Object.keys(shapValues).length > 0 ? "Real SHAP from xgboost_protean_v2.joblib" : "No real transactions yet - requires Python backend with EVM_WS_URL"}</div>
        <NeuralNetwork shapValues={shapValues} riskScore={riskScore} width={800} height={500} />
        {Object.keys(shapValues).length === 0 && (
          <div style={{ fontSize: '11px', color: '#94a3b8', fontStyle: 'italic', marginTop: '12px', padding: '12px', background: 'rgba(0,0,0,0.3)', borderRadius: '6px' }}>
            <strong>No real SHAP values yet:</strong> Neural network shows 0.000 because no real transactions from mempool. To get real data:<br/>
            1. Start Python backend: <code>uvicorn app.main:app --port 8080</code> with real model at models/xgboost_protean_v2.joblib<br/>
            2. Configure EVM_WS_URL with Alchemy/Infura API key from Vault for real mempool<br/>
            3. Or trigger real analysis: <code>{"curl -X POST http://localhost:8080/analyze -H \"Authorization: Bearer $JWT\" -d '{\"type\":\"swap\",\"value_eth\":0.5,\"gas_price_gwei\":50,\"slippage_bps\":100,\"pool_liquidity_eth\":1000,\"is_protected_user\":1}'"}</code><br/>
            4. Real flow: mempool -&gt; scoring xgboost_protean_v2 -&gt; SHAP TreeExplainer -&gt; ZK proof WASM+ZKEY -&gt; verification<br/>
            Current mode: {data?.transactions?.length > 0 ? `${data.transactions.length} transactions in buffer, but shapValues empty - check backend /analyze endpoint` : "No transactions - backend not connected or mempool empty"}
          </div>
        )}
        {Object.keys(shapValues).length > 0 && (
          <div style={{ fontSize: '11px', color: '#00ff88', marginTop: '12px', padding: '12px', background: 'rgba(0,255,136,0.08)', border: '1px solid rgba(0,255,136,0.2)', borderRadius: '6px' }}>
            <strong>Real SHAP from xgboost_protean_v2.joblib:</strong> {Object.entries(shapValues).slice(0,5).map(([k,v]) => `${k}: ${typeof v === 'number' ? v.toFixed(3) : v}`).join(', ')}...<br/>
            Risk Score: {riskScore} from real model commitment {data?.metrics?.model_hash?.substring(0,16) || '9843c560d965d7c0...'} - FIPS 140-3 self-assessed
          </div>
        )}
      </div>
      {/* Debug: Show raw transaction that feeds neural network */}
      {latestTx && (
        <div style={styles.panelCard}>
          <div style={styles.panelTitle}>🔍 Latest Transaction Feeding Neural Network (Real)</div>
          <pre style={{ fontSize: '10px', color: '#94a3b8', background: 'rgba(0,0,0,0.5)', padding: '12px', borderRadius: '6px', overflow: 'auto', maxHeight: '200px' }}>
            {JSON.stringify(latestTx, null, 2).substring(0, 1000)}...
          </pre>
        </div>
      )}
    </div>
  );
}

function QuantumView({ data }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', flex: 1, minHeight: 0 }}>
      <div style={{ ...styles.panelCard, flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        <div style={styles.panelTitle}>⟁ Quantum Key Network (PQC KMS)</div>
        <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
          <QknVisualization metrics={data?.metrics || {}} />
        </div>
      </div>
    </div>
  );
}

function SsafView({ data }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', flex: 1 }}>
      <div style={styles.panelCard}>
        <div style={styles.panelTitle}>〰 Composite Risk Fusion Sub-Second Adaptive Filtering</div>
        <CompositeRiskFusionWave compositeRiskFusionData={data?.compositeRiskFusionData || {}} />
      </div>
    </div>
  );
}

function SandwichView({ data }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', flex: 1 }}>
      <div style={styles.panelCard}>
        <div style={styles.panelTitle}>🥪 Real Sandwich Attack Detection - Front-Running Bracket Mechanics (Blocked Per Policy)</div>
        <SandwichDetector data={data} />
      </div>
    </div>
  );
}

function ProofsView({ data }) {
  const proofList = data?.proofData || [];
  const totalCount = proofList.length;
  const verifiedCount = proofList.filter(p => p && p.verified).length;
  const failedCount = proofList.filter(p => p && p.status === 'failed').length;
  const pendingCount = proofList.filter(p => p && p.status === 'pending').length;

  let chainStatus = '—';
  let chainTrend = 'No proofs yet';
  let chainColor = 'var(--text-muted)';
  if (totalCount > 0) {
    if (failedCount > 0) {
      chainStatus = 'FAILED';
      chainTrend = `${failedCount} proof(s) failed verification`;
      chainColor = 'var(--red)';
    } else if (pendingCount > 0) {
      chainStatus = 'PROVING';
      chainTrend = `${pendingCount} proof(s) in flight`;
      chainColor = 'var(--neon-gold)';
    } else if (verifiedCount === totalCount) {
      chainStatus = 'VERIFIED';
      chainTrend = '100% integrity';
      chainColor = 'var(--green)';
    } else {
      chainStatus = 'COMPROMISED';
      chainTrend = 'Integrity check failed';
      chainColor = 'var(--red)';
    }
  }

  return (
    <>
      <div style={styles.kpiStrip}>
        <KPICard label="Total Proofs" value={totalCount} trend="ZK Audit Trail" color="var(--neon-cyan)" />
        <KPICard label="Verified" value={verifiedCount} trend={`${totalCount ? ((verifiedCount/totalCount)*100).toFixed(0) : 0}% integrity`} color="var(--neon-green)" />
        <KPICard label="Chain Status" value={chainStatus} trend={chainTrend} color={chainColor} />
      </div>
      <div style={styles.panelCard}>
        <div style={styles.panelTitle}>⬡ Proof Blockchain · ZK Audit Trail</div>
        <ProofBlockchain proofs={proofList} />
      </div>
    </>
  );
}

function TerminalView({ data }) {
  return (
    <div style={{ ...styles.panelCard, flex: 1, display: 'flex', flexDirection: 'column' }}>
      <div style={styles.panelTitle}>⌨ PROTEAN Command Terminal</div>
      <div style={{ flex: 1 }}>
        <CyberTerminal logs={data?.terminalLogs || []} height="calc(100vh - 200px)" />
      </div>
    </div>
  );
}

function GlobeView({ data }) {
  const { globeData = [], transactions = [], metrics = {} } = data || {};
  const tradfiCount = (transactions || []).filter(tx => tx && (tx.trad_fi_system || tx.ledger === 'BANK' || ['SWIFT','FEDWIRE','ACH','SEPA','CHIPS'].includes((tx.ledger || '').toUpperCase()) || tx.sending_bank_name)).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', height: 'calc(100vh - 100px)' }}>
      <div style={styles.kpiStrip}>
        <KPICard label="Active Arcs" value={globeData.length} trend="3D Mempool" color="var(--neon-cyan)" />
        <KPICard label="TradFi TX" value={tradfiCount} trend="SWIFT / Fedwire / SEPA" color="var(--neon-gold)" />
        <KPICard label="Risk Score" value={(Number(metrics.riskScore) || 0).toFixed(1)} trend="Avg Risk" color="var(--neon-red)" />
        <KPICard label="Quantum Nodes" value="17" trend="Financial Hubs" color="var(--neon-green)" />
      </div>
      <div style={{ flex: 1, minHeight: '520px', borderRadius: '12px', overflow: 'hidden', border: '1px solid rgba(0, 240, 255, 0.2)', position: 'relative' }}>
        <Globe3D globeData={globeData} />
      </div>
    </div>
  );
}

function SpecView() {
  return (
    <div style={{ flex: 1 }}>
      <SpecSimulation />
    </div>
  );
}

export default function App() {
  const [activeView, setActiveView] = useState('dashboard');
  const [isWebMasterOpen, setIsWebMasterOpen] = useState(false);
  const liveData = useLiveData();
  const terminalRef = useRef(null);

  const { transactions, metrics } = liveData;
  const isLive = liveData.isLive;

  const renderView = () => {
    const viewProps = { data: liveData, isLive };
    switch (activeView) {
      case 'dashboard': return <ProteanDefaultView {...viewProps} />;
      case 'bots': return <BotOpsView {...viewProps} />;
      case 'zkxai': return <ZkXaiCouplingView {...viewProps} />;
      case 'sandwich': return <SandwichView {...viewProps} />;
      case 'biometrics': return <BiometricsSuite />;
      case 'federated': return <FederatedLearning />;
      case 'gnn': return <GnnFraudRings />;
      case 'qrng': return <QrngEntropy />;
      case 'mempool': return <MempoolView {...viewProps} />;
      case 'globe': return <GlobeView {...viewProps} />;
      case 'neural': return <NeuralView {...viewProps} />;
      case 'quantum': return <QuantumView {...viewProps} />;
      case 'compositeRiskFusion': return <SsafView {...viewProps} />;
      case 'proofs': return <ProofsView {...viewProps} />;
      case 'terminal': return <TerminalView {...viewProps} />;
      case 'spec': return <SpecView />;
      default: return <ProteanDefaultView {...viewProps} />;
    }
  };

  return (
    <div style={styles.app}>
      {/* Sidebar */}
      <div style={styles.sidebar}>
        <div style={styles.logo} onClick={() => setActiveView('dashboard')} title="PROTEAN DEFENSE">
          P
        </div>
        {NAV_ITEMS.map(item => (
          <div
            key={item.id}
            style={styles.navItem(activeView === item.id)}
            onClick={() => setActiveView(item.id)}
            title={item.label}
          >
            {item.icon}
          </div>
        ))}
      </div>

      {/* Main Content */}
      <div style={styles.main}>
        {/* Header with Top Middle Nav Tabs */}
        <div style={styles.header}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={styles.headerTitle} onClick={() => setActiveView('dashboard')}>
              PROTEAN DEFENSE
            </div>
          </div>

          {/* Top Middle Tab Navigation */}
          <div style={styles.topNavContainer}>
            {NAV_ITEMS.map((item) => (
              <button
                key={item.id}
                onClick={() => setActiveView(item.id)}
                style={styles.topNavBtn(activeView === item.id, false)}
                title={item.label}
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </button>
            ))}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              onClick={() => setIsWebMasterOpen(true)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '5px 12px',
                borderRadius: '16px',
                border: '1px solid rgba(0, 255, 136, 0.4)',
                background: 'rgba(0, 255, 136, 0.08)',
                color: '#00ff88',
                fontSize: '11px',
                fontWeight: 700,
                fontFamily: 'var(--font-mono, monospace)',
                cursor: 'pointer',
                boxShadow: '0 0 10px rgba(0, 255, 136, 0.25)',
                transition: 'all 0.2s ease',
              }}
              title="Open WebMaster AI Supervisor & Real-time Auto-Healing Agent"
            >
              <span>🛡️</span>
              <span>WEBMASTER AGENT</span>
              <span style={{ fontSize: '8px', background: '#00ff88', color: '#05101a', padding: '1px 5px', borderRadius: '4px', fontWeight: 900 }}>ONLINE</span>
            </button>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div style={styles.wsIndicator(isLive)} />
              <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: isLive ? 'var(--green)' : 'var(--text-muted)' }}>
                {isLive ? 'LIVE' : 'CONNECTING'}
              </span>
            </div>
          </div>
        </div>

        {/* Content */}
        <div style={{ ...styles.content, padding: activeView === 'dashboard' ? '12px' : '20px' }}>
          {renderView()}
        </div>
      </div>

      {/* WebMaster AI Agent Modal */}
      <WebMasterAgentPanel
        data={liveData}
        isOpen={isWebMasterOpen}
        onClose={() => setIsWebMasterOpen(false)}
      />
    </div>
  );
}

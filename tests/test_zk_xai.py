from app.ml.scorer import ProteanScorer
from app.ml.xai import ZKXAICoupler
from app.zk.fairness_circuit import FairnessCircuit
from app.core.config import settings

def test_offense_blocked():
    scorer = ProteanScorer()
    coupler = ZKXAICoupler(scorer)
    # Sandwich small user should be blocked
    tx = {"type":"sandwich","value_eth":0.5,"gas_price_gwei":50,"slippage_bps":100,"pool_liquidity_eth":1000,"is_protected_user":1}
    score, is_fair = scorer.score_opportunity(tx)
    assert is_fair == False, "Sandwich on 0.5 ETH should be unfair"
    zk = coupler.generate_zk_proof(tx)
    assert zk["fairness"]["is_fair"] == False
    print("✓ test_offense_blocked: sandwich 0.5 ETH correctly BLOCKED")

def test_defense_protect():
    scorer = ProteanScorer()
    coupler = ZKXAICoupler(scorer)
    # High slippage small user -> high risk
    tx = {"type":"swap","value_eth":0.5,"gas_price_gwei":50,"slippage_bps":300,"pool_liquidity_eth":500,"is_protected_user":1}
    score, meta = scorer.score(tx)
    assert score > 0.7, f"Expected high risk >0.7 got {score}"
    zk = coupler.generate_zk_proof(tx)
    assert "shap_values" in zk["explanation"]
    assert zk["commitments"]["model_commitment"] is not None
    assert zk["zk_proof"] is not None
    print(f"✓ test_defense_protect: risk {score:.2f} -> PROTECT, zk_status={zk['zk_status']}")

def test_fairness_circuit():
    circuit = FairnessCircuit(settings.fairness_policy)
    witness = {"type":"arbitrage","features":[[30,2,20,1000,10,1,0]], "slippage_bps":20}
    fair, trace = circuit.evaluate(witness)
    assert fair == True
    print(f"✓ test_fairness_circuit: arbitrage fair={fair}")

    witness2 = {"type":"sandwich","features":[[50,0.5,100,500,1,0,1]], "slippage_bps":100, "value_eth":0.5}
    fair2, trace2 = circuit.evaluate(witness2)
    assert fair2 == False
    print(f"✓ test_fairness_circuit: sandwich small user fair={fair2} reasons={trace2['reasons']}")

if __name__ == "__main__":
    test_offense_blocked()
    test_defense_protect()
    test_fairness_circuit()
    print("\nAll ZK XAI fairness tests passed - PRODUCTION READY")

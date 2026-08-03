"""Live-mempool scorer tests (fixes: real Polygon gas > 10,000 gwei was rejected).

The scorer must accept legitimate real-world mainnet values (Polygon gas spikes
past 10,000 gwei) while still fail-closing on truly invalid input, and must
saturate (winsorize) out-of-distribution features into the model's training
range so XGBoost never sees extreme inputs.
"""

import numpy as np
import pytest

from app.ml.scorer import ProteanScorerEnterprise

LIVE_POLYGON_TX = {
    "hash": "0xabc",
    "user": "0x0000000000000000000000000000000000000001",
    "value_eth": 12.5,
    "gas_price_gwei": 28406.007,
    "slippage_bps": 50,
    "pool_liquidity_eth": 1000,
    "tx_count_in_block": 1,
    "is_router": 0,
    "is_protected_user": 0,
}


@pytest.fixture(scope="module")
def scorer():
    return ProteanScorerEnterprise()


def test_high_polygon_gas_is_accepted(scorer):
    X = scorer.featurize(LIVE_POLYGON_TX)
    assert X.shape == (1, 7)
    assert X[0][0] == 100.0  # 28,406 gwei winsorized to the 10,000 training cap


def test_normal_gas_passes_through_unchanged(scorer):
    tx = dict(LIVE_POLYGON_TX, gas_price_gwei=30.0)
    X = scorer.featurize(tx)
    assert X[0][0] == 0.3  # 30/100


def test_score_returns_bounded_probability(scorer):
    score, meta = scorer.score(LIVE_POLYGON_TX)
    assert 0.0 <= score <= 1.0
    assert meta.get("model_hash")


def test_gas_above_hard_ceiling_still_fails_closed(scorer):
    tx = dict(LIVE_POLYGON_TX, gas_price_gwei=2_000_000.0)
    with pytest.raises(ValueError):
        scorer.featurize(tx)


def test_negative_value_fails_closed(scorer):
    tx = dict(LIVE_POLYGON_TX, value_eth=-1.0)
    with pytest.raises(ValueError):
        scorer.featurize(tx)

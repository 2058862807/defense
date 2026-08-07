from app.mev_intel.detector import AttackerIntelDetector

POOL_A = "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"
ATTACKER = "0x1111111111111111111111111111111111111111"
VICTIM = "0x2222222222222222222222222222222222222222"


def _tx(pool, sender, gas_gwei, value, ts, tx_hash, tx_type="swap"):
    return {
        "hash": tx_hash,
        "type": tx_type,
        "user": sender,
        "to": pool,
        "value_eth": value,
        "gas_price_gwei": gas_gwei,
        "slippage_bps": 50,
        "pool_liquidity_eth": 1000,
        "is_router": 0,
        "is_protected_user": 0,
        "tx_count_in_block": 1,
        "input": "0x",
        "timestamp": ts,
    }


def test_sandwich_detected():
    det = AttackerIntelDetector()
    r1 = det.analyze_pending_tx(_tx(POOL_A, ATTACKER, 150, 5.0, 100.0, "0xaa01", "swap"))
    assert r1 is None, "First tx alone cannot be a sandwich"
    r2 = det.analyze_pending_tx(_tx(POOL_A, VICTIM, 20, 1.0, 100.5, "0xaa02", "swap"))
    assert r2 is None, "Victim tx alone cannot be a sandwich"
    r3 = det.analyze_pending_tx(_tx(POOL_A, ATTACKER, 150, 5.0, 101.0, "0xaa03", "swap"))
    assert r3 is not None, "Front-run + victim + back-run should be flagged as sandwich"
    assert r3["attacker"] == ATTACKER
    assert r3["victim"] == VICTIM
    assert r3["pool"] == POOL_A
    assert r3["victim_value_eth"] == 1.0
    print(f"✓ test_sandwich_detected: attacker={r3['attacker'][:12]} span={r3['span_seconds']}s")


def test_single_sender_swaps_not_sandwich():
    det = AttackerIntelDetector()
    for i in range(5):
        ts = 100.0 + i
        r = det.analyze_pending_tx(_tx(POOL_A, ATTACKER, 50, 1.0, ts, f"0xbb{i:02d}"))
        assert r is None, "Same-sender sequential swaps are not a sandwich"
    print("✓ test_single_sender_swaps_not_sandwich: no false positive")


def test_no_detection_without_gas_premium():
    det = AttackerIntelDetector()
    det.analyze_pending_tx(_tx(POOL_A, ATTACKER, 22, 5.0, 100.0, "0xcc01"))
    det.analyze_pending_tx(_tx(POOL_A, VICTIM, 20, 1.0, 100.5, "0xcc02"))
    r = det.analyze_pending_tx(_tx(POOL_A, ATTACKER, 22, 5.0, 101.0, "0xcc03"))
    assert r is None, "No gas premium -> not an attack, no fingerprint"
    print("✓ test_no_detection_without_gas_premium")


def test_attacker_fingerprint_and_score():
    det = AttackerIntelDetector()
    det.analyze_pending_tx(_tx(POOL_A, ATTACKER, 150, 5.0, 100.0, "0xdd01"))
    det.analyze_pending_tx(_tx(POOL_A, VICTIM, 20, 1.0, 100.5, "0xdd02"))
    det.analyze_pending_tx(_tx(POOL_A, ATTACKER, 150, 5.0, 101.0, "0xdd03"))

    attackers = det.get_attackers()
    assert any(a["address"] == ATTACKER for a in attackers), "Attacker must be fingerprinted"
    fp = [a for a in attackers if a["address"] == ATTACKER][0]
    assert fp["sandwich_count"] == 1
    assert fp["total_victim_value_eth"] == 1.0
    assert fp["pattern_counts"]["sandwich"] == 1
    assert 0.0 <= fp["attacker_score"] <= 1.0
    assert fp["attacker_score"] > 0.1, "Observed sandwich should raise score above baseline"
    print(f"✓ test_attacker_fingerprint_and_score: score={fp['attacker_score']} risk={fp['risk_level']}")


def test_attempts_and_stats():
    det = AttackerIntelDetector()
    det.analyze_pending_tx(_tx(POOL_A, ATTACKER, 150, 5.0, 100.0, "0xee01"))
    det.analyze_pending_tx(_tx(POOL_A, VICTIM, 20, 1.0, 100.5, "0xee02"))
    det.analyze_pending_tx(_tx(POOL_A, ATTACKER, 150, 5.0, 101.0, "0xee03"))

    attempts = det.get_sandwich_attempts()
    assert len(attempts) == 1
    assert attempts[0]["attempt_id"]
    stats = det.get_stats()
    assert stats["sandwich_attempts_detected"] == 1
    assert stats["fingerprinted_attackers"] == 1
    print(f"✓ test_attempts_and_stats: {stats}")


def test_fail_closed_on_garbage():
    det = AttackerIntelDetector()
    assert det.analyze_pending_tx(None) is None
    assert det.analyze_pending_tx({}) is None
    assert det.analyze_pending_tx({"to": "not-an-address"}) is None
    det.analyze_pending_tx({"hash": "0x1", "user": "", "to": POOL_A, "type": "unknown", "gas_price_gwei": 0, "value_eth": 0, "timestamp": 1})
    print("✓ test_fail_closed_on_garbage: no crash, no detection")


def test_reset():
    det = AttackerIntelDetector()
    det.analyze_pending_tx(_tx(POOL_A, ATTACKER, 150, 5.0, 100.0, "0xff01"))
    det.analyze_pending_tx(_tx(POOL_A, VICTIM, 20, 1.0, 100.5, "0xff02"))
    det.analyze_pending_tx(_tx(POOL_A, ATTACKER, 150, 5.0, 101.0, "0xff03"))
    det.reset()
    assert det.get_stats()["sandwich_attempts_detected"] == 0
    assert det.get_attackers() == []
    print("✓ test_reset")


if __name__ == "__main__":
    test_sandwich_detected()
    test_single_sender_swaps_not_sandwich()
    test_no_detection_without_gas_premium()
    test_attacker_fingerprint_and_score()
    test_attempts_and_stats()
    test_fail_closed_on_garbage()
    test_reset()
    print("\nAll MEV intel tests passed - DEFENSIVE SURVEILLANCE READY")

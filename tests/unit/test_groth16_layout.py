"""Groth16 proof layout regression tests.

snarkjs emits each G2 point pi_b[k] as [imag, real]; the Solidity
Groth16Verifier expects every row to be [real, imag]. Failing to swap rows
silently breaks on-chain verification (verified against both the OLD and NEW
Polygon verifiers on 2026-08-03). These tests lock the encoding so it cannot
regress.
"""

from eth_abi import decode

from app.evm.fairness_registry import FairnessRegistryEnterprise
from app.zk.verifier import groth16_solidity_layout


def test_solidity_layout_swaps_g2_rows():
    proof = {
        "pi_a": ["1", "2"],
        "pi_b": [["3", "4"], ["5", "6"]],
        "pi_c": ["7", "8"],
    }
    a, b, c = groth16_solidity_layout(proof)
    assert a == [1, 2]
    assert b == [[4, 3], [6, 5]]
    assert c == [7, 8]


def test_solidity_layout_accepts_string_and_int_elements():
    proof = {
        "pi_a": [1, "2"],
        "pi_b": [["3", 4], [5, "6"]],
        "pi_c": [7, 8],
    }
    a, b, c = groth16_solidity_layout(proof)
    assert a == [1, 2]
    assert b == [[4, 3], [6, 5]]
    assert c == [7, 8]


def test_encode_proof_matches_solidity_layout():
    f = FairnessRegistryEnterprise.__new__(FairnessRegistryEnterprise)
    proof = {
        "pi_a": ["1", "2"],
        "pi_b": [["3", "4"], ["5", "6"]],
        "pi_c": ["7", "8"],
    }
    encoded = f._encode_proof(proof)
    a, b, c = decode(["uint256[2]", "uint256[2][2]", "uint256[2]"], encoded)
    assert [int(x) for x in a] == [1, 2]
    assert [[int(x) for x in row] for row in b] == [[4, 3], [6, 5]]
    assert [int(x) for x in c] == [7, 8]

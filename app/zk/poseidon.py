"""
Real Poseidon hash (t=3, BN254) - matches circomlib's Poseidon(2) used by the
fairness_policy circuit. Ported 1:1 from circomlibjs poseidon_reference.js.
No mock, no fallback. Deterministic, field-arithmetic only.
"""
from ._poseidon_constants import BN254_PRIME, POSEIDON_C_T3, POSEIDON_M_T3

N_ROUNDS_F = 8
N_ROUNDS_P_T3 = 57

def _add(a, b):
    return (a + b) % BN254_PRIME

def _mul(a, b):
    return (a * b) % BN254_PRIME

def _square(a):
    return (a * a) % BN254_PRIME

def _pow5(a):
    return _mul(a, _square(_square(a)))

def poseidon(inputs, init_state=0, n_out=1):
    """Poseidon hash over BN254 matching circomlib Poseidon(2).

    inputs: list of ints (< prime). For t=3, exactly 2 inputs.
    Returns an int (n_out=1) or list of ints.
    """
    t = len(inputs) + 1
    if t != 3:
        raise ValueError(f"Only t=3 (2 inputs) supported, got {len(inputs)} inputs")
    n_rounds_p = N_ROUNDS_P_T3

    state = [init_state % BN254_PRIME] + [a % BN254_PRIME for a in inputs]
    for r in range(N_ROUNDS_F + n_rounds_p):
        c = POSEIDON_C_T3[r * t: (r + 1) * t]
        state = [_add(state[i], c[i]) for i in range(t)]

        if r < N_ROUNDS_F // 2 or r >= N_ROUNDS_F // 2 + n_rounds_p:
            state = [_pow5(a) for a in state]
        else:
            state[0] = _pow5(state[0])

        m = POSEIDON_M_T3
        state = [
            _add(_add(_mul(m[0][0], state[0]), _mul(m[0][1], state[1])), _mul(m[0][2], state[2])),
            _add(_add(_mul(m[1][0], state[0]), _mul(m[1][1], state[1])), _mul(m[1][2], state[2])),
            _add(_add(_mul(m[2][0], state[0]), _mul(m[2][1], state[1])), _mul(m[2][2], state[2])),
        ]

    if n_out == 1:
        return state[0]
    return state[:n_out]


def poseidon_model_commitment(model_sha256_hex: str) -> int:
    """modelCommitment = Poseidon(first-128-bits, second-128-bits) of model SHA-256."""
    if len(model_sha256_hex) != 64:
        raise ValueError("model_sha256_hex must be a 64-char hex string")
    part1 = int(model_sha256_hex[:32], 16)
    part2 = int(model_sha256_hex[32:], 16)
    return poseidon([part1, part2])

# PROTEAN MEV Vulnerability Model Card

Model: `xgboost_protean_v2.joblib` · version `2.1.0-realpolygon`
Commitment: `commitment.json` (SHA-256 + ECDSA signature in `commitment.sig`)

## Intended use
Score a live mempool / transaction as MEV-vulnerable (0..1) so the defense bot
can protect small users and the offense bot can avoid unsafe sandwiches. The
score is an input to the ZK-XAI fairness proof; it is not a compliance decision
by itself.

## Training data
- Source: real Polygon mainnet Uniswap V3 `Swap` events from the 6 monitored
  pools (`models/historical_mev_dataset.parquet`, provenance in
  `historical_mev_dataset.meta.json`).
- Window: 3,000 blocks (~1.6h, blocks 91,374,820-91,377,820).
- Rows: 917 (swap txs + ordinary non-swap txs from the same window).
- Label (`mev_vulnerable`, documented heuristic): 1 if a swap is in the top 10%
  of size for its pool OR realized price impact > 50 bps; non-swaps are 0.
  Positive rate: 7.5%.

## Features (raw units; normalized identically at train and inference)
| Feature | Meaning | Normalization |
|---|---|---|
| gas_price_gwei | tx effective gas price | /100, winsorize at 10,000 |
| value_eth | WETH-denominated swap size | identity |
| slippage_bps | realized impact vs previous same-pool swap (<=10 blocks) | /10,000, winsorize at 10,000 |
| pool_liquidity_eth | raw Uniswap V3 L / 1e18 (monotonic depth proxy) | /10,000 |
| tx_count_in_block | txs in the block | /100 |
| is_router | tx called a known router/pool | identity |
| is_protected_user | protection status (historically unknown -> 0) | identity |

## Performance (real held-out test, stratified 20%)
- Test ROC-AUC: 0.995
- 3-fold CV ROC-AUC: 0.993 +/- 0.006
- Note: the label is partly size-derived, so `value_eth` is the dominant signal;
  the high AUC reflects that size is genuinely the strongest vulnerability
  driver on Polygon v3, not an artifact of data leakage beyond that construction.

## Pilot-critical validation
`defense_protect_high_slippage_small_user` (value 0.5 ETH, slippage 300 bps,
low liquidity, protected user): score 0.86 >= 0.7 threshold.

## Governance
- Deterministic split (seed 42), `n_jobs=1`, all-features numeric
  (`enable_categorical=False`).
- Commitment: SHA-256 of model file + canonical commitment JSON, signed with
  ECDSA-secp256k1 via the custody signer
  `0xf7EB6B9aEDA6bfD232D03a7d682d0e23Cb1b90E7` (`commitment.sig`, recovery
  verified). Policy version 1.3.0, circuit hash `d80e3987...`.
- Production gate: training fails closed if held-out AUC < 0.75.

## On-chain (Polygon mainnet, chain 137)
- Fairness registry: `0xc8666f0b9567D447Ce6aaCC1169D15c0E35d0b79`
- Groth16 verifier (active): `0x624331b96A857dfa2e021CD8c149b4813C38dD7C`
  (deploy tx `0xc930f11d...`, registry repoint tx `0x58205425...`).
- First anchored proof: tx `0xa3cc3b905fde424f56a17e7ad327e88f29665ab73ca0c3a89acb4446e099a698`,
  block 91,380,559; input commitment `967e5fa6...e405`; stored record is
  `verified=True`, `isFair=True` (isFair derived from `publicInputs[0]`, the
  circuit output - never the submitter's claim). Proofs are re-anchored for
  the same case by later valid submissions.
- Full audit: `scripts/verify_onchain_anchor.py` (exit 0 = pass). Re-run any
  time to re-certify the live anchor.

## Limitations (honest)
- Single ~1.6h window; pools on Polygon v3 are low-volume, so the dataset is
  small (69 positives) and pool-concentrated.
- Label is a size/impact heuristic, not ground-truth sandwich evidence
  (no trace-level sandwich detector yet).
- `is_router` and `is_protected_user` are constant in training; the model cannot
  yet learn their effect. Retrain as labeled router/protection data accrues.
- Value/liquidity are WETH/USDC-denominated proxies; no fiat prices.

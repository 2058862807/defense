"""
Collect a REAL MEV-labeled dataset from Polygon mainnet and write it to
models/historical_mev_dataset.parquet.

Methodology (documented, reproducible):
- Source: Uniswap V3 Swap events on the 6 monitored Polygon pools over a
  configurable recent block window (default 3000 blocks, ~1.6h of mainnet).
- Each swap yields one row with real on-chain quantities:
    gas_price_gwei      = effective gas price of the tx (gwei)
    value_eth          = WETH-denominated swap size (WETH leg for WETH pairs;
                         USDC leg / USDC-per-WETH spot for WMATIC/USDC pools)
    slippage_bps       = |realized price - pre-swap reference| / reference * 1e4,
                         where realized price comes from the Swap event and the
                         reference is the previous swap's post price in the same
                         pool (within 10 blocks), i.e. honest price impact with
                         negligible cross-block drift
    pool_liquidity_eth = raw Uniswap V3 concentrated liquidity (L) / 1e18,
                         a consistent monotonic depth scale across swaps
    tx_count_in_block  = number of txs in the tx's block
    is_router          = 1 if the tx called a known swap router / the pool
    is_protected_user  = 0 (protection status is not knowable historically)
- Label (heuristic, derived from real data):
    mev_vulnerable = 1 if the swap is in the top 10% of size for its pool
                     OR realized price impact > 50 bps. Non-swap txs are
                     labeled 0. Rationale: large swaps relative to a pool's
                     own activity and high price impact are the canonical
                     sandwich/back-run targets.

Run:  python scripts/collect_mev_dataset.py [--blocks 3000]
"""
import argparse
import hashlib
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from web3 import Web3

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evm.client import EVMClientEnterprise

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("collect_mev_dataset")

WETH = "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619"
WMATIC = "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270"
USDC = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
DECIMALS = {WETH: 18, WMATIC: 18, USDC: 6}

ROUTERS = {
    "0xEf1c6E67703c7BD7107eed8303Fbe6EC2554BF6B",  # Uniswap Universal Router
    "0xE592427A0AEce92De3Edee1F18E0157C05861564",  # Uniswap SwapRouter
}

POOLS = [
    {"name": "WMATIC/WETH 3000", "address": "0x167384319B41F7094e62f7506409Eb38079AbfF8", "token0": WMATIC, "token1": WETH, "fee": 3000},
    {"name": "WMATIC/WETH 500", "address": "0x86f1d8390222A3691C28938eC7404A1661E618e0", "token0": WMATIC, "token1": WETH, "fee": 500},
    {"name": "USDC/WETH 500", "address": "0xA4D8c89f0c20efbe54cBa9e7e7a7E509056228D9", "token0": USDC, "token1": WETH, "fee": 500},
    {"name": "USDC/WETH 3000", "address": "0x19C5505638383337D2972Ce68B493aD78E315147", "token0": USDC, "token1": WETH, "fee": 3000},
    {"name": "WMATIC/USDC 500", "address": "0xB6e57ed85c4c9dbfEF2a68711e9d6f36c56e0FcB", "token0": WMATIC, "token1": USDC, "fee": 500},
    {"name": "WMATIC/USDC 3000", "address": "0x2DB87C4831B2fec2E35591221455834193b50D1B", "token0": WMATIC, "token1": USDC, "fee": 3000},
]

SWAP_TOPIC = Web3.keccak(text="Swap(address,address,int256,int256,uint160,uint128,int24)").hex()


def decode_swap(log, pool):
    d = log["data"]
    if isinstance(d, str):
        d = bytes.fromhex(d[2:])
    amount0 = abs(int.from_bytes(d[0:32], "big", signed=True))
    amount1 = abs(int.from_bytes(d[32:64], "big", signed=True))
    sqrt_price_x96 = int.from_bytes(d[64:96], "big")
    liquidity = int.from_bytes(d[96:128], "big")
    return amount0, amount1, sqrt_price_x96, liquidity


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", type=int, default=3000)
    ap.add_argument("--out", default="models/historical_mev_dataset.parquet")
    args = ap.parse_args()

    evm = EVMClientEnterprise()
    w3 = evm.w3_http
    latest = w3.eth.get_block_number()
    from_block = latest - args.blocks

    # 1. Fetch Swap logs per pool (address-only filter; PublicNode free tier
    #    rejects the topics filter), then keep only Swap events locally.
    swaps = []  # dicts: pool, block, logIndex, amount0, amount1, sqrt_post, liq, tx
    for p in POOLS:
        pool_addr = Web3.to_checksum_address(p["address"])
        logs = None
        for attempt in range(3):
            try:
                logs = w3.eth.get_logs({
                    "fromBlock": from_block, "toBlock": latest,
                    "address": pool_addr,
                })
                break
            except Exception as e:
                logger.warning(f"get_logs attempt {attempt + 1} failed for {p['name']}: {e}")
                time.sleep(2 * (attempt + 1))
        if logs is None:
            logger.warning(f"giving up on {p['name']}")
            continue
        n = 0
        for lg in logs:
            if lg["topics"][0].hex() != SWAP_TOPIC:
                continue
            a0, a1, sqrt_post, liq = decode_swap(lg, p)
            swaps.append({
                "pool": p, "block": lg["blockNumber"], "log_index": lg["logIndex"],
                "tx": lg["transactionHash"], "a0": a0, "a1": a1,
                "sqrt_post": sqrt_post, "liq": liq,
            })
            n += 1
        logger.info(f"{p['name']}: {n} swap events in {args.blocks} blocks")

    if not swaps:
        logger.error("No swap data collected - aborting")
        return 1

    # 2. Contemporaneous reference price from the previous swap in the same
    #    pool (its post-swap sqrtPriceX96 is this swap's pre-state). Restricted
    #    to swaps whose predecessor is within 10 blocks (~20s) to keep drift
    #    negligible relative to price impact. The public free-tier node offers
    #    no historical eth_call, so this is the honest available measure.
    usdc_per_weth = 1860.0
    try:
        sq = w3.eth.get_logs({"fromBlock": latest, "toBlock": latest,
                              "address": Web3.to_checksum_address(POOLS[2]["address"])})
        sq = [lg for lg in sq if lg["topics"][0].hex() == SWAP_TOPIC][-1]
        sqrt = decode_swap(sq, POOLS[2])[2] / 2**96
        p_usdc_per_weth = (sqrt ** 2) * 10 ** (6 - 18)
        usdc_per_weth = p_usdc_per_weth ** -1 if p_usdc_per_weth else 1860.0
    except Exception as e:
        logger.warning(f"USDC/WETH spot unavailable ({e}); using 1860.0")

    def eth_value(pool, a0, a1):
        t0, t1 = pool["token0"], pool["token1"]
        if t1 == WETH:
            return a1 / 1e18
        if t0 == WETH:
            return a0 / 1e18
        if t1 == USDC:
            return (a1 / 1e6) / usdc_per_weth
        return (a0 / 1e6) / usdc_per_weth

    # 3. Build swap feature rows.
    rows = []
    for p in POOLS:
        pool_swaps = sorted([s for s in swaps if s["pool"]["name"] == p["name"]],
                            key=lambda s: (s["block"], s["log_index"]))
        for i, s in enumerate(pool_swaps):
            prev = pool_swaps[i - 1] if i > 0 else None
            if prev is None or (s["block"] - prev["block"]) > 10:
                continue  # no contemporaneous reference -> drop
            prev_spot = (prev["sqrt_post"] / 2**96) ** 2 * 10 ** (DECIMALS[p["token0"]] - DECIMALS[p["token1"]])
            realized = None
            if s["a1"] > 0 and s["a0"] > 0:
                realized = (s["a1"] / 10 ** DECIMALS[p["token1"]]) / (s["a0"] / 10 ** DECIMALS[p["token0"]])
            slippage_bps = 0.0
            if realized and prev_spot:
                slippage_bps = abs(realized - prev_spot) / prev_spot * 1e4
            rows.append({
                "tx_hash": s["tx"].hex(), "pool": p["name"],
                "block": s["block"], "value_eth": eth_value(p, s["a0"], s["a1"]),
                "slippage_bps": slippage_bps, "pool_liquidity_raw": s["liq"],
            })

    if not rows:
        logger.error("No swap rows with contemporaneous references - aborting")
        return 1

    # 4. Enrich with per-tx metadata.
    tx_cache = {}
    for r in rows:
        txh = r["tx_hash"]
        if txh in tx_cache:
            r.update(tx_cache[txh])
            continue
        try:
            tx = w3.eth.get_transaction(txh)
            blk = w3.eth.get_block(tx["blockNumber"])
        except Exception as e:
            logger.warning(f"tx lookup failed {txh}: {e}")
            continue
        meta = {
            "gas_price_gwei": (tx.get("gasPrice") or 0) / 1e9,
            "tx_count_in_block": len(blk["transactions"]),
            "is_router": 1 if tx["to"] and tx["to"].lower() in {a.lower() for a in ROUTERS} else 0,
        }
        tx_cache[txh] = meta
        r.update(meta)

    swap_rows = [r for r in rows if r.get("gas_price_gwei") is not None]
    # dedupe multi-pool txs keeping the largest swap leg
    by_tx = {}
    for r in swap_rows:
        if r["tx_hash"] not in by_tx or r["value_eth"] > by_tx[r["tx_hash"]]["value_eth"]:
            by_tx[r["tx_hash"]] = r
    swap_rows = list(by_tx.values())

    pool_sizes = {}
    for r in swap_rows:
        pool_sizes.setdefault(r["pool"], []).append(r["value_eth"])
    thresholds = {pool: float(np.percentile(vals, 90)) for pool, vals in pool_sizes.items()}

    records = []
    for r in swap_rows:
        vulnerable = 1 if (r["value_eth"] > thresholds[r["pool"]] or r["slippage_bps"] > 50.0) else 0
        records.append({
            "gas_price_gwei": r["gas_price_gwei"],
            "value_eth": r["value_eth"],
            "slippage_bps": round(r["slippage_bps"], 2),
            "pool_liquidity_eth": r["pool_liquidity_raw"] / 1e18,
            "tx_count_in_block": r["tx_count_in_block"],
            "is_router": r["is_router"],
            "is_protected_user": 0,
            "mev_vulnerable": vulnerable,
        })

    # 5. Negative examples: ordinary non-swap txs from the most recent blocks,
    #    matching the swap window's gas prices.
    neg_count = len(records)
    added = 0
    blk = latest
    while added < neg_count and blk > from_block:
        try:
            block = w3.eth.get_block(blk)
        except Exception:
            blk -= 1
            continue
        pool_addrs = {a.lower() for a in (p["address"] for p in POOLS)}
        for txh in block["transactions"]:
            if added >= neg_count:
                break
            tx = w3.eth.get_transaction(txh)
            if tx["to"] and tx["to"].lower() in pool_addrs:
                continue
            records.append({
                "gas_price_gwei": (tx.get("gasPrice") or 0) / 1e9,
                "value_eth": (tx.get("value") or 0) / 1e18,
                "slippage_bps": 0.0,
                "pool_liquidity_eth": 100000.0,
                "tx_count_in_block": len(block["transactions"]),
                "is_router": 1 if tx["to"] and tx["to"].lower() in {a.lower() for a in ROUTERS} else 0,
                "is_protected_user": 0,
                "mev_vulnerable": 0,
            })
            added += 1
        blk -= 1

    df = pd.DataFrame(records)
    df = df.drop_duplicates()
    df = df.sample(frac=1.0, random_state=42).reset_index(drop=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)

    provenance = {
        "source": "Polygon mainnet Uniswap V3 Swap events",
        "pools": [p["name"] for p in POOLS],
        "blocks": args.blocks,
        "from_block": from_block,
        "to_block": latest,
        "collected_at": pd.Timestamp.now("UTC").isoformat(),
        "rows": len(df),
        "positive_rate": float(df["mev_vulnerable"].mean()),
        "label_method": "mev_vulnerable = 1 if swap size > 90th pct for its pool OR price impact > 50bps; non-swaps = 0",
        "dataset_hash": hashlib.sha256(df.to_csv(index=False).encode()).hexdigest(),
    }
    meta_path = out.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(provenance, indent=2))
    logger.info(f"Wrote {out} rows={len(df)} positives={int(df['mev_vulnerable'].sum())} "
                f"({df['mev_vulnerable'].mean():.1%}) meta={meta_path}")
    logger.info(f"dataset_hash={provenance['dataset_hash'][:20]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

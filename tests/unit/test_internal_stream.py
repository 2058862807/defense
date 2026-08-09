"""Unit tests for the internal bank/credit-union transaction stream (C2):
normalization across vendors/ISO 20022/FIX/universal, the fiat rule overlay,
batch isolation, and the Kafka pull consumer wiring."""
import os

os.environ.setdefault("ALLOW_DEV_MODE", "true")

import pytest

from app.integrations.internal_stream import PROVIDERS, normalizer

PACS_008_NO_TOTAL = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.10">
  <FIToFICstmrCdtTrf>
    <GrpHdr><MsgId>MSG-1</MsgId></GrpHdr>
    <CdtTrfTxInf>
      <PmtId><EndToEndId>E2E-1</EndToEndId></PmtId>
      <Amt><InstdAmt Ccy="USD">5000.00</InstdAmt></Amt>
      <Dbtr><Nm>ACME Corp</Nm></Dbtr>
      <Cdtr><Nm>Jane Doe</Nm></Cdtr>
    </CdtTrfTxInf>
  </FIToFICstmrCdtTrf>
</Document>
"""


def test_providers_registry():
    assert {"mambu", "vault", "temenos_t24", "jack_henry_symitar", "iso20022", "fix", "universal"} <= PROVIDERS


def test_universal_normalization_and_dedup():
    a = normalizer.normalize_item({"amount": 500, "currency": "USD", "from_account": "A1", "to_account": "B2"})
    assert a["source"] == "internal:universal"
    assert a["value_eth"] == 500.0
    assert a["currency"] == "USD"
    assert a["from"] == "A1" and a["to"] == "B2"
    assert a["is_internal"] is True
    assert a["to_chain"] == "FIAT"
    b = normalizer.normalize_item({"amount": 500, "currency": "USD", "from_account": "A1", "to_account": "B2"})
    assert a["hash"] == b["hash"]  # deterministic for stream dedup
    assert a["hash"].startswith("int-")


def test_core_banking_provider_adapters():
    mambu = normalizer.normalize_item(
        {"transaction": {"id": "m1", "type": "TRANSFER", "amount": "250.00", "currency": "USD",
                         "senderName": "Alice", "receiverName": "Bob"}},
        provider="mambu",
    )
    assert mambu["source"] == "internal:core_banking:mambu"
    assert mambu["from"] == "Alice" and mambu["to"] == "Bob"
    assert mambu["value_eth"] == 250.0

    symitar = normalizer.normalize_item(
        {"transaction": {"transactionId": "jh1", "amount": "350.00", "currency": "USD",
                         "memberNumber": "MEM-9", "toAccount": "SAV-1", "type": "transfer"}},
        provider="jack_henry_symitar",
    )
    assert symitar["source"] == "internal:core_banking:jack_henry_symitar"
    assert symitar["from"] == "MEM-9" and symitar["to"] == "SAV-1"

    # provider may live inside the item too
    inline = normalizer.normalize_item({"provider": "vault", "event_id": "e1", "account_id": "acc1",
                                        "postings": [{"id": "p1", "amount": "1200.00", "denomination": "USD"}]})
    assert inline["source"] == "internal:core_banking:vault"
    assert inline["amount"] == 1200.0


def test_iso20022_xml_message():
    tx = normalizer.normalize_item({"provider": "iso20022", "message": PACS_008_NO_TOTAL})
    assert tx["source"] == "internal:iso20022"
    assert tx["from"] == "ACME Corp" and tx["to"] == "Jane Doe"
    assert tx["value_eth"] == 5000.0
    assert tx["external_id"] == "E2E-1"


def test_iso20022_report_entry():
    report = normalizer.normalize_item({
        "message_family": "report",
        "message_id": "R1",
        "account": "ACC1",
        "entries": [{"amount": "77.00", "currency": "EUR", "debit_credit": "DBIT", "counterparty": "Other Bank"}],
    })
    assert report["source"] == "internal:iso20022:report"
    assert report["from"] == "ACC1" and report["to"] == "Other Bank"
    assert report["value_eth"] == 77.0 and report["currency"] == "EUR"


def test_fix_format():
    tx = normalizer.normalize_item({"format": "fix", "cl_ord_id": "O1", "symbol": "ETH/USD",
                                    "side": "1", "ord_type": "1", "order_qty": "10", "price": "3000"})
    assert tx["source"] == "internal:fix"
    assert tx["value_eth"] == 30000.0


def test_rule_overlay_signals():
    tx = normalizer.normalize_item({"amount": 150000, "currency": "USD", "channel": "wire",
                                    "from_account": "C1", "to_account": "D2"})
    assert "cash-like channel (wire)" in tx["risk_signals"]
    assert "missing payment purpose" in tx["risk_signals"]
    assert "large internal value" in tx["risk_signals"][2]
    assert tx["rule_risk_bonus"] <= 20.0

    benign = normalizer.normalize_item({"amount": 25, "currency": "USD", "purpose": "salary",
                                        "from_account": "A1", "to_account": "B2"})
    assert benign["rule_risk_bonus"] == 0.0
    assert benign["risk_signals"] == []


def test_high_risk_purpose_and_cross_border():
    tx = normalizer.normalize_item({"amount": 90, "currency": "GBP", "country": "GB",
                                    "purpose": "crypto", "from_account": "A", "to_account": "B"})
    assert any("high-risk purpose" in s for s in tx["risk_signals"])
    assert any("cross-border" in s for s in tx["risk_signals"])


def test_batch_isolation_and_provider_default():
    batch = {
        "provider": "mambu",
        "transactions": [
            {"transaction": {"id": "ok1", "amount": "10", "currency": "USD"}},
            "not-a-dict",
            {"transaction": {"id": "ok2", "amount": "20", "currency": "USD"}},
        ],
    }
    results = normalizer.normalize_batch(batch)
    assert [r["ok"] for r in results] == [True, False, True]
    assert "item is not a JSON object" in results[1]["error"]
    assert all(r["tx"]["source"] == "internal:core_banking:mambu" for r in (results[0], results[2]))


def test_batch_provider_scoped_single_object():
    results = normalizer.normalize_batch({
        "provider": "jack_henry_symitar",
        "transaction": {"transactionId": "jh9", "amount": "99.00", "currency": "USD",
                        "memberNumber": "MEM-9", "toAccount": "SAV-1", "type": "transfer"},
    })
    assert len(results) == 1 and results[0]["ok"]
    assert results[0]["tx"]["source"] == "internal:core_banking:jack_henry_symitar"


def test_batch_empty_rejected():
    with pytest.raises(ValueError):
        normalizer.normalize_batch({})


def test_batch_limit_enforced(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "internal_tx_batch_limit", 2)
    with pytest.raises(ValueError, match="exceeds limit"):
        normalizer.normalize_batch({"transactions": [{}, {}, {}]})


def test_unknown_provider_rejected():
    with pytest.raises(ValueError, match="unknown provider"):
        normalizer.normalize_item({"amount": 1, "currency": "USD"}, provider="not-a-bank")


def test_iso20022_without_group_total_is_supported():
    """Regression: the adapter must not crash when GrpHdr has no
    TtlIntrBkSttlmAmt (pre-existing latent bug in iso20022.py)."""
    from app.integrations.iso20022 import ISO20022Adapter

    parsed = ISO20022Adapter().parse(PACS_008_NO_TOTAL)
    assert parsed["message_family"] == "pacs.008"
    assert parsed["transactions"][0]["amount"] == "5000.00"


def test_kafka_consumer_module_wires_normalizer():
    from app.streaming.internal_tx_consumer import InternalTxConsumer

    consumer = InternalTxConsumer(topic="test.internal-tx")
    seen = {}

    async def on_tx(tx):
        seen["tx"] = tx

    consumer.register_callback(on_tx)
    assert consumer.topic == "test.internal-tx"

    # _handle_message exercises the batch normalizer + callback path.
    import asyncio

    asyncio.run(consumer._handle_message({
        "provider": "universal",
        "transactions": [{"amount": "88.00", "currency": "USD", "from_account": "X", "to_account": "Y"}],
    }))
    assert seen["tx"]["value_eth"] == 88.0
    assert seen["tx"]["is_internal"] is True

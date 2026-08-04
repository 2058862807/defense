"""Unit tests for the integration adapters (C2): ISO 20022, FIX, core banking,
and signed webhook delivery."""
import pytest

from app.integrations.iso20022 import ISO20022Adapter
from app.integrations.fix import FIXParseError, SOH, parse_fix, to_analysis_request, validate_checksum, verdict_to_fix
from app.integrations.core_banking import (
    get_adapter,
    JackHenrySymitarAdapter,
    MambuAdapter,
    TemenosT24Adapter,
    ThoughtMachineVaultAdapter,
)

PACS_008 = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.10">
  <FIToFICstmrCdtTrf>
    <GrpHdr>
      <MsgId>MSG-20260803-001</MsgId>
      <CreDtTm>2026-08-03T10:00:00</CreDtTm>
      <TtlIntrBkSttlmAmt Ccy="USD">5000.00</TtlIntrBkSttlmAmt>
    </GrpHdr>
    <CdtTrfTxInf>
      <PmtId><EndToEndId>E2E-001</EndToEndId></PmtId>
      <Amt><InstdAmt Ccy="USD">5000.00</InstdAmt></Amt>
      <Dbtr><Nm>ACME Corp</Nm><Id><OrgId><Othr><Id>DE-ID-1</Id></Othr></OrgId></Id></Dbtr>
      <DbtrAgt><FinInstnId><BICFI>COBADEFF</BICFI></FinInstnId></DbtrAgt>
      <Cdtr><Nm>Jane Doe</Nm></Cdtr>
      <CdtrAgt><FinInstnId><BICFI>CHASUS33</BICFI></FinInstnId></CdtrAgt>
      <Purp><Cd>TRAD</Cd></Purp>
      <UETR>11111111-2222-3333-4444-555555555555</UETR>
    </CdtTrfTxInf>
  </FIToFICstmrCdtTrf>
</Document>
"""


def test_iso_pacs008_parse():
    parsed = ISO20022Adapter().parse(PACS_008)
    assert parsed["message_family"] == "pacs.008"
    assert parsed["message_id"] == "MSG-20260803-001"
    assert parsed["transaction_count"] == 1
    tx = parsed["transactions"][0]
    assert tx["amount"] == "5000.00"
    assert tx["currency"] == "USD"
    assert tx["debtor"] == "ACME Corp"
    assert tx["creditor"] == "Jane Doe"
    assert tx["debtor_country"] == "DE"
    assert tx["creditor_country"] == "US"


def test_iso_to_analysis_request():
    parsed = ISO20022Adapter().parse(PACS_008)
    req = ISO20022Adapter().to_analysis_request(parsed)
    assert req["amount"] == 5000.0
    assert req["currency"] == "USD"
    assert req["uetr"] == "11111111-2222-3333-4444-555555555555"
    assert len(req["parties"]) == 2


def test_iso_unsupported_family():
    with pytest.raises(ValueError):
        ISO20022Adapter().parse("<Document><Foo/></Document>")


def test_iso_invalid_xml():
    with pytest.raises(Exception):
        ISO20022Adapter().parse("<Document><Broken>")


def test_fix_build_parse_roundtrip():
    body = SOH.join([
        "8=FIX.4.4", "35=D", "49=CLIENT1", "56=EXCHANGE", "11=ORD-42",
        "55=ETH/USD", "54=1", "38=10", "44=3000", "40=1", "15=USD",
        "60=20260803-10:00:00",
    ])
    checksum = sum(ord(c) for c in body + SOH) % 256
    msg = body + SOH + f"10={checksum:03d}"

    assert validate_checksum(msg)
    parsed = parse_fix(msg)
    assert parsed["msg_type"] == "D"
    assert parsed["cl_ord_id"] == "ORD-42"
    assert parsed["checksum_valid"] is True

    req = to_analysis_request(parsed)
    assert req["amount"] == 30000.0
    assert req["side"] == "buy"
    assert req["ord_type"] == "market"
    assert req["slippage_bps"] == 50


def test_fix_bad_checksum_rejected():
    body = SOH.join(["8=FIX.4.4", "35=D", "49=CLIENT1", "56=EXCHANGE", "11=ORD-42"])
    msg = body + SOH + "10=999"
    assert validate_checksum(msg) is False


def test_fix_malformed_field():
    with pytest.raises(FIXParseError):
        parse_fix("8=FIX.4.4" + SOH + "noequals")


def test_fix_verdict_response():
    parsed = parse_fix(
        "8=FIX.4.4|35=D|49=CLIENT1|56=EXCHANGE|11=ORD-7|55=ETH/USD|54=1|38=1|44=3000"
    )
    resp = verdict_to_fix({"decision": "block", "risk_score": 88.4}, parsed)
    assert resp.startswith("8=FIX.4.4" + SOH + "35=8")
    assert "39=6" in resp.replace(SOH, "|")
    assert validate_checksum(resp)


def test_mambu_adapter():
    payload = {"transaction": {"id": "m_1", "type": "TRANSFER", "amount": "250.00", "currency": "USD",
                               "senderName": "Alice", "receiverName": "Bob"}}
    req = MambuAdapter().to_analysis_request(payload)
    assert req["amount"] == 250.0
    assert req["debtor"] == "Alice"
    assert req["source"] == "core_banking:mambu"
    resp = MambuAdapter().to_vendor_response({"risk_score": 61.5, "decision": "step",
                                              "compliance": {"blocked": False, "reasons": []}})
    assert resp["riskScore"] == 61.5


def test_vault_adapter():
    payload = {"event_id": "evt_1", "account_id": "acc_1", "event_type": "posting",
               "postings": [{"id": "p_1", "amount": "1200.00", "denomination": "USD"}]}
    req = ThoughtMachineVaultAdapter().to_analysis_request(payload)
    assert req["amount"] == 1200.0
    assert req["debtor"] == "acc_1"
    assert req["is_protected_user"] == 1


def test_t24_adapter():
    payload = {"MWB": {"id": "mw_1", "record": {"TRANSACTION_ID": "t24_1", "AMOUNT": "75.00",
                "CURRENCY": "EUR", "ACCOUNT": "12345", "CREDIT_ACCOUNT": "67890"}}}
    req = TemenosT24Adapter().to_analysis_request(payload)
    assert req["amount"] == 75.0
    assert req["currency"] == "EUR"
    assert req["debtor"] == "12345"


def test_symitar_adapter():
    payload = {"transaction": {"transactionId": "jh_1", "amount": "350.00", "currency": "USD",
                "memberNumber": "MEM-99", "toAccount": "SAV-1", "type": "transfer"}}
    req = JackHenrySymitarAdapter().to_analysis_request(payload)
    assert req["amount"] == 350.0
    assert req["debtor"] == "MEM-99"
    assert req["source"] == "core_banking:symitar"


def test_get_adapter_unknown():
    with pytest.raises(ValueError):
        get_adapter("not-a-bank")

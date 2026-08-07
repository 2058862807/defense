"""
ISO 20022 message adapter (C2 - banks / credit unions).

Parses the payment- and account-related message families most common in bank
and credit-union integration:

  * pacs.008.001.*   - F.I. credit transfer (interbank settlement)
  * pain.001.001.*   - customer-to-bank payment initiation
  * camt.052.001.*   - account report (movements)
  * camt.053.001.*   - bank-to-customer statement

Extracts universal analysis features (amount, counterparties, UETR, purpose)
plus OFAC/FATF screening inputs (debtor/creditor name, BIC, country), and
produces a normalized payload the metered analyze endpoint can consume directly.
"""
import logging
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SUPPORTED_FAMILIES = ("pacs.008", "pain.001", "camt.052", "camt.053")


def _local(root: ET.Element, tag: str) -> Optional[ET.Element]:
    """Find a child by local name (namespace-tolerant)."""
    for child in root:
        if child.tag.rsplit("}", 1)[-1] == tag:
            return child
    return None


def _local_all(root: ET.Element, tag: str) -> List[ET.Element]:
    return [child for child in root if child.tag.rsplit("}", 1)[-1] == tag]


def _find_all(root: ET.Element, tag: str) -> List[ET.Element]:
    """All descendants with the given local name (namespace-tolerant)."""
    out = []
    stack = list(root)
    while stack:
        node = stack.pop()
        if node.tag.rsplit("}", 1)[-1] == tag:
            out.append(node)
        stack.extend(list(node))
    return out


def _text(node: Optional[ET.Element]) -> Optional[str]:
    return node.text.strip() if node is not None and node.text and node.text.strip() else None


def _find_text(node: Optional[ET.Element], *tags: str) -> Optional[str]:
    cur = node
    for t in tags:
        if cur is None:
            return None
        cur = _local(cur, t)
    return _text(cur)


def _bic_country(bic: Optional[str]) -> Optional[str]:
    if not bic or len(bic) < 6:
        return None
    return bic[4:6]


class ISO20022Adapter:
    """Namespace-tolerant parser + normalizer for ISO 20022 XML messages."""

    def parse(self, xml: str) -> Dict[str, Any]:
        root = ET.fromstring(xml)
        # Real ISO 20022 envelopes every message in <Document>; simulators often
        # emit the message element directly. Work from the message element.
        node = root
        if root.tag.rsplit("}", 1)[-1] == "Document" and len(root) > 0:
            node = root[0]
        node_tag = node.tag.rsplit("}", 1)[-1]

        # The authoritative message family lives in the XML namespace URI.
        family = None
        ns = node.tag.split("}", 1)[1] if node.tag.startswith("{") else ""
        for f in SUPPORTED_FAMILIES:
            if f in ns:
                family = f
                break
        if family is None:
            name_map = {
                "FIToFICstmrCdtTrf": "pacs.008",
                "CstmrCdtTrfInitn": "pain.001",
                "AcctRpt": "camt.052",
                "Stmt": "camt.053",
            }
            family = name_map.get(node_tag)
        if family is None:
            raise ValueError(f"unsupported ISO 20022 message: {node_tag}")

        grphdr = _local(node, "GrpHdr")
        msg_id = _find_text(node, "GrpHdr", "MsgId")
        created = _find_text(node, "GrpHdr", "CreDtTm")

        if family in ("pacs.008", "pain.001"):
            tx_list = _find_all(node, "CdtTrfTxInf")
            return self._parse_payment(node, grphdr, tx_list, msg_id, created, family)
        return self._parse_report(node, grphdr, msg_id, created)

    # ------------------------------------------------------------------ #
    def _parse_payment(self, root, grphdr, tx_infos, msg_id, created, family="pacs.008") -> Dict[str, Any]:
        total_amt = _find_text(root, "GrpHdr", "TtlIntrBkSttlmAmt") or _find_text(root, "GrpHdr", "CtrlSum")
        ccy = _find_text(root, "GrpHdr", "TtlIntrBkSttlmAmt")
        if ccy:
            node = _local(grphdr, "TtlIntrBkSttlmAmt") if grphdr is not None else None
            ccy = node.get("Ccy") if node is not None else None

        uetr = _find_text(node, "GrpHdr", "MsgId")
        txns = []
        parties = []
        for tx in (tx_infos or []):
            amt = _find_text(tx, "Amt", "InstdAmt") or _find_text(tx, "Amt")
            tx_ccy = None
            amt_node = _local(tx, "Amt")
            if amt_node is not None:
                instd = _local(amt_node, "InstdAmt")
                tx_ccy = instd.get("Ccy") if instd is not None else amt_node.get("Ccy")
                if not amt and amt_node.text:
                    amt = amt_node.text.strip()
            tx_uetr = _local(tx, "UETR")
            if tx_uetr is not None and tx_uetr.text:
                uetr = tx_uetr.text.strip()

            dbtr = _local(tx, "Dbtr")
            dbtr_nm = _find_text(tx, "Dbtr", "Nm")
            dbtr_id = _find_text(tx, "Dbtr", "Id", "OrgId", "Othr", "Id") or _find_text(tx, "Dbtr", "Id", "PrvtId", "Othr", "Id")
            cdtr = _local(tx, "Cdtr")
            cdtr_nm = _find_text(tx, "Cdtr", "Nm")
            cdtr_id = _find_text(tx, "Cdtr", "Id", "OrgId", "Othr", "Id") or _find_text(tx, "Cdtr", "Id", "PrvtId", "Othr", "Id")

            dbtr_agt = _find_text(tx, "DbtrAgt", "FinInstnId", "BICFI") or _find_text(tx, "DbtrAgt", "FinInstnId", "ClrSysMmbId", "MmbId")
            cdtr_agt = _find_text(tx, "CdtrAgt", "FinInstnId", "BICFI") or _find_text(tx, "CdtrAgt", "FinInstnId", "ClrSysMmbId", "MmbId")
            purp = _find_text(tx, "Purp", "Cd") or _find_text(tx, "Purp", "Prtry")
            ctgy_purp = _find_text(tx, "PmtTpInf", "CtgyPurp", "Prtry") or _find_text(tx, "PmtTpInf", "CtgyPurp", "Cd")

            txns.append({
                "instruction_id": _find_text(tx, "PmtId", "InstrId"),
                "end_to_end_id": _find_text(tx, "PmtId", "EndToEndId"),
                "amount": amt,
                "currency": tx_ccy,
                "debtor": dbtr_nm,
                "creditor": cdtr_nm,
                "debtor_bic": dbtr_agt,
                "creditor_bic": cdtr_agt,
                "purpose": purp,
                "category_purpose": ctgy_purp,
                "debtor_country": _bic_country(dbtr_agt),
                "creditor_country": _bic_country(cdtr_agt),
            })
            parties.append({"name": dbtr_nm, "role": "debtor", "id": dbtr_id, "bic": dbtr_agt, "country": _bic_country(dbtr_agt)})
            parties.append({"name": cdtr_nm, "role": "creditor", "id": cdtr_id, "bic": cdtr_agt, "country": _bic_country(cdtr_agt)})

        return {
            "message_family": family,
            "root_tag": node.tag.rsplit("}", 1)[-1],
            "message_id": msg_id,
            "created": created,
            "total_amount": total_amt,
            "currency": ccy,
            "uetr": uetr,
            "transaction_count": len(txns),
            "transactions": txns,
            "parties": [p for p in parties if p["name"] or p["id"]],
        }

    # ------------------------------------------------------------------ #
    def _parse_report(self, root, grphdr, msg_id, created) -> Dict[str, Any]:
        entries = []
        statements = _local_all(root, "Stmt")
        if not statements and root.tag.rsplit("}", 1)[-1] == "Stmt":
            statements = [root]
        for stmt in statements:
            acct = _find_text(stmt, "Acct", "Id", "IBAN") or _find_text(stmt, "Acct", "Id", "Othr", "Id")
            for entry in _local_all(stmt, "Ntry"):
                amt = _find_text(entry, "Amt")
                amt_node = _local(entry, "Amt")
                ccy = amt_node.get("Ccy") if amt_node is not None else None
                db_ind = _find_text(entry, "CdtDbtInd")
                book_date = _find_text(entry, "BookgDt", "Dt")
                purpose = _find_text(entry, "NtryDtls", "TxDtls", "Purp", "Cd")
                counterparty = _find_text(entry, "NtryDtls", "TxDtls", "RltdPties", "Cdtr", "Nm") or _find_text(
                    entry, "NtryDtls", "TxDtls", "RltdPties", "Dbtr", "Nm")
                entries.append({
                    "amount": amt, "currency": ccy, "debit_credit": db_ind,
                    "booked_date": book_date, "purpose": purpose, "counterparty": counterparty,
                })
        return {
            "message_family": "report",
            "root_tag": root.tag.rsplit("}", 1)[-1],
            "message_id": msg_id,
            "created": created,
            "account": acct if "acct" in locals() else None,
            "entries": entries,
            "parties": [],
        }

    def to_analysis_request(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize into the universal metered analysis request."""
        tx = (parsed.get("transactions") or [{}])[0]
        amount = None
        try:
            amount = float(tx.get("amount") or parsed.get("total_amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        return {
            "source": "iso20022",
            "message_id": parsed.get("message_id"),
            "uetr": parsed.get("uetr"),
            "amount": amount,
            "currency": tx.get("currency") or parsed.get("currency"),
            "debtor": tx.get("debtor"),
            "creditor": tx.get("creditor"),
            "debtor_bic": tx.get("debtor_bic"),
            "creditor_bic": tx.get("creditor_bic"),
            "purpose": tx.get("purpose"),
            "category_purpose": tx.get("category_purpose"),
            "parties": parsed.get("parties", []),
        }

    @staticmethod
    def verdict_to_message(verdict: Dict[str, Any]) -> Dict[str, Any]:
        """Map a metered analysis verdict onto an ISO 20022-style response."""
        return {
            "message_family": "protean.verdict",
            "msg_id": verdict.get("message_id"),
            "decision": verdict.get("decision"),
            "risk_score": verdict.get("risk_score"),
            "ofac_blocked": verdict.get("compliance", {}).get("blocked", False),
            "reasons": verdict.get("compliance", {}).get("reasons", []),
            "proof_present": bool(verdict.get("zk_proof_present")),
            "onchain_anchor": verdict.get("onchain_hash", ""),
        }

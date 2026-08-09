"""Hash-chained ledger integrity: concurrent multi-process appends must never
fork the chain, and verify_chain must report failures precisely."""

import subprocess
import sys
import tempfile
from pathlib import Path

from app.core.ledger import HashChainedLedger


def test_concurrent_writers_single_chain():
    with tempfile.TemporaryDirectory() as d:
        db = str(Path(d) / "ledger.db")
        code = (
            "import sys\n"
            "from app.core.ledger import HashChainedLedger\n"
            "led = HashChainedLedger(sys.argv[1])\n"
            "tag = sys.argv[2]\n"
            "for i in range(150):\n"
            "    led.append('CONC_TEST', {'writer': tag, 'i': i}, "
            "tx_hash='0x' + tag + ('%04d' % i), status='ok')\n"
        )
        procs = [
            subprocess.Popen([sys.executable, "-c", code, db, t], cwd=Path(__file__).parent.parent.parent)
            for t in ("A", "B")
        ]
        for p in procs:
            assert p.wait() == 0
        led = HashChainedLedger(db)
        assert led.count() == 300
        res = led.verify_chain()
        assert res["ok"] is True
        assert res["checked"] == 300


def test_verify_chain_reports_bad_position():
    with tempfile.TemporaryDirectory() as d:
        db = str(Path(d) / "ledger.db")
        led = HashChainedLedger(db)
        led.append("A", {"n": 1}, status="ok")
        led.append("B", {"n": 2}, status="ok")
        # Corrupt the middle row so prev_hash no longer matches the head.
        led._conn.execute(
            "UPDATE ledger_entries SET prev_hash = '0'*64 WHERE event_type = 'B'"
        )
        led._conn.commit()
        res = led.verify_chain()
        assert res["ok"] is False
        assert res["first_bad"] == 2
        assert res["checked"] == 2

#!/usr/bin/env python3
"""Run the full Research Receipts flow on a throwaway LOCAL anvil chain and write a demo
receipts.json (docs/demo/receipts.demo.json) for screenshots and the website's verify script.

Everything here is labelled demo: local chain 31337, anvil's PUBLIC dev keys, and the
made-up FIXTURE prices in tests/fixtures/prices.json. Never publish this as a real record.

    python scripts/demo_anvil.py
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from receipts import cli  # noqa: E402

DEV0 = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"   # public anvil key #0
DEV0_ADDR = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"  # address of public anvil key #0

CALLS = [
    ("HOOD", "equity", "Q4 FY2026 earnings", "up", 0.65, "2027-02-10", "2027-02-18"),
    ("COIN", "equity", "Q4 FY2026 earnings", "down", 0.60, "2027-02-10", "2027-02-18"),
    ("NVDA", "equity", "Q4 FY2027 earnings", "up", 0.70, "2027-02-24", "2027-03-04"),
    ("CBRS", "equity", "Q4 FY2026 earnings", "up", 0.60, "2027-02-25", "2027-03-05"),
    ("PURR", "equity", "price horizon", "up", 0.55, "2027-01-15", "2027-01-29"),
    ("HOOD", "equity", "Q1 FY2027 earnings", "up", 0.60, "2027-04-28", "2027-05-06"),  # stays locked
]


def main():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    url = f"http://127.0.0.1:{port}"
    anvil = subprocess.Popen(["anvil", "--port", str(port), "--silent"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(urllib.request.Request(url, data=b'{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}',
                                                              headers={"Content-Type": "application/json"}), timeout=1)
                break
            except Exception:
                time.sleep(0.1)
        dep = json.loads(subprocess.run(["forge", "create", "src/ResearchLedger.sol:ResearchLedger", "--rpc-url", url,
                                         "--private-key", DEV0, "--broadcast", "--json"], cwd=ROOT, check=True,
                                        capture_output=True, text=True).stdout)
        work = Path(tempfile.mkdtemp(prefix="receipts-demo-"))
        os.environ["RECEIPTS_HOME"] = str(work / "home")
        assert cli.main(["init", "--ledger", dep["deployedTo"], "--author", DEV0_ADDR, "--chain-id", "31337",
                         "--rpc", url, "--explorer", "https://explorer.example.invalid"]) == 0
        ids = []
        for i, (t, at, ev, d, c, s0, s1) in enumerate(CALLS):
            call = {"asset_type": at, "baseline": "close on horizon_start_date", "confidence": c,
                    "created_at": "2026-12-15T15:00:00Z", "direction": d, "event": ev,
                    "horizon_end_date": s1, "horizon_start_date": s0, "ticker": t}
            cp, notep = work / f"c{i}.json", work / f"c{i}.md"
            cp.write_text(json.dumps(call))
            notep.write_text(f"# {t} {ev}\nDemo thesis note.\n")
            assert cli.main(["commit", str(cp), str(notep), "--key", "dev-key"]) == 0
        recs = sorted((json.loads(p.read_text()) for p in (work / "home" / "receipts").glob("*.json")), key=lambda r: r["onchain_id"])
        for r in recs:
            if r["call"]["horizon_start_date"] != "2027-04-28":
                assert cli.main(["reveal", str(r["onchain_id"]), "--early", "--key", "dev-key"]) == 0
        assert cli.main(["sync", "--chunk", "1000"]) == 0
        assert cli.main(["score", "--prices", str(ROOT / "tests" / "fixtures" / "prices.json")]) == 0
        out = ROOT / "docs" / "demo" / "receipts.demo.json"
        assert cli.main(["export", "--out", str(out)]) == 0
        data = json.loads(out.read_text())
        data["demo"] = "DEMO: local anvil chain, public dev keys, made-up fixture prices. Not a real track record."
        out.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        print(f"demo written: {out}")
    finally:
        anvil.kill()
        anvil.wait()


if __name__ == "__main__":
    main()

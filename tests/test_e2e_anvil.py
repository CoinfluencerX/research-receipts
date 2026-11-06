"""Full cycle on a real local chain: deploy -> commit -> reveal -> sync -> score -> export.

Uses anvil's well-known PUBLIC development keys (never real keys) and FIXTURE prices
(made-up numbers in tests/fixtures/prices.json). Skipped if Foundry is not installed.
"""
import json
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

from receipts import cli

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "prices.json"
DEV0 = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"  # public anvil key #0
DEV1 = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"  # public anvil key #1
DEV1_ADDR = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"

pytestmark = pytest.mark.skipif(not (shutil.which("anvil") and shutil.which("forge") and shutil.which("cast")),
                                reason="Foundry (anvil/forge/cast) not installed")


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _start_anvil(chain_id=31337):
    port = _free_port()
    proc = subprocess.Popen(["anvil", "--port", str(port), "--chain-id", str(chain_id), "--silent"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            req = urllib.request.Request(url, data=b'{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}',
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=1).read()
            return proc, url
        except Exception:
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("anvil did not start")


@pytest.fixture
def chain():
    proc, url = _start_anvil()
    yield url
    proc.kill()
    proc.wait()


def _deploy(url):
    out = subprocess.run(["forge", "create", "src/ResearchLedger.sol:ResearchLedger", "--rpc-url", url,
                          "--private-key", DEV0, "--broadcast", "--json"], cwd=ROOT, capture_output=True, text=True, check=True)
    data = json.loads(out.stdout)
    return data["deployedTo"], data["transactionHash"]


def _call(tmp, name, **kw):
    c = {"asset_type": "equity", "baseline": "close on horizon_start_date", "confidence": 0.7,
         "created_at": "2026-11-06T12:00:00Z", "direction": "up", "event": "Q4 FY2026 earnings",
         "horizon_end_date": "2027-02-18", "horizon_start_date": "2027-02-10", "ticker": "HOOD"}
    c.update(kw)
    p = tmp / f"{name}.json"
    p.write_text(json.dumps(c))
    note = tmp / f"{name}.md"
    note.write_text(f"# {name}\nThesis text for the e2e test.\n")
    return str(p), str(note)


def test_full_cycle(chain, tmp_path, monkeypatch, capsys):
    home = tmp_path / "home"
    monkeypatch.setenv("RECEIPTS_HOME", str(home))
    monkeypatch.setenv("E2E_PW", "test-only-password")
    ledger, _ = _deploy(chain)

    ks_dir = tmp_path / "keystores"
    ks_dir.mkdir()
    subprocess.run(["cast", "wallet", "import", "e2e", "--keystore-dir", str(ks_dir), "--private-key", DEV1,
                    "--unsafe-password", "test-only-password"], check=True, capture_output=True)
    key = ["--key", f"keystore:{ks_dir / 'e2e'}", "--password-env", "E2E_PW"]

    assert cli.main(["init", "--ledger", ledger, "--author", DEV1_ADDR, "--chain-id", "31337",
                     "--rpc", chain, "--explorer", "http://explorer.local"]) == 0

    hood = _call(tmp_path, "hood")
    coin = _call(tmp_path, "coin", ticker="COIN", direction="down", confidence=0.6)
    nvda = _call(tmp_path, "nvda", ticker="NVDA", confidence=0.8, horizon_start_date="2027-02-24",
                 horizon_end_date="2027-03-04")
    for c in (hood, coin, nvda):
        assert cli.main(["commit", *c, *key]) == 0

    # Someone else (a different public dev key) commits to the same ledger: must not show in our export.
    other = _call(tmp_path, "other", ticker="COIN")
    subprocess.run(["cast", "send", ledger, "commit(bytes32)", "0x" + "11" * 32, "--rpc-url", chain,
                    "--private-key", DEV0], check=True, capture_output=True)

    # The salt and call are private: nothing about them is on-chain yet.
    recs = {r["call"]["ticker"]: r for r in json.loads(json.dumps([json.loads(p.read_text())
            for p in (home / "receipts").glob("*.json")]))}
    assert all(r["status"] == "committed" for r in recs.values())
    assert oct((home / "receipts").stat().st_mode)[-3:] == "700"

    # Revealing before the horizon ends is refused unless --early.
    with pytest.raises(SystemExit):
        cli.main(["reveal", str(recs["HOOD"]["onchain_id"]), *key])
    for t in ("HOOD", "COIN"):
        assert cli.main(["reveal", str(recs[t]["onchain_id"]), "--early", *key]) == 0

    # A tampered salt can never reveal (the chain itself rejects it).
    rec = recs["NVDA"]
    rec_path = home / "receipts" / f"{rec['local_id']}.json"
    tampered = dict(rec, salt="0x" + "00" * 32)
    rec_path.write_text(json.dumps(tampered))
    capsys.readouterr()
    assert cli.main(["reveal", str(rec["onchain_id"]), "--early", *key]) == 2
    assert "CommitmentMismatch" in capsys.readouterr().err
    rec_path.write_text(json.dumps(rec))  # restore

    assert cli.main(["sync", "--chunk", "1000"]) == 0
    assert cli.main(["score", "--prices", str(FIXTURE)]) == 0
    out = tmp_path / "receipts.json"
    assert cli.main(["export", "--out", str(out)]) == 0
    data = json.loads(out.read_text())

    assert data["network"]["chain_id"] == 31337
    rows = {r["id"]: r for r in data["receipts"]}
    assert len(rows) == 3  # the stranger's commit is filtered out by author
    revealed = [r for r in rows.values() if r["status"] == "revealed"]
    locked = [r for r in rows.values() if r["status"] == "locked"]
    assert len(revealed) == 2 and len(locked) == 1
    assert all(r["verified"] for r in revealed)
    assert {r["call"]["ticker"] for r in revealed} == {"HOOD", "COIN"}
    assert all(r["score"]["hit"] is True for r in revealed)  # fixture: HOOD 50->54 up, COIN 200->190 down
    assert data["summary"]["n"] == 2 and data["summary"]["hits"] == 2 and data["summary"]["too_few_to_judge"]

    # The locked call leaks nothing: no ticker, call, or salt in the public file.
    lk = locked[0]
    assert set(lk) == {"id", "status", "commitment", "committed_at", "commit_tx", "commit_tx_url"}
    text = out.read_text()
    assert rec["salt"] not in text and "NVDA" not in text and rec["call_json"] not in text


def test_refuses_non_testnet_chain(tmp_path, monkeypatch):
    proc, url = _start_anvil(chain_id=1)  # pretend Ethereum mainnet
    try:
        monkeypatch.setenv("RECEIPTS_HOME", str(tmp_path / "home"))
        with pytest.raises(SystemExit) as e:
            cli.main(["init", "--ledger", "0x" + "11" * 20, "--author", DEV1_ADDR, "--chain-id", "1",
                      "--rpc", url, "--explorer", "http://x"])
        assert "testnet" in str(e.value).lower()
        with pytest.raises(SystemExit) as e:
            cli.main(["init", "--ledger", "0x" + "11" * 20, "--author", DEV1_ADDR, "--chain-id", "31337",
                      "--rpc", url, "--explorer", "http://x"])
        assert "testnet" in str(e.value).lower() or "refusing" in str(e.value).lower()
    finally:
        proc.kill()
        proc.wait()


def test_dev_key_refused_on_robinhood_testnet():
    from receipts.wallet import WalletError, key_args

    with pytest.raises(WalletError):
        key_args("dev-key", 46630)
    assert key_args("dev-key", 31337)[0][0] == "--private-key"


def test_password_file_is_removed_after_send(tmp_path, monkeypatch):
    """The keystore password goes to cast via a 0600 temp file that never outlives the call."""
    import tempfile as tf

    from receipts import wallet

    made = []
    real = tf.mkstemp

    def spy(*a, **k):
        fd, path = real(*a, **k)
        made.append(path)
        return fd, path

    monkeypatch.setattr(wallet.tempfile, "mkstemp", spy)
    monkeypatch.setenv("PWVAR", "secret")
    monkeypatch.setattr(wallet.shutil, "which", lambda _: "/bin/false")
    with pytest.raises(wallet.WalletError):
        wallet.send("0x" + "11" * 20, "commit(bytes32)", ["0x" + "22" * 32], "http://127.0.0.1:1", 31337,
                    "keystore:/nonexistent", env_var="PWVAR")
    assert made and not any(Path(p).exists() for p in made)

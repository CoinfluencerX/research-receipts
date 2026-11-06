"""Private local state in ~/.research-receipts (chmod 700). Holds call files and SALTS:
they must never be committed to git, logged, or shared before reveal."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

TESTNETS = {46630: "Robinhood Chain Testnet", 31337: "Local anvil"}
DEFAULTS = {
    "chain_id": 46630,
    "rpc_url": "https://rpc.testnet.chain.robinhood.com",          # docs.robinhood.com/chain/connecting
    "explorer": "https://explorer.testnet.chain.robinhood.com",     # docs.robinhood.com/chain/connecting
}


def home() -> Path:
    return Path(os.environ.get("RECEIPTS_HOME", Path.home() / ".research-receipts")).expanduser()


def _secure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    os.chmod(p, 0o700)
    return p


def write_private(path: Path, obj) -> None:
    _secure_dir(path.parent)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def read(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


class Store:
    def __init__(self, root: Path | None = None):
        self.root = _secure_dir(root or home())
        self.calls_dir = _secure_dir(self.root / "receipts")

    @property
    def config_path(self) -> Path:
        return self.root / "config.json"

    def config(self) -> dict:
        cfg = read(self.config_path)
        if not cfg:
            raise SystemExit("Not set up yet. Run: receipts init --ledger <address> --author <your testnet address>")
        return cfg

    def save_config(self, cfg: dict) -> None:
        write_private(self.config_path, cfg)

    def new_record(self, rec: dict) -> dict:
        rec = dict(rec, local_id=rec.get("local_id") or uuid.uuid4().hex[:12])
        write_private(self.calls_dir / f"{rec['local_id']}.json", rec)
        return rec

    def save_record(self, rec: dict) -> None:
        write_private(self.calls_dir / f"{rec['local_id']}.json", rec)

    def records(self) -> list:
        return [json.loads(p.read_text()) for p in sorted(self.calls_dir.glob("*.json"))]

    def find(self, ref: str) -> dict:
        for r in self.records():
            if r["local_id"] == ref or (r.get("onchain_id") is not None and str(r["onchain_id"]) == str(ref)):
                return r
        raise SystemExit(f"No local receipt with id {ref!r} (use `receipts status`)")

    def chain_view(self) -> dict:
        return read(self.root / "chain.json", {"receipts": []})

    def save_chain_view(self, view: dict) -> None:
        write_private(self.root / "chain.json", view)

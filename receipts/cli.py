"""`receipts`: commit, reveal, sync, score and export research calls.

    receipts init --ledger 0x... --author 0x... --start-block N
    receipts template HOOD --event "Q4 FY2026 earnings" --start 2027-02-10 --end 2027-02-18 > hood.json
    receipts commit hood.json hood-note.md            # locks the call on-chain, keeps salt locally
    receipts status                                    # your private local view
    receipts reveal <id>                               # after horizon_end_date
    receipts sync                                      # read Committed/Revealed events from the chain
    receipts score                                     # live prices (or --prices fixture.json)
    receipts export --out receipts.json                # public file for the website
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import secrets
import sys
from pathlib import Path

from . import abi, calls, scoring
from .prices import FixturePrices, LivePrices
from .rpc import RPC
from .store import DEFAULTS, TESTNETS, Store
from .wallet import WalletError, send

DEFAULT_KEY = os.environ.get("RECEIPTS_KEY", "account:receipts-testnet")


def _check_chain(cfg: dict) -> RPC:
    rpc = RPC(cfg["rpc_url"])
    live = rpc.chain_id()
    if live not in TESTNETS:
        raise SystemExit(f"Refusing: RPC is chain {live}. Research Receipts runs on testnets only {sorted(TESTNETS)}.")
    if live != cfg["chain_id"]:
        raise SystemExit(f"Refusing: RPC chain {live} != configured chain {cfg['chain_id']}.")
    return rpc


def _addr(a: str) -> str:
    a = a.strip()
    if not (a.startswith("0x") and len(a) == 42):
        raise SystemExit(f"not an address: {a}")
    int(a, 16)
    return a


def cmd_init(a, store: Store) -> None:
    cfg = {
        "chain_id": a.chain_id, "rpc_url": a.rpc, "explorer": a.explorer.rstrip("/"),
        "ledger": _addr(a.ledger), "author": _addr(a.author), "start_block": a.start_block,
        "network": TESTNETS.get(a.chain_id, "unknown"),
    }
    if cfg["chain_id"] not in TESTNETS:
        raise SystemExit(f"Refusing chain {cfg['chain_id']}: testnets only {sorted(TESTNETS)}.")
    rpc = _check_chain(cfg)
    code = rpc.call("eth_getCode", [cfg["ledger"], "latest"])
    if code in ("0x", "0x0", None):
        raise SystemExit(f"No contract at {cfg['ledger']} on chain {cfg['chain_id']}.")
    store.save_config(cfg)
    print(f"Configured {cfg['network']} ledger {cfg['ledger']} for author {cfg['author']} (data in {store.root})")


def cmd_template(a, store: Store) -> None:
    call = {
        "asset_type": a.asset_type or "equity",
        "baseline": calls.BASELINE, "confidence": a.confidence, "created_at": calls.now_utc(),
        "direction": a.direction, "event": a.event, "horizon_end_date": a.end, "horizon_start_date": a.start,
        "thesis_sha256": "filled in from your note by `receipts commit`", "ticker": a.ticker,
    }
    print(json.dumps(call, indent=2, sort_keys=True))


def _prepare_call(call_path: Path, note_path: Path) -> dict:
    call = json.loads(call_path.read_text())
    sha = calls.sha256_file(note_path)
    existing = call.get("thesis_sha256", "")
    if existing and len(existing) == 64 and existing != sha:
        raise SystemExit("thesis_sha256 in the call does not match the note file. Remove it or fix the note.")
    call["thesis_sha256"] = sha
    if not calls._TS.match(str(call.get("created_at", ""))):
        call["created_at"] = calls.now_utc()
    return call


def cmd_commit(a, store: Store) -> None:
    cfg = store.config()
    call = _prepare_call(Path(a.call), Path(a.note))
    call_json = calls.canonical_json(call)  # validates
    if call["horizon_start_date"] <= dt.date.today().isoformat() and not a.allow_late:
        raise SystemExit("Refusing: the horizon has already started. Commit before horizon_start_date "
                         "(or pass --allow-late, and say so publicly).")
    rpc = _check_chain(cfg)
    salt = "0x" + secrets.token_hex(32)
    commitment = abi.commitment(cfg["author"], cfg["chain_id"], cfg["ledger"], call_json, salt)
    onchain = rpc.eth_call(cfg["ledger"], abi.encode_commitment_for(cfg["author"], call_json, salt), cfg["author"])
    if onchain.lower() != commitment.lower():
        raise SystemExit("Commitment mismatch between this tool and the contract. Nothing was sent.")
    # Save locally BEFORE sending, so the salt can never be lost.
    rec = store.new_record({"call": json.loads(call_json), "call_json": call_json, "salt": salt,
                            "commitment": commitment, "note_path": str(Path(a.note).resolve()),
                            "status": "sending", "chain_id": cfg["chain_id"], "ledger": cfg["ledger"]})
    try:
        receipt = send(cfg["ledger"], "commit(bytes32)", [commitment], cfg["rpc_url"], cfg["chain_id"],
                       a.key, a.password_keychain, a.password_env)
    except WalletError as e:
        rec["status"] = "send_failed"
        store.save_record(rec)
        raise SystemExit(f"{e}\nYour call and salt are saved locally as {rec['local_id']}; nothing is on-chain.")
    logs = [lg for lg in receipt["logs"] if lg["topics"][0].lower() == abi.COMMITTED_TOPIC]
    ev = abi.decode_committed(logs[0])
    if ev["author"].lower() != cfg["author"].lower():
        print(f"WARNING: committed from {ev['author']}, but config author is {cfg['author']}.", file=sys.stderr)
    rec.update(status="committed", onchain_id=ev["id"], commit_tx=receipt["transactionHash"],
               commit_block=int(receipt["blockNumber"], 16), committed_at=ev["committed_at"])
    store.save_record(rec)
    print(f"Committed receipt #{ev['id']} ({call['ticker']}, hidden until reveal)")
    print(f"  tx: {cfg['explorer']}/tx/{receipt['transactionHash']}")
    print(f"  reveal on or after {call['horizon_end_date']}:  receipts reveal {ev['id']}")


def cmd_reveal(a, store: Store) -> None:
    cfg = store.config()
    rec = store.find(a.id)
    if rec.get("status") != "committed":
        raise SystemExit(f"Receipt {a.id} is {rec.get('status')}, not committed.")
    end = rec["call"]["horizon_end_date"]
    if dt.date.today().isoformat() < end and not a.early:
        raise SystemExit(f"Not yet: the horizon ends {end}. Revealing early leaks the call (use --early to override).")
    _check_chain(cfg)
    receipt = send(cfg["ledger"], "reveal(uint256,string,bytes32)", [rec["onchain_id"], rec["call_json"], rec["salt"]],
                   cfg["rpc_url"], cfg["chain_id"], a.key, a.password_keychain, a.password_env)
    rec.update(status="revealed", reveal_tx=receipt["transactionHash"])
    store.save_record(rec)
    print(f"Revealed receipt #{rec['onchain_id']}: {cfg['explorer']}/tx/{receipt['transactionHash']}")


def cmd_sync(a, store: Store) -> None:
    cfg = store.config()
    rpc = _check_chain(cfg)
    latest = rpc.block_number()
    author_topic = "0x" + "0" * 24 + cfg["author"][2:].lower()
    found: dict = {}
    times: dict = {}
    start = cfg.get("start_block", 0)
    step = a.chunk
    for frm in range(start, latest + 1, step):
        to = min(frm + step - 1, latest)
        for topic, kind in ((abi.COMMITTED_TOPIC, "commit"), (abi.REVEALED_TOPIC, "reveal")):
            for lg in rpc.get_logs(cfg["ledger"], [topic, None, author_topic], frm, to):
                blk = int(lg["blockNumber"], 16)
                if kind == "commit":
                    ev = abi.decode_committed(lg)
                    found.setdefault(ev["id"], {}).update(id=ev["id"], author=ev["author"], commitment=ev["commitment"],
                                                         committed_at=ev["committed_at"], commit_block=blk,
                                                         commit_tx=lg["transactionHash"])
                else:
                    ev = abi.decode_revealed(lg)
                    if blk not in times:
                        times[blk] = rpc.block_timestamp(blk)
                    found.setdefault(ev["id"], {}).update(call_json=ev["call_json"], salt=ev["salt"],
                                                         call_hash=ev["call_hash"], revealed_at=times[blk],
                                                         reveal_block=blk, reveal_tx=lg["transactionHash"])
    out = []
    for rid in sorted(found):
        r = found[rid]
        r["status"] = "revealed" if "call_json" in r else "locked"
        if r["status"] == "revealed":
            # Independent check: recompute the commitment from what was revealed.
            r["verified"] = abi.commitment(r["author"], cfg["chain_id"], cfg["ledger"], r["call_json"],
                                           r["salt"]).lower() == r["commitment"].lower()
            r["call"] = json.loads(r["call_json"])
        out.append(r)
    store.save_chain_view({"synced_at": calls.now_utc(), "latest_block": latest, "receipts": out})
    n_rev = sum(1 for r in out if r["status"] == "revealed")
    print(f"Synced {len(out)} receipts ({n_rev} revealed, {len(out) - n_rev} locked) up to block {latest}")


def cmd_score(a, store: Store) -> None:
    view = store.chain_view()
    prices = FixturePrices(a.prices) if a.prices else LivePrices()
    scored = []
    for r in view["receipts"]:
        if r["status"] == "revealed" and r.get("verified"):
            s = scoring.score_call(r["call"], prices)
            s["id"] = r["id"]
            scored.append(s)
    summary = scoring.summarize(scored)
    view["scores"] = {str(s["id"]): s for s in scored}
    view["summary"] = summary
    view["prices_source"] = "fixture (made-up test data)" if a.prices else "live (yfinance / Hyperliquid public API)"
    store.save_chain_view(view)
    hr = "n/a" if summary["hit_rate"] is None else f"{summary['hit_rate']:.0%}"
    br = "n/a" if summary["brier"] is None else f"{summary['brier']:.3f}"
    print(f"Scored {summary['n']} calls: hit rate {hr}, Brier {br}"
          + (" (too few to judge)" if summary["too_few_to_judge"] else ""))


def build_export(cfg: dict, view: dict) -> dict:
    """The PUBLIC file. Locked receipts expose only what is already public on-chain."""
    scores = view.get("scores", {})
    rows = []
    for r in view["receipts"]:
        row = {
            "id": r["id"], "status": r["status"], "commitment": r["commitment"],
            "committed_at": dt.datetime.fromtimestamp(r["committed_at"], dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "commit_tx": r["commit_tx"], "commit_tx_url": f"{cfg['explorer']}/tx/{r['commit_tx']}",
        }
        if r["status"] == "revealed":
            row.update(
                verified=r.get("verified", False), call=r["call"], salt=r["salt"],
                revealed_at=dt.datetime.fromtimestamp(r["revealed_at"], dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                reveal_tx=r["reveal_tx"], reveal_tx_url=f"{cfg['explorer']}/tx/{r['reveal_tx']}",
                score=scores.get(str(r["id"])),
            )
        rows.append(row)
    return {
        "schema": "research-receipts/v1",
        "generated_at": calls.now_utc(),
        "network": {"name": TESTNETS.get(cfg["chain_id"], "unknown"), "chain_id": cfg["chain_id"],
                    "explorer": cfg["explorer"], "ledger": cfg["ledger"],
                    "ledger_url": f"{cfg['explorer']}/address/{cfg['ledger']}"},
        "author": cfg["author"],
        "summary": view.get("summary") or scoring.summarize([]),
        "prices_source": view.get("prices_source"),
        "receipts": rows,
        "disclaimer": "Testnet research record. Paper calls for education, not investment advice.",
    }


def cmd_export(a, store: Store) -> None:
    data = build_export(store.config(), store.chain_view())
    text = json.dumps(data, indent=2, sort_keys=True)
    if a.out == "-":
        print(text)
    else:
        Path(a.out).write_text(text + "\n")
        print(f"Wrote {a.out} ({len(data['receipts'])} receipts)")


def cmd_status(a, store: Store) -> None:
    for r in store.records():
        c = r["call"]
        print(f"{r['local_id']}  #{r.get('onchain_id', '-'):>3}  {r['status']:<11} {c['ticker']:<6} {c['direction']:<4} "
              f"{c['confidence']:.2f}  {c['horizon_start_date']} -> {c['horizon_end_date']}  ({c['event']})")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="receipts", description="Research Receipts (Robinhood Chain testnet)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def key_opts(sp):
        sp.add_argument("--key", default=DEFAULT_KEY, help="account:<name> | keystore:<path> | dev-key (anvil only)")
        sp.add_argument("--password-keychain", help="macOS Keychain service holding the keystore password")
        sp.add_argument("--password-env", help="env var holding the keystore password")

    s = sub.add_parser("init")
    s.add_argument("--ledger", required=True)
    s.add_argument("--author", required=True, help="your testnet wallet address")
    s.add_argument("--start-block", type=int, default=0, help="block the ledger was deployed in")
    s.add_argument("--chain-id", type=int, default=DEFAULTS["chain_id"])
    s.add_argument("--rpc", default=DEFAULTS["rpc_url"])
    s.add_argument("--explorer", default=DEFAULTS["explorer"])
    s = sub.add_parser("template")
    s.add_argument("ticker")
    s.add_argument("--event", required=True)
    s.add_argument("--start", required=True)
    s.add_argument("--end", required=True)
    s.add_argument("--direction", default="up", choices=["up", "down"])
    s.add_argument("--confidence", type=float, default=0.6)
    s.add_argument("--asset-type", choices=["equity", "crypto"],
                   help="default equity. PURR: equity = Hyperliquid Strategies (Nasdaq), crypto = Hyperliquid spot token")
    s = sub.add_parser("commit")
    s.add_argument("call")
    s.add_argument("note")
    s.add_argument("--allow-late", action="store_true")
    key_opts(s)
    s = sub.add_parser("reveal")
    s.add_argument("id")
    s.add_argument("--early", action="store_true")
    key_opts(s)
    s = sub.add_parser("sync")
    s.add_argument("--chunk", type=int, default=50_000)
    s = sub.add_parser("score")
    s.add_argument("--prices", help="fixture JSON of made-up prices (tests/demos only)")
    s = sub.add_parser("export")
    s.add_argument("--out", default="receipts.json")
    sub.add_parser("status")
    return p


def main(argv: list | None = None) -> int:
    a = build_parser().parse_args(argv)
    store = Store()
    try:
        {"init": cmd_init, "template": cmd_template, "commit": cmd_commit, "reveal": cmd_reveal, "sync": cmd_sync,
         "score": cmd_score, "export": cmd_export, "status": cmd_status}[a.cmd](a, store)
    except (calls.CallError, WalletError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

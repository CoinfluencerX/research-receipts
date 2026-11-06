"""Just enough ABI encoding/decoding for ResearchLedger (no web3 dependency)."""
from __future__ import annotations

from .keccak import keccak256

COMMITTED_SIG = "Committed(uint256,address,bytes32,uint64)"
REVEALED_SIG = "Revealed(uint256,address,bytes32,string,bytes32)"
COMMITTED_TOPIC = "0x" + keccak256(COMMITTED_SIG.encode()).hex()
REVEALED_TOPIC = "0x" + keccak256(REVEALED_SIG.encode()).hex()


def _hex(b: str) -> bytes:
    b = b[2:] if b.startswith("0x") else b
    return bytes.fromhex(b)


def word_address(addr: str) -> bytes:
    raw = _hex(addr)
    if len(raw) != 20:
        raise ValueError(f"bad address {addr}")
    return b"\x00" * 12 + raw


def word_uint(n: int) -> bytes:
    return int(n).to_bytes(32, "big")


def word_bytes32(h: str) -> bytes:
    raw = _hex(h)
    if len(raw) != 32:
        raise ValueError("expected 32 bytes")
    return raw


def commitment(author: str, chain_id: int, ledger: str, call_json: str, salt: str) -> str:
    """keccak256(abi.encode(author, chainid, ledger, keccak256(bytes(callJson)), salt))."""
    call_hash = keccak256(call_json.encode("utf-8"))
    enc = word_address(author) + word_uint(chain_id) + word_address(ledger) + call_hash + word_bytes32(salt)
    return "0x" + keccak256(enc).hex()


def selector(sig: str) -> str:
    return keccak256(sig.encode()).hex()[:8]


def encode_commitment_for(author: str, call_json: str, salt: str) -> str:
    """Calldata for commitmentFor(address,string,bytes32) to cross-check on-chain."""
    data = call_json.encode("utf-8")
    padded = data + b"\x00" * ((32 - len(data) % 32) % 32)
    head = word_address(author) + word_uint(96) + word_bytes32(salt)
    return "0x" + selector("commitmentFor(address,string,bytes32)") + (head + word_uint(len(data)) + padded).hex()


def decode_committed(log: dict) -> dict:
    t = log["topics"]
    data = _hex(log["data"])
    return {
        "id": int(t[1], 16),
        "author": "0x" + t[2][-40:],
        "commitment": "0x" + t[3][2:].rjust(64, "0"),
        "committed_at": int.from_bytes(data[:32], "big"),
    }


def decode_revealed(log: dict) -> dict:
    t = log["topics"]
    data = _hex(log["data"])
    call_hash = "0x" + data[0:32].hex()
    off = int.from_bytes(data[32:64], "big")
    salt = "0x" + data[64:96].hex()
    ln = int.from_bytes(data[off:off + 32], "big")
    call_json = data[off + 32:off + 32 + ln].decode("utf-8")
    return {"id": int(t[1], 16), "author": "0x" + t[2][-40:], "call_hash": call_hash,
            "call_json": call_json, "salt": salt}

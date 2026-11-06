"""Hashing, the call format, and commitment encoding, cross-checked against Foundry's `cast`."""
import json
import shutil
import subprocess

import pytest

from receipts import abi, calls
from receipts.keccak import keccak256, keccak_hex

CAST = shutil.which("cast")
ALICE = "0x328809Bc894f92807417D2dAD6b7C998c1aFdac6"
LEDGER = "0x5FbDB2315678afecb367f032d93F642f64180aa3"
SALT = "0x" + "ab" * 32


def good_call(**over):
    c = {
        "asset_type": "equity", "baseline": calls.BASELINE, "confidence": 0.65,
        "created_at": "2027-01-20T14:00:00Z", "direction": "up", "event": "Q4 FY2026 earnings",
        "horizon_end_date": "2027-02-18", "horizon_start_date": "2027-02-10",
        "thesis_sha256": "0" * 64, "ticker": "HOOD",
    }
    c.update(over)
    return c


def test_keccak_known_vectors():
    assert keccak256(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    assert keccak256(b"abc").hex() == "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45"
    # multi-block input (> 136-byte rate)
    assert len(keccak256(b"x" * 1000)) == 32


@pytest.mark.skipif(not CAST, reason="Foundry cast not installed")
@pytest.mark.parametrize("s", ["", "hello", "x" * 135, "x" * 136, "x" * 137, "Robinhood Chain ✓"])
def test_keccak_matches_cast(s):
    out = subprocess.run([CAST, "keccak", s], capture_output=True, text=True, check=True).stdout.strip()
    assert keccak_hex(s.encode()) == out


def test_canonical_json_is_sorted_and_compact():
    j = calls.canonical_json(good_call())
    assert " " not in j.replace("Q4 FY2026 earnings", "").replace(calls.BASELINE, "")
    assert list(json.loads(j)) == sorted(json.loads(j))
    assert calls.canonical_json(dict(reversed(list(good_call().items())))) == j


@pytest.mark.parametrize("bad", [
    {"ticker": "hood"}, {"asset_type": "bond"}, {"direction": "sideways"}, {"confidence": 0.4},
    {"confidence": 1.0}, {"confidence": 0.655}, {"confidence": True}, {"horizon_end_date": "2027-02-01"},
    {"baseline": "open"}, {"thesis_sha256": "XYZ"}, {"created_at": "2027-01-20"}, {"horizon_start_date": "2027-13-01"},
])
def test_validation_rejects_bad_calls(bad):
    with pytest.raises((calls.CallError, ValueError)):
        calls.canonical_json(good_call(**bad))


def test_validation_rejects_extra_and_missing_fields():
    with pytest.raises(calls.CallError):
        calls.validate(dict(good_call(), price_target=99))
    c = good_call()
    del c["ticker"]
    with pytest.raises(calls.CallError):
        calls.validate(c)


@pytest.mark.skipif(not CAST, reason="Foundry cast not installed")
def test_commitment_matches_cast_abi_encode():
    j = calls.canonical_json(good_call())
    call_hash = keccak_hex(j.encode())
    enc = subprocess.run([CAST, "abi-encode", "f(address,uint256,address,bytes32,bytes32)",
                          ALICE, "46630", LEDGER, call_hash, SALT], capture_output=True, text=True, check=True).stdout.strip()
    expected = subprocess.run([CAST, "keccak", enc], capture_output=True, text=True, check=True).stdout.strip()
    assert abi.commitment(ALICE, 46630, LEDGER, j, SALT) == expected


@pytest.mark.skipif(not CAST, reason="Foundry cast not installed")
def test_commitment_for_calldata_matches_cast_calldata():
    j = calls.canonical_json(good_call())
    expected = subprocess.run([CAST, "calldata", "commitmentFor(address,string,bytes32)", ALICE, j, SALT],
                              capture_output=True, text=True, check=True).stdout.strip()
    assert abi.encode_commitment_for(ALICE, j, SALT) == expected


def test_event_topics():
    assert abi.COMMITTED_TOPIC == keccak_hex(b"Committed(uint256,address,bytes32,uint64)")
    assert abi.REVEALED_TOPIC == keccak_hex(b"Revealed(uint256,address,bytes32,string,bytes32)")

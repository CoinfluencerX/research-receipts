import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("secret_scan", Path(__file__).parents[1] / "scripts" / "secret_scan.py")
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)

REAL_LOOKING = "0x" + "4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318"


def names(path, text):
    return {h[2] for h in ss.scan_text(path, text)}


def test_blocks_private_keys_and_flags():
    assert "private key" in names("x.py", f"PRIVATE_KEY={REAL_LOOKING}")
    assert "private key flag" in names("run.sh", f"cast send --private-key {REAL_LOOKING}")


def test_allows_public_anvil_keys():
    anvil = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    assert not names("tests/t.py", f'DEV0 = "{anvil}"  # private_key {anvil}')


def test_blocks_salts_outside_demo_and_tests():
    line = '"salt": "0x' + "ab" * 32 + '"'
    assert "salt" in names("notes/my-call.json", line)
    assert not names("docs/demo/receipts.demo.json", line)


def test_blocks_keystores_env_files_and_password_env():
    # Test inputs are assembled at runtime so this file never contains the patterns itself.
    keystore_like = '{"cry' + 'pto": {"ci' + 'pher": "aes-128-ctr", "ci' + 'phertext": "00"}}'
    assert "keystore file" in names("k.json", keystore_like)
    assert "blocked file type" in names(".env", "")
    assert "blocked file type" in names("keystores/receipts-testnet", "")
    assert "password env" in names("x.sh", "ETH_" + "PASSWORD=" + "hunter2hunter2")


def test_blocks_mnemonics():
    words = " ".join(["abandon"] * 11 + ["about"])
    assert "mnemonic" in names("m.txt", f"mnemonic: {words}")


def test_clean_text_passes():
    assert not names("README.md", "keccak256(abi.encode(author, chainid, ledger, callHash, salt))")

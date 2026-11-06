"""Send transactions with Foundry's `cast`, never touching raw keys in this process.

Key sources (pick with --key or RECEIPTS_KEY):
  account:<name>   Foundry ENCRYPTED keystore in ~/.foundry/keystores (recommended).
                   Password: cast prompts you, or --password-keychain <service> reads it from the
                   macOS Keychain, or --password-env <VAR> reads it from an env var. The password is
                   handed to cast through a 0600 temp file that is deleted right after (cast's
                   ETH_PASSWORD is a password-FILE path; passing --password would expose it in `ps`).
                   It is never printed or kept.
  keystore:<path>  An encrypted keystore file at a path (same password options).
  dev-key          Anvil's well-known PUBLIC development key. Refused on any chain except 31337.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

ANVIL_DEV_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"  # public anvil key #0


class WalletError(RuntimeError):
    pass


def _password(keychain: str | None, env_var: str | None) -> str | None:
    if keychain:
        r = subprocess.run(["security", "find-generic-password", "-s", keychain, "-w"], capture_output=True, text=True)
        if r.returncode != 0:
            raise WalletError(f"no Keychain item for service {keychain!r} (see docs/DEPLOY-MAC.md)")
        return r.stdout.rstrip("\n")
    if env_var:
        if env_var not in os.environ:
            raise WalletError(f"env var {env_var} is not set")
        return os.environ[env_var]
    return None


def key_args(source: str, chain_id: int, keychain: str | None = None, env_var: str | None = None):
    """Returns (cast args, password or None) for a key source."""
    env = _password(keychain, env_var)
    if source.startswith("account:"):
        return ["--account", source.split(":", 1)[1]], env
    if source.startswith("keystore:"):
        return ["--keystore", source.split(":", 1)[1]], env
    if source == "dev-key":
        if chain_id != 31337:
            raise WalletError("dev-key is only allowed on a local anvil chain (31337)")
        return ["--private-key", ANVIL_DEV_KEY], env
    raise WalletError(f"unknown key source {source!r}; use account:<name>, keystore:<path> or dev-key")


def send(ledger: str, sig: str, args: list, rpc_url: str, chain_id: int, source: str,
         keychain: str | None = None, env_var: str | None = None) -> dict:
    cast = shutil.which("cast")
    if not cast:
        raise WalletError("Foundry's `cast` is not installed (see README: Install)")
    kargs, password = key_args(source, chain_id, keychain, env_var)
    cmd = [cast, "send", ledger, sig, *map(str, args), "--rpc-url", rpc_url, "--chain", str(chain_id), "--json", *kargs]
    env = {k: v for k, v in os.environ.items() if k != "ETH_PASSWORD"}
    pw_file = None
    try:
        if password is not None:
            fd, pw_file = tempfile.mkstemp(prefix="receipts-pw-")
            os.chmod(pw_file, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(password)
            env["ETH_PASSWORD"] = pw_file  # cast reads this as --password-file
        r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    finally:
        if pw_file and os.path.exists(pw_file):
            os.remove(pw_file)
    if r.returncode != 0 or not r.stdout.strip():
        # cast can exit 0 on keystore errors, so empty output also counts as failure.
        # Some cast versions print the revert reason on stdout, others on stderr: keep both.
        detail = "\n".join(x for x in (r.stderr.strip(), r.stdout.strip()) if x) or "no output from cast"
        tail = "\n".join(detail.splitlines()[-4:])
        raise WalletError("transaction failed: " + tail)
    receipt = json.loads(r.stdout)
    if receipt.get("status") not in ("0x1", 1, "1"):
        raise WalletError(f"transaction reverted: {receipt.get('transactionHash')}")
    return receipt

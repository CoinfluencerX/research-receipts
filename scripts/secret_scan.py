#!/usr/bin/env python3
"""Block private keys, keystores, mnemonics and unrevealed salts from ever being committed.

    python scripts/secret_scan.py            # scan staged files (pre-commit hook)
    python scripts/secret_scan.py --all      # scan every tracked file (CI)

Allowed on purpose:
- Anvil's well-known PUBLIC development keys (used only in tests/demo against a local chain).
- Salts inside docs/demo/ and tests/: those are demo or test values, and a REVEALED salt is public anyway.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ANVIL_PUBLIC_KEYS = {
    "ac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",  # anvil #0
    "59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",  # anvil #1
}
SALT_OK_PREFIXES = ("docs/demo/", "tests/")
HEX64 = r"(?:0x)?([0-9a-fA-F]{64})\b"
RULES = [
    ("private key", re.compile(r"(?i)(private[_-]?key|privkey|secret[_-]?key|PRIVATE_KEY)[\"'\s:=]+" + HEX64)),
    ("private key flag", re.compile(r"--private-key[\s=]+" + HEX64)),
    ("salt", re.compile(r"(?i)\"?salt\"?\s*[:=]\s*\"?" + HEX64)),
    ("keystore file", re.compile(r"\"crypto\"\s*:\s*\{[^}]*\"cipher(text|params)?\"", re.S)),
    ("password env", re.compile(r"(?i)(ETH_PASSWORD|CAST_PASSWORD|RECEIPTS_PASSWORD)\s*=\s*[^\s$]{4,}")),
    ("mnemonic", re.compile(r"(?i)(mnemonic|seed[_ ]?phrase)[\"'\s:=]+([a-z]+\s+){11,23}[a-z]+")),
]
BLOCKED_PATHS = re.compile(r"(^|/)(\.env(\..*)?|.*\.key|keystores?/.*|\.research-receipts/.*)$")


def scan_text(path: str, text: str) -> list:
    hits = []
    if BLOCKED_PATHS.search(path):
        hits.append((path, 0, "blocked file type"))
    for lineno, line in enumerate(text.splitlines(), 1):
        for name, rx in RULES:
            for m in rx.finditer(line):
                value = next((g for g in m.groups()[::-1] if g and re.fullmatch(r"[0-9a-fA-F]{64}", g)), None)
                if value and value.lower() in ANVIL_PUBLIC_KEYS:
                    continue
                if name == "salt" and path.startswith(SALT_OK_PREFIXES):
                    continue
                hits.append((path, lineno, name))
    return hits


def files(all_tracked: bool) -> list:
    cmd = ["git", "ls-files"] if all_tracked else ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"]
    return [f for f in subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.splitlines() if f]


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    hits = []
    for f in files("--all" in argv):
        p = Path(f)
        if f.startswith("lib/") or not p.is_file() or p.suffix in {".png", ".jpg", ".gif"}:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        hits.extend(scan_text(f, text))
    for path, line, name in hits:
        print(f"BLOCKED {name}: {path}:{line}", file=sys.stderr)
    if hits:
        print("Secret scan failed. Keys, keystores and unrevealed salts must never be committed.", file=sys.stderr)
        return 1
    print("secret scan: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

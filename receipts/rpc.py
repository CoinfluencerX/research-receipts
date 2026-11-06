"""Minimal JSON-RPC client (stdlib only)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


class RPCError(RuntimeError):
    pass


class RPC:
    def __init__(self, url: str, timeout: int = 30):
        self.url = url
        self.timeout = timeout
        self._id = 0

    def call(self, method: str, params: list, retries: int = 3):
        self._id += 1
        body = json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}).encode()
        last = None
        for attempt in range(retries):
            try:
                req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 (configured RPC URL)
                    resp = json.loads(r.read())
                if "error" in resp:
                    raise RPCError(f"{method}: {resp['error']}")
                return resp["result"]
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last = e
                time.sleep(0.5 * (2 ** attempt))
        raise RPCError(f"{method}: {last}")

    def chain_id(self) -> int:
        return int(self.call("eth_chainId", []), 16)

    def block_number(self) -> int:
        return int(self.call("eth_blockNumber", []), 16)

    def eth_call(self, to: str, data: str, frm: str | None = None) -> str:
        tx = {"to": to, "data": data}
        if frm:
            tx["from"] = frm
        return self.call("eth_call", [tx, "latest"])

    def get_logs(self, address: str, topics: list, from_block: int, to_block: int) -> list:
        return self.call("eth_getLogs", [{"address": address, "topics": topics,
                                          "fromBlock": hex(from_block), "toBlock": hex(to_block)}])

    def block_timestamp(self, number: int) -> int:
        return int(self.call("eth_getBlockByNumber", [hex(number), False])["timestamp"], 16)

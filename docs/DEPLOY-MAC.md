# Deploy and run Research Receipts from your Mac

Copy-paste, in order. Everything here is **Robinhood Chain testnet** (chain ID 46630). Your key never leaves your Mac.

Network facts are from Robinhood's docs ([connecting](https://docs.robinhood.com/chain/connecting), [deploy a contract](https://docs.robinhood.com/chain/deploy-smart-contracts)):

| | Testnet |
|---|---|
| Chain ID | `46630` (confirmed live with `cast chain-id`) |
| Public RPC | `https://rpc.testnet.chain.robinhood.com` (rate-limited, fine for a few transactions) |
| Explorer | `https://explorer.testnet.chain.robinhood.com` (Blockscout; API at `/api/`) |

## 1. Install the tools (once)
```
curl -L https://foundry.paradigm.xyz | bash && foundryup
```
Or, if that host is blocked: `npm i -g @foundry-rs/forge @foundry-rs/cast @foundry-rs/anvil`. You also need Python 3.9+ (`python3 --version`).

## 2. Get the code and run the tests
```
git clone --recurse-submodules https://github.com/CoinfluencerX/research-receipts ~/Developer/research-receipts
cd ~/Developer/research-receipts
forge test
python3 -m venv .venv && .venv/bin/pip install -e '.[dev,prices]'
.venv/bin/pytest -q
git config core.hooksPath .githooks
```
The last line turns on the secret scan before every commit.

## 3. Create a NEW testnet-only wallet (never your real wallet)
```
mkdir -p ~/.foundry/keystores
cast wallet new ~/.foundry/keystores receipts-testnet
```
- It asks for a password (hidden) and prints only your new **address**. The key is stored encrypted, so there's nothing to copy or paste.
- Save the password in your macOS Keychain so the CLI can use it without you typing it each time:
  ```
  security add-generic-password -s research-receipts-testnet -a "$USER" -w
  ```
  It prompts for the password. Don't type the password on the command line.
- Note your address:
  ```
  cast wallet address --account receipts-testnet
  ```

## 4. Get free testnet ETH
Use one of these faucets (sources are third-party, so check the page loads):
- Robinhood Chain testnet faucet: https://faucet.testnet.chain.robinhood.com (listed in BitGo's developer docs).
- Alchemy's Robinhood Testnet faucet: https://www.alchemy.com/faucets/robinhood-testnet (Alchemy is Robinhood's recommended provider).

Check the balance:
```
cast balance $(cast wallet address --account receipts-testnet) --rpc-url robinhood_testnet --ether
```
Deploying used about 0.54M gas in a dry run, so a tiny amount of test ETH is plenty.

## 5. Deploy the contract
```
forge script script/Deploy.s.sol --rpc-url robinhood_testnet --account receipts-testnet --broadcast
```
It refuses any chain except 46630 or a local anvil. Copy the printed `ResearchLedger deployed at 0x…` address and the transaction hash, then get the deployment block:
```
cast receipt <DEPLOY_TX_HASH> blockNumber --rpc-url robinhood_testnet
```
Verify the source on the explorer (command from Robinhood's docs, with testnet values):
```
forge verify-contract <LEDGER_ADDRESS> src/ResearchLedger.sol:ResearchLedger \
  --chain-id 46630 --rpc-url robinhood_testnet \
  --verifier blockscout --verifier-url https://explorer.testnet.chain.robinhood.com/api/
```
Then open `https://explorer.testnet.chain.robinhood.com/address/<LEDGER_ADDRESS>`. It should show "Contract source code verified".

## 6. Point the CLI at your ledger
```
.venv/bin/receipts init --ledger <LEDGER_ADDRESS> --author <YOUR_ADDRESS> --start-block <DEPLOY_BLOCK>
```
Your calls and salts live in `~/.research-receipts/` (private, chmod 700). Back that folder up: **without a salt, a call can never be revealed.**

## 7. Dry run: one real receipt (a 1-week PURR stock call)
```
.venv/bin/receipts template PURR --event "price horizon" --start <TOMORROW> --end <TOMORROW+7> --direction up --confidence 0.55 > ~/purr-dryrun.json
printf '# PURR dry run\nTesting the receipts flow end to end.\n' > ~/purr-dryrun.md
.venv/bin/receipts commit ~/purr-dryrun.json ~/purr-dryrun.md --password-keychain research-receipts-testnet
```
A week later:
```
.venv/bin/receipts reveal <ID> --password-keychain research-receipts-testnet
.venv/bin/receipts sync && .venv/bin/receipts score && .venv/bin/receipts export --out ~/data/research-receipts/receipts.json
```
`~/data` is the site's production data folder (per its `AGENTS.md`). franklineth.ai/receipts picks the file up once the page is merged.

PURR here is Hyperliquid Strategies on Nasdaq (`--asset-type equity`, the default), priced via yfinance and compared with SPY like the other names. If `--start` falls on a weekend, the baseline is the last close before it. (`--asset-type crypto` would score the Hyperliquid spot token instead; it isn't part of the plan.)

## 8. Merge the website page (check for drift first)
The page is on branch `feat/research-receipts-page` of `franklineth-blog-work`. Production on this Mac has differed from GitHub before, so check first:
```
cd ~/franklineth-blog-work
git status --short
git fetch origin
git log --oneline HEAD..origin/main
git diff --stat origin/main
```
- **If `git status` is clean and the diff is only what you expect:**
  ```
  git merge origin/feat/research-receipts-page
  npm run verify:receipts
  launchctl kickstart -k gui/$(id -u)/ai.franklineth.site
  ```
- **If there are uncommitted changes or unexpected differences, stop** and have Claude look before merging. Don't overwrite production.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Refusing: RPC is chain …` | You're pointed at a non-testnet RPC. Use `robinhood_testnet`. |
| `transaction failed … insufficient funds` | Get testnet ETH (step 4). |
| `no Keychain item for service` | Re-run the `security add-generic-password` line in step 3. |
| `Not yet: the horizon ends …` | Reveals wait until the horizon ends, by design. |
| `Commitment mismatch … Nothing was sent` | The tool and contract disagree. Don't force it; open an issue. |

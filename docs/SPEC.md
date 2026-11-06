# Research Receipts: full spec (agreed 2026-11-06)

---
created: 2026-11-06
status: active
type: project
---

Build "Research Receipts": a tamper-proof, publicly verifiable track record of my stock and crypto calls on the Robinhood Chain testnet, plus a page on franklineth.ai, as a portfolio project for equity research / fintech / crypto employers (Robinhood especially).

## Context
- I'm Franklin (Temple econ, graduating May 2027), targeting equity research in tech/crypto. This project shows research discipline, honesty, and engineering.
- Repos: CoinfluencerX/research-receipts (new, PUBLIC, all project code goes here) and CoinfluencerX/franklineth-blog-work (my site; add the page on a branch).
- Do NOT put wallet or signing code in alpha-engine (its guardrail tests forbid it). You may copy its scoring ideas (significance.py, point-in-time discipline).

## How it works
1. Commit: before an event, I write a call. Its fingerprint goes on-chain; the content stays private.
2. Reveal: after the horizon, I publish the call and salt. The contract checks it matches the fingerprint.
3. Score: hit or miss against real prices. Brier score and calibration across all revealed calls.

## Call format (canonical JSON: sorted keys, no whitespace, UTF-8)
{ticker, asset_type: "equity"|"crypto", event (e.g. "Q4 FY2026 earnings" or "price horizon"), direction: "up"|"down", horizon_start_date, horizon_end_date, baseline: "close on horizon_start_date", confidence: 0.50–0.99, thesis_sha256 (hash of my full written note), created_at}

First names: HOOD, COIN, NVDA, Cerebras (verify the ticker and listing; alpha-engine config uses CBRS), PURR (Hyperliquid spot token).
- PURR calls are price-horizon calls, not earnings.
- PURR prices come from Hyperliquid's PUBLIC read-only info API, or CoinGecko. Read-only data only: no Hyperliquid accounts, trading or signing.
- Equity prices come from yfinance or an equivalent free source.

## Build
1. Contract `ResearchLedger.sol` (Foundry):
   - commit(bytes32) and reveal(id, callJson, salt).
   - Commitment = keccak256(abi.encode(msg.sender, block.chainid, address(this), keccak256(bytes(callJson)), salt)), so a commitment can't be replayed or copied by another address or chain.
   - Events for commits and reveals; reveal only by the original author; no double reveal.
   - No funds, no owner/admin, no upgradeability, no external calls.
   - Tests first: unit tests plus fuzz tests (wrong salt, wrong author, wrong chain/contract, double reveal, tampered JSON). Gas snapshot.
2. Deploy script for the Robinhood Chain TESTNET only.
   - Take chain ID, RPC, faucet and explorer from Robinhood's official docs (docs.robinhood.com/chain). Don't guess them. If a host is blocked, request access properly.
   - Verify the source on the explorer.
3. Python CLI `receipts` (my Mac runs it):
   - init, commit <call.json> <note.md>, reveal <id>, sync (read events from chain), score, export (writes receipts.json for the site).
   - Salts and call files live in ~/.research-receipts/ (chmod 700), never in the repo.
   - Private key: a NEW testnet-only wallet I create on my Mac, read from the macOS Keychain or an env var at run time. Never printed, logged, committed, or sent to the cloud.
4. Scoring:
   - Hit/miss using point-in-time closes; per-call return over the horizon versus SPY for equities.
   - Brier score, calibration buckets, hit rate with a confidence interval, and a "too few calls to judge" flag under 10 reveals.
   - Unit tests with fixed price fixtures, clearly labeled.
5. Site page /receipts on a branch of franklineth-blog-work, following that repo's existing stack and style:
   - Rendered from exported receipts.json (no wallet connection, no RPC calls from the browser).
   - Table: ticker, committed at (block time + explorer link), status (locked/revealed), call, outcome, score.
   - Summary: hit rate, Brier, calibration chart.
   - "How it works / why it's tamper-proof" explainer.
   - Disclaimer: testnet, paper research, not investment advice.
   - Mobile-friendly.
   - Before merging anything, check whether the GitHub copy of the site matches production on my Mac (it has diverged before). Tell me rather than overwrite.
6. Repo quality, since employers will read it:
   - README with an architecture diagram, threat model (what the commitment proves and doesn't), how to verify a receipt yourself with `cast`, and a demo GIF or screenshots.
   - MIT license. GitHub Actions CI (forge test + pytest).
   - .gitignore and a pre-commit secret scan that blocks keys and salts.
7. End-to-end demo:
   - Deploy and run a full commit → reveal → sync → score → export cycle on a local anvil chain in tests.
   - Give me exact copy-paste steps to deploy and make my first real commits from my Mac.

## Rules
- Testnet only. No mainnet, no real funds, no trading, no Hyperliquid account interaction.
- I run deployments and commits from my Mac with my own key. Claude never holds a key that represents me.
- Tests before code. Show real command output and exit codes. Never fake a chain result.
- Work on branches. Push research-receipts main only when CI is green. The site change stays on a branch for my review.
- Everything public-facing stays general: no personalized advice. Add a compliance note to the README (an employer may restrict public stock calls).

## Done when
- research-receipts CI is green, the contract is verified on the Robinhood Chain testnet explorer (or exact steps are ready for me to deploy it), and the README is employer-ready.
- The /receipts page is on a site branch with a screenshot.
- I have a one-page "first calls" checklist: how to write and commit my HOOD, COIN, NVDA, Cerebras and PURR calls in January before the February reports, and when to reveal each.

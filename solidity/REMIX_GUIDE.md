# Deploying MPCAuction.sol via Remix IDE — step by step

Remix is a browser IDE; you don't install anything. Total time: **~15 minutes**, all free.

---

## Prerequisites

1. **Chrome / Brave / Firefox** browser
2. **MetaMask** extension installed and unlocked (https://metamask.io)
3. **A fresh wallet** in MetaMask, never used on Ethereum mainnet
4. **~0.5 Sepolia ETH** in that wallet (we'll get this from a faucet)

If you already have MetaMask but only with a mainnet account, click the account avatar → **Add account** → create a new one. Keep mainnet keys far away from this work.

---

## Step 1 — Get Sepolia ETH from a faucet

Try in this order. The first one that works is fine; 0.05 ETH is enough.

| Faucet | URL | Requirement | Reward |
|---|---|---|---|
| Alchemy | https://sepoliafaucet.com | free Alchemy account | 0.5 ETH/day |
| QuickNode | https://faucet.quicknode.com/ethereum/sepolia | Twitter/X account | 0.05 ETH |
| Infura | https://www.infura.io/faucet/sepolia | Infura account | 0.5 ETH |
| PoW faucet | https://sepolia-faucet.pk910.de | none — solve PoW in browser | up to 1 ETH |
| Chainlink | https://faucets.chain.link/sepolia | GitHub login | 0.1 ETH |

Paste your MetaMask account address (starts with `0x...`), submit, wait ~30 seconds. The ETH should appear in MetaMask once you switch to the Sepolia network (top dropdown in MetaMask → "Show test networks" must be enabled in Settings).

If the faucet refuses ("your account is too new" / "not eligible"), use the PoW faucet — it never refuses.

---

## Step 2 — Connect MetaMask to Sepolia

1. Open MetaMask.
2. Click the network dropdown at the top (probably says "Ethereum Mainnet").
3. Toggle **Show test networks** in MetaMask Settings → Advanced if you don't see it.
4. Select **Sepolia**.
5. Confirm your account now shows the test ETH balance (~0.5 ETH).

---

## Step 3 — Open Remix

1. Go to **https://remix.ethereum.org** in your browser.
2. The default workspace opens. If a tutorial pops up, dismiss it.
3. In the left sidebar, click the **File explorer** icon (top icon).
4. Right-click anywhere in the file tree → **New File**.
5. Name it `MPCAuction.sol`.
6. Open `MPCAuction.sol` from this repo (`solidity/MPCAuction.sol`), copy its entire contents, and paste into the Remix editor.

---

## Step 4 — Compile

1. Click the **Solidity compiler** icon in the left sidebar (looks like a stylised "S").
2. **Compiler version**: select `0.8.20+commit.a1b79de6` (or the closest `0.8.20`).
3. **Language**: Solidity.
4. **EVM Version**: `default` (Cancun is also fine).
5. **Enable optimization**: tick the box. **Runs**: `200`.
6. Click the big **Compile MPCAuction.sol** button.
7. You should see a green ✓. If you see a red ✗, scroll the editor to find the underlined error — usually a copy-paste glitch on a missing brace.

---

## Step 5 — Deploy to Sepolia

1. Click the **Deploy & Run Transactions** icon in the left sidebar (a stylised "D" with an arrow).
2. **Environment** dropdown: select **Injected Provider — MetaMask**. MetaMask will pop up asking to connect; accept.
3. Confirm the **Account** field shows your Sepolia address and balance.
4. The **Contract** dropdown should show `MPCAuction - MPCAuction.sol`.
5. Constructor parameters (the `▸` expand button next to the orange **Deploy** button):
   - `_MINDEPOSIT`: `1000000000000000` (= 0.001 ETH in wei)
   - `_REGISTRATIONWINDOW`: `3600` (1 hour, in seconds)
   - `_COMMITWINDOW`: `3600`
   - `_SHAREWINDOW`: `3600`
6. Click **Deploy**.
7. MetaMask pops up showing the deployment transaction with the estimated gas. Click **Confirm**.
8. Wait ~15 seconds for the Sepolia block. The deployed contract appears under **Deployed Contracts** at the bottom-left.

---

## Step 6 — Find the contract on Sepolia Etherscan

1. In the **Deployed Contracts** list, expand your contract.
2. Click the clipboard icon next to the contract address to copy it.
3. Open https://sepolia.etherscan.io.
4. Paste the address into the search bar.
5. You should see a one-transaction history showing the contract creation.

**Save this URL** — it goes into your paper as a footnote citing the artifact:

```latex
\footnote{Sepolia deployment at
\url{https://sepolia.etherscan.io/address/0xYOUR_CONTRACT_ADDRESS}.}
```

---

## Step 7 — Drive a full auction interactively from Remix

In the **Deployed Contracts** panel, your contract exposes every public function. You can run a full auction by hand (good for understanding) or programmatically from Python (faster — see below). Manual walkthrough:

1. **Call `register()`** with **Value = 0.001 ETH** (set in the *Value* field above the function list, units = "ether"). This registers the currently-selected MetaMask account.
2. To register a second bidder, click the **Account** dropdown in Remix → select another MetaMask account → click `register()` again with 0.001 ETH. (You'll need a second funded Sepolia account; MetaMask lets you add multiple).
3. **Call `advancePhase()`** (admin-only — must be the deploying account).
4. **Call `submitCommitment(C, pi)`** with synthetic test data:
   - `C`: `0x` followed by any 64 hex chars (e.g. `0xaaaa...aaaa`)
   - `pi`: `0x` followed by 192 hex chars (96 bytes)
5. `advancePhase()` → `submitShareHashes(root)` → `advancePhase()` → `finalize(winner, bid, openingHash)`.

Every call gets a Sepolia transaction hash and a gas cost reported in Remix's console.

---

## Step 8 — Automated benchmark from Python (recommended)

For the gas table that goes into the paper, you want consistent numbers across `n = 5, 10, 20`. Don't do this by hand in Remix; use the Python driver:

1. Back in MetaMask, go to **Account details → Show private key**. Copy the 64-char hex (with `0x` prefix).
2. In your terminal:
   ```bash
   cd icst2026/solidity
   cp ../../.env.example .env   # if you've created one; otherwise:
   ```
3. Create `.env`:
   ```
   SEPOLIA_RPC_URL=https://eth-sepolia.g.alchemy.com/v2/YOUR_ALCHEMY_KEY
   SEPOLIA_PRIVATE_KEY=0xYOUR_PRIVATE_KEY
   ```
4. Run:
   ```bash
   pip install -r ../requirements.txt
   python deploy_and_run.py --n 5
   python deploy_and_run.py --n 10
   python deploy_and_run.py --n 20
   ```

Each run takes ~3–8 minutes (Sepolia block time + n+3 transactions). At the end you'll get three JSON files (`gas_result_n5.json`, etc.) with the real gas numbers to paste into Table 3 of the paper.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| MetaMask says "Insufficient funds" | Top up from a different faucet |
| Remix won't connect to MetaMask | Refresh the page, then click "Injected Provider" again |
| Transaction "out of gas" | Increase gas limit in MetaMask's confirmation popup to 500,000 |
| `register()` reverts with "deposit too low" | You set Value = 0 in Remix; set it to 0.001 ether |
| `submitCommitment` reverts with "proof too short" | `pi` must be at least 96 bytes (192 hex chars) |
| `advancePhase` reverts with "not admin" | You're calling from a non-deployer account; switch back to the deploying account in MetaMask |
| Gas numbers vary 5–10% between runs | Normal — Sepolia base fee fluctuates. Report the average of 3 runs. |

---

## What this gives you

After Step 5 you have **a real, verifiable, on-chain artifact**: a contract address on Sepolia that anyone can inspect. This is the difference between "we simulated a blockchain in Python" (what the original draft had) and "we deployed to Ethereum and these are our real gas numbers" (what the ICST submission claims).

The contract address goes:
1. Into Table 3 caption as a footnote
2. Into the GitHub repo README
3. Into the artifact-availability statement at submission
4. (Optionally) into a "Verified Contract" badge if you submit the source to Etherscan via Remix's *Etherscan plugin* — totally free and adds credibility.

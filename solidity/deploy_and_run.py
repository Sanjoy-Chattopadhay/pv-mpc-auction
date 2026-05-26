#!/usr/bin/env python3
"""
deploy_and_run.py
==================

Deploys the MPCAuction.sol smart contract to Ethereum's Sepolia testnet
and drives a full five-phase auction end-to-end, recording the real
gas cost of each transaction.

Outputs the gas table referenced as Table~3 in the ICST 2026 paper.

------------------------------------------------------------------------
Prerequisites
------------------------------------------------------------------------
  pip install web3 py-solc-x python-dotenv

  Sepolia testnet account funded from a faucet (e.g. https://sepoliafaucet.com
  or https://www.alchemy.com/faucets/ethereum-sepolia).
  Get free Sepolia ETH (~0.5 ETH is more than enough).

  Set the following environment variables OR put them in a `.env` file
  in the same directory:

      SEPOLIA_RPC_URL=https://sepolia.infura.io/v3/<YOUR_INFURA_PROJECT_ID>
      SEPOLIA_PRIVATE_KEY=0x<YOUR_64_HEX_PRIVATE_KEY>      # admin / deployer
      # Optional: more accounts for additional bidders
      BIDDER_PRIVATE_KEYS=0x...,0x...,0x...

  Alternative RPC providers: Alchemy, QuickNode, Ankr, Public RPC.
  Never use mainnet keys here.  USE A FRESH KEY.

------------------------------------------------------------------------
Run
------------------------------------------------------------------------
  python deploy_and_run.py             # default: 5 bidders
  python deploy_and_run.py --n 10      # 10 bidders
  python deploy_and_run.py --n 20      # 20 bidders (Sepolia faucet ETH ~0.6)

The script:
  1. Compiles MPCAuction.sol via solc 0.8.20
  2. Deploys it to Sepolia, records deployment gas
  3. Generates n bidder wallets (HD-derived from the admin seed) and
     funds them from the admin account
  4. Runs Phase 1 (register), Phase 2 (commit), Phase 3 (share-hash)
  5. Advances to Result, calls finalize() with a synthetic winner
  6. Prints a gas-usage table compatible with Table 3 of the paper
"""

import argparse
import hashlib
import json
import os
import secrets
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from solcx import compile_source, install_solc, set_solc_version
from web3 import Web3
from eth_account import Account

# Sepolia is post-Merge PoS, so no PoA middleware is needed. (In web3.py
# 7+, `geth_poa_middleware` was renamed to `ExtraDataToPOAMiddleware`;
# we don't inject any middleware here.)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SOLC_VERSION = "0.8.20"
CONTRACT_FILE = Path(__file__).parent / "MPCAuction.sol"

MIN_DEPOSIT_WEI = Web3.to_wei(0.001, "ether")  # 0.001 ETH per bidder
REGISTRATION_WINDOW = 60 * 60       # 1 hour
COMMIT_WINDOW       = 60 * 60
SHARE_WINDOW        = 60 * 60

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def banner(msg: str) -> None:
    print()
    print("=" * 72)
    print(msg)
    print("=" * 72)


def wait_for_receipt(w3: Web3, tx_hash, label: str) -> dict:
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=600)
    status = "OK" if receipt.status == 1 else "FAIL"
    print(f"  {label:<32}  {status}  gas={receipt.gasUsed:>10,}  "
          f"block={receipt.blockNumber}")
    return receipt


def boosted_gas_price(w3: Web3) -> int:
    """Sepolia gets congested; bid 1.5x the reported gas price to ensure
    timely inclusion. Returns wei/gas as an int."""
    return int(w3.eth.gas_price * 3 // 2)


def fund_bidder(w3: Web3, admin: Account, bidder_addr: str, amount_wei: int):
    nonce = w3.eth.get_transaction_count(admin.address, "pending")
    tx = {
        "to":       bidder_addr,
        "value":    amount_wei,
        "gas":      21_000,
        "gasPrice": boosted_gas_price(w3),
        "nonce":    nonce,
        "chainId":  w3.eth.chain_id,
    }
    signed = admin.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(getattr(signed, "raw_transaction", None) or signed.rawTransaction)
    return wait_for_receipt(w3, tx_hash, f"fund {bidder_addr[:10]}...")


def compile_contract():
    print(f"[+] Installing solc {SOLC_VERSION}...")
    install_solc(SOLC_VERSION)
    set_solc_version(SOLC_VERSION)
    source = CONTRACT_FILE.read_text()
    compiled = compile_source(
        source,
        output_values=["abi", "bin"],
        optimize=True,
        optimize_runs=200,
        solc_version=SOLC_VERSION,
    )
    # Find the contract entry
    name = [k for k in compiled if k.endswith(":MPCAuction")][0]
    return compiled[name]["abi"], compiled[name]["bin"]


def deploy_contract(w3: Web3, admin: Account, abi: list, bytecode: str):
    print("[+] Deploying MPCAuction.sol to Sepolia ...")
    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    nonce = w3.eth.get_transaction_count(admin.address, "pending")
    tx = contract.constructor(
        MIN_DEPOSIT_WEI,
        REGISTRATION_WINDOW,
        COMMIT_WINDOW,
        SHARE_WINDOW,
    ).build_transaction({
        "from":     admin.address,
        "nonce":    nonce,
        "gas":      3_000_000,
        "gasPrice": boosted_gas_price(w3),
        "chainId":  w3.eth.chain_id,
    })
    signed = admin.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(getattr(signed, "raw_transaction", None) or signed.rawTransaction)
    receipt = wait_for_receipt(w3, tx_hash, "deploy MPCAuction")
    contract_addr = receipt.contractAddress
    print(f"    -> contract address: {contract_addr}")
    print(f"    -> Sepolia explorer: https://sepolia.etherscan.io/address/"
          f"{contract_addr}")
    return contract_addr, receipt.gasUsed


def send_tx(w3: Web3, account: Account, fn_call, value_wei: int = 0):
    nonce = w3.eth.get_transaction_count(account.address, "pending")
    # Gas limit 200k: register/commit/share-hash all use ~135-167k actual
    # gas (measured on Sepolia), so 200k gives 20% headroom while keeping
    # the per-tx wallet lockup small enough for our 0.008 ETH bidder budget.
    tx = fn_call.build_transaction({
        "from":     account.address,
        "nonce":    nonce,
        "gas":      200_000,
        "gasPrice": boosted_gas_price(w3),
        "value":    value_wei,
        "chainId":  w3.eth.chain_id,
    })
    signed = account.sign_transaction(tx)
    return w3.eth.send_raw_transaction(getattr(signed, "raw_transaction", None) or signed.rawTransaction)


def fake_pedersen_commitment(bid: int) -> bytes:
    """Stand-in for the off-chain Pedersen commitment digest."""
    return hashlib.sha256(bid.to_bytes(32, "big") +
                          secrets.token_bytes(32)).digest()


def fake_schnorr_proof() -> bytes:
    """Stand-in for the off-chain Schnorr Pedersen-opening proof bytes."""
    return secrets.token_bytes(96)  # tau || s_m || s_r, 32 bytes each


def fake_share_hash_root() -> bytes:
    """Merkle root over {H(s_{i,j})}_j -- synthetic for gas measurement."""
    return hashlib.sha256(secrets.token_bytes(64)).digest()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=5,
                        help="number of bidders (default 5)")
    args = parser.parse_args()
    n = args.n
    if n < 2 or n > 20:
        sys.exit("--n must be in [2, 20]")

    rpc_url   = os.environ.get("SEPOLIA_RPC_URL")
    admin_key = os.environ.get("SEPOLIA_PRIVATE_KEY")
    if not rpc_url or not admin_key:
        sys.exit("Set SEPOLIA_RPC_URL and SEPOLIA_PRIVATE_KEY env vars.")

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        sys.exit("Web3 connection failed.")
    print(f"[+] Connected to chain {w3.eth.chain_id} "
          f"(Sepolia = 11155111).  Latest block: {w3.eth.block_number}")

    admin = Account.from_key(admin_key)
    print(f"[+] Admin address: {admin.address}")
    bal = w3.eth.get_balance(admin.address)
    print(f"    Balance: {Web3.from_wei(bal, 'ether')} ETH")
    if bal < Web3.to_wei(0.05, "ether"):
        sys.exit("Admin balance < 0.05 ETH; please top up from faucet.")

    # 1. Compile + deploy
    banner("STEP 1  :  compile + deploy MPCAuction.sol")
    abi, bytecode = compile_contract()
    contract_addr, deploy_gas = deploy_contract(w3, admin, abi, bytecode)
    contract = w3.eth.contract(address=contract_addr, abi=abi)

    # 2. Generate n bidder wallets
    banner(f"STEP 2  :  generate + fund {n} bidder wallets")
    bidders = [Account.create() for _ in range(n)]
    # Per-bidder budget: 0.001 ETH deposit + ~0.007 ETH lockup buffer for
    # the three transactions each bidder runs (register, commit, share-hash).
    # Ethereum reserves gas_limit * gas_price upfront, so with our
    # 200k-gas limit (see send_tx) and Sepolia at ~6 gwei * 1.5 boost,
    # each tx ties up ~0.0018 ETH momentarily. 0.008 ETH covers it with
    # plenty of headroom even if Sepolia gas spikes 3x mid-run.
    fund_amount = MIN_DEPOSIT_WEI + Web3.to_wei(0.007, "ether")
    for b in bidders:
        fund_bidder(w3, admin, b.address, fund_amount)

    # 3. Phase 1 - Registration
    banner(f"STEP 3  :  Phase 1 -- register {n} bidders")
    reg_gas = []
    for b in bidders:
        tx_hash = send_tx(w3, b, contract.functions.register(),
                          value_wei=MIN_DEPOSIT_WEI)
        r = wait_for_receipt(w3, tx_hash, f"register {b.address[:8]}")
        reg_gas.append(r.gasUsed)
    avg_reg = sum(reg_gas) // len(reg_gas)

    # Admin advances Reg -> Commit
    tx_hash = send_tx(w3, admin, contract.functions.advancePhase())
    wait_for_receipt(w3, tx_hash, "advancePhase (Reg->Commit)")

    # 4. Phase 2 - Commitment
    banner("STEP 4  :  Phase 2 -- submit Pedersen commitments + ZKPs")
    commit_gas = []
    bids = [secrets.randbelow(1_000_000) for _ in range(n)]
    for b, bid in zip(bidders, bids):
        C  = fake_pedersen_commitment(bid)
        pi = fake_schnorr_proof()
        tx_hash = send_tx(w3, b,
            contract.functions.submitCommitment(C, pi))
        r = wait_for_receipt(w3, tx_hash, f"commit {b.address[:8]}")
        commit_gas.append(r.gasUsed)
    avg_commit = sum(commit_gas) // len(commit_gas)

    tx_hash = send_tx(w3, admin, contract.functions.advancePhase())
    wait_for_receipt(w3, tx_hash, "advancePhase (Commit->Share)")

    # 5. Phase 3 - Share-hash Merkle root
    banner("STEP 5  :  Phase 3 -- submit share-hash Merkle roots")
    share_gas = []
    for b in bidders:
        root = fake_share_hash_root()
        tx_hash = send_tx(w3, b,
            contract.functions.submitShareHashes(root))
        r = wait_for_receipt(w3, tx_hash, f"share-hash {b.address[:8]}")
        share_gas.append(r.gasUsed)
    avg_share = sum(share_gas) // len(share_gas)

    tx_hash = send_tx(w3, admin, contract.functions.advancePhase())
    wait_for_receipt(w3, tx_hash, "advancePhase (Share->Result)")

    # 6. Phase 5 - finalize (off-chain MPC tournament is Phase 4 and
    # happens off-chain among the bidders; the on-chain leg jumps
    # from Share -> Result).
    banner("STEP 6  :  Phase 5 -- finalize with synthetic winner")
    winner_idx = bids.index(max(bids))
    winner = bidders[winner_idx]
    opening_hash = hashlib.sha256(
        bids[winner_idx].to_bytes(32, "big") +
        secrets.token_bytes(32)
    ).digest()
    tx_hash = send_tx(w3, admin, contract.functions.finalize(
        winner.address, bids[winner_idx], opening_hash))
    fin_receipt = wait_for_receipt(w3, tx_hash, "finalize")
    final_gas = fin_receipt.gasUsed

    # 7. Print gas table for the paper
    banner(f"GAS USAGE SUMMARY  --  n = {n}  (Sepolia)")
    print(f"  Deployment ............................. {deploy_gas:>10,} gas")
    print(f"  Phase 1  register()         (avg/bidder) {avg_reg:>10,} gas")
    print(f"  Phase 2  submitCommitment   (avg/bidder) {avg_commit:>10,} gas")
    print(f"  Phase 3  submitShareHashes  (avg/bidder) {avg_share:>10,} gas")
    print(f"  Phase 5  finalize           (one-shot)   {final_gas:>10,} gas")
    total = (deploy_gas + n*avg_reg + n*avg_commit + n*avg_share + final_gas)
    print(f"  ------------------------------------------ ----------")
    print(f"  TOTAL per auction (incl. deploy) .......  {total:>10,} gas")
    print(f"  TOTAL per auction (excl. deploy) .......  "
          f"{total - deploy_gas:>10,} gas")

    # Persist for later re-use
    out = {
        "n":               n,
        "chain_id":        w3.eth.chain_id,
        "contract":        contract_addr,
        "deploy_gas":      deploy_gas,
        "register_gas":    avg_reg,
        "commit_gas":      avg_commit,
        "share_gas":       avg_share,
        "finalize_gas":    final_gas,
        "total_gas":       total,
        "explorer":        f"https://sepolia.etherscan.io/address/{contract_addr}",
        "timestamp":       int(time.time()),
    }
    out_file = Path(__file__).parent / f"gas_result_n{n}.json"
    out_file.write_text(json.dumps(out, indent=2))
    print(f"\n[+] Wrote {out_file}")
    print("[+] Done.")


if __name__ == "__main__":
    main()

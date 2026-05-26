# PV-MPC-Auction

> A privacy-preserving sealed-bid auction protocol composing Pedersen commitments, Shamir secret sharing, and Schnorr zero-knowledge proofs, anchored to an Ethereum smart contract.
>
> Companion code for the paper submitted to **ICST 2026** (8th International Conference on Intelligent Computing and Sustainable Technologies, IIT Patna, August 1–2, 2026).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Solidity 0.8.20](https://img.shields.io/badge/solidity-0.8.20-363636.svg)](https://soliditylang.org/)

---

## What this is

`PV-MPC-Auction` is a five-phase protocol that:

1. **Hides bids** using perfectly-hiding Pedersen commitments.
2. **Distributes custody** via Shamir $(t,n)$ secret sharing — no single party can reconstruct any bid.
3. **Computes the winner** via a bit-decomposed secure greater-than tournament on Shamir shares — without revealing any input bid.
4. **Anchors every state transition** to an Ethereum smart contract (`MPCAuction.sol`) acting as a Merkle-authenticated commitment bulletin board.
5. **Verifies publicly** that the announced winner opens a previously-mined commitment.

The result: a sealed-bid auction with bid privacy, public verifiability, fairness, accountability, and collusion resistance up to $t-1$ corrupt bidders — without FHE, without garbled circuits, and without a trusted setup.

---

## Repository layout

```
.
├── paper-icst2026.tex         <- camera-ready LaTeX (Springer LNCS class)
├── references.bib             <- bibliography
├── README.md                  <- you are here
├── README-ICST.md             <- submission runbook
├── LICENSE                    <- MIT
├── pyproject.toml             <- Python package metadata
├── requirements.txt           <- pip-installable deps
├── src/pv_mpc_auction/        <- the protocol implementation
│   ├── group.py               <- RFC 3526 2048-bit MODP group
│   ├── pedersen.py            <- commitments + Schnorr ZKP
│   ├── shamir.py              <- (t,n) secret sharing
│   ├── secgt.py               <- bit-decomposed secure greater-than
│   ├── chain_sim.py           <- in-memory PoW chain (offline experiments)
│   ├── protocol.py            <- 5-phase orchestration
│   └── benchmark.py           <- regenerates the paper's figures
├── tests/                     <- pytest suite (25+ tests)
├── notebooks/
│   └── PV_MPC_Auction_Colab.ipynb  <- Colab-ready walkthrough
└── solidity/
    ├── MPCAuction.sol         <- 180-line smart contract
    ├── deploy_and_run.py      <- web3.py automated deployment
    └── REMIX_GUIDE.md         <- step-by-step Remix IDE walkthrough
```

---

## Quick start — three paths

### Path A: Colab (zero install, runs in your browser)

1. Open the notebook on Colab:

   [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Sanjoy-Chattopadhay/pv-mpc-auction/blob/main/notebooks/PV_MPC_Auction_Colab.ipynb)

2. Edit Cell 1 to point at your fork.
3. *Runtime → Run all.*
4. ~3 minutes later you have: all primitives demonstrated, a full auction run, and the scalability figure.

### Path B: Local Python (offline experiments only)

```bash
git clone https://github.com/Sanjoy-Chattopadhay/pv-mpc-auction.git
cd pv-mpc-auction
pip install -e ".[dev]"
pytest                          # all tests should pass (~10 seconds)
python -m pv_mpc_auction.benchmark --out figures
```

### Path C: Sepolia deployment (real on-chain artifact)

Two ways:

- **Remix IDE** (browser, no install): see [`solidity/REMIX_GUIDE.md`](solidity/REMIX_GUIDE.md). 15 minutes, free.
- **Python automation** (gas-cost table for the paper):
  ```bash
  cd solidity
  cp .env.example .env       # then edit with your Sepolia RPC + key
  python deploy_and_run.py --n 5
  python deploy_and_run.py --n 10
  python deploy_and_run.py --n 20
  ```

You will need:

- **A Sepolia RPC URL** — free at [Alchemy](https://alchemy.com) or [Infura](https://infura.io).
- **A funded Sepolia private key** — get free testnet ETH from [sepoliafaucet.com](https://sepoliafaucet.com), [QuickNode faucet](https://faucet.quicknode.com/ethereum/sepolia), or [the PoW faucet](https://sepolia-faucet.pk910.de).
- **Never use a key with mainnet funds.** Create a fresh wallet.

---

## Empirical results

Real Sepolia testnet gas costs (measured, n=5):

| Phase | Gas / bidder | Notes |
|---|---:|---|
| Contract deployment (one-shot) | 1,594,691 | independent of n |
| Phase 1 — `register()` | 138,893 | O(1) per bidder |
| Phase 2 — `submitCommitment(C, π)` | 166,816 | O(1) per bidder |
| Phase 3 — `submitShareHashes(root)` | 76,311 | O(1) per bidder |
| Phase 5 — `finalize(...)` | 169,984 at n=5 | scales linearly via refund loop |
| **Total per auction at n=5 (excl. deploy)** | **2,080,084** | well under Ethereum's 30M block limit |

Canonical deployment: **[`0xE8bF0981d3b75413F669279A7A1Fd2807c19a2FB`](https://sepolia.etherscan.io/address/0xE8bF0981d3b75413F669279A7A1Fd2807c19a2FB)** on the Sepolia testnet (Solc 0.8.20, optimizer enabled, 200 runs).

---

## Reproducing the paper's results

| Result | How to reproduce |
|---|---|
| Table 1 (primitive latency) | `python -m pv_mpc_auction.benchmark --out figures`; values in `figures/primitives.json` |
| Figure 3(a) scalability | same command as above; `figures/fig_auction_scalability.pdf` |
| Figure 3(b) FHE comparison | projection from published ratios; numbers hard-coded in `benchmark.py` |
| Table 3 (Sepolia gas) | `python solidity/deploy_and_run.py --n 5` (canonical run committed as `solidity/gas_result_n5.json`; deployed contract: [`0xE8bF...a2FB`](https://sepolia.etherscan.io/address/0xE8bF0981d3b75413F669279A7A1Fd2807c19a2FB)) |
| Table 4 (security comparison) | qualitative — comes from the literature surveyed in §2 |

---

## Test suite

```bash
pytest -v
```

25+ tests covering:

- **Pedersen** — hiding, binding, homomorphic addition, ZKP completeness, ZKP soundness against forged proofs, ZKP rejection of tampered transcripts, proof serialisation.
- **Shamir** — reconstruction from any-`t` subset, linear operations, simulated multiplication, invalid-parameter handling.
- **SecGT** — exhaustive `(a, b)` comparison correctness, tournament correctness on random inputs, edge cases (equal bids, odd-count tournaments), bit-decomposition range checks.
- **End-to-end protocol** — picks the max, chain integrity holds after every run, all phases produce mined blocks, timings non-zero.

---

## Cite this work

If you use this code or paper, please cite:

```bibtex
@inproceedings{chattopadhyay2026pvmpc,
  author    = {Chattopadhyay, Sanjoy},
  title     = {Blockchain-Anchored Sealed-Bid Auctions via {Pedersen} Commitments,
               {Shamir} Sharing, and {Schnorr} Zero-Knowledge Proofs},
  booktitle = {8th International Conference on Intelligent Computing and
               Sustainable Technologies (ICST 2026)},
  publisher = {Springer Lecture Notes in Networks and Systems},
  year      = {2026},
  address   = {Patna, India}
}
```

---

## License

MIT — see [`LICENSE`](LICENSE). Use it freely; please cite the paper if you build on it.

## Contact

**Sanjoy Chattopadhyay** — Assistant Professor, Department of Computer Science & Engineering, Pranveer Singh Institute of Technology (PSIT), Kanpur, India — sanjoy.chattopadhyay@psit.ac.in

## Acknowledgments

Sepolia testnet ETH for the on-chain experiments was sourced from public faucets. Thanks to colleagues at PSIT Kanpur and IIT Patna for early feedback.

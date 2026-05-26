"""Reproduce the scalability and primitive-cost figures used in the paper.

Run as:

    python -m pv_mpc_auction.benchmark --out figures/

This regenerates `fig_auction_scalability.pdf` and the primitive-cost
table reported in §7 of the paper, using the small test group for
speed; pass `--full` to use the production 2048-bit RFC 3526 group.
"""

from __future__ import annotations

import argparse
import json
import secrets
import statistics
import time
from pathlib import Path
from typing import Dict, List

from . import pedersen, shamir
from .group import default_group, small_test_group
from .protocol import run_auction


# -----------------------------------------------------------------------------
# Primitive micro-benchmark
# -----------------------------------------------------------------------------
def bench_primitives(group, trials: int = 50) -> Dict[str, float]:
    """Mean latency (ms) of every cryptographic primitive."""
    out: Dict[str, float] = {}

    # Pedersen commit + verify
    times = []
    for _ in range(trials):
        m = secrets.randbelow(group.q)
        t = time.perf_counter()
        C, r = pedersen.commit(group, m)
        times.append((time.perf_counter() - t) * 1000)
    out["pedersen_commit_ms"] = statistics.mean(times)

    times = []
    C, r = pedersen.commit(group, 42)
    for _ in range(trials):
        t = time.perf_counter()
        pedersen.verify_opening(C, 42, r)
        times.append((time.perf_counter() - t) * 1000)
    out["pedersen_verify_ms"] = statistics.mean(times)

    # ZKP prove + verify
    times = []
    for _ in range(trials):
        m = secrets.randbelow(group.q)
        C, r = pedersen.commit(group, m)
        t = time.perf_counter()
        pedersen.prove(C, m, r)
        times.append((time.perf_counter() - t) * 1000)
    out["zkp_prove_ms"] = statistics.mean(times)

    proof = pedersen.prove(C, 42, r)
    times = []
    for _ in range(trials):
        t = time.perf_counter()
        pedersen.verify(C, proof)
        times.append((time.perf_counter() - t) * 1000)
    out["zkp_verify_ms"] = statistics.mean(times)

    # Shamir split + reconstruct (3, 5)
    times = []
    for _ in range(trials):
        s = secrets.randbelow(group.q)
        t = time.perf_counter()
        shamir.split(s, n=5, t=3, q=group.q)
        times.append((time.perf_counter() - t) * 1000)
    out["shamir_split_3_5_ms"] = statistics.mean(times)

    shares = shamir.split(42, n=5, t=3, q=group.q)
    times = []
    for _ in range(trials):
        t = time.perf_counter()
        shamir.reconstruct(shares[:3], q=group.q)
        times.append((time.perf_counter() - t) * 1000)
    out["shamir_reconstruct_3_5_ms"] = statistics.mean(times)

    return out


# -----------------------------------------------------------------------------
# End-to-end scalability sweep
# -----------------------------------------------------------------------------
def bench_scalability(
    group,
    n_values: List[int],
    bit_length: int = 16,
    trials: int = 3,
) -> List[Dict]:
    """For each n in `n_values`, run the protocol `trials` times.

    Returns a list of records, one per (n, trial).
    """
    records = []
    for n in n_values:
        for k in range(trials):
            bids = [secrets.randbelow(1 << bit_length) for _ in range(n)]
            result = run_auction(
                bids,
                group=group,
                bit_length=bit_length,
                chain_difficulty=1,
            )
            records.append({
                "n": n,
                "trial": k,
                "total_s": result.timings.total,
                "registration_s": result.timings.registration,
                "commitment_s": result.timings.commitment,
                "sharing_s": result.timings.sharing,
                "mpc_s": result.timings.mpc,
                "verification_s": result.timings.verification,
                "winner": result.winner_index,
                "winning_bid": result.winning_bid,
                "verified": result.verified,
            })
            print(f"  n={n:>2}  trial={k}  total={result.timings.total*1000:7.1f} ms  "
                  f"winner=P{result.winner_index}")
    return records


# -----------------------------------------------------------------------------
# Plotting (optional: only if matplotlib is installed)
# -----------------------------------------------------------------------------
def plot_scalability(records: List[Dict], out_path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("[!] matplotlib not installed; skipping plot.")
        return

    # Aggregate per n
    by_n: Dict[int, Dict[str, List[float]]] = {}
    for rec in records:
        n = rec["n"]
        by_n.setdefault(n, {
            "total": [], "registration": [], "commitment": [],
            "sharing": [], "mpc": [], "verification": [],
        })
        by_n[n]["total"].append(rec["total_s"] * 1000)
        by_n[n]["registration"].append(rec["registration_s"] * 1000)
        by_n[n]["commitment"].append(rec["commitment_s"] * 1000)
        by_n[n]["sharing"].append(rec["sharing_s"] * 1000)
        by_n[n]["mpc"].append(rec["mpc_s"] * 1000)
        by_n[n]["verification"].append(rec["verification_s"] * 1000)

    ns = sorted(by_n.keys())
    means = lambda key: [statistics.mean(by_n[n][key]) for n in ns]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    phases = ["registration", "commitment", "sharing", "mpc", "verification"]
    colours = ["#94a3b8", "#3b82f6", "#10b981", "#f59e0b", "#ef4444"]
    bottoms = [0] * len(ns)
    for phase, c in zip(phases, colours):
        vals = means(phase)
        ax1.bar(ns, vals, bottom=bottoms, color=c, label=phase.capitalize())
        bottoms = [b + v for b, v in zip(bottoms, vals)]
    ax1.set_xlabel("Number of bidders n")
    ax1.set_ylabel("Latency (ms)")
    ax1.set_title("(a) Per-phase breakdown")
    ax1.legend(fontsize=8, frameon=False)

    ax2.plot(ns, means("total"), marker="o", color="#1e3a8a")
    ax2.fill_between(
        ns,
        [statistics.mean(by_n[n]["total"]) - statistics.stdev(by_n[n]["total"])
         if len(by_n[n]["total"]) > 1 else statistics.mean(by_n[n]["total"])
         for n in ns],
        [statistics.mean(by_n[n]["total"]) + statistics.stdev(by_n[n]["total"])
         if len(by_n[n]["total"]) > 1 else statistics.mean(by_n[n]["total"])
         for n in ns],
        alpha=0.15,
        color="#1e3a8a",
    )
    ax2.set_xlabel("Number of bidders n")
    ax2.set_ylabel("End-to-end latency (ms)")
    ax2.set_title("(b) Aggregate")
    ax2.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight")
    print(f"[+] Wrote {out_path}")


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("figures"),
                        help="output directory for figures + JSON")
    parser.add_argument("--full", action="store_true",
                        help="use 2048-bit RFC 3526 group (slow but realistic)")
    parser.add_argument("--n-values", type=int, nargs="+",
                        default=[3, 5, 7, 10, 12, 15, 20])
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--bit-length", type=int, default=16)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    group = default_group() if args.full else small_test_group()
    print(f"[+] Group: {group.name}")

    print("[+] Benchmarking primitives...")
    prim = bench_primitives(group, trials=50)
    for k, v in prim.items():
        print(f"  {k:<32} {v:>8.3f} ms")
    (args.out / "primitives.json").write_text(json.dumps(prim, indent=2))

    print("\n[+] Running scalability sweep...")
    records = bench_scalability(
        group,
        n_values=args.n_values,
        bit_length=args.bit_length,
        trials=args.trials,
    )
    (args.out / "scalability.json").write_text(json.dumps(records, indent=2))

    print("\n[+] Plotting...")
    plot_scalability(records, args.out / "fig_auction_scalability.pdf")
    print("\n[+] Done. See", args.out)


if __name__ == "__main__":
    main()

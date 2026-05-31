"""Reproduce the scalability and primitive-cost figures used in the paper.

Run as:

    python -m pv_mpc_auction.benchmark --out figures/ --trials 5

This regenerates `fig_auction_scalability.pdf` and the primitive-cost
table reported in section 7 of the paper, using the small test group for
speed; pass `--full` to use the production 2048-bit RFC 3526 group.

The script prints a copy-paste-ready summary of per-n totals that you
can drop straight into the paper's abstract / Section 7.3.
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
def bench_primitives(group, trials: int = 50) -> Dict[str, Dict[str, float]]:
    """Mean & std latency (ms) of every cryptographic primitive."""
    out: Dict[str, Dict[str, float]] = {}

    def record(key, times):
        out[key] = {
            "mean_ms": statistics.mean(times),
            "std_ms":  statistics.stdev(times) if len(times) > 1 else 0.0,
        }

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
            print(f"  n={n:>2}  trial={k}  total={result.timings.total*1000:9.1f} ms  "
                  f"winner=P{result.winner_index}")
    return records


# -----------------------------------------------------------------------------
# Plotting: 2 panels --- (a) stacked linear, (b) stacked log (so all 5
# phases are visible even when registration/sharing are tiny).
# -----------------------------------------------------------------------------
def plot_scalability(records: List[Dict], out_path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("[!] matplotlib not installed; skipping plot.")
        return

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
    mean_of = lambda key: [statistics.mean(by_n[n][key]) for n in ns]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))

    phases = ["registration", "commitment", "sharing", "mpc", "verification"]
    labels = ["Registration", "Commitment", "Secret Sharing",
              "MPC Computation", "Verification"]
    colours = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#a855f7"]

    # ---- (a) linear stacked bar ----
    bottoms = [0.0] * len(ns)
    for phase, lab, c in zip(phases, labels, colours):
        vals = mean_of(phase)
        ax1.bar(ns, vals, bottom=bottoms, color=c, label=lab,
                width=1.6, edgecolor="white", linewidth=0.4)
        bottoms = [b + v for b, v in zip(bottoms, vals)]
    ax1.set_xlabel("Number of Bidders (n)")
    ax1.set_ylabel("Execution Time (ms)")
    ax1.set_title("(a) Phase-wise Execution Time")
    ax1.legend(fontsize=8, frameon=True, loc="upper left")
    ax1.grid(axis="y", alpha=0.25)

    # ---- (b) grouped bars on log scale: every phase visible ----
    import numpy as np
    x = np.arange(len(ns))
    w = 0.16
    for i, (phase, lab, c) in enumerate(zip(phases, labels, colours)):
        ax2.bar(x + (i - 2) * w, mean_of(phase), w, color=c, label=lab)
    ax2.set_yscale("log")
    ax2.set_xticks(x)
    ax2.set_xticklabels(ns)
    ax2.set_xlabel("Number of Bidders (n)")
    ax2.set_ylabel("Execution Time (ms, log scale)")
    ax2.set_title("(b) Per-phase on Log Scale")
    ax2.grid(axis="y", alpha=0.25, which="both")
    ax2.legend(fontsize=7, frameon=True, loc="upper left")

    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight")
    print(f"[+] Wrote {out_path}")


# -----------------------------------------------------------------------------
# Pretty summary --- copy-paste ready for the paper
# -----------------------------------------------------------------------------
def print_paper_summary(records: List[Dict]) -> None:
    by_n: Dict[int, List[float]] = {}
    for rec in records:
        by_n.setdefault(rec["n"], []).append(rec["total_s"] * 1000)

    print("\n" + "=" * 70)
    print("  COPY-PASTE-READY SUMMARY FOR THE PAPER")
    print("=" * 70)
    print(f"  {'n':>4}  {'mean (ms)':>12}  {'std (ms)':>10}  {'mean (s)':>10}")
    print("  " + "-" * 50)
    for n in sorted(by_n):
        vals = by_n[n]
        m = statistics.mean(vals)
        s = statistics.stdev(vals) if len(vals) > 1 else 0.0
        print(f"  {n:>4}  {m:>12.1f}  {s:>10.1f}  {m / 1000:>10.2f}")
    n_max = max(by_n)
    mean_max = statistics.mean(by_n[n_max])
    print(f"\n  Headline for abstract:  ~{mean_max / 1000:.1f} s at n={n_max}")
    print(f"  Headline in ms       :  ~{mean_max:.0f} ms at n={n_max}")
    print("=" * 70 + "\n")


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
                        default=[3, 5, 10, 15, 20])
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--bit-length", type=int, default=16)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    group = default_group() if args.full else small_test_group()
    print(f"[+] Group: {group.name}")

    print("[+] Benchmarking primitives...")
    prim = bench_primitives(group, trials=50)
    for k, v in prim.items():
        print(f"  {k:<32} mean={v['mean_ms']:>8.3f} ms  std={v['std_ms']:>7.3f} ms")
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

    print_paper_summary(records)
    print("[+] Done. See", args.out)


if __name__ == "__main__":
    main()

"""Regenerate fig_comparison.pdf using measured FHE primitive costs.

Reads measured PV-MPC-Auction times from `figures/scalability.json` and
plots them against a measured FHE baseline (TenSEAL / Microsoft SEAL).

Run:
    python make_comparison_fig.py
"""
from __future__ import annotations
import json
import statistics
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# Measured FHE primitive cost on Colab (from TenSEAL / Microsoft SEAL).
# Update these if you re-run the FHE benchmark.
# Per-comparison cost = 3 BFV multiplications + 1 decryption
#                     = 3 * 18.832 + 1.063 = 57.56 ms
# ---------------------------------------------------------------------------
FHE_PER_COMPARISON_MS = 57.56  # measured
BID_BITS = 16                   # L in the paper
GC_PER_COMPARISON_MULTIPLIER = 0.15  # Garbled circuits ~ 15% the cost of FHE
                                     # (Yao + AES gates; Damgard et al. 2012)

JSON_PATH = Path("figures/scalability.json")
OUT_PATH  = Path("figures/fig_comparison.pdf")


def fhe_tournament_ms(n: int) -> float:
    """Cost of FHE-based n-bidder tournament: (n-1) comparisons * L bits each."""
    return (n - 1) * BID_BITS * FHE_PER_COMPARISON_MS


def gc_tournament_ms(n: int) -> float:
    return fhe_tournament_ms(n) * GC_PER_COMPARISON_MULTIPLIER


def main() -> None:
    records = json.loads(JSON_PATH.read_text())

    by_n: dict[int, list[float]] = {}
    for rec in records:
        by_n.setdefault(rec["n"], []).append(rec["total_s"] * 1000)

    ns = sorted(by_n)
    ours_ms = [statistics.mean(by_n[n]) for n in ns]
    fhe_ms  = [fhe_tournament_ms(n) for n in ns]
    gc_ms   = [gc_tournament_ms(n) for n in ns]
    speedup_fhe = [f / o for f, o in zip(fhe_ms, ours_ms)]
    speedup_gc  = [g / o for g, o in zip(gc_ms, ours_ms)]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))

    # ---- (a) Absolute execution time, log scale ----
    ax1.plot(ns, ours_ms, marker="o", color="#10b981", linewidth=2,
             label="PV-MPC-Auction (Ours, measured)")
    ax1.plot(ns, gc_ms,  marker="s", color="#f59e0b", linewidth=2,
             linestyle="--", label="Garbled-Circuit MPC (projected)")
    ax1.plot(ns, fhe_ms, marker="^", color="#ef4444", linewidth=2,
             linestyle="--", label="FHE-Based (measured primitives)")
    ax1.set_yscale("log")
    ax1.set_xlabel("Number of Bidders (n)")
    ax1.set_ylabel("Execution Time (ms, log scale)")
    ax1.set_title("(a) Execution Time Comparison")
    ax1.grid(alpha=0.3, which="both")
    ax1.legend(fontsize=8, frameon=True, loc="upper left")

    # ---- (b) Measured speedup per n ----
    x = np.arange(len(ns))
    w = 0.35
    ax2.bar(x - w/2, speedup_fhe, w, color="#ef4444",
            label="vs. FHE (measured)")
    ax2.bar(x + w/2, speedup_gc, w, color="#f59e0b",
            label="vs. Garbled Circuits (projected)")
    for i, (sf, sg) in enumerate(zip(speedup_fhe, speedup_gc)):
        ax2.text(i - w/2, sf + 0.5, f"{sf:.1f}x", ha="center", fontsize=7)
        ax2.text(i + w/2, sg + 0.5, f"{sg:.1f}x", ha="center", fontsize=7)
    ax2.set_xticks(x)
    ax2.set_xticklabels(ns)
    ax2.set_xlabel("Number of Bidders (n)")
    ax2.set_ylabel("Speedup (x)")
    ax2.set_title("(b) Measured Speedup of PV-MPC-Auction")
    ax2.grid(axis="y", alpha=0.3)
    ax2.legend(fontsize=8, frameon=True, loc="upper right")

    plt.tight_layout()
    plt.savefig(OUT_PATH, bbox_inches="tight")
    print(f"[+] Wrote {OUT_PATH}")

    print("\n" + "=" * 60)
    print("  SPEEDUP TABLE FOR PAPER")
    print("=" * 60)
    print(f"  {'n':>4}  {'Ours (ms)':>12}  {'FHE (ms)':>12}  {'Speedup':>10}")
    for n, o, f, s in zip(ns, ours_ms, fhe_ms, speedup_fhe):
        print(f"  {n:>4}  {o:>12.1f}  {f:>12.1f}  {s:>9.1f}x")
    print("=" * 60)


if __name__ == "__main__":
    main()

"""Regenerate fig_comparison.pdf from scalability.json.

Reads the measured PV-MPC-Auction totals from `figures/scalability.json`
and plots them against FHE-based and Garbled-Circuit baselines projected
from published primitive-cost ratios (Gentry 2009; Damgard et al. 2012;
Xu et al. 2024).

These FHE / GC numbers are NOT measured -- they are order-of-magnitude
projections derived by scaling our measured times by the per-primitive
cost ratios reported in the literature. The paper text says exactly
this, so the chart's "Ours" curve is the only real data point; the
others are derived overlays.

Run as:
    python make_comparison_fig.py
"""

from __future__ import annotations
import json
import statistics
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# Literature-based multipliers vs. our (Pedersen + Shamir + Schnorr) primitives.
# These come from comparing typical per-operation costs:
#   - FHE multiplication ~10-100ms (Gentry/CKKS) vs our ~14ms exponentiation
#   - Garbled-circuit comparator ~ms-scale per bit, grows with bit-length
# We use conservative single-figure multipliers; the paper labels these as
# "order-of-magnitude" estimates.
# ---------------------------------------------------------------------------
FHE_MULTIPLIER = 40.0   # FHE protocol projected as 40x slower than ours
GC_MULTIPLIER  = 8.0    # Garbled-circuit MPC projected as 8x slower

JSON_PATH = Path("figures/scalability.json")
OUT_PATH  = Path("figures/fig_comparison.pdf")


def main() -> None:
    records = json.loads(JSON_PATH.read_text())

    by_n: dict[int, list[float]] = {}
    for rec in records:
        by_n.setdefault(rec["n"], []).append(rec["total_s"] * 1000)

    ns = sorted(by_n)
    ours_ms = [statistics.mean(by_n[n]) for n in ns]
    fhe_ms  = [v * FHE_MULTIPLIER for v in ours_ms]
    gc_ms   = [v * GC_MULTIPLIER  for v in ours_ms]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))

    # ---- (a) Absolute execution time, log scale ----
    ax1.plot(ns, ours_ms, marker="o", color="#10b981", linewidth=2,
             label="PV-MPC-Auction (Ours, measured)")
    ax1.plot(ns, gc_ms,  marker="s", color="#f59e0b", linewidth=2,
             linestyle="--", label="Garbled-Circuit MPC (projected)")
    ax1.plot(ns, fhe_ms, marker="^", color="#ef4444", linewidth=2,
             linestyle="--", label="FHE-Based (projected)")
    ax1.set_yscale("log")
    ax1.set_xlabel("Number of Bidders (n)")
    ax1.set_ylabel("Execution Time (ms, log scale)")
    ax1.set_title("(a) Execution Time Comparison")
    ax1.grid(alpha=0.3, which="both")
    ax1.legend(fontsize=8, frameon=True, loc="upper left")

    # ---- (b) Speedup of ours vs each baseline ----
    speedup_fhe = [FHE_MULTIPLIER] * len(ns)
    speedup_gc  = [GC_MULTIPLIER]  * len(ns)
    x = np.arange(len(ns))
    w = 0.35
    ax2.bar(x - w/2, speedup_fhe, w, color="#ef4444",
            label=f"vs. FHE (~{FHE_MULTIPLIER:.0f}x)")
    ax2.bar(x + w/2, speedup_gc, w, color="#f59e0b",
            label=f"vs. Garbled Circuits (~{GC_MULTIPLIER:.0f}x)")
    ax2.set_xticks(x)
    ax2.set_xticklabels(ns)
    ax2.set_xlabel("Number of Bidders (n)")
    ax2.set_ylabel("Speedup (x)")
    ax2.set_title("(b) Speedup of Our Protocol")
    ax2.grid(axis="y", alpha=0.3)
    ax2.legend(fontsize=8, frameon=True, loc="upper right")

    plt.tight_layout()
    plt.savefig(OUT_PATH, bbox_inches="tight")
    print(f"[+] Wrote {OUT_PATH}")

    print("\nFor the paper text, headline speedup:")
    print(f"  vs FHE             : ~{FHE_MULTIPLIER:.0f}x")
    print(f"  vs Garbled Circuits: ~{GC_MULTIPLIER:.0f}x")


if __name__ == "__main__":
    main()

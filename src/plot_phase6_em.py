"""
Phase 6 - plot EM convergence curves (one per initialization) from the real
log-likelihoods already written by run_phase6_em.py.

Run with:  python3 src/plot_phase6_em.py
"""
from pathlib import Path
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
VIS = ROOT / "visualizations"
VIS.mkdir(parents=True, exist_ok=True)

with open(PROCESSED / "phase6_em_log_likelihoods.json") as f:
    data = json.load(f)

fig, (ax_full, ax_zoom) = plt.subplots(1, 2, figsize=(12, 5))
colors = {"supervised": "#1b9e77", "uniform": "#d95f02", "random": "#7570b3"}
for name, lls in data.items():
    iterations = list(range(1, len(lls) + 1))
    ax_full.plot(iterations, lls, marker="o", markersize=3, label=f"{name} init",
                 color=colors.get(name))
    ax_zoom.plot(iterations[1:], lls[1:], marker="o", markersize=3, label=f"{name} init",
                 color=colors.get(name))

ax_full.set_xlabel("EM iteration")
ax_full.set_ylabel("Total corpus log-likelihood (351 avartans)")
ax_full.set_title("Full range (iteration 1's huge jump dwarfs the rest)")
ax_full.legend()
ax_full.grid(alpha=0.3)

ax_zoom.set_xlabel("EM iteration")
ax_zoom.set_ylabel("Total corpus log-likelihood")
ax_zoom.set_title("Zoomed to iterations 2-20 (the actual ranking)")
ax_zoom.legend()
ax_zoom.grid(alpha=0.3)

fig.suptitle("Phase 6: Inside-Outside EM convergence by initialization")
fig.tight_layout()
out_path = VIS / "phase6_em_convergence.png"
fig.savefig(out_path, dpi=150)
print(f"Wrote {out_path}")

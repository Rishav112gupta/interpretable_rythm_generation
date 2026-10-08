"""
Phase 8 - structural priors (parameter tying) and ablations, scored by
held-out likelihood on the train+val compositions only. The Phase 1 test
split is NOT touched here: it is reserved for Phase 11's grammar-vs-baseline
comparison, so choosing a tie here cannot leak into that result.

Produces:
    data/processed/phase8_results.json
    visualizations/phase8_tying_grid.png

Run with:  python3 src/run_phase8_priors.py
"""
from __future__ import annotations

import json
import math
import random
from collections import Counter
from fractions import Fraction
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from mts_loader import load_all_compositions
from representation import build_representation, TEENTAL
from bol_normalization import BolNormalizer, BolNormalizationMode
from pcfg import train_supervised, tree_log_prob, REST_TOKEN
from attributes import annotate, is_well_formed_avartan, matra_tops, leaf_nodes
from generation import sample_avartan_constrained
from tying import (
    GROUPINGS, Variant, matra_records, events, TiedModel, cross_validate,
    bits_per_stroke, paired_bootstrap,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data" / "raw" / "mts"
PROCESSED = ROOT / "data" / "processed"
VIS = ROOT / "visualizations"

ALPHAS = (0.1, 0.5, 1.0)
MAIN_ALPHA = 0.5
BETAS = (1, 10, 100, 1000, 10000)
BASE = Variant("one", "sam", tails=True)
GROUPING_NAMES = list(GROUPINGS)


def section(title):
    print(f"\n=== {title} ===")


def main():
    comps = load_all_compositions(DATA_ROOT)
    normalizer = BolNormalizer(DATA_ROOT / "syllableMapping.txt")
    vocab = sorted(normalizer.mapped_to_raw)
    splits = json.loads((PROCESSED / "splits.json").read_text())
    dev_names = set(splits["train"]) | set(splits["val"])
    results: dict = {"vocab_size": len(vocab), "main_alpha": MAIN_ALPHA}

    # -----------------------------------------------------------------
    section("1. MatraTail fix: effect on generated output")
    real_empty = sum(1 for c in comps for a in build_representation(c, TEENTAL).avartans
                     for v in a.vibhags for m in v.matras if not m.slots)
    real_total = sum(TEENTAL.n_matras * len(build_representation(c, TEENTAL).avartans) for c in comps)
    print(f"real data: empty matras {real_empty}/{real_total} ({real_empty / real_total:.3f}), "
          f"matras with a rest mixed among strokes: 0 (by construction of the data)")
    fix = {}
    for tails in (False, True):
        g, _ = train_supervised(comps, BolNormalizationMode.NORMALIZED, normalizer,
                                include_rests=True, tail_labels=tails)
        rng = random.Random(7)
        ok = empty = total = mixed = 0
        for _ in range(2000):
            t = sample_avartan_constrained(g, rng)
            annotate(t, Fraction(0))
            ok += is_well_formed_avartan(t)[0]
            for _, _, m in matra_tops(t):
                toks = [lf.bol for lf in leaf_nodes(m)]
                total += 1
                empty += toks == [REST_TOKEN]
                mixed += len(toks) > 1 and REST_TOKEN in toks
        d = g.diagnostics()
        label = "with tails" if tails else "Phase 7 (no tails)"
        print(f"{label}: {d['n_nonterminals']} non-terminals, {d['n_rules']} rules; "
              f"2000 constrained cycles: well-formed {ok}, empty matras {empty}/{total} "
              f"({empty / total:.3f}), matras with a rest mixed in {mixed}")
        fix["tails" if tails else "no_tails"] = {
            "n_rules": d["n_rules"], "wellformed": ok, "empty_rate": empty / total, "mixed": mixed}
    fix["real_empty_rate"] = real_empty / real_total
    results["matratail_fix"] = fix

    # -----------------------------------------------------------------
    section("2. Held-out setup")
    dev = [c for c in comps if c.name in dev_names]
    records, n_av, n_strokes, reps = {}, {}, {}, {}
    for c in dev:
        rep = build_representation(c, TEENTAL)
        for s in rep.all_slots():
            s.bol = normalizer.normalize(s.bol)
        reps[c.name] = rep
        records[c.name] = matra_records(rep)
        n_av[c.name] = len(rep.avartans)
        n_strokes[c.name] = len(rep.all_slots())
    units: list[list[str]] = []
    glued = [n for n in records if n.startswith("ajr_10_")]
    if glued:
        units.append(sorted(glued))
    units += [[n] for n in sorted(records) if n not in glued]
    print(f"train+val compositions: {len(records)} in {len(units)} leave-one-out units "
          f"(ajr_10_ajr/ajr_10_dli held out together, per Phase 1 §10); "
          f"{sum(n_strokes.values())} strokes, {sum(n_av.values())} cycles; "
          f"test split ({len(splits['test'])} compositions) untouched")
    results["n_dev_compositions"] = len(records)
    results["n_units"] = len(units)
    results["n_dev_strokes"] = sum(n_strokes.values())

    cache: dict = {}

    def run(variant: Variant, alpha: float, beta=None):
        key = (variant, alpha, beta)
        if key not in cache:
            ev = {n: events(records[n], n_av[n], variant) for n in records}
            cache[key] = cross_validate(units, ev, n_strokes, vocab, alpha, beta)
        return cache[key]

    # -----------------------------------------------------------------
    section("3. Cost of the cycle structure: plain context-free grammar vs attribute layer")
    per_cycle = 9 * math.log2(3) + 6 * math.log2(3 / 2)
    base_scores = run(BASE, MAIN_ALPHA)
    total_cycles = sum(n_av.values())
    extra = per_cycle * total_cycles / sum(n_strokes.values())
    print(f"plain CF structure cost: {per_cycle:.3f} bits per cycle "
          f"(9 choices at 1/3, 6 at 2/3 - every cycle has the same structure, so this is exact)")
    print(f"held-out bits/stroke: attribute-constrained {bits_per_stroke(base_scores):.4f}; "
          f"plain CF would be {bits_per_stroke(base_scores) + extra:.4f} (+{extra:.4f})")
    results["structure_cost_bits_per_cycle"] = per_cycle
    results["structure_cost_bits_per_stroke"] = extra

    # -----------------------------------------------------------------
    section(f"4. Tails ablation (alpha={MAIN_ALPHA})")
    no_tails = Variant("one", "sam", tails=False)
    a, b = run(BASE, MAIN_ALPHA), run(no_tails, MAIN_ALPHA)
    obs, lo, hi = paired_bootstrap(a, b)
    print(f"with tails {bits_per_stroke(a):.4f} vs without {bits_per_stroke(b):.4f} bits/stroke; "
          f"difference {obs:+.4f} [95% CI {lo:+.4f}, {hi:+.4f}]")
    results["tails_ablation"] = {"with": bits_per_stroke(a), "without": bits_per_stroke(b),
                                 "diff": obs, "ci": [lo, hi]}

    # -----------------------------------------------------------------
    section("5. Tying grid: stroke grouping x shape grouping (hard splits, tails on)")
    grid = {}
    for alpha in ALPHAS:
        grid[alpha] = {}
        for sg in GROUPING_NAMES:
            for hg in GROUPING_NAMES:
                grid[alpha][(sg, hg)] = bits_per_stroke(run(Variant(sg, hg), alpha))
    for alpha in ALPHAS:
        print(f"\nalpha={alpha}: held-out bits/stroke (rows: strokes split by, cols: shapes split by)")
        print(f"{'':>12}" + "".join(f"{hg:>12}" for hg in GROUPING_NAMES))
        for sg in GROUPING_NAMES:
            print(f"{sg:>12}" + "".join(f"{grid[alpha][(sg, hg)]:>12.4f}" for hg in GROUPING_NAMES))
        best = min(grid[alpha], key=grid[alpha].get)
        print(f"best: strokes={best[0]}, shapes={best[1]} ({grid[alpha][best]:.4f}); "
              f"base (strokes=one, shapes=sam) {grid[alpha][('one', 'sam')]:.4f}")
    results["grid"] = {str(alpha): {f"{sg}|{hg}": v for (sg, hg), v in g.items()} for alpha, g in grid.items()}

    # -----------------------------------------------------------------
    section(f"6. Each split vs the base, with paired 95% CIs (alpha={MAIN_ALPHA})")
    comparisons = {}
    for sg in GROUPING_NAMES:
        if sg == "one":
            continue
        v = Variant(sg, "sam")
        obs, lo, hi = paired_bootstrap(run(v, MAIN_ALPHA), run(BASE, MAIN_ALPHA))
        n_params = v.n_free_parameters(len(vocab))
        print(f"strokes split by {sg:>10} ({n_params:>3} params): {obs:+.4f} bits/stroke "
              f"[{lo:+.4f}, {hi:+.4f}]{'  *' if hi < 0 else ''}")
        comparisons[f"strokes={sg}"] = {"diff": obs, "ci": [lo, hi], "params": n_params}
    for hg in GROUPING_NAMES:
        if hg == "sam":
            continue
        v = Variant("one", hg)
        obs, lo, hi = paired_bootstrap(run(v, MAIN_ALPHA), run(BASE, MAIN_ALPHA))
        n_params = v.n_free_parameters(len(vocab))
        print(f"shapes  split by {hg:>10} ({n_params:>3} params): {obs:+.4f} bits/stroke "
              f"[{lo:+.4f}, {hi:+.4f}]{'  *' if hi < 0 else ''}")
        comparisons[f"shapes={hg}"] = {"diff": obs, "ci": [lo, hi], "params": n_params}
    print(f"base has {BASE.n_free_parameters(len(vocab))} free parameters; "
          f"'*' = the split predicts held-out compositions better, CI excludes 0")
    results["comparisons_vs_base"] = comparisons

    best = min(grid[MAIN_ALPHA], key=grid[MAIN_ALPHA].get)
    best_v = Variant(*best)
    obs, lo, hi = paired_bootstrap(run(best_v, MAIN_ALPHA), run(BASE, MAIN_ALPHA))
    print(f"best grid cell ({best_v.name()}, {best_v.n_free_parameters(len(vocab))} params) "
          f"vs base: {obs:+.4f} [{lo:+.4f}, {hi:+.4f}]")
    results["best"] = {"variant": best_v.name(), "diff": obs, "ci": [lo, hi],
                       "params": best_v.n_free_parameters(len(vocab))}

    # -----------------------------------------------------------------
    section(f"7. Soft tying: shrink the best split toward the shared table (alpha={MAIN_ALPHA})")
    soft = {}
    for beta in BETAS:
        s = run(best_v, MAIN_ALPHA, beta)
        obs, lo, hi = paired_bootstrap(s, run(best_v, MAIN_ALPHA))
        print(f"beta={beta:>5}: {bits_per_stroke(s):.4f} bits/stroke; vs hard split {obs:+.4f} "
              f"[{lo:+.4f}, {hi:+.4f}]")
        soft[str(beta)] = {"bits": bits_per_stroke(s), "diff_vs_hard": obs, "ci": [lo, hi]}
    print(f"(hard split {bits_per_stroke(run(best_v, MAIN_ALPHA)):.4f}, "
          f"fully tied base {bits_per_stroke(run(BASE, MAIN_ALPHA)):.4f})")
    results["soft_tying"] = soft

    # -----------------------------------------------------------------
    section("8. What the strongest stroke split says (fit on all train+val, descriptive only)")
    strongest = min((k for k in comparisons if k.startswith("strokes=")),
                    key=lambda k: comparisons[k]["diff"])
    sg = strongest.split("=")[1]
    total = Counter()
    for n in records:
        total.update(events(records[n], n_av[n], Variant(sg, "sam")))
    model = TiedModel(total, vocab, MAIN_ALPHA)
    pooled = model._pooled_prob("stroke")
    groups = sorted({t for (t, _) in total if t[0] == "stroke"})
    described = {}
    for table in groups:
        tab = model.table(table)
        n = sum(model.by_table[table].values())
        ratios = sorted(((tab[b] / pooled[b], b) for b in vocab if model.by_table[table][b] >= 10),
                        reverse=True)
        top = sorted(vocab, key=lambda b: -tab[b])[:5]
        print(f"{table[1]:>6} ({n} strokes): most common {', '.join(f'{b} {tab[b]:.2f}' for b in top)}; "
              f"most over-represented vs pooled (>=10 occurrences): "
              f"{', '.join(f'{b} x{r:.2f}' for r, b in ratios[:3])}")
        described[table[1]] = {"n": n, "top": {b: tab[b] for b in top},
                               "over": {b: r for r, b in ratios[:3]}}
    results["strongest_stroke_split"] = {"grouping": sg, "groups": described}

    # -----------------------------------------------------------------
    VIS.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.5, 6))
    base_val = grid[MAIN_ALPHA][("one", "sam")]
    mat = [[grid[MAIN_ALPHA][(sg, hg)] - base_val for hg in GROUPING_NAMES] for sg in GROUPING_NAMES]
    lim = max(abs(x) for row in mat for x in row)
    im = ax.imshow(mat, cmap="RdBu_r", vmin=-lim, vmax=lim)
    ax.set_xticks(range(len(GROUPING_NAMES)), GROUPING_NAMES, rotation=30, ha="right")
    ax.set_yticks(range(len(GROUPING_NAMES)), GROUPING_NAMES)
    ax.set_xlabel("matra shapes split by")
    ax.set_ylabel("strokes split by")
    for i, row in enumerate(mat):
        for j, x in enumerate(row):
            ax.text(j, i, f"{x:+.3f}", ha="center", va="center", fontsize=8)
    ax.set_title(f"Held-out bits/stroke vs base (strokes=one, shapes=sam)\n"
                 f"leave-one-out over train+val, alpha={MAIN_ALPHA}; blue = better")
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    fig.savefig(VIS / "phase8_tying_grid.png", dpi=150)
    print("\nWrote visualizations/phase8_tying_grid.png")

    with open(PROCESSED / "phase8_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("Wrote data/processed/phase8_results.json")


if __name__ == "__main__":
    main()

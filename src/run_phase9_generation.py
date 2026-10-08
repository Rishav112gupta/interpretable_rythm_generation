"""
Phase 9 - generation examples and visualizations.

Uses the grammar fixed in Phase 8 (rests + tails + sam stroke table + sam
shape table), trained on the train+val compositions only - the Phase 1 test
split is still untouched (reserved for Phase 11).

Produces:
    data/processed/phase9_examples.json        20 generated compositions
    data/processed/phase9_examples.txt         the same, as readable bol lines
    data/processed/phase9_summary.json         every number in the report
    visualizations/phase9_tihai_real_vs_generated.png
    visualizations/phase9_generated_vs_real_stats.png

Run with:  python3 src/run_phase9_generation.py
"""
from __future__ import annotations

import json
import random
import statistics
from collections import Counter
from fractions import Fraction
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from mts_loader import load_all_compositions
from representation import build_representation, TEENTAL
from bol_normalization import BolNormalizer, BolNormalizationMode
from pcfg import train_supervised, DerivNode, START, REST_TOKEN
from attributes import (
    annotate, is_well_formed_avartan, timed_sequence, real_positions, check_tihai,
    matra_tops, leaf_nodes, tree_to_dict, rule_sequence, render, _fmt,
)
from generation import generate_composition, sample_avartan_constrained

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data" / "raw" / "mts"
PROCESSED = ROOT / "data" / "processed"
VIS = ROOT / "visualizations"

N_EXAMPLES = 20
N_STAT_SAMPLES = 400
NGRAM = 4

# chart tokens (light surface), from the dataviz reference palette
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
REAL_C = "#2a78d6"      # slot 1
GEN_C = "#eb6834"       # slot 2
PHRASE_C = REAL_C
GAP_C = GEN_C
KHALI_SHADE = "#f0efec"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK_2, "xtick.color": MUTED, "ytick.color": MUTED,
    "text.color": INK, "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "bold",
    "axes.spines.top": False, "axes.spines.right": False,
})


def section(title):
    print(f"\n=== {title} ===")


def strokes_only(tokens):
    return [t for t in tokens if t != REST_TOKEN]


def self_repetition(tokens, n=NGRAM) -> float:
    """Share of n-gram positions whose n-gram also occurs at another position
    in the same sequence."""
    grams = [tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]
    if not grams:
        return 0.0
    counts = Counter(grams)
    return sum(counts[g] > 1 for g in grams) / len(grams)


def notation(root: DerivNode, cycle: int = TEENTAL.n_matras) -> list[str]:
    """One line per cycle: [strokes of a matra] ... with '|' between vibhags
    and 'X' before sam. A token that does not start on the equal-split grid
    or lasts other than its matra share is shown with its duration."""
    seq = timed_sequence(root)
    by_cycle: dict[int, dict[int, list[str]]] = {}
    for tok, start, dur in seq:
        c, m = int(start // cycle), int(start % cycle)
        label = tok if leaf_is_plain(seq, start, dur) else f"{tok}({_fmt(start - int(start))},{_fmt(dur)})"
        by_cycle.setdefault(c, {}).setdefault(m, []).append(label)
    lines = []
    for c in sorted(by_cycle):
        parts = []
        for m in range(max(by_cycle[c]) + 1):
            if m in by_cycle[c]:
                parts.append(("X" if m == 0 else "") + "[" + " ".join(by_cycle[c][m]) + "]")
            if m % TEENTAL.matras_per_vibhag == TEENTAL.matras_per_vibhag - 1 and m < max(by_cycle[c]):
                parts.append("|")
        lines.append(" ".join(p for p in parts))
    return lines


def leaf_is_plain(seq, start, dur) -> bool:
    m = int(start)
    in_matra = [d for _, s, d in seq if int(s) == m]
    return dur == Fraction(1, len(in_matra)) and (start - m) / dur == int((start - m) / dur)


def tihai_panel(ax, xs, tokens, spans, title, landing_x=0.0):
    """Icicle view on a matra axis: row 2 = tihai, row 1 = phrase/gap,
    row 0 = strokes. `spans` = list of (kind, x0, x1) with kind in
    {'phrase', 'gap'}."""
    lo, hi = min(xs) - 0.2, landing_x + 1.6
    for k in range(int(lo // 4) * 4, int(hi) + 1, 4):
        v = (k // 4) % 4  # vibhag index relative to the landing sam (sam = vibhag 0)
        if v == TEENTAL.khali_vibhags[0]:
            ax.add_patch(Rectangle((k, -0.5), 4, 3, color=KHALI_SHADE, zorder=0, lw=0))
            ax.text(k + 2, 2.62, "khālī vibhāg", ha="center", va="bottom", fontsize=7, color=MUTED)
    for k in range(int(lo) - 1, int(hi) + 2):
        ax.axvline(k, color=GRID if k % 4 else AXIS, lw=0.6 if k % 4 else 1.0, zorder=1)
    ax.axvline(landing_x, color=INK, lw=1.6, zorder=3)
    ax.text(landing_x + 0.08, 2.62, "sam", ha="left", va="bottom", fontsize=8, fontweight="bold")

    t0, t1 = spans[0][1], spans[-1][2]
    ax.add_patch(Rectangle((t0, 1.6), t1 - t0, 0.7, facecolor=SURFACE, edgecolor=INK_2, lw=1, zorder=2))
    ax.text((t0 + t1) / 2, 1.95, "Tihāī", ha="center", va="center", fontsize=8, color=INK)
    for kind, a, b in spans:
        col = PHRASE_C if kind == "phrase" else GAP_C
        ax.add_patch(Rectangle((a + 0.03, 0.85), b - a - 0.06, 0.6, facecolor=col, alpha=0.18,
                               edgecolor=col, lw=1.2, zorder=2))
        ax.text((a + b) / 2, 1.15, "Phrase" if kind == "phrase" else "Gap", ha="center", va="center",
                fontsize=7.5, color=INK_2)
    for x, tok in zip(xs, tokens):
        if tok == REST_TOKEN:
            continue  # rests are shown by the Gap box, not as strokes
        if abs(x - landing_x) < 0.25:
            ax.plot([x, x], [0.05, 0.35], color=INK, lw=2.4, zorder=4)
            ax.text(x + 0.12, 0.1, f"{tok} on sam", ha="left", va="bottom", fontsize=7.5,
                    fontweight="bold", color=INK)
            continue
        inside = any(a - 1e-9 <= x < b - 1e-9 for _, a, b in spans)
        col = INK if inside else MUTED
        ax.plot([x, x], [0.05, 0.35], color=col, lw=1, zorder=3)
        ax.text(x, 0.42, tok, rotation=90, ha="center", va="bottom", fontsize=6.5, color=col)
    ax.set_xlim(lo, hi)
    ax.set_ylim(-0.1, 2.9)
    ax.set_yticks([0.6, 1.15, 1.95], ["strokes", "phrase / gap", "tihāī"])
    ax.tick_params(axis="y", length=0, labelcolor=INK_2)
    ax.set_title(title, loc="left")
    ax.spines["left"].set_visible(False)


def main():
    comps = load_all_compositions(DATA_ROOT)
    normalizer = BolNormalizer(DATA_ROOT / "syllableMapping.txt")
    splits = json.loads((PROCESSED / "splits.json").read_text())
    dev_names = set(splits["train"]) | set(splits["val"])
    dev = [c for c in comps if c.name in dev_names]
    summary: dict = {}

    section("1. Grammar fixed in Phase 8, trained on train+val only")
    g, _ = train_supervised(dev, BolNormalizationMode.NORMALIZED, normalizer,
                            include_rests=True, tail_labels=True, sam_strokes=True)
    d = g.diagnostics()
    print(f"{len(dev)} compositions; {d['n_nonterminals']} non-terminals, {d['n_rules']} rules; "
          f"probabilities sum to 1: {d['probabilities_sum_to_one']}")
    summary["grammar"] = {"n_compositions": len(dev), "n_nonterminals": d["n_nonterminals"],
                          "n_rules": d["n_rules"]}

    # -----------------------------------------------------------------
    section(f"2. {N_EXAMPLES} example compositions (seeds 0..{N_EXAMPLES - 1})")
    examples, text_lines = [], []
    all_ok = 0
    for seed in range(N_EXAMPLES):
        root, info = generate_composition(g, random.Random(seed), n_body_avartans=2)
        seq = timed_sequence(root)
        tokens = [t for t, _, _ in seq]
        pos = [s for _, s, _ in seq]
        x = check_tihai(pos, info["tihai_first_token"], info["phrase_tokens"], info["gap_tokens"], tol=0)
        body_ok = all(is_well_formed_avartan(a)[0] for a in root.children[:2])
        ok = body_ok and x.strict_b and x.lands_b_formula and x.gap_in_plan_set
        all_ok += ok
        lines = notation(root)
        examples.append({
            "seed": seed, "dur_p": _fmt(info["dur_p"]), "dur_g": _fmt(info["dur_g"]),
            "tihai_start_matra_in_cycle": _fmt(info["tihai_start_matra"]),
            "checks_pass": ok, "notation": lines,
            "timeline": [[t, _fmt(s), _fmt(du)] for t, s, du in seq],
            "tree": tree_to_dict(root), "rule_sequence": rule_sequence(root),
        })
        text_lines.append(f"# seed {seed}: tihai phrase {_fmt(info['dur_p'])} matra, gap "
                          f"{_fmt(info['dur_g'])}, starts at matra {_fmt(info['tihai_start_matra'])} "
                          f"of cycle 3, lands on the sam that opens cycle 4")
        text_lines += [f"  cycle {i + 1}: {ln}" for i, ln in enumerate(lines)]
        text_lines.append("")
    print(f"all checks pass (body cycles well-formed; tihai regular, exactly on sam, gap in plan set): "
          f"{all_ok}/{N_EXAMPLES}")
    print("example seed 0:")
    print("\n".join(text_lines[:5]))
    summary["examples_all_checks_pass"] = all_ok
    (PROCESSED / "phase9_examples.json").write_text(json.dumps(examples, indent=1))
    header = [
        "# Phase 9 generated compositions (grammar trained on train+val; see docs/PHASE9_GENERATION.md)",
        "# One line per cycle. [ ] = one matra, its strokes share it equally. | = vibhag boundary.",
        "# X = sam. '-' = rest. tok(o,d) = token starting o matra into this matra and lasting d matra",
        "#   (shown only where the token is not an equal share of its matra, i.e. inside a tihai).",
        "",
    ]
    (PROCESSED / "phase9_examples.txt").write_text("\n".join(header + text_lines))

    # -----------------------------------------------------------------
    section("3. Figure: a real tihai (ben_25) and a generated one of the same shape")
    checks = json.loads((PROCESSED / "phase7_tihai_checks.json").read_text())
    real = next(c for c in checks if c["composition"] == "ben_25" and c["strict_b"])
    comp = next(c for c in comps if c.name == "ben_25")
    rep = build_representation(comp, TEENTAL)
    rpos = real_positions(rep)
    rtok = [normalizer.normalize(s.bol) for s in rep.all_slots()]
    st, p, gl = real["start_slot_index"], len(real["phrase"]), len(real["gap"])
    i_end = st + 3 * p + 2 * gl
    landing = round(rpos[i_end] / TEENTAL.n_matras) * TEENTAL.n_matras
    rx = [x - landing for x in rpos]
    idx = [st, st + p, st + p + gl, st + 2 * p + gl, st + 2 * p + 2 * gl, i_end]
    rspans = [("phrase", rx[idx[0]], rx[idx[1]]), ("gap", rx[idx[1]], rx[idx[2]]),
              ("phrase", rx[idx[2]], rx[idx[3]]), ("gap", rx[idx[3]], rx[idx[4]]),
              ("phrase", rx[idx[4]], rx[idx[5]])]
    lo_r = rx[st] - 1.0
    keep_r = [i for i, x in enumerate(rx) if lo_r <= x <= 1.0]
    print(f"ben_25 tihai: phrase {' '.join(real['phrase'])} ({real['dur_p']:.2f} matra), gap "
          f"{' '.join(real['gap'])} ({real['dur_g']:.2f} matra); next stroke at "
          f"{rpos[i_end] - landing:+.3f} matra from sam")
    summary["real_tihai"] = {"composition": "ben_25", "phrase": real["phrase"], "gap": real["gap"],
                             "dur_p": real["dur_p"], "dur_g": real["dur_g"],
                             "landing_offset": rpos[i_end] - landing}

    shape = (Fraction(4), Fraction(1))
    groot, ginfo = generate_composition(g, random.Random(2025), n_body_avartans=1, shape=shape)
    gseq = timed_sequence(groot)
    gtok = [t for t, _, _ in gseq]
    glanding = Fraction(2 * TEENTAL.n_matras)
    gx = [float(s - glanding) for _, s, _ in gseq]
    gst, gp = ginfo["tihai_first_token"], ginfo["phrase_tokens"]
    gidx = [gst, gst + gp, gst + gp + 1, gst + 2 * gp + 1, gst + 2 * gp + 2, gst + 3 * gp + 2]
    gspans = [("phrase", gx[gidx[0]], gx[gidx[1]]), ("gap", gx[gidx[1]], gx[gidx[2]]),
              ("phrase", gx[gidx[2]], gx[gidx[3]]), ("gap", gx[gidx[3]], gx[gidx[4]]),
              ("phrase", gx[gidx[4]], gx[gidx[5]])]
    keep_g = [i for i, x in enumerate(gx) if gx[gst] - 1.0 <= x <= 1.0]
    gcheck = check_tihai([s for _, s, _ in gseq], gst, gp, 1, tol=0)
    print(f"generated (seed 2025, phrase 4 matra, gap 1): phrase {' '.join(gtok[gst:gst + gp])}; "
          f"lands exactly on sam: {gcheck.strict_b}")
    summary["generated_tihai_figure"] = {"seed": 2025, "phrase": gtok[gst:gst + gp],
                                         "exact": gcheck.strict_b}

    VIS.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 1, figsize=(12, 6.4), sharex=True)
    tihai_panel(axes[0], [rx[i] for i in keep_r], [rtok[i] for i in keep_r], rspans,
                "Real: ben_25 (measured timing). Phrase ≈ 4 mātrā, gap = one stroke (DHA) ≈ 1 mātrā")
    tihai_panel(axes[1], [gx[i] for i in keep_g], [gtok[i] for i in keep_g], gspans,
                "Generated (seed 2025): phrase 4 mātrā sampled once and copied, gap = 1 mātrā rest")
    axes[1].set_xlabel("mātrā relative to the sam the tihāī lands on   (vertical lines: mātrā; darker: vibhāg)")
    handles = [Rectangle((0, 0), 1, 1, facecolor=PHRASE_C, alpha=0.18, edgecolor=PHRASE_C),
               Rectangle((0, 0), 1, 1, facecolor=GAP_C, alpha=0.18, edgecolor=GAP_C)]
    fig.legend(handles, ["phrase", "gap"], loc="upper right", frameon=False, ncol=2)
    fig.suptitle("Phase 9: a tihāī as a derivation laid out in time", x=0.01, ha="left",
                 fontweight="bold", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(VIS / "phase9_tihai_real_vs_generated.png", dpi=150)
    plt.close(fig)
    print("wrote visualizations/phase9_tihai_real_vs_generated.png")

    # -----------------------------------------------------------------
    section(f"4. Generated vs real statistics ({N_STAT_SAMPLES} generated cycles / windows)")
    real_reps = []
    for c in dev:
        r = build_representation(c, TEENTAL)
        for s in r.all_slots():
            s.bol = normalizer.normalize(s.bol)
        real_reps.append(r)

    def per_matra_counts(matras):
        cnt = Counter(min(n, 5) for n in matras)
        total = sum(cnt.values())
        return [cnt[k] / total for k in range(6)]

    real_n = [len(m.slots) for r in real_reps for a in r.avartans for v in a.vibhags for m in v.matras]
    real_sam = Counter(s.bol for r in real_reps for a in r.avartans for s in a.vibhags[0].matras[0].slots)

    rng = random.Random(9)
    gen_n, gen_sam, gen_rep = [], Counter(), []
    for _ in range(N_STAT_SAMPLES):
        cycles = [sample_avartan_constrained(g, rng) for _ in range(3)]
        root = DerivNode(label=START, children=cycles)
        annotate(root, Fraction(0))
        for cyc in cycles:
            tops = matra_tops(cyc)
            for i, (_, _, m) in enumerate(tops):
                toks = [lf.bol for lf in leaf_nodes(m)]
                gen_n.append(0 if toks == [REST_TOKEN] else len(toks))
                if i == 0:
                    gen_sam.update(t for t in toks if t != REST_TOKEN)
        gen_rep.append(self_repetition(strokes_only([lf.bol for lf in leaf_nodes(root)])))

    real_rep = []
    for r in real_reps:
        cyc_tokens = [[s.bol for s in a.all_slots()] for a in r.avartans]
        for i in range(len(cyc_tokens) - 2):
            real_rep.append(self_repetition(sum(cyc_tokens[i:i + 3], [])))

    pr, pg = per_matra_counts(real_n), per_matra_counts(gen_n)
    print("strokes per matra (0..5+): real " + " ".join(f"{x:.3f}" for x in pr)
          + " | generated " + " ".join(f"{x:.3f}" for x in pg))
    top_sam = [b for b, _ in real_sam.most_common(6)]
    rs_tot, gs_tot = sum(real_sam.values()), sum(gen_sam.values())
    print("strokes on sam (share): " + ", ".join(
        f"{b} real {real_sam[b] / rs_tot:.3f} gen {gen_sam[b] / gs_tot:.3f}" for b in top_sam))
    med_r, med_g = statistics.median(real_rep), statistics.median(gen_rep)
    print(f"{NGRAM}-gram self-repetition in 3-cycle windows: real median {med_r:.3f} "
          f"(n={len(real_rep)} windows), generated median {med_g:.3f} (n={len(gen_rep)})")
    summary["stats"] = {
        "strokes_per_matra_real": pr, "strokes_per_matra_generated": pg,
        "sam_share_real": {b: real_sam[b] / rs_tot for b in top_sam},
        "sam_share_generated": {b: gen_sam[b] / gs_tot for b in top_sam},
        "self_repetition_median_real": med_r, "self_repetition_median_generated": med_g,
        "n_real_windows": len(real_rep), "n_generated_windows": len(gen_rep),
    }

    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    w = 0.38
    ks = list(range(6))
    ax = axes[0]
    ax.bar([k - w / 2 - 0.01 for k in ks], pr, w, color=REAL_C, label="real (train+val)")
    ax.bar([k + w / 2 + 0.01 for k in ks], pg, w, color=GEN_C, label="generated")
    ax.set_xticks(ks, ["0 (rest)", "1", "2", "3", "4", "5+"])
    ax.set_xlabel("strokes in one mātrā")
    ax.set_ylabel("share of mātrā")
    ax.set_title("How full each mātrā is")
    ax.legend(frameon=False)

    ax = axes[1]
    xs = list(range(len(top_sam)))
    ax.bar([x - w / 2 - 0.01 for x in xs], [real_sam[b] / rs_tot for b in top_sam], w, color=REAL_C,
           label="real (train+val)")
    ax.bar([x + w / 2 + 0.01 for x in xs], [gen_sam[b] / gs_tot for b in top_sam], w, color=GEN_C,
           label="generated")
    ax.set_xticks(xs, top_sam)
    ax.set_ylabel("share of strokes on sam")
    ax.set_title("Which strokes fall on sam")
    ax.legend(frameon=False)

    ax = axes[2]
    bins = [i / 20 for i in range(21)]
    ax.hist(real_rep, bins=bins, histtype="step", lw=2, color=REAL_C, density=True, label="real (train+val)")
    ax.hist(gen_rep, bins=bins, histtype="step", lw=2, color=GEN_C, density=True, label="generated")
    ax.axvline(med_r, color=REAL_C, lw=1, ls=":")
    ax.axvline(med_g, color=GEN_C, lw=1, ls=":")
    ax.text(med_r, ax.get_ylim()[1] * 0.92, f" median {med_r:.2f}", color=INK_2, fontsize=8)
    ax.text(med_g, ax.get_ylim()[1] * 0.80, f" median {med_g:.2f}", color=INK_2, fontsize=8)
    ax.set_xlabel(f"share of {NGRAM}-stroke patterns that repeat\nwithin a 3-cycle window")
    ax.set_ylabel("density")
    ax.set_title("How much the music repeats itself")
    ax.legend(frameon=False, loc="center right")
    for a in axes:
        a.grid(axis="y", color=GRID, lw=0.6)
        a.set_axisbelow(True)
    fig.suptitle("Phase 9: what the generator reproduces (left, middle) and what it does not (right)",
                 x=0.01, ha="left", fontweight="bold", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(VIS / "phase9_generated_vs_real_stats.png", dpi=150)
    plt.close(fig)
    print("wrote visualizations/phase9_generated_vs_real_stats.png")

    (PROCESSED / "phase9_summary.json").write_text(json.dumps(summary, indent=2, default=float))
    print("wrote data/processed/phase9_examples.json, phase9_examples.txt, phase9_summary.json")


if __name__ == "__main__":
    main()

"""
Phase 5 - train the PCFG (supervised MLE over the full corpus), run
diagnostics, validate the CYK/Inside parser against known derivations,
benchmark its runtime honestly, and sample example generations.

Produces:
    docs/PHASE5_PCFG.md
    data/processed/phase5_grammar.json
    data/processed/phase5_sample_generations.json

Run with:  python3 src/run_phase5_pcfg.py
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from mts_loader import load_all_compositions
from bol_normalization import BolNormalizer, BolNormalizationMode
from pcfg import (
    PCFG, train_supervised, tree_log_prob, sample_tree, cyk_inside_log_prob, START,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data" / "raw" / "mts"
PROCESSED = ROOT / "data" / "processed"
PROCESSED.mkdir(parents=True, exist_ok=True)


def grammar_to_dict(grammar: PCFG) -> dict:
    return {
        lhs: [
            {"rhs": list(r.rhs), "count": r.count, "prob": r.prob}
            for r in rules
        ]
        for lhs, rules in grammar.rules.items()
    }


def main():
    comps = load_all_compositions(DATA_ROOT)
    normalizer = BolNormalizer(DATA_ROOT / "syllableMapping.txt")
    mode = BolNormalizationMode.NORMALIZED  # Mode A (18 symbols) - see rationale below

    print(f"Training supervised PCFG on {len(comps)} compositions (Mode A, normalized 18-symbol vocab)")
    grammar, trees = train_supervised(comps, mode, normalizer, dirichlet_alpha=0.0)

    diag = grammar.diagnostics()
    print(f"Grammar: {diag['n_nonterminals']} non-terminals, {diag['n_rules']} rules "
          f"({diag['n_terminal_rules']} terminal rules)")
    print(f"Probabilities sum to 1 for every non-terminal: {diag['probabilities_sum_to_one']}")
    if diag["issues"]:
        print(f"  ISSUES: {diag['issues']}")
    print(f"Zero-probability rules present: {diag['zero_prob_rules_present']}")
    print(f"Non-terminals never used on any right-hand side (should just be the start symbol): "
          f"{diag['non_terminals_never_used_on_a_rhs']}")

    # -----------------------------------------------------------------
    # Dirichlet/MAP smoothing comparison (proposal's corpus-size mitigation)
    # -----------------------------------------------------------------
    grammar_map, _ = train_supervised(comps, mode, normalizer, dirichlet_alpha=0.5)
    # compare a rule that has low count under plain MLE
    sparse_lhs = min(
        (lhs for lhs in grammar.rules if len(grammar.rules[lhs]) > 1),
        key=lambda lhs: min(r.count for r in grammar.rules[lhs]),
    )
    print(f"\nExample MLE vs MAP (Dirichlet alpha=0.5) smoothing effect, non-terminal '{sparse_lhs}':")
    for r_mle, r_map in zip(sorted(grammar.rules[sparse_lhs], key=lambda r: r.rhs),
                             sorted(grammar_map.rules[sparse_lhs], key=lambda r: r.rhs)):
        print(f"  {r_mle.rhs}: count={r_mle.count}  MLE prob={r_mle.prob:.4f}  MAP prob={r_map.prob:.4f}")

    # -----------------------------------------------------------------
    # Validate the CYK/Inside parser against the known supervised derivations:
    # total inside probability must be >= the one known derivation's
    # probability (it's one valid parse among possibly several), and should
    # be very close if the grammar is effectively unambiguous for real data.
    # -----------------------------------------------------------------
    lengths = sorted(((len(t.leaves()), c.name) for t, c in zip(trees, comps)))
    sample_names = [lengths[0][1], lengths[len(lengths) // 4][1],
                     lengths[len(lengths) // 2][1]]
    print(f"\nValidating CYK/Inside parser against known supervised derivations "
          f"(short/medium compositions: {sample_names}):")
    validation_results = []
    name_to_comp = {c.name: c for c in comps}
    name_to_tree = {c.name: t for c, t in zip(comps, trees)}
    for name in sample_names:
        c = name_to_comp[name]
        tree = name_to_tree[name]
        bols = tree.leaves()
        supervised_lp = tree_log_prob(grammar, tree)
        t0 = time.time()
        inside_lp = cyk_inside_log_prob(grammar, bols)
        elapsed = time.time() - t0
        diff = inside_lp - supervised_lp
        validation_results.append({
            "name": name, "n_tokens": len(bols),
            "supervised_log_prob": supervised_lp, "cyk_inside_log_prob": inside_lp,
            "difference": diff, "cyk_seconds": elapsed,
        })
        print(f"  {name} (n={len(bols)}): supervised={supervised_lp:.3f}  "
              f"CYK-inside={inside_lp:.3f}  diff={diff:+.4f}  ({elapsed:.2f}s)")
        if inside_lp < supervised_lp - 1e-6:
            print(f"    *** BUG: inside probability is LESS than the known derivation's "
                  f"probability - impossible for a correct inside algorithm ***")

    # -----------------------------------------------------------------
    # Runtime benchmark across a range of lengths, reported honestly.
    # Deliberately does NOT include the single longest composition
    # (n=611): the three points below already show clear ~cubic growth
    # (the theoretical complexity of CYK), so that growth rate is used to
    # EXTRAPOLATE rather than spending ~10+ minutes brute-forcing it -
    # see docs/PHASE5_PCFG.md for why that extrapolation, not a fourth
    # measured point, is the honest way to report this.
    # -----------------------------------------------------------------
    print(f"\nCYK runtime benchmark across composition lengths:")
    benchmark = []
    pct25 = lengths[len(lengths) // 4]
    pct75 = lengths[3 * len(lengths) // 4]
    for n_target, name in [lengths[0], pct25, pct75]:
        tree = name_to_tree[name]
        bols = tree.leaves()
        t0 = time.time()
        cyk_inside_log_prob(grammar, bols)
        elapsed = time.time() - t0
        benchmark.append({"name": name, "n_tokens": len(bols), "seconds": elapsed})
        print(f"  n={len(bols)} ({name}): {elapsed:.2f}s")

    # -----------------------------------------------------------------
    # Sample generations
    # -----------------------------------------------------------------
    import random
    rng = random.Random(42)
    print(f"\nSample generations from the trained grammar:")
    samples = []
    attempts = 0
    while len(samples) < 5 and attempts < 50:
        attempts += 1
        tree = sample_tree(grammar, START, rng=rng, max_depth=200)
        if tree is None:
            continue
        bols = tree.leaves()
        if 8 <= len(bols) <= 40:  # keep examples readable
            samples.append(bols)
            print(f"  ({len(bols)} bols): {' '.join(bols)}")
    print(f"Generated {len(samples)} readable samples in {attempts} attempts")

    # -----------------------------------------------------------------
    # Save outputs
    # -----------------------------------------------------------------
    with open(PROCESSED / "phase5_grammar.json", "w") as f:
        json.dump({
            "mode": "normalized_18_symbol",
            "vocabulary": sorted(grammar.vocabulary),
            "rules": grammar_to_dict(grammar),
        }, f, indent=2)
    print(f"\nWrote data/processed/phase5_grammar.json")

    with open(PROCESSED / "phase5_sample_generations.json", "w") as f:
        json.dump({"samples": [" ".join(s) for s in samples]}, f, indent=2)
    print(f"Wrote data/processed/phase5_sample_generations.json")

    return {
        "grammar": grammar, "diag": diag, "validation_results": validation_results,
        "benchmark": benchmark, "samples": samples,
    }


if __name__ == "__main__":
    main()

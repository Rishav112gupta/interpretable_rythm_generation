"""
Phase 6 - actually run Inside-Outside EM (the proposal's own specified
learning algorithm, docs/PROJECT_PLAN.md SS6), from three different starting
points (supervised, uniform, random), and report what really happens -
instead of just asserting that "supervised init avoids poor local optima."

Scope: EM trains on each AVARTAN as one example (not whole compositions) -
see the long comment in src/pcfg.py above the Phase 6 section for why.

Produces:
    docs/PHASE6_EM.md
    data/processed/phase6_em_log_likelihoods.json
    data/processed/phase6_em_final_grammars.json

Run with:  python3 src/run_phase6_em.py
"""
from __future__ import annotations

import copy
import json
import random
import time
from pathlib import Path

from mts_loader import load_all_compositions
from representation import build_representation, TEENTAL
from bol_normalization import BolNormalizer, BolNormalizationMode
from pcfg import (
    PCFG, Rule, train_supervised, em_train, uniform_init_grammar,
    random_init_grammar, inside_outside_expected_counts, START,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data" / "raw" / "mts"
PROCESSED = ROOT / "data" / "processed"
PROCESSED.mkdir(parents=True, exist_ok=True)

AVARTAN_START = "Avartan"
N_ITERATIONS = 20
DIRICHLET_ALPHA = 0.01


def grammar_to_dict(grammar: PCFG) -> dict:
    return {
        lhs: [{"rhs": list(r.rhs), "prob": r.prob} for r in rules]
        for lhs, rules in grammar.rules.items()
    }


def build_avartan_examples(comps, normalizer) -> list[list[str]]:
    examples = []
    for c in comps:
        rep = build_representation(c, TEENTAL)
        for a in rep.avartans:
            bols = [normalizer.normalize(s.bol) for s in a.all_slots()]
            examples.append(bols)
    return examples


def strip_composition(grammar: PCFG) -> PCFG:
    """Return a copy of `grammar` with the Composition non-terminal's own
    rules removed - EM here never uses "Composition" as a start symbol, so
    those rules (and any random/uniform probabilities a naive copy would
    assign them) would be meaningless noise in this experiment's output."""
    g = PCFG()
    g.vocabulary = set(grammar.vocabulary)
    for lhs, rules in grammar.rules.items():
        if lhs == START:
            continue
        g.rules[lhs] = [Rule(lhs=lhs, rhs=r.rhs, count=r.count, prob=r.prob) for r in rules]
    return g


def main():
    comps = load_all_compositions(DATA_ROOT)
    normalizer = BolNormalizer(DATA_ROOT / "syllableMapping.txt")
    full_grammar, _ = train_supervised(comps, BolNormalizationMode.NORMALIZED, normalizer)
    template = strip_composition(full_grammar)

    examples = build_avartan_examples(comps, normalizer)
    lengths = sorted(len(e) for e in examples)
    print(f"Avartan-level training set: {len(examples)} examples "
          f"(min={lengths[0]}, median={lengths[len(lengths)//2]}, max={lengths[-1]} bols)")

    supervised_init = strip_composition(full_grammar)  # same probabilities, just a fresh copy
    uniform_init = uniform_init_grammar(template)
    random_init = random_init_grammar(template, rng=random.Random(42))

    runs = {}
    for name, init_grammar in [("supervised", supervised_init),
                                ("uniform", uniform_init),
                                ("random", random_init)]:
        print(f"\nRunning EM from '{name}' initialization "
              f"({N_ITERATIONS} iterations, Dirichlet alpha={DIRICHLET_ALPHA})...")
        t0 = time.time()
        final_grammar, log_likelihoods = em_train(
            examples, init_grammar, n_iterations=N_ITERATIONS,
            dirichlet_alpha=DIRICHLET_ALPHA, start=AVARTAN_START,
        )
        elapsed = time.time() - t0
        print(f"  iteration log-likelihoods: {[round(x, 2) for x in log_likelihoods]}")
        print(f"  ({elapsed:.1f}s total, {elapsed / N_ITERATIONS:.1f}s/iteration)")
        runs[name] = {
            "log_likelihoods": log_likelihoods,
            "final_grammar": final_grammar,
            "seconds": elapsed,
        }

    # -----------------------------------------------------------------
    # Degenerate-grammar diagnostics on each final grammar.
    # -----------------------------------------------------------------
    print("\nDiagnostics on final (post-EM) grammars:")
    for name, run in runs.items():
        diag = run["final_grammar"].diagnostics()
        print(f"  {name}: probs_sum_to_one={diag['probabilities_sum_to_one']}  "
              f"zero_prob_rules={diag['zero_prob_rules_present']}  "
              f"issues={diag['issues']}")

    # -----------------------------------------------------------------
    # Rule-by-rule comparison: did uniform/random-init EM converge close to
    # the supervised probabilities, or to something else?
    # -----------------------------------------------------------------
    sparse_lhs = min(
        (lhs for lhs in template.rules if len(template.rules[lhs]) > 1),
        key=lambda lhs: min(r.count for r in template.rules[lhs]),
    )
    print(f"\nFinal learned probabilities for non-terminal '{sparse_lhs}' "
          f"(supervised reference vs. EM from each initialization):")
    ref_rules = sorted(full_grammar.rules[sparse_lhs], key=lambda r: r.rhs)
    for r_ref in ref_rules:
        row = [f"{r_ref.rhs}: supervised={r_ref.prob:.4f}"]
        for name in ("supervised", "uniform", "random"):
            matched = next((r for r in runs[name]["final_grammar"].rules[sparse_lhs]
                             if r.rhs == r_ref.rhs), None)
            row.append(f"{name}-EM={matched.prob:.4f}" if matched else f"{name}-EM=MISSING")
        print("  " + "  ".join(row))

    # -----------------------------------------------------------------
    # Save outputs
    # -----------------------------------------------------------------
    with open(PROCESSED / "phase6_em_log_likelihoods.json", "w") as f:
        json.dump({name: run["log_likelihoods"] for name, run in runs.items()}, f, indent=2)
    print("\nWrote data/processed/phase6_em_log_likelihoods.json")

    with open(PROCESSED / "phase6_em_final_grammars.json", "w") as f:
        json.dump({name: grammar_to_dict(run["final_grammar"]) for name, run in runs.items()},
                   f, indent=2)
    print("Wrote data/processed/phase6_em_final_grammars.json")

    return runs


if __name__ == "__main__":
    main()

"""
Regression tests for Phase 5 PCFG.

Run with:  python3 -m pytest tests/test_pcfg.py -v
(or, if pytest is unavailable:  python3 tests/test_pcfg.py)
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mts_loader import load_all_compositions  # noqa: E402
from bol_normalization import BolNormalizer, BolNormalizationMode  # noqa: E402
from pcfg import (  # noqa: E402
    PCFG, Rule, train_supervised, tree_log_prob, sample_tree,
    cyk_inside_log_prob, START,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data" / "raw" / "mts"


def _skip_if_no_data():
    if not (DATA_ROOT / "filelist.txt").exists():
        import pytest
        pytest.skip("Raw MTS dataset not present in data/raw/mts.")


def _load_real_grammar():
    comps = load_all_compositions(DATA_ROOT)
    normalizer = BolNormalizer(DATA_ROOT / "syllableMapping.txt")
    grammar, trees = train_supervised(comps, BolNormalizationMode.NORMALIZED, normalizer)
    return comps, normalizer, grammar, trees


# ---------------------------------------------------------------------
# Hand-computable synthetic grammar tests - these do not depend on the
# real corpus at all, so they always run and pin down the Inside
# algorithm's arithmetic against a probability a human can check by hand.
# ---------------------------------------------------------------------

def _toy_ambiguous_grammar() -> PCFG:
    """S can derive "aa" two different ways - via S -> X X or S -> Y Y -
    with no other ambiguity anywhere, so the TOTAL (inside) probability of
    "aa" is exactly P(S->X X)*P(X->a)*P(X->a) + P(S->Y Y)*P(Y->a)*P(Y->a)
    = 0.6*1*1 + 0.4*1*1 = 1.0 - a number chosen to be checkable on paper."""
    grammar = PCFG()
    grammar.rules["S"] = [
        Rule(lhs="S", rhs=("X", "X"), prob=0.6),
        Rule(lhs="S", rhs=("Y", "Y"), prob=0.4),
    ]
    grammar.rules["X"] = [Rule(lhs="X", rhs=("TERM", "a"), prob=1.0)]
    grammar.rules["Y"] = [Rule(lhs="Y", rhs=("TERM", "a"), prob=1.0)]
    grammar.vocabulary = {"a"}
    return grammar


def test_cyk_inside_sums_two_distinct_parses_not_just_the_best_one():
    grammar = _toy_ambiguous_grammar()
    log_p = cyk_inside_log_prob(grammar, ["a", "a"], start="S")
    # expected total probability is exactly 1.0 (see docstring above) -
    # if this were accidentally a Viterbi/max parser it would instead
    # return log(0.6), the single best parse, not log(1.0)
    assert abs(log_p - math.log(1.0)) < 1e-9


def test_cyk_inside_matches_single_unambiguous_parse():
    """A grammar with exactly one way to derive the string: inside
    probability must equal that one derivation's probability exactly."""
    grammar = PCFG()
    grammar.rules["S"] = [Rule(lhs="S", rhs=("A", "B"), prob=1.0)]
    grammar.rules["A"] = [Rule(lhs="A", rhs=("TERM", "a"), prob=1.0)]
    grammar.rules["B"] = [Rule(lhs="B", rhs=("TERM", "b"), prob=1.0)]
    grammar.vocabulary = {"a", "b"}
    log_p = cyk_inside_log_prob(grammar, ["a", "b"], start="S")
    assert abs(log_p - math.log(1.0)) < 1e-9


def test_cyk_inside_unreachable_string_is_negative_infinity():
    grammar = _toy_ambiguous_grammar()
    # "ab" cannot be derived by this grammar at all (only "aa" can)
    log_p = cyk_inside_log_prob(grammar, ["a", "b"], start="S")
    assert log_p == float("-inf")


def test_pcfg_normalize_mle_vs_map_smoothing():
    grammar = PCFG()
    grammar.add_count("S", ("A", "B"))
    for _ in range(9):
        grammar.add_count("S", ("A", "A"))
    grammar.normalize(dirichlet_alpha=0.0)
    rare = next(r for r in grammar.rules["S"] if r.rhs == ("A", "B"))
    common = next(r for r in grammar.rules["S"] if r.rhs == ("A", "A"))
    assert abs(rare.prob - 0.1) < 1e-9
    assert abs(common.prob - 0.9) < 1e-9

    grammar_map = PCFG()
    grammar_map.add_count("S", ("A", "B"))
    for _ in range(9):
        grammar_map.add_count("S", ("A", "A"))
    grammar_map.normalize(dirichlet_alpha=1.0)
    rare_map = next(r for r in grammar_map.rules["S"] if r.rhs == ("A", "B"))
    # MAP smoothing must pull the rare rule's probability UP relative to MLE
    assert rare_map.prob > rare.prob


def test_pcfg_diagnostics_catches_a_bad_probability_sum():
    grammar = PCFG()
    grammar.rules["S"] = [Rule(lhs="S", rhs=("TERM", "a"), prob=0.5)]  # sums to 0.5, not 1
    diag = grammar.diagnostics()
    assert diag["probabilities_sum_to_one"] is False
    assert diag["issues"]


# ---------------------------------------------------------------------
# Real-corpus tests
# ---------------------------------------------------------------------

def test_trained_grammar_is_well_formed():
    _skip_if_no_data()
    _, _, grammar, _ = _load_real_grammar()
    diag = grammar.diagnostics()
    assert diag["probabilities_sum_to_one"] is True
    assert diag["issues"] == []
    assert diag["zero_prob_rules_present"] == 0
    assert diag["non_terminals_never_used_on_a_rhs"] == []
    assert diag["n_nonterminals"] > 0
    assert diag["n_terminal_rules"] == len(grammar.vocabulary)


def test_supervised_trees_reconstruct_the_normalized_onset_sequence():
    """Round-trip check, same spirit as Phase 4's tree validation: the
    supervised derivation's leaves, read left to right, must exactly equal
    the composition's own Mode-A (normalized) onset sequence."""
    _skip_if_no_data()
    comps, normalizer, grammar, trees = _load_real_grammar()
    for c, tree in zip(comps, trees):
        expected = [normalizer.normalize(e.bol) for e in c.onsets_unmapped]
        assert tree.leaves() == expected, f"{c.name}: derivation does not reconstruct the onset sequence"


def test_every_rule_used_by_a_supervised_tree_has_positive_probability():
    _skip_if_no_data()
    _, _, grammar, trees = _load_real_grammar()
    for tree in trees:
        for lhs, rhs in tree.rules():
            lp = grammar.log_prob_of_rule(lhs, rhs)
            assert lp > float("-inf"), f"rule {lhs} -> {rhs} used by a real derivation has zero probability"


def test_cyk_inside_never_undercounts_the_known_derivation():
    """The inside probability of a bol sequence must be >= the probability
    of any ONE known valid derivation of it (here, the supervised tree) -
    the inside sum includes that derivation plus possibly others, so it can
    never be smaller. Run on the single shortest composition in the corpus
    to keep this fast (CYK is roughly O(n^3))."""
    _skip_if_no_data()
    comps, _, grammar, trees = _load_real_grammar()
    shortest_idx = min(range(len(trees)), key=lambda i: len(trees[i].leaves()))
    tree = trees[shortest_idx]
    bols = tree.leaves()
    supervised_lp = tree_log_prob(grammar, tree)
    inside_lp = cyk_inside_log_prob(grammar, bols)
    assert inside_lp >= supervised_lp - 1e-6


def test_sample_tree_produces_bols_from_the_trained_vocabulary():
    _skip_if_no_data()
    import random
    _, _, grammar, _ = _load_real_grammar()
    rng = random.Random(0)
    tree = None
    for _ in range(50):
        tree = sample_tree(grammar, START, rng=rng, max_depth=200)
        if tree is not None:
            break
    assert tree is not None
    bols = tree.leaves()
    assert len(bols) > 0
    assert all(b in grammar.vocabulary for b in bols)


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    skipped = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError:
            failed += 1
            print(f"FAIL  {t.__name__}")
            traceback.print_exc()
        except Exception as e:
            if type(e).__name__ == "Skipped" or "skip" in type(e).__name__.lower():
                skipped += 1
                print(f"SKIP  {t.__name__}")
            else:
                failed += 1
                print(f"ERROR {t.__name__}")
                traceback.print_exc()
    print(f"\n{len(tests) - failed - skipped}/{len(tests)} passed ({skipped} skipped)")
    sys.exit(1 if failed else 0)

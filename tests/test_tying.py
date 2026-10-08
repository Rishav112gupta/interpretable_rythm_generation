"""
Regression tests for Phase 8: tail labels and parameter tying.

Run with:  python3 -m pytest tests/test_tying.py -v
(or, if pytest is unavailable:  python3 tests/test_tying.py)
"""
import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mts_loader import load_all_compositions  # noqa: E402
from representation import build_representation, TEENTAL  # noqa: E402
from bol_normalization import BolNormalizer, BolNormalizationMode  # noqa: E402
from pcfg import train_supervised, tree_log_prob, _bolslot_list_node, MATRA  # noqa: E402
from tying import (  # noqa: E402
    Variant, MatraRecord, matra_records, events, TiedModel, cross_validate,
    paired_bootstrap, GROUPINGS,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data" / "raw" / "mts"
VOCAB = ["DHA", "NA", "TA"]


def _skip_if_no_data():
    if not (DATA_ROOT / "filelist.txt").exists():
        import pytest
        pytest.skip("Raw MTS dataset not present in data/raw/mts.")


def test_tail_label_chain_shape():
    node = _bolslot_list_node(MATRA, ["DHA", "TI", "TA"], MATRA + "Tail")
    assert [lhs for lhs, _ in node.rules() if lhs != "BolSlot"] == ["Matra", "MatraTail", "MatraTail"]
    assert node.leaves() == ["DHA", "TI", "TA"]


def test_events_counted_by_hand():
    recs = [MatraRecord(0, True, ["DHA", "NA"]), MatraRecord(0, False, []),
            MatraRecord(2, False, ["TA"])]
    ev = events(recs, n_avartans=2, variant=Variant("khali", "sam", tails=True))
    assert ev[(("comp",), "continue")] == 1 and ev[(("comp",), "stop")] == 1
    assert ev[(("top", "sam"), "continue")] == 1
    assert ev[(("tail", "sam"), "stop")] == 1
    assert ev[(("top", "other"), "rest")] == 1
    assert ev[(("top", "other"), "single")] == 1
    assert ev[(("stroke", "bhari"), "DHA")] == 1 and ev[(("stroke", "bhari"), "NA")] == 1
    assert ev[(("stroke", "khali"), "TA")] == 1


def test_no_tail_events_reuse_the_top_table():
    ev = events([MatraRecord(1, False, ["DHA", "NA", "TA"])], 1, Variant("one", "one", tails=False))
    assert ev[(("top", "all"), "continue")] == 2 and ev[(("top", "all"), "single")] == 1


def test_smoothed_tables_sum_to_one_and_soft_tie_limits():
    counts = Counter({(("stroke", "a"), "DHA"): 9, (("stroke", "a"), "NA"): 1,
                      (("stroke", "b"), "TA"): 10})
    hard = TiedModel(counts, VOCAB, alpha=0.5)
    zero_beta = TiedModel(counts, VOCAB, alpha=0.5, beta=0.0)
    huge = TiedModel(counts, VOCAB, alpha=0.5, beta=1e9)
    for m in (hard, zero_beta, huge):
        for g in ("a", "b"):
            assert abs(sum(m.table(("stroke", g)).values()) - 1) < 1e-12
    assert hard.table(("stroke", "a")) == zero_beta.table(("stroke", "a"))
    pooled = huge._pooled_prob("stroke")
    for e in VOCAB:
        assert abs(huge.table(("stroke", "a"))[e] - pooled[e]) < 1e-6
    assert abs(hard.table(("stroke", "a"))["DHA"] - 9.5 / 11.5) < 1e-12


def test_cross_validation_never_trains_on_the_held_out_unit():
    """A unit whose only stroke is never seen elsewhere must get exactly the
    unseen-event probability alpha / (n + alpha*K)."""
    ev = {"x": Counter({(("stroke", "all"), "DHA"): 4}),
          "y": Counter({(("stroke", "all"), "TA"): 1})}
    scores = cross_validate([["x"], ["y"]], ev, {"x": 4, "y": 1}, VOCAB, alpha=0.5)
    expected = -math.log2(0.5 / (4 + 0.5 * 3))
    assert abs(scores["y"][0] - expected) < 1e-12


def test_paired_bootstrap_identical_models_is_zero():
    a = {"x": (10.0, 5), "y": (20.0, 5)}
    obs, lo, hi = paired_bootstrap(a, a, n_boot=200)
    assert obs == lo == hi == 0.0


def test_every_grouping_puts_sam_somewhere():
    for name, f in GROUPINGS.items():
        assert isinstance(f(0, True), str) and isinstance(f(2, False), str)


def test_event_model_equals_pcfg_up_to_constant_structure_cost():
    """Unsmoothed, fit on the whole corpus: the event score of every
    composition differs from pcfg.tree_log_prob by exactly the plain grammar's
    structural cost per cycle, 9*log2(3) + 6*log2(3/2) bits - so the two are
    the same model apart from the cycle structure the attribute layer fixes."""
    _skip_if_no_data()
    comps = load_all_compositions(DATA_ROOT)
    norm = BolNormalizer(DATA_ROOT / "syllableMapping.txt")
    g, trees = train_supervised(comps, BolNormalizationMode.NORMALIZED, norm,
                                include_rests=True, tail_labels=True)
    vocab = sorted(norm.mapped_to_raw)
    ev, nav = {}, {}
    for c in comps:
        rep = build_representation(c, TEENTAL)
        for s in rep.all_slots():
            s.bol = norm.normalize(s.bol)
        ev[c.name] = events(matra_records(rep), len(rep.avartans), Variant("one", "sam", True))
        nav[c.name] = len(rep.avartans)
    total = Counter()
    for e in ev.values():
        total.update(e)
    model = TiedModel(total, vocab, alpha=0.0)
    per_cycle = 9 * math.log2(3) + 6 * math.log2(1.5)
    for c, t in zip(comps, trees):
        pcfg_bits = -tree_log_prob(g, t) / math.log(2)
        event_bits = -model.log2_prob(ev[c.name])
        assert abs((pcfg_bits - event_bits) - per_cycle * nav[c.name]) < 1e-6, c.name


def test_default_grammar_unchanged_by_tail_option():
    _skip_if_no_data()
    comps = load_all_compositions(DATA_ROOT)
    norm = BolNormalizer(DATA_ROOT / "syllableMapping.txt")
    d = train_supervised(comps, BolNormalizationMode.NORMALIZED, norm)[0].diagnostics()
    assert d["n_nonterminals"] == 9 and d["n_rules"] == 44
    d = train_supervised(comps, BolNormalizationMode.NORMALIZED, norm, include_rests=True)[0].diagnostics()
    assert d["n_nonterminals"] == 10 and d["n_rules"] == 38


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
            if "skip" in type(e).__name__.lower():
                skipped += 1
                print(f"SKIP  {t.__name__}")
            else:
                failed += 1
                print(f"ERROR {t.__name__}")
                traceback.print_exc()
    print(f"\n{len(tests) - failed - skipped}/{len(tests)} passed ({skipped} skipped)")
    sys.exit(1 if failed else 0)

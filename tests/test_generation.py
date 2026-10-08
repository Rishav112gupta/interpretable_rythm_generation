"""
Regression tests for Phase 9: the selected grammar and the generation outputs.

Run with:  python3 -m pytest tests/test_generation.py -v
(or, if pytest is unavailable:  python3 tests/test_generation.py)
"""
import math
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mts_loader import load_all_compositions  # noqa: E402
from representation import build_representation, TEENTAL  # noqa: E402
from bol_normalization import BolNormalizer, BolNormalizationMode  # noqa: E402
from pcfg import train_supervised, tree_log_prob, SAM_BOLSLOT, BOLSLOT  # noqa: E402
from tying import Variant, matra_records, events, TiedModel  # noqa: E402
from attributes import timed_sequence, check_tihai  # noqa: E402
from generation import generate_composition  # noqa: E402
from run_phase9_generation import self_repetition, notation  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data" / "raw" / "mts"


def _skip_if_no_data():
    if not (DATA_ROOT / "filelist.txt").exists():
        import pytest
        pytest.skip("Raw MTS dataset not present in data/raw/mts.")


def test_self_repetition_by_hand():
    # 4-grams: ABCD, BCDA, CDAB, DABC, ABCD -> ABCD appears twice (positions 0 and 4)
    assert self_repetition(list("ABCDABCD")) == 2 / 5
    assert self_repetition(list("ABCDEFGH")) == 0.0
    assert self_repetition(list("ABC")) == 0.0


def _load():
    comps = load_all_compositions(DATA_ROOT)
    norm = BolNormalizer(DATA_ROOT / "syllableMapping.txt")
    return comps, norm


def test_sam_strokes_only_relabel_sam_matra_strokes():
    _skip_if_no_data()
    comps, norm = _load()
    g, trees = train_supervised(comps, BolNormalizationMode.NORMALIZED, norm,
                                include_rests=True, tail_labels=True, sam_strokes=True)
    lhs_of_sam_slot = {lhs for lhs, rules in g.rules.items()
                       for r in rules if SAM_BOLSLOT in r.rhs}
    assert lhs_of_sam_slot == {"SamMatra", "SamMatraTail"}
    lhs_of_slot = {lhs for lhs, rules in g.rules.items() for r in rules if BOLSLOT in r.rhs}
    assert lhs_of_slot == {"Matra", "MatraTail"}
    d = train_supervised(comps, BolNormalizationMode.NORMALIZED, norm)[0].diagnostics()
    assert d["n_rules"] == 44  # Phase 5 default still unchanged


def test_generation_grammar_is_the_phase8_selected_model():
    """Unsmoothed on the whole corpus, the generation grammar must equal the
    Phase 8 tied model (strokes split by sam, shapes split by sam, tails),
    up to the constant 17.774-bit structure cost per cycle."""
    _skip_if_no_data()
    comps, norm = _load()
    g, trees = train_supervised(comps, BolNormalizationMode.NORMALIZED, norm,
                                include_rests=True, tail_labels=True, sam_strokes=True)
    vocab = sorted(norm.mapped_to_raw)
    ev, nav = {}, {}
    for c in comps:
        rep = build_representation(c, TEENTAL)
        for s in rep.all_slots():
            s.bol = norm.normalize(s.bol)
        ev[c.name] = events(matra_records(rep), len(rep.avartans), Variant("sam", "sam", True))
        nav[c.name] = len(rep.avartans)
    total = Counter()
    for e in ev.values():
        total.update(e)
    model = TiedModel(total, vocab, alpha=0.0)
    per_cycle = 9 * math.log2(3) + 6 * math.log2(1.5)
    for c, t in zip(comps, trees):
        diff = -tree_log_prob(g, t) / math.log(2) + model.log2_prob(ev[c.name])
        assert abs(diff - per_cycle * nav[c.name]) < 1e-6, c.name


def test_generated_examples_pass_checks_and_notation_is_per_cycle():
    _skip_if_no_data()
    comps, norm = _load()
    g, _ = train_supervised(comps, BolNormalizationMode.NORMALIZED, norm,
                            include_rests=True, tail_labels=True, sam_strokes=True)
    for seed in range(5):
        root, info = generate_composition(g, random.Random(seed), n_body_avartans=2)
        pos = [s for _, s, _ in timed_sequence(root)]
        x = check_tihai(pos, info["tihai_first_token"], info["phrase_tokens"], 1, tol=0)
        assert x.strict_b and x.gap_in_plan_set
        lines = notation(root)
        assert len(lines) == 4  # 2 body cycles, tihai cycle, closing sam
        assert all(line.startswith("X[") for line in lines)
        assert lines[-1].count("[") == 1  # closing sam: one matra only


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

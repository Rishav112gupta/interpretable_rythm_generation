"""
Regression tests for Phase 7: attribute layer, tihai arithmetic check,
constrained generation.

Run with:  python3 -m pytest tests/test_attributes.py -v
(or, if pytest is unavailable:  python3 tests/test_attributes.py)
"""
import random
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mts_loader import load_all_compositions  # noqa: E402
from representation import build_representation, TEENTAL  # noqa: E402
from bol_normalization import BolNormalizer, BolNormalizationMode  # noqa: E402
from pcfg import (  # noqa: E402
    DerivNode, train_supervised, build_avartan_deriv, MATRA, SAM_MATRA, BOLSLOT,
    VIBHAG, AVARTAN, REST_TOKEN,
)
from attributes import (  # noqa: E402
    annotate, timed_sequence, is_well_formed_avartan, check_tihai, leaf_nodes,
)
from generation import (  # noqa: E402
    sample_avartan_constrained, generate_composition, valid_tihai_shapes,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data" / "raw" / "mts"


def _skip_if_no_data():
    if not (DATA_ROOT / "filelist.txt").exists():
        import pytest
        pytest.skip("Raw MTS dataset not present in data/raw/mts.")


def _matra(label, bols):
    """Right-branching X -> BolSlot X | BolSlot, as Phase 5 builds it."""
    leaf = DerivNode(label=BOLSLOT, bol=bols[0])
    if len(bols) == 1:
        return DerivNode(label=label, children=[leaf])
    return DerivNode(label=label, children=[leaf, _matra(label, bols[1:])])


def _avartan(n_matras_per_vibhag=(4, 4, 4, 4)):
    vibs = []
    for v, n in enumerate(n_matras_per_vibhag):
        ms = [_matra(SAM_MATRA if v == 0 and i == 0 else MATRA, ["DHA"]) for i in range(n)]
        node = DerivNode(label=VIBHAG[v], children=ms)  # n-ary is fine for the attribute walk
        vibs.append(node)
    return DerivNode(label=AVARTAN, children=vibs)


_GRAMMAR_CACHE = {}


def _rest_grammar():
    if "g" not in _GRAMMAR_CACHE:
        comps = load_all_compositions(DATA_ROOT)
        norm = BolNormalizer(DATA_ROOT / "syllableMapping.txt")
        _GRAMMAR_CACHE["g"] = train_supervised(comps, BolNormalizationMode.NORMALIZED, norm,
                                               include_rests=True)[0]
        _GRAMMAR_CACHE["comps"] = comps
    return _GRAMMAR_CACHE["g"]


# ---------------------------------------------------------------------
# Attribute layer (synthetic, no corpus needed)
# ---------------------------------------------------------------------

def test_matra_splits_equally_with_exact_fractions():
    m = _matra(MATRA, ["DHA", "TI", "TA"])
    annotate(m, Fraction(5))
    seq = timed_sequence(m)
    assert [s for _, s, _ in seq] == [Fraction(5), Fraction(16, 3), Fraction(17, 3)]
    assert all(d == Fraction(1, 3) for _, _, d in seq)
    assert m.start == 5 and m.dur == 1


def test_well_formed_avartan_accepted_and_malformed_rejected():
    good = _avartan()
    annotate(good, Fraction(0))
    assert is_well_formed_avartan(good) == (True, "")
    assert good.dur == 16

    short = _avartan((4, 4, 3, 4))
    annotate(short, Fraction(0))
    ok, reason = is_well_formed_avartan(short)
    assert not ok and "15 matras" in reason


def test_leaf_outside_a_matra_requires_a_preset_duration():
    node = DerivNode(label="Gap", children=[DerivNode(label="Rest", bol=REST_TOKEN)])
    try:
        annotate(node, Fraction(0))
    except ValueError:
        return
    raise AssertionError("expected ValueError for a rest with no duration")


# ---------------------------------------------------------------------
# Tihai arithmetic (synthetic, hand-checkable)
# ---------------------------------------------------------------------

def _tihai_positions(start, dur_p, dur_g, tokens_per_phrase=2):
    """Positions for: phrase(2 tokens) gap(1 token) phrase gap phrase, then one
    more stroke - phrase tokens evenly split dur_p."""
    pos = []
    t = Fraction(start)
    step = Fraction(dur_p) / tokens_per_phrase
    for k in range(3):
        for _ in range(tokens_per_phrase):
            pos.append(t)
            t += step
        if k < 2:
            pos.append(t)
            t += Fraction(dur_g)
    pos.append(t)  # the stroke right after the tihai
    return pos


def test_check_tihai_reading_b_exact_landing():
    # 3*2 + 2*1 = 8 matras starting at 8 -> the next stroke is at 16, a sam
    pos = _tihai_positions(start=8, dur_p=2, dur_g=1)
    x = check_tihai(pos, 0, 2, 1, tol=0)
    assert x.dur_p == 2 and x.dur_g == 1
    assert x.regular and x.gap_in_plan_set
    assert x.lands_b_observed and x.lands_b_formula and x.strict_b
    assert not x.lands_a  # the last phrase stroke is at 15, not on sam


def test_check_tihai_off_by_a_quarter_is_rejected_exactly():
    pos = _tihai_positions(start=Fraction(33, 4), dur_p=2, dur_g=1)
    x = check_tihai(pos, 0, 2, 1, tol=0)
    assert not x.lands_b_observed and not x.strict_b


def test_check_tihai_reading_a():
    # phrase of 2 tokens over 2 matras, last token starts 1 matra before phrase end;
    # start at 9 -> last phrase stroke at 9 + 8 - 1 = 16 (sam) under reading A
    pos = _tihai_positions(start=9, dur_p=2, dur_g=1)
    x = check_tihai(pos, 0, 2, 1, tol=0)
    assert x.lands_a and not x.lands_b_observed


def test_gap_outside_plan_set_is_flagged():
    pos = _tihai_positions(start=0, dur_p=2, dur_g=Fraction(5, 2))
    x = check_tihai(pos, 0, 2, 1, tol=0)
    assert not x.gap_in_plan_set


def test_valid_tihai_shapes_fit_after_own_sam():
    shapes = valid_tihai_shapes()
    assert len(shapes) == 23
    assert all(3 * p + 2 * g <= 15 for p, g in shapes)


# ---------------------------------------------------------------------
# Real corpus
# ---------------------------------------------------------------------

def test_phase5_default_grammar_is_unchanged_by_rest_option():
    """include_rests is opt-in: the default must still reproduce Phase 5's
    reported grammar (9 non-terminals, 44 rules)."""
    _skip_if_no_data()
    comps = load_all_compositions(DATA_ROOT)
    norm = BolNormalizer(DATA_ROOT / "syllableMapping.txt")
    g, _ = train_supervised(comps, BolNormalizationMode.NORMALIZED, norm)
    d = g.diagnostics()
    assert d["n_nonterminals"] == 9 and d["n_rules"] == 44


def test_every_real_avartan_is_well_formed_with_rests():
    """With empty matras made explicit, every real cycle must be exactly 16
    matras in vibhag order with sam first - and its strokes (ignoring rests)
    must be the original onset sequence in order."""
    _skip_if_no_data()
    comps = load_all_compositions(DATA_ROOT)
    for c in comps:
        rep = build_representation(c, TEENTAL)
        for a in rep.avartans:
            t = build_avartan_deriv(a, include_rests=True)
            annotate(t, Fraction(0))
            assert is_well_formed_avartan(t)[0], f"{c.name} avartan {a.index}"
            strokes = [lf.bol for lf in leaf_nodes(t) if lf.bol != REST_TOKEN]
            assert strokes == [s.bol for s in a.all_slots()]


def test_constrained_sampling_always_well_formed():
    _skip_if_no_data()
    g = _rest_grammar()
    rng = random.Random(3)
    for _ in range(100):
        t = sample_avartan_constrained(g, rng)
        annotate(t, Fraction(0))
        assert is_well_formed_avartan(t)[0]


def test_generated_tihai_lands_exactly_on_next_sam():
    _skip_if_no_data()
    g = _rest_grammar()
    rng = random.Random(11)
    for _ in range(30):
        root, info = generate_composition(g, rng, n_body_avartans=1)
        seq = timed_sequence(root)
        tokens = [t for t, _, _ in seq]
        pos = [s for _, s, _ in seq]
        st, p = info["tihai_first_token"], info["phrase_tokens"]
        x = check_tihai(pos, st, p, 1, tol=0)
        assert x.strict_b and x.lands_b_formula and x.gap_in_plan_set
        assert tokens[st:st + p] == tokens[st + p + 1:st + 2 * p + 1] == tokens[st + 2 * p + 2:st + 3 * p + 2]
        assert pos[st + 3 * p + 2] % 16 == 0
        assert tokens[st + 3 * p + 2] != REST_TOKEN  # an actual stroke on sam


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

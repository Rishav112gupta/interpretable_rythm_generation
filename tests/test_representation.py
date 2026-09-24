"""
Regression tests for Phase 3 rhythmic representation.

Run with:  python3 -m pytest tests/test_representation.py -v
(or, if pytest is unavailable:  python3 tests/test_representation.py)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mts_loader import load_all_compositions, load_composition  # noqa: E402
from representation import build_representation, TEENTAL, TalaDefinition  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data" / "raw" / "mts"


def _skip_if_no_data():
    if not (DATA_ROOT / "filelist.txt").exists():
        import pytest
        pytest.skip("Raw MTS dataset not present in data/raw/mts.")


def test_teental_definition_invariants():
    assert TEENTAL.n_matras == 16
    assert TEENTAL.n_vibhags == 4
    assert TEENTAL.matras_per_vibhag == 4
    assert TEENTAL.khali_vibhags == (2,)


def test_tala_definition_rejects_inconsistent_matra_count():
    try:
        TalaDefinition(name="BAD", n_matras=10, n_vibhags=4, matras_per_vibhag=4,
                        khali_vibhags=(), source="test")
        assert False, "expected an assertion error for 4*4 != 10"
    except AssertionError:
        pass


def test_no_onset_data_lost_for_dli_1():
    _skip_if_no_data()
    comp = load_composition(DATA_ROOT, "dli_1")
    rep = build_representation(comp, TEENTAL)
    assert len(rep.all_slots()) == len(comp.onsets_unmapped)


def test_all_slots_within_valid_matra_and_vibhag_range():
    _skip_if_no_data()
    comps = load_all_compositions(DATA_ROOT)
    for c in comps:
        rep = build_representation(c, TEENTAL)
        for s in rep.all_slots():
            assert 0 <= s.matra_index < TEENTAL.n_matras, (c.name, s)
            assert 0 <= s.vibhag_index < TEENTAL.n_vibhags, (c.name, s)
            assert s.vibhag_index == s.matra_index // TEENTAL.matras_per_vibhag


def test_sam_flag_matches_matra_zero_exactly():
    _skip_if_no_data()
    comps = load_all_compositions(DATA_ROOT)
    for c in comps:
        rep = build_representation(c, TEENTAL)
        for s in rep.all_slots():
            assert s.is_sam == (s.matra_index == 0), (c.name, s)


def test_khali_flag_matches_third_vibhag_exactly():
    _skip_if_no_data()
    comps = load_all_compositions(DATA_ROOT)
    for c in comps:
        rep = build_representation(c, TEENTAL)
        for s in rep.all_slots():
            assert s.is_khali == (s.vibhag_index in TEENTAL.khali_vibhags), (c.name, s)


def test_no_onset_data_lost_across_full_corpus():
    _skip_if_no_data()
    comps = load_all_compositions(DATA_ROOT)
    mismatches = []
    for c in comps:
        rep = build_representation(c, TEENTAL)
        if len(rep.all_slots()) != len(c.onsets_unmapped):
            mismatches.append(c.name)
    assert mismatches == [], f"Slot/onset count mismatch in: {mismatches}"


def test_avartan_count_matches_number_of_nonempty_score_lines():
    _skip_if_no_data()
    comp = load_composition(DATA_ROOT, "dli_1")
    rep = build_representation(comp, TEENTAL)
    # dli_1 has 3 sections (Quayda, Dohra, Adha Dohra), 4 non-empty lines each
    expected_lines = sum(1 for sec in comp.sections for line in sec.lines if line)
    assert len(rep.avartans) == expected_lines


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError:
            failed += 1
            print(f"FAIL  {t.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)

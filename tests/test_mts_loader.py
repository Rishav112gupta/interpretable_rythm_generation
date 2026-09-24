"""
Regression tests for the Phase 1 MTS loader and audit.

These encode the audit's key findings as assertions, so that if the raw
dataset files are ever touched, or the parser is changed, a silent regression
(e.g. score/onset alignment breaking) is caught immediately rather than
discovered downstream in grammar training.

Run with:  python3 -m pytest tests/test_mts_loader.py -v
(or, if pytest is unavailable:  python3 tests/test_mts_loader.py)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mts_loader import (  # noqa: E402
    load_all_compositions,
    load_filelist,
    load_syllable_mapping,
    flatten_score_bols,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data" / "raw" / "mts"


def _skip_if_no_data():
    if not (DATA_ROOT / "filelist.txt").exists():
        import pytest
        pytest.skip("Raw MTS dataset not present in data/raw/mts — dataset is not committed to git.")


def test_filelist_has_38_compositions():
    _skip_if_no_data()
    names = load_filelist(DATA_ROOT)
    assert len(names) == 38
    assert "dli_1" in names
    assert "ajr_10_ajr" in names and "ajr_10_dli" in names


def test_syllable_mapping_has_18_symbols_no_header_leak():
    _skip_if_no_data()
    mapping = load_syllable_mapping(DATA_ROOT / "syllableMapping.txt")
    assert len(mapping) == 18
    assert "Symbol" not in mapping  # regression guard for the header-row parsing bug


def test_onsmap_vocabulary_matches_syllable_mapping_exactly():
    _skip_if_no_data()
    mapping = load_syllable_mapping(DATA_ROOT / "syllableMapping.txt")
    comps = load_all_compositions(DATA_ROOT)
    observed = {e.bol for c in comps for e in c.onsets_mapped}
    assert observed == set(mapping.keys())


def test_score_and_onset_streams_align_exactly_for_all_compositions():
    _skip_if_no_data()
    comps = load_all_compositions(DATA_ROOT)
    assert len(comps) == 38
    mismatches = []
    for c in comps:
        score_bols = flatten_score_bols(c.sections, drop_rests=True)
        onset_bols = [e.bol for e in c.onsets_unmapped]
        if score_bols != onset_bols:
            mismatches.append(c.name)
    assert mismatches == [], f"Score/onset misalignment in: {mismatches}"


def test_all_compositions_are_teental():
    _skip_if_no_data()
    comps = load_all_compositions(DATA_ROOT)
    non_teental = [c.name for c in comps if c.tala != "TEENTAL"]
    assert non_teental == []


def test_splits_are_disjoint_and_keep_ajr10_variants_together():
    import json
    splits_path = ROOT / "data" / "processed" / "splits.json"
    if not splits_path.exists():
        import pytest
        pytest.skip("splits.json not generated yet — run src/run_phase1_audit.py first.")
    with open(splits_path) as f:
        splits = json.load(f)
    train, val, test = set(splits["train"]), set(splits["val"]), set(splits["test"])
    assert train & val == set()
    assert train & test == set()
    assert val & test == set()
    assert len(train) + len(val) + len(test) == 38
    linked = {"ajr_10_ajr", "ajr_10_dli"}
    assert linked <= train or linked <= val or linked <= test, (
        "ajr_10_ajr and ajr_10_dli must be in the same split (leakage risk)"
    )


if __name__ == "__main__":
    # allow running without pytest installed
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

"""
Regression tests for Phase 2 bol normalization.

Run with:  python3 -m pytest tests/test_bol_normalization.py -v
(or, if pytest is unavailable:  python3 tests/test_bol_normalization.py)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mts_loader import load_all_compositions  # noqa: E402
from bol_normalization import BolNormalizer, BolNormalizationMode, onset_bols  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data" / "raw" / "mts"


def _skip_if_no_data():
    if not (DATA_ROOT / "filelist.txt").exists():
        import pytest
        pytest.skip("Raw MTS dataset not present in data/raw/mts.")


def test_normalizer_maps_known_raw_variants_correctly():
    _skip_if_no_data()
    norm = BolNormalizer(DATA_ROOT / "syllableMapping.txt")
    # spot-check a few entries straight from syllableMapping.pdf
    assert norm.normalize("KA") == "KI"
    assert norm.normalize("GHE") == "GE"
    assert norm.normalize("TAA") == "NA"
    assert norm.normalize("KRU") == "KDA"
    assert norm.normalize("CHAP") == "TIT"
    # a mapped symbol normalizes to itself
    assert norm.normalize("DHA") == "DHA"


def test_normalizer_raises_on_unknown_bol():
    _skip_if_no_data()
    norm = BolNormalizer(DATA_ROOT / "syllableMapping.txt")
    try:
        norm.normalize("NOT_A_REAL_BOL")
        assert False, "expected KeyError for an unmapped symbol"
    except KeyError:
        pass


def test_mode_a_vocabulary_is_18_symbols_across_corpus():
    _skip_if_no_data()
    comps = load_all_compositions(DATA_ROOT)
    vocab = set()
    for c in comps:
        vocab.update(onset_bols(c, BolNormalizationMode.NORMALIZED))
    assert len(vocab) == 18


def test_mode_b_vocabulary_is_40_symbols_across_corpus():
    _skip_if_no_data()
    comps = load_all_compositions(DATA_ROOT)
    vocab = set()
    for c in comps:
        vocab.update(onset_bols(c, BolNormalizationMode.DISTINCT))
    assert len(vocab) == 40


def test_apply_matches_precomputed_onset_streams():
    """BolNormalizer.apply() on a raw stream should equal the dataset's own
    onsMap stream for the same composition — i.e. the normalizer reproduces
    the dataset's own normalization exactly, not an approximation of it."""
    _skip_if_no_data()
    comps = load_all_compositions(DATA_ROOT)
    norm = BolNormalizer(DATA_ROOT / "syllableMapping.txt")
    mismatches = []
    for c in comps:
        raw = onset_bols(c, BolNormalizationMode.DISTINCT)
        mapped_expected = onset_bols(c, BolNormalizationMode.NORMALIZED)
        mapped_actual = norm.apply(raw, BolNormalizationMode.NORMALIZED)
        if mapped_actual != mapped_expected:
            mismatches.append(c.name)
    assert mismatches == [], f"BolNormalizer.apply() diverged from onsMap for: {mismatches}"


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

"""
Regression tests for Phase 4 seed treebank.

Run with:  python3 -m pytest tests/test_treebank.py -v
(or, if pytest is unavailable:  python3 tests/test_treebank.py)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mts_loader import load_all_compositions, load_composition  # noqa: E402
from representation import build_representation, TEENTAL  # noqa: E402
from treebank import TreeNode, build_section_tree, find_tihai_candidates  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data" / "raw" / "mts"


def _skip_if_no_data():
    if not (DATA_ROOT / "filelist.txt").exists():
        import pytest
        pytest.skip("Raw MTS dataset not present in data/raw/mts.")


def test_treenode_leaves_recovers_bol_sequence():
    leaf_a = TreeNode(label="DHA", bol="DHA", start_time=0.0, duration=0.1, matra_index=0, vibhag_index=0)
    leaf_b = TreeNode(label="GE", bol="GE", start_time=0.1, duration=0.1, matra_index=0, vibhag_index=0)
    parent = TreeNode(label="Avartan", children=[leaf_a, leaf_b], rule="Avartan -> DHA GE")
    assert parent.bol_sequence() == ["DHA", "GE"]


def test_compute_synthesized_attributes_bottom_up():
    leaf_a = TreeNode(label="DHA", bol="DHA", start_time=0.0, duration=0.5, matra_index=0, vibhag_index=0)
    leaf_b = TreeNode(label="GE", bol="GE", start_time=0.5, duration=0.3, matra_index=1, vibhag_index=0)
    parent = TreeNode(label="Avartan", children=[leaf_a, leaf_b])
    parent.compute_synthesized_attributes()
    assert parent.start_time == 0.0
    assert parent.matra_index == 0
    assert abs(parent.duration - 0.8) < 1e-9


def test_quayda_trees_recover_exact_onset_sequence():
    """The core validation: for every QUAYDA-type composition, the tree's
    leaves, read left to right, must reconstruct the original onset
    sequence exactly - this is what 'validate every tree' means here."""
    _skip_if_no_data()
    comps = load_all_compositions(DATA_ROOT)
    quayda = [c for c in comps if c.comp_type and "QUAYDA" in c.comp_type]
    assert len(quayda) == 10
    for c in quayda:
        rep = build_representation(c, TEENTAL)
        tree = build_section_tree(c, rep)
        expected = [e.bol for e in c.onsets_unmapped]
        assert tree.bol_sequence() == expected, f"{c.name}: tree does not reconstruct original sequence"


def test_section_labels_matching_proposal_terms_are_tagged_as_such():
    _skip_if_no_data()
    comp = load_composition(DATA_ROOT, "dli_1")
    rep = build_representation(comp, TEENTAL)
    tree = build_section_tree(comp, rep)
    labels = [c.label for c in tree.children]
    assert labels == ["Quayda", "Dohra", "AdhaDohra"]
    dohra_node = tree.children[1]
    assert "matches proposal's documented term exactly" in dohra_node.source


def test_tihai_detector_finds_a_synthetic_exact_tihai():
    """Construct a textbook-exact tihai: phrase P, gap G, phrase P, gap G,
    phrase P - and confirm the detector finds it."""
    phrase = ["DHA", "GE", "TA"]
    gap = ["NA"]
    bols = phrase + gap + phrase + gap + phrase
    # pad with unrelated material before/after so it's not the whole sequence
    bols = ["KI", "TA"] + bols + ["DHIN"]

    class FakeSlot:
        def __init__(self, i):
            self.matra_index = i % 16
    class FakeAvartan:
        def __init__(self, slots):
            self._slots = slots
        def all_slots(self):
            return self._slots
    class FakeRep:
        def __init__(self, n):
            self.avartans = [FakeAvartan([FakeSlot(i) for i in range(n)])]

    rep = FakeRep(len(bols))
    candidates = find_tihai_candidates(bols, rep, min_phrase_len=2, max_phrase_len=6, max_gap_len=3)
    assert len(candidates) == 1
    assert candidates[0].phrase == phrase
    assert candidates[0].gap == gap
    assert candidates[0].phrase_len == 3
    assert candidates[0].gap_len == 1


def test_tihai_detector_runs_on_real_corpus_without_error():
    _skip_if_no_data()
    comps = load_all_compositions(DATA_ROOT)
    total = 0
    for c in comps:
        rep = build_representation(c, TEENTAL)
        bols = [e.bol for e in c.onsets_unmapped]
        cands = find_tihai_candidates(bols, rep)
        total += len(cands)
        for cand in cands:
            # every candidate's phrase must actually repeat 3x with the same gap, by construction
            start = cand.start_slot_index
            p, g = cand.phrase_len, cand.gap_len
            assert bols[start:start + p] == cand.phrase
            assert bols[start + p:start + p + g] == cand.gap
            assert bols[start + p + g:start + 2 * p + g] == cand.phrase
            assert bols[start + 2 * p + g:start + 2 * p + 2 * g] == cand.gap
            assert bols[start + 2 * p + 2 * g:start + 3 * p + 2 * g] == cand.phrase
    assert total > 0


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

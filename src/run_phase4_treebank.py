"""
Phase 4 - build and validate the seed treebank.

Produces:
    docs/PHASE4_SEED_TREEBANK.md
    data/processed/phase4_treebank.jsonl          (the 10 QUAYDA-type trees)
    data/processed/phase4_tihai_candidates.json   (algorithmic tihai search, all 38 compositions)

Run with:  python3 src/run_phase4_treebank.py
"""
from __future__ import annotations

import json
from pathlib import Path

from mts_loader import load_all_compositions
from representation import build_representation, TEENTAL
from treebank import build_section_tree, find_tihai_candidates

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data" / "raw" / "mts"
PROCESSED = ROOT / "data" / "processed"
PROCESSED.mkdir(parents=True, exist_ok=True)


def main():
    comps = load_all_compositions(DATA_ROOT)
    quayda_comps = [c for c in comps if c.comp_type and "QUAYDA" in c.comp_type]
    print(f"QUAYDA-type compositions (seed treebank scope): {len(quayda_comps)} / {len(comps)}")
    print([c.name for c in quayda_comps])

    # ---------------------------------------------------------------
    # Build + validate the 10 seed trees
    # ---------------------------------------------------------------
    treebank_records = []
    validation_failures = []
    for c in quayda_comps:
        rep = build_representation(c, TEENTAL)
        tree = build_section_tree(c, rep)

        recovered = tree.bol_sequence()
        expected = [e.bol for e in c.onsets_unmapped]
        if recovered != expected:
            validation_failures.append(c.name)
            continue

        record = {
            "name": c.name,
            "gharana": c.gharana,
            "type": c.comp_type,
            "section_labels_used": [ch.label for ch in tree.children],
            "n_avartans": len(rep.avartans),
            "tree": tree.to_dict(),
        }
        treebank_records.append(record)

    print(f"Trees built and validated (leaf sequence == original onset sequence, exactly): "
          f"{len(treebank_records)}/{len(quayda_comps)}")
    if validation_failures:
        print(f"VALIDATION FAILURES (excluded from treebank): {validation_failures}")

    with open(PROCESSED / "phase4_treebank.jsonl", "w") as f:
        for r in treebank_records:
            f.write(json.dumps(r) + "\n")
    print(f"Wrote data/processed/phase4_treebank.jsonl ({len(treebank_records)} trees)")

    canonical_count = sum(
        1 for r in treebank_records
        for label in r["section_labels_used"]
        if label in ("Dohra", "AdhaDohra")
    )
    print(f"Section children using the proposal's exact documented non-terminal names "
          f"(Dohra/AdhaDohra): {canonical_count}")

    # ---------------------------------------------------------------
    # Tihai candidate search, across ALL 38 compositions (not scope-limited
    # to QUAYDA - tihai-like repetition appears in other forms too, e.g.
    # Chakradar is explicitly built on repeated tihai-like structures)
    # ---------------------------------------------------------------
    all_candidates = {}
    total_candidates = 0
    for c in comps:
        rep = build_representation(c, TEENTAL)
        bols = [e.bol for e in c.onsets_unmapped]
        cands = find_tihai_candidates(bols, rep)
        if cands:
            all_candidates[c.name] = [
                {
                    "phrase": cand.phrase, "gap": cand.gap,
                    "phrase_len": cand.phrase_len, "gap_len": cand.gap_len,
                    "start_slot_index": cand.start_slot_index, "end_slot_index": cand.end_slot_index,
                    "lands_near_sam": cand.lands_near_sam,
                    "sam_distance_matras": cand.sam_distance_matras,
                }
                for cand in cands
            ]
            total_candidates += len(cands)

    print(f"Tihai candidates found: {total_candidates} across {len(all_candidates)}/{len(comps)} compositions")
    near_sam = sum(
        1 for comp_cands in all_candidates.values() for c in comp_cands if c["lands_near_sam"]
    )
    print(f"Of these, {near_sam} land within 1 matra of a sam (the strongest tihai signal)")

    with open(PROCESSED / "phase4_tihai_candidates.json", "w") as f:
        json.dump(all_candidates, f, indent=2)
    print(f"Wrote data/processed/phase4_tihai_candidates.json")

    return {
        "treebank_records": treebank_records,
        "validation_failures": validation_failures,
        "canonical_count": canonical_count,
        "all_candidates": all_candidates,
        "total_candidates": total_candidates,
        "near_sam": near_sam,
    }


if __name__ == "__main__":
    main()

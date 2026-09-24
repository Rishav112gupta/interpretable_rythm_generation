"""
Phase 3 — build and validate the rhythmic representation for all 38 MTS
compositions, and write:
    docs/PHASE3_REPRESENTATION.md
    data/processed/phase3_representation.jsonl   (one composition per line)
    visualizations/phase3_*.png

Run with:  python3 src/run_phase3_representation.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from mts_loader import load_all_compositions
from representation import build_representation, TEENTAL

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data" / "raw" / "mts"
PROCESSED = ROOT / "data" / "processed"
VIZ = ROOT / "visualizations"
PROCESSED.mkdir(parents=True, exist_ok=True)
VIZ.mkdir(parents=True, exist_ok=True)


def main():
    comps = load_all_compositions(DATA_ROOT)

    # ---------------------------------------------------------------
    # Corpus-wide structural diagnostic (justifies the time-based design —
    # see the docstring in representation.py): vibhag-group count per line,
    # and !S: header value vs. group-length patterns.
    # ---------------------------------------------------------------
    group_count_mismatch = []
    header_group_patterns: dict[str, Counter] = {}
    for c in comps:
        for sec in c.sections:
            header_group_patterns.setdefault(sec.subdivisions, Counter())
            for line in sec.lines:
                if len(line) != TEENTAL.n_vibhags:
                    group_count_mismatch.append((c.name, sec.name, len(line)))
                group_lens = tuple(len(g) for g in line)
                header_group_patterns[sec.subdivisions][group_lens] += 1

    print(f"Lines with != {TEENTAL.n_vibhags} vibhag-groups: {len(group_count_mismatch)} {group_count_mismatch}")
    for hdr in sorted(header_group_patterns):
        print(f"!S:{hdr} -> {dict(header_group_patterns[hdr].most_common(6))}")

    # ---------------------------------------------------------------
    # Build representations, validating no data loss
    # ---------------------------------------------------------------
    represented = []
    build_failures = []
    for c in comps:
        try:
            rep = build_representation(c, TEENTAL)
        except ValueError as e:
            build_failures.append((c.name, str(e)))
            continue
        n_slots = len(rep.all_slots())
        n_onsets = len(c.onsets_unmapped)
        if n_slots != n_onsets:
            build_failures.append((c.name, f"slot count {n_slots} != onset count {n_onsets}"))
            continue
        represented.append(rep)

    print(f"Built representations for {len(represented)}/{len(comps)} compositions.")
    if build_failures:
        print(f"Build failures: {build_failures}")

    # ---------------------------------------------------------------
    # Invariant checks across every slot in every composition
    # ---------------------------------------------------------------
    bad_matra = bad_vibhag = bad_sam = bad_khali = 0
    subdivision_offsets = []
    matra_hist = Counter()
    vibhag_hist = Counter()
    for rep in represented:
        for s in rep.all_slots():
            if not (0 <= s.matra_index < TEENTAL.n_matras):
                bad_matra += 1
            if not (0 <= s.vibhag_index < TEENTAL.n_vibhags):
                bad_vibhag += 1
            if s.is_sam != (s.matra_index == 0):
                bad_sam += 1
            if s.is_khali != (s.vibhag_index in TEENTAL.khali_vibhags):
                bad_khali += 1
            subdivision_offsets.append(s.subdivision_offset)
            matra_hist[s.matra_index] += 1
            vibhag_hist[s.vibhag_index] += 1

    print(f"Invariant violations — matra range: {bad_matra}, vibhag range: {bad_vibhag}, "
          f"sam flag: {bad_sam}, khali flag: {bad_khali} (all should be 0)")

    n_avartans = sum(len(r.avartans) for r in represented)
    n_extrapolated = sum(1 for r in represented for a in r.avartans if a.end_time_is_extrapolated)
    print(f"Total avartans across corpus: {n_avartans}; "
          f"of these, {n_extrapolated} have an extrapolated end time "
          f"(the last avartan of each composition, {len(represented)} compositions).")

    # ---------------------------------------------------------------
    # Visualizations
    # ---------------------------------------------------------------
    plt.figure(figsize=(7, 4))
    plt.hist(subdivision_offsets, bins=40, color="#4C72B0", edgecolor="white")
    plt.xlabel("Position within matra (0 = on-beat, fractional = off-beat)")
    plt.ylabel("# onsets (corpus-wide)")
    plt.title("Onset position within matra (time-based grid)")
    plt.tight_layout()
    plt.savefig(VIZ / "phase3_subdivision_offset_hist.png", dpi=150)
    plt.close()

    plt.figure(figsize=(7, 4))
    plt.bar(range(TEENTAL.n_matras), [matra_hist[i] for i in range(TEENTAL.n_matras)], color="#55A868")
    plt.xlabel("Matra index (0 = sam)")
    plt.ylabel("# onsets (corpus-wide)")
    plt.title("Onset count per matra position")
    plt.xticks(range(TEENTAL.n_matras))
    plt.tight_layout()
    plt.savefig(VIZ / "phase3_matra_position_hist.png", dpi=150)
    plt.close()

    plt.figure(figsize=(6, 4))
    labels = [f"Vibhag {i}{' (khali)' if i in TEENTAL.khali_vibhags else ''}" for i in range(TEENTAL.n_vibhags)]
    plt.bar(labels, [vibhag_hist[i] for i in range(TEENTAL.n_vibhags)], color=["#C44E52" if i in TEENTAL.khali_vibhags else "#4C72B0" for i in range(TEENTAL.n_vibhags)])
    plt.ylabel("# onsets (corpus-wide)")
    plt.title("Onset count per vibhag (khali vibhag in red)")
    plt.tight_layout()
    plt.savefig(VIZ / "phase3_vibhag_onset_counts.png", dpi=150)
    plt.close()

    print("Saved visualizations: phase3_subdivision_offset_hist.png, phase3_matra_position_hist.png, "
          "phase3_vibhag_onset_counts.png in visualizations/")

    # ---------------------------------------------------------------
    # Serialize (flat, audit-friendly)
    # ---------------------------------------------------------------
    with open(PROCESSED / "phase3_representation.jsonl", "w") as f:
        for rep in represented:
            record = {
                "name": rep.name,
                "gharana": rep.gharana,
                "tala": rep.tala,
                "n_avartans": len(rep.avartans),
                "avartans": [
                    {
                        "index": a.index,
                        "start_time": a.start_time,
                        "end_time": a.end_time,
                        "duration": a.duration,
                        "end_time_is_extrapolated": a.end_time_is_extrapolated,
                        "slots": [
                            {"bol": s.bol, "t": s.start_time, "duration": s.duration,
                             "matra": s.matra_index, "vibhag": s.vibhag_index,
                             "subdivision_offset": round(s.subdivision_offset, 4),
                             "is_sam": s.is_sam, "is_khali": s.is_khali}
                            for s in a.all_slots()
                        ],
                    }
                    for a in rep.avartans
                ],
            }
            f.write(json.dumps(record) + "\n")
    print(f"Wrote data/processed/phase3_representation.jsonl ({len(represented)} compositions)")

    return {
        "represented": represented,
        "build_failures": build_failures,
        "group_count_mismatch": group_count_mismatch,
        "header_group_patterns": header_group_patterns,
        "n_avartans": n_avartans,
        "n_extrapolated": n_extrapolated,
        "invariant_violations": (bad_matra, bad_vibhag, bad_sam, bad_khali),
    }


if __name__ == "__main__":
    main()

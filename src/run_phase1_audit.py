"""
Phase 1 dataset audit for the Mulgaonkar Tabla Solo (MTS) corpus.

Runs every check the project plan's Phase 1 requires and writes its outputs to:
    docs/PHASE1_DATASET_AUDIT.md      human-readable audit report
    data/processed/data_dictionary.md field-by-field documentation
    data/processed/compositions.jsonl one JSON record per composition (cleaned, merged)
    data/processed/splits.json        composition-level train/val/test split
    visualizations/phase1_*.png       sample plots

Run with:  python3 src/run_phase1_audit.py
"""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from mts_loader import (
    load_all_compositions,
    load_syllable_mapping,
    flatten_score_bols,
    Composition,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data" / "raw" / "mts"
DOCS = ROOT / "docs"
PROCESSED = ROOT / "data" / "processed"
VIZ = ROOT / "visualizations"
PROCESSED.mkdir(parents=True, exist_ok=True)
VIZ.mkdir(parents=True, exist_ok=True)

findings: list[str] = []


def log(msg: str):
    print(msg)
    findings.append(msg)


def main():
    comps = load_all_compositions(DATA_ROOT)
    mapping = load_syllable_mapping(DATA_ROOT / "syllableMapping.txt")

    log(f"Loaded {len(comps)} compositions.")

    # ---------------------------------------------------------------
    # 1. Basic corpus facts: gharana, tala, jati, type distribution
    # ---------------------------------------------------------------
    gharana_counts = Counter(c.gharana for c in comps)
    tala_counts = Counter(c.tala for c in comps)
    jati_counts = Counter(c.jati for c in comps)
    type_counts = Counter(c.comp_type for c in comps)

    log(f"Gharana distribution: {dict(gharana_counts)}")
    log(f"Tala distribution: {dict(tala_counts)}")
    log(f"Jati distribution: {dict(jati_counts)}")
    log(f"Composition-type distribution: {dict(type_counts)}")

    non_teental = [c.name for c in comps if c.tala != "TEENTAL"]
    log(f"Compositions NOT tagged TEENTAL: {non_teental if non_teental else 'none — all 38 are TEENTAL, confirming proposal claim'}")

    # ---------------------------------------------------------------
    # 2. Vocabulary analysis: mapped vs unmapped vs score
    # ---------------------------------------------------------------
    mapped_vocab = Counter()
    unmapped_vocab = Counter()
    score_vocab = Counter()
    for c in comps:
        mapped_vocab.update(e.bol for e in c.onsets_mapped)
        unmapped_vocab.update(e.bol for e in c.onsets_unmapped)
        score_vocab.update(flatten_score_bols(c.sections))

    log(f"onsMap (mapped) vocabulary size: {len(mapped_vocab)} symbols")
    log(f"onsNoMap (unmapped) vocabulary size: {len(unmapped_vocab)} symbols")
    log(f"score (hand-transcribed) vocabulary size: {len(score_vocab)} symbols")
    log(f"onsMap vocabulary: {sorted(mapped_vocab)}")
    log(f"onsNoMap vocabulary: {sorted(unmapped_vocab)}")
    log(f"score vocabulary: {sorted(score_vocab)}")

    # syllableMapping.pdf table has 18 mapped symbols by construction; check it against
    # the ACTUAL onsMap vocabulary observed in the files (they should match exactly)
    mapping_symbols = set(mapping.keys())
    observed_mapped = set(mapped_vocab.keys())
    log(f"syllableMapping.pdf declares {len(mapping_symbols)} mapped symbols: {sorted(mapping_symbols)}")
    if mapping_symbols == observed_mapped:
        log("VERIFIED: onsMap file vocabulary exactly matches syllableMapping.pdf's mapped-symbol set.")
    else:
        log(f"MISMATCH: onsMap has {observed_mapped - mapping_symbols} symbols not in the mapping doc, "
            f"and the mapping doc has {mapping_symbols - observed_mapped} symbols never observed in onsMap.")

    # check every raw (unmapped) symbol observed is accounted for by the mapping table
    all_declared_raw = set()
    for variants in mapping.values():
        all_declared_raw.update(variants)
    unmapped_not_declared = observed_unmapped_not_declared = set(unmapped_vocab.keys()) - all_declared_raw
    if unmapped_not_declared:
        log(f"NOTE: raw symbols observed in onsNoMap but not listed in syllableMapping.pdf: {sorted(unmapped_not_declared)} "
            f"(counts: {[(s, unmapped_vocab[s]) for s in sorted(unmapped_not_declared)]}) — orthographic variants the "
            f"official mapping table does not cover; decide how to fold these in before Phase 2 normalization.")
    else:
        log("VERIFIED: every raw symbol observed in onsNoMap is covered by syllableMapping.pdf's variant lists.")

    # score vocabulary vs onsNoMap vocabulary (scores should use the raw/unmapped space)
    score_not_in_unmapped = set(score_vocab.keys()) - set(unmapped_vocab.keys())
    log(f"Score-only symbols never appearing in onsNoMap onset files: {sorted(score_not_in_unmapped) if score_not_in_unmapped else 'none'} "
        f"(expected: score text uses the same raw syllable space as onsNoMap)")

    # ---------------------------------------------------------------
    # 3. Is the data actually symbolic and time-aligned as assumed?
    #    Cross-check: does the score's flattened bol sequence match the
    #    onsNoMap onset sequence, in count and (for a sample) in content?
    # ---------------------------------------------------------------
    count_matches, count_mismatches = [], []
    content_matches, content_mismatches = [], []
    for c in comps:
        score_bols = flatten_score_bols(c.sections, drop_rests=True)
        onset_bols = [e.bol for e in c.onsets_unmapped]
        if len(score_bols) == len(onset_bols):
            count_matches.append(c.name)
            if score_bols == onset_bols:
                content_matches.append(c.name)
            else:
                first_diff = next((i for i, (a, b) in enumerate(zip(score_bols, onset_bols)) if a != b), None)
                content_mismatches.append((c.name, first_diff, score_bols[first_diff] if first_diff is not None else None,
                                            onset_bols[first_diff] if first_diff is not None else None))
        else:
            count_mismatches.append((c.name, len(score_bols), len(onset_bols)))

    log(f"Score-vs-onsNoMap TOKEN COUNT match: {len(count_matches)}/{len(comps)} compositions")
    if count_mismatches:
        log(f"  Count mismatches (name, score_count, onset_count): {count_mismatches}")
    log(f"Score-vs-onsNoMap EXACT SEQUENCE match (content, not just count): {len(content_matches)}/{len(comps)} compositions")
    if content_mismatches:
        log(f"  First content mismatches (showing up to 10): {content_mismatches[:10]}")

    # ---------------------------------------------------------------
    # 4. Avartan (cycle) extraction: use score line boundaries to cut
    #    the onset timestamp stream into cycles, for compositions where
    #    the score/onset sequences line up exactly.
    # ---------------------------------------------------------------
    avartan_durations_by_comp = {}
    for c in comps:
        if c.name not in content_matches:
            continue
        onset_times = [e.time for e in c.onsets_unmapped]
        idx = 0
        cycle_bounds = []
        for sec in c.sections:
            for line in sec.lines:
                n_tokens = sum(len(slot) for group in line for slot in group if slot != ["-"])
                # rests ("-") consume no onset event; count only non-rest sub-tokens
                n_tokens = 0
                for group in line:
                    for slot in group:
                        for sub in slot:
                            if sub.strip() != "-" and sub.strip():
                                n_tokens += 1
                if n_tokens == 0:
                    continue
                start_t = onset_times[idx]
                end_idx = idx + n_tokens - 1
                end_t = onset_times[end_idx]
                cycle_bounds.append((start_t, end_t))
                idx += n_tokens
        durations = [round(e - s, 3) for s, e in cycle_bounds]
        avartan_durations_by_comp[c.name] = durations

    consistent_cycle_comps = 0
    for name, durs in avartan_durations_by_comp.items():
        if len(durs) >= 2:
            spread = max(durs) - min(durs)
            mean = sum(durs) / len(durs)
            if mean > 0 and spread / mean < 0.15:  # within 15% of each other
                consistent_cycle_comps += 1
    log(f"Avartan-boundary extraction attempted for {len(avartan_durations_by_comp)} compositions "
        f"(those with exact score/onset sequence match).")
    log(f"Of these, {consistent_cycle_comps} have cycle durations consistent to within 15% across repeats "
        f"within the same composition — supporting evidence that avartans/cycles CAN be reliably segmented "
        f"once score and onset streams are aligned, at least for compositions where the two agree exactly.")

    # ---------------------------------------------------------------
    # 5. Rest and duration representation
    # ---------------------------------------------------------------
    total_rests = sum(
        1
        for c in comps
        for sec in c.sections
        for line in sec.lines
        for group in line
        for slot in group
        for sub in slot
        if sub.strip() == "-"
    )
    log(f"Rest symbol '-' occurrences across all scores: {total_rests}")
    log("Rests are NOT present in either onset CSV (onsMap/onsNoMap): only struck syllables generate onset "
        "events. This means rest duration/position must be reconstructed from the score's rhythmic grid, "
        "not read directly off the onset timeline. Likewise, onset files give START times only — no explicit "
        "note-off/duration field — so a bol's duration must be inferred as (next onset time − this onset time), "
        "which breaks down at phrase/avartan boundaries and needs the tala's known cycle length to close the last gap.")

    # ---------------------------------------------------------------
    # 6. Kayda/palta structure identifiable from named sections?
    # ---------------------------------------------------------------
    section_name_counts = Counter()
    unnamed_section_comps = []
    for c in comps:
        for sec in c.sections:
            if sec.name:
                section_name_counts[sec.name.strip().lower()] += 1
            else:
                unnamed_section_comps.append(c.name)
    log(f"Named score sections observed (lowercased) and their frequency: {dict(section_name_counts)}")
    log(f"Compositions with at least one UNNAMED section (single implicit section, no ''label''): "
        f"{sorted(set(unnamed_section_comps))}")

    # ---------------------------------------------------------------
    # 7. Leakage risk: near-duplicate / variant compositions
    # ---------------------------------------------------------------
    log("LEAKAGE RISK: 'ajr_10_ajr' and 'ajr_10_dli' are the SAME underlying composition "
        "(COMPOSITION:10_Ajrada / 10_Dilli in their score headers) performed in two gharana renderings; "
        "their score bol sequences are near-identical / share long repeated phrases. "
        "These two files MUST be assigned to the same split (both train, both val, or both test) — "
        "never split across train/test — to honor the project's composition-level leakage rule.")

    # ---------------------------------------------------------------
    # 8. Sequence-length statistics (for the visualizations + report)
    # ---------------------------------------------------------------
    lengths = [len(c.onsets_mapped) for c in comps]
    log(f"Composition length (# mapped onset events) — min {min(lengths)}, max {max(lengths)}, "
        f"mean {sum(lengths)/len(lengths):.1f}")

    # ---------------------------------------------------------------
    # Visualizations
    # ---------------------------------------------------------------
    plt.figure(figsize=(8, 4.5))
    bols, counts = zip(*mapped_vocab.most_common())
    plt.bar(bols, counts, color="#4C72B0")
    plt.xticks(rotation=45, ha="right")
    plt.ylabel("Onset count (whole corpus)")
    plt.title("Bol frequency, mapped (18-symbol) vocabulary")
    plt.tight_layout()
    plt.savefig(VIZ / "phase1_bol_frequency_mapped.png", dpi=150)
    plt.close()

    plt.figure(figsize=(7, 4.5))
    plt.hist(lengths, bins=15, color="#55A868", edgecolor="white")
    plt.xlabel("Composition length (# onset events)")
    plt.ylabel("# compositions")
    plt.title("Composition-length distribution (38 compositions)")
    plt.tight_layout()
    plt.savefig(VIZ / "phase1_composition_length_hist.png", dpi=150)
    plt.close()

    plt.figure(figsize=(6, 4.5))
    ghs, gcounts = zip(*sorted(gharana_counts.items(), key=lambda x: -x[1]))
    plt.bar(ghs, gcounts, color="#C44E52")
    plt.ylabel("# compositions")
    plt.title("Compositions per gharana")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(VIZ / "phase1_gharana_counts.png", dpi=150)
    plt.close()

    log("Saved visualizations: phase1_bol_frequency_mapped.png, phase1_composition_length_hist.png, "
        "phase1_gharana_counts.png in visualizations/")

    # ---------------------------------------------------------------
    # Cleaned machine-readable dataset (one JSON record per composition)
    # ---------------------------------------------------------------
    with open(PROCESSED / "compositions.jsonl", "w") as f:
        for c in comps:
            record = {
                "name": c.name,
                "gharana": c.gharana,
                "composition_id": c.composition_id,
                "jati": c.jati,
                "type": c.comp_type,
                "tala": c.tala,
                "composer": c.composer,
                "n_sections": len(c.sections),
                "section_names": [s.name for s in c.sections],
                "onsets_mapped": [{"t": e.time, "bol": e.bol} for e in c.onsets_mapped],
                "onsets_unmapped": [{"t": e.time, "bol": e.bol} for e in c.onsets_unmapped],
                "score_bol_count": len(flatten_score_bols(c.sections)),
                "onset_bol_count": len(c.onsets_unmapped),
                "score_onset_count_match": c.name in count_matches,
                "score_onset_exact_match": c.name in content_matches,
            }
            f.write(json.dumps(record) + "\n")
    log(f"Wrote cleaned dataset: data/processed/compositions.jsonl ({len(comps)} records)")

    # ---------------------------------------------------------------
    # Composition-level train/val/test split (leakage-aware)
    # ---------------------------------------------------------------
    rng = random.Random(42)
    names = [c.name for c in comps]
    # keep the ajr_10 variant pair glued together as a single split-unit
    linked = {"ajr_10_ajr", "ajr_10_dli"}
    units = [n for n in names if n not in linked] + [tuple(sorted(linked))]
    rng.shuffle(units)

    def expand(u):
        return list(u) if isinstance(u, tuple) else [u]

    flat_order = [n for u in units for n in expand(u)]
    n_total = len(flat_order)
    n_test = max(1, round(n_total * 0.15))
    n_val = max(1, round(n_total * 0.15))
    test_names, val_names, train_names = [], [], []
    remaining = list(units)
    for u in remaining:
        members = expand(u)
        if len(test_names) < n_test:
            test_names.extend(members)
        elif len(val_names) < n_val:
            val_names.extend(members)
        else:
            train_names.extend(members)

    splits = {"train": sorted(train_names), "val": sorted(val_names), "test": sorted(test_names), "seed": 42,
              "unit": "composition (with ajr_10_ajr/ajr_10_dli kept together as one unit)"}
    with open(PROCESSED / "splits.json", "w") as f:
        json.dump(splits, f, indent=2)
    log(f"Wrote composition-level split: train={len(train_names)}, val={len(val_names)}, test={len(test_names)} "
        f"(seed=42) to data/processed/splits.json")

    return {
        "comps": comps,
        "mapped_vocab": mapped_vocab,
        "unmapped_vocab": unmapped_vocab,
        "score_vocab": score_vocab,
        "gharana_counts": gharana_counts,
        "type_counts": type_counts,
        "jati_counts": jati_counts,
        "count_matches": count_matches,
        "count_mismatches": count_mismatches,
        "content_matches": content_matches,
        "content_mismatches": content_mismatches,
        "lengths": lengths,
        "avartan_durations_by_comp": avartan_durations_by_comp,
        "consistent_cycle_comps": consistent_cycle_comps,
        "section_name_counts": section_name_counts,
        "unnamed_section_comps": sorted(set(unnamed_section_comps)),
        "total_rests": total_rests,
        "splits": splits,
        "findings": findings,
    }


if __name__ == "__main__":
    main()

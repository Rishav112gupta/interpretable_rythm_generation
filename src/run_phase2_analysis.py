"""
Phase 2 — bol normalization analysis.

Runs the vocabulary / rare-bol / gharana-variant / compound-bol analyses the
project plan's Phase 2 requires, under both normalization modes, and writes:
    docs/PHASE2_BOL_NORMALIZATION.md      report
    data/processed/phase2_vocab_mode_a.json / phase2_vocab_mode_b.json
    data/processed/phase2_gharana_variants.json
    data/processed/phase2_compound_slots.json
    visualizations/phase2_*.png

Run with:  python3 src/run_phase2_analysis.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from mts_loader import load_all_compositions
from bol_normalization import BolNormalizer, BolNormalizationMode, onset_bols

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data" / "raw" / "mts"
PROCESSED = ROOT / "data" / "processed"
VIZ = ROOT / "visualizations"
PROCESSED.mkdir(parents=True, exist_ok=True)
VIZ.mkdir(parents=True, exist_ok=True)

RARE_THRESHOLD = 10  # a bol occurring fewer than this many times, corpus-wide, is "rare"


def main():
    comps = load_all_compositions(DATA_ROOT)
    normalizer = BolNormalizer(DATA_ROOT / "syllableMapping.txt")

    # -----------------------------------------------------------------
    # 1. Vocabulary size + frequency distribution, both modes
    # -----------------------------------------------------------------
    vocab_a = Counter()  # mode A: normalized (18 symbols)
    vocab_b = Counter()  # mode B: distinct (raw ~40 symbols)
    for c in comps:
        vocab_a.update(onset_bols(c, BolNormalizationMode.NORMALIZED))
        vocab_b.update(onset_bols(c, BolNormalizationMode.DISTINCT))

    print(f"Mode A (normalized) vocabulary size: {len(vocab_a)}")
    print(f"Mode B (distinct) vocabulary size: {len(vocab_b)}")

    with open(PROCESSED / "phase2_vocab_mode_a.json", "w") as f:
        json.dump(dict(vocab_a.most_common()), f, indent=2)
    with open(PROCESSED / "phase2_vocab_mode_b.json", "w") as f:
        json.dump(dict(vocab_b.most_common()), f, indent=2)

    # -----------------------------------------------------------------
    # 2. Rare bols under each mode
    # -----------------------------------------------------------------
    rare_a = {b: n for b, n in vocab_a.items() if n < RARE_THRESHOLD}
    rare_b = {b: n for b, n in vocab_b.items() if n < RARE_THRESHOLD}
    print(f"Rare bols (< {RARE_THRESHOLD} occurrences), mode A: {rare_a}")
    print(f"Rare bols (< {RARE_THRESHOLD} occurrences), mode B: {rare_b}")

    # -----------------------------------------------------------------
    # 3. Gharana-specific variant preference: for every mapped symbol with
    #    >1 raw variant actually observed, does variant choice correlate
    #    with gharana?
    # -----------------------------------------------------------------
    # per-gharana raw-symbol counts
    gharana_raw_counts: dict[str, Counter] = defaultdict(Counter)
    for c in comps:
        gh = c.gharana or "UNKNOWN"
        gharana_raw_counts[gh].update(onset_bols(c, BolNormalizationMode.DISTINCT))

    gharanas = sorted(gharana_raw_counts.keys())
    variant_report = {}
    for mapped_symbol, raw_variants in normalizer.mapped_to_raw.items():
        observed_variants = [v for v in raw_variants if vocab_b.get(v, 0) > 0]
        if len(observed_variants) <= 1:
            continue  # nothing to compare — only one spelling is actually used
        per_gharana = {}
        for gh in gharanas:
            counts = {v: gharana_raw_counts[gh].get(v, 0) for v in observed_variants}
            total = sum(counts.values())
            if total == 0:
                continue
            per_gharana[gh] = {"counts": counts, "total": total,
                                "dominant_variant": max(counts, key=counts.get)}
        # flag if different gharanas have different dominant variants
        dominants = {gh: d["dominant_variant"] for gh, d in per_gharana.items()}
        varies_by_gharana = len(set(dominants.values())) > 1
        variant_report[mapped_symbol] = {
            "observed_variants": observed_variants,
            "per_gharana": per_gharana,
            "dominant_variant_varies_by_gharana": varies_by_gharana,
        }

    with open(PROCESSED / "phase2_gharana_variants.json", "w") as f:
        json.dump(variant_report, f, indent=2)

    varying_symbols = [s for s, r in variant_report.items() if r["dominant_variant_varies_by_gharana"]]
    print(f"Mapped symbols with >1 observed raw variant: {len(variant_report)}")
    print(f"Of those, dominant spelling varies by gharana for: {varying_symbols}")

    # -----------------------------------------------------------------
    # 4. Compound bols: sequential multi-stroke slots in the score files
    #    (comma-joined tokens, e.g. "TI,RA", "KI,TA,TA,KA")
    # -----------------------------------------------------------------
    slot_arity_counts = Counter()          # 1, 2, 3, 4 sub-bols per slot
    slot_arity_by_gharana = defaultdict(Counter)
    multi_slot_combo_counts = Counter()    # e.g. ("TI","RA") -> count

    for c in comps:
        gh = c.gharana or "UNKNOWN"
        for sec in c.sections:
            for line in sec.lines:
                for group in line:
                    for slot in group:
                        non_rest = [s for s in slot if s.strip() != "-" and s.strip()]
                        if not non_rest:
                            continue
                        arity = len(non_rest)
                        slot_arity_counts[arity] += 1
                        slot_arity_by_gharana[gh][arity] += 1
                        if arity > 1:
                            multi_slot_combo_counts[tuple(non_rest)] += 1

    print(f"Slot arity distribution (# sub-bols per slot, corpus-wide): {dict(sorted(slot_arity_counts.items()))}")
    print(f"Top 15 multi-bol slot combinations: {multi_slot_combo_counts.most_common(15)}")

    compound_report = {
        "slot_arity_counts": dict(sorted(slot_arity_counts.items())),
        "slot_arity_by_gharana": {gh: dict(sorted(c.items())) for gh, c in slot_arity_by_gharana.items()},
        "top_multi_bol_combinations": [
            {"combo": list(k), "count": v} for k, v in multi_slot_combo_counts.most_common(30)
        ],
    }
    with open(PROCESSED / "phase2_compound_slots.json", "w") as f:
        json.dump(compound_report, f, indent=2)

    # -----------------------------------------------------------------
    # Visualizations
    # -----------------------------------------------------------------
    plt.figure(figsize=(7, 4.5))
    arities = sorted(slot_arity_counts.keys())
    plt.bar([str(a) for a in arities], [slot_arity_counts[a] for a in arities], color="#8172B2")
    plt.xlabel("Sub-bols per slot (1 = single stroke, 2+ = compound slot)")
    plt.ylabel("# slots (corpus-wide)")
    plt.title("Score slot arity distribution")
    plt.tight_layout()
    plt.savefig(VIZ / "phase2_slot_arity.png", dpi=150)
    plt.close()

    plt.figure(figsize=(9, 5))
    combos = multi_slot_combo_counts.most_common(15)
    labels = [",".join(k) for k, _ in combos]
    values = [v for _, v in combos]
    plt.barh(labels[::-1], values[::-1], color="#CCB974")
    plt.xlabel("Occurrences (corpus-wide)")
    plt.title("Top 15 multi-bol slot combinations")
    plt.tight_layout()
    plt.savefig(VIZ / "phase2_top_compound_slots.png", dpi=150)
    plt.close()

    plt.figure(figsize=(10, 5))
    width = 0.8 / max(len(gharanas), 1)
    mode_a_vals = [vocab_a.get(b, 0) for b in sorted(vocab_a)]
    plt.bar(sorted(vocab_a), mode_a_vals, color="#4C72B0", alpha=0.85, label="Mode A (normalized, 18 symbols)")
    plt.yscale("log")
    plt.ylabel("Onset count (log scale)")
    plt.title("Mode A vocabulary frequency (log scale) — rare bols visible")
    plt.xticks(rotation=45, ha="right")
    plt.axhline(RARE_THRESHOLD, color="red", linestyle="--", linewidth=1, label=f"rare threshold ({RARE_THRESHOLD})")
    plt.legend()
    plt.tight_layout()
    plt.savefig(VIZ / "phase2_mode_a_frequency_log.png", dpi=150)
    plt.close()

    print("Saved visualizations: phase2_slot_arity.png, phase2_top_compound_slots.png, "
          "phase2_mode_a_frequency_log.png in visualizations/")

    return {
        "vocab_a": vocab_a, "vocab_b": vocab_b,
        "rare_a": rare_a, "rare_b": rare_b,
        "variant_report": variant_report, "varying_symbols": varying_symbols,
        "slot_arity_counts": slot_arity_counts,
        "multi_slot_combo_counts": multi_slot_combo_counts,
    }


if __name__ == "__main__":
    main()

"""
Phase 7 - attribute layer, tihai arithmetic, constrained generation.

Produces:
    data/processed/phase7_summary.json
    data/processed/phase7_tihai_checks.json
    data/processed/phase7_generated_examples.json

Run with:  python3 src/run_phase7_attributes.py
"""
from __future__ import annotations

import json
import random
import statistics
from collections import Counter
from fractions import Fraction
from pathlib import Path

from mts_loader import load_all_compositions
from representation import build_representation, TEENTAL
from bol_normalization import BolNormalizer, BolNormalizationMode
from pcfg import (
    train_supervised, build_avartan_deriv, sample_tree, DerivNode, AVARTAN, REST_TOKEN, START,
)
from treebank import find_tihai_candidates
from attributes import (
    annotate, is_well_formed_avartan, timed_sequence, real_positions, check_tihai,
    near_sam, render, rule_sequence, tree_to_dict, leaf_nodes, matra_tops, _fmt,
)
from generation import (
    sample_avartan_constrained, generate_composition, valid_tihai_shapes,
)

ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = ROOT / "data" / "raw" / "mts"
PROCESSED = ROOT / "data" / "processed"
PROCESSED.mkdir(parents=True, exist_ok=True)

TOL = 0.15
TOL_SENSITIVITY = (0.10, 0.15, 0.25)
N_SAMPLES = 2000
N_GENERATED = 200
N_SPONTANEOUS = 300


class _ShimSlot:
    def __init__(self, matra_index):
        self.matra_index = matra_index


class _ShimAvartan:
    def __init__(self, slots):
        self._slots = slots

    def all_slots(self):
        return self._slots


class _ShimRep:
    """Lets Phase 4's detector run on a generated sequence."""
    def __init__(self, positions):
        self.avartans = [_ShimAvartan([_ShimSlot(int(p % TEENTAL.n_matras)) for p in positions])]


def section(title):
    print(f"\n=== {title} ===")


def main():
    comps = load_all_compositions(DATA_ROOT)
    normalizer = BolNormalizer(DATA_ROOT / "syllableMapping.txt")
    summary: dict = {}

    # -----------------------------------------------------------------
    section("1. Grammar with explicit empty-matra rests (opt-in; Phase 5 default unchanged)")
    g_plain, _ = train_supervised(comps, BolNormalizationMode.NORMALIZED, normalizer)
    g_rest, _ = train_supervised(comps, BolNormalizationMode.NORMALIZED, normalizer, include_rests=True)
    for name, g in (("Phase 5 (onsets only)", g_plain), ("Phase 7 (+ rests)", g_rest)):
        d = g.diagnostics()
        print(f"{name}: {d['n_nonterminals']} non-terminals, {d['n_rules']} rules, "
              f"probs sum to 1: {d['probabilities_sum_to_one']}, zero-prob rules: {d['zero_prob_rules_present']}")
        print(f"  Avartan rules: " + ", ".join(
            f"{r.rhs} n={r.count}" for r in sorted(g.rules[AVARTAN], key=lambda r: r.rhs)))
    summary["grammar_plain_rules"] = g_plain.diagnostics()["n_rules"]
    summary["grammar_rest_rules"] = g_rest.diagnostics()["n_rules"]
    summary["grammar_rest_nonterminals"] = g_rest.diagnostics()["n_nonterminals"]

    # -----------------------------------------------------------------
    section("2. Attribute layer on real avartans")
    n_av = n_full16 = n_wf_plain = n_wf_rest = 0
    deviations = []
    empty_matras = total_matras = 0
    for c in comps:
        rep = build_representation(c, TEENTAL)
        for a in rep.avartans:
            n_av += 1
            n_full16 += all(m.slots for v in a.vibhags for m in v.matras)
            for v in a.vibhags:
                for m in v.matras:
                    total_matras += 1
                    empty_matras += not m.slots
            t_plain = build_avartan_deriv(a, include_rests=False)
            annotate(t_plain, Fraction(0))
            n_wf_plain += is_well_formed_avartan(t_plain)[0]
            t_rest = build_avartan_deriv(a, include_rests=True)
            annotate(t_rest, Fraction(0))
            n_wf_rest += is_well_formed_avartan(t_rest)[0]
            strokes = [lf for lf in leaf_nodes(t_rest) if lf.bol != REST_TOKEN]
            for lf, s in zip(strokes, a.all_slots()):
                deviations.append(abs(float(lf.start) - (s.matra_index + s.subdivision_offset)))
    deviations.sort()
    print(f"real avartans with a stroke in all 16 matras: {n_full16}/{n_av}")
    print(f"empty matras: {empty_matras}/{total_matras} ({empty_matras / total_matras:.1%})")
    print(f"well-formed (16 matras, vibhag order, sam first, duration 16): "
          f"onsets-only derivations {n_wf_plain}/{n_av}; with rests {n_wf_rest}/{n_av}")
    med = statistics.median(deviations)
    p90 = deviations[int(0.9 * len(deviations))]
    print(f"notational position (equal split within a matra) vs measured position, "
          f"{len(deviations)} strokes: median |diff| = {med:.3f} matra, 90th pct = {p90:.3f}")

    offsets = [s.subdivision_offset for c in comps for s in build_representation(c, TEENTAL).all_slots()]
    n_off = len(offsets)
    on_beat = sum(o <= 0.05 or o >= 0.95 for o in offsets) / n_off
    half = sum(abs(o - 0.5) <= 0.05 for o in offsets) / n_off
    quarter = sum(abs(o - 0.25) <= 0.05 or abs(o - 0.75) <= 0.05 for o in offsets) / n_off
    print(f"sub-matra offsets (+-0.05): on-beat {on_beat:.3f} (chance 0.100), "
          f"half {half:.3f} (chance 0.100), quarter/three-quarter {quarter:.3f} (chance 0.200)")
    summary.update({
        "real_avartans": n_av, "real_full16": n_full16,
        "empty_matras": empty_matras, "total_matras": total_matras,
        "real_wellformed_plain": n_wf_plain, "real_wellformed_rest": n_wf_rest,
        "notational_vs_measured_median": med, "notational_vs_measured_p90": p90,
        "offset_on_beat": on_beat, "offset_half": half, "offset_quarter": quarter,
    })

    # -----------------------------------------------------------------
    section("3. Unconstrained vs attribute-constrained sampling")
    rng = random.Random(7)
    for name, g in (("Phase 5 (onsets only)", g_plain), ("Phase 7 (+ rests)", g_rest)):
        ok = 0
        counts = Counter()
        for _ in range(N_SAMPLES):
            t = sample_tree(g, AVARTAN, rng=rng, max_depth=400)
            if t is None:
                counts["no finite sample"] += 1
                continue
            annotate(t, Fraction(0))
            good, _ = is_well_formed_avartan(t)
            ok += good
            counts[int(t.dur)] += 1
        print(f"unconstrained {name}: well-formed {ok}/{N_SAMPLES}; "
              f"most common durations (matras): {counts.most_common(5)}")
        summary[f"unconstrained_wellformed_{'plain' if g is g_plain else 'rest'}"] = ok

    ok = 0
    gen_empty = gen_total = 0
    for _ in range(N_SAMPLES):
        t = sample_avartan_constrained(g_rest, rng)
        annotate(t, Fraction(0))
        ok += is_well_formed_avartan(t)[0]
        for _, _, m in matra_tops(t):
            gen_total += 1
            gen_empty += [lf.bol for lf in leaf_nodes(m)] == [REST_TOKEN]
    print(f"attribute-constrained (+ rests): well-formed {ok}/{N_SAMPLES}; "
          f"empty matras {gen_empty}/{gen_total} ({gen_empty / gen_total:.1%}) vs real "
          f"{empty_matras / total_matras:.1%}")
    summary.update({"constrained_wellformed": ok, "n_samples": N_SAMPLES,
                    "constrained_empty_matra_rate": gen_empty / gen_total})

    # -----------------------------------------------------------------
    section("4. Tihai arithmetic on Phase 4's 115 symbolic candidates (real timing)")
    records = []
    all_onset_pos = []
    for c in comps:
        rep = build_representation(c, TEENTAL)
        pos = real_positions(rep)
        all_onset_pos += pos
        bols = [e.bol for e in c.onsets_unmapped]
        for cand in find_tihai_candidates(bols, rep):
            checks = {tol: check_tihai(pos, cand.start_slot_index, cand.phrase_len, cand.gap_len, tol=tol)
                      for tol in TOL_SENSITIVITY}
            records.append((c.name, cand, checks))
    print(f"candidates: {len(records)}")
    chance = sum(near_sam(p, TOL) for p in all_onset_pos) / len(all_onset_pos)
    print(f"chance: fraction of ALL onsets within {TOL} matra of a sam = {chance:.3f} "
          f"(=> ~{chance * len(records):.1f} of {len(records)} by chance)")
    for tol in TOL_SENSITIVITY:
        ch = [r[2][tol] for r in records]
        print(f"tol={tol}: A(last stroke on sam)={sum(x.lands_a for x in ch)}  "
              f"B observed(next stroke on sam)={sum(x.lands_b_observed for x in ch)}  "
              f"B formula={sum(x.lands_b_formula for x in ch)}  "
              f"regular periods={sum(x.regular for x in ch)}  "
              f"strict (B observed & regular)={sum(x.strict_b for x in ch)}")
    main_ch = [r[2][TOL] for r in records]
    no_follow = sum(not x.has_following_stroke for x in main_ch)
    nonzero_gap = [(r, x) for r, x in zip(records, main_ch) if r[1].gap_len > 0]
    in_set = sum(x.gap_in_plan_set for _, x in nonzero_gap)
    print(f"candidates at a composition's very end (reading B uncheckable): {no_follow}")
    print(f"zero-gap candidates: {len(records) - len(nonzero_gap)} (the plan's gap set excludes 0)")
    print(f"nonzero-gap candidates whose measured gap is within {TOL} of the plan's set: "
          f"{in_set}/{len(nonzero_gap)}")
    print("measured nonzero gap durations (rounded to 1/4):",
          Counter(round(x.dur_g * 4) / 4 for _, x in nonzero_gap).most_common())
    strict = [(r, x) for r, x in zip(records, main_ch) if x.strict_b]
    print(f"strict tihais (B observed & regular, tol {TOL}):")
    for (name, cand, _), x in strict:
        print(f"  {name}: phrase={' '.join(cand.phrase)} gap={' '.join(cand.gap) or '(none)'} "
              f"dur_p={x.dur_p:.2f} dur_g={x.dur_g:.2f} gap_in_plan_set={x.gap_in_plan_set}")
    a_hits = [(r, x) for r, x in zip(records, main_ch) if x.lands_a]
    print(f"reading-A hits (tol {TOL}): " + ", ".join(
        f"{n}[{' '.join(c.phrase)}]" for (n, c, _), _ in a_hits))
    summary.update({
        "n_candidates": len(records), "chance_near_sam": chance, "tol": TOL,
        "by_tol": {str(tol): {
            "lands_a": sum(r[2][tol].lands_a for r in records),
            "lands_b_observed": sum(r[2][tol].lands_b_observed for r in records),
            "lands_b_formula": sum(r[2][tol].lands_b_formula for r in records),
            "regular": sum(r[2][tol].regular for r in records),
            "strict_b": sum(r[2][tol].strict_b for r in records),
        } for tol in TOL_SENSITIVITY},
        "no_following_stroke": no_follow,
        "zero_gap": len(records) - len(nonzero_gap),
        "nonzero_gap": len(nonzero_gap), "gap_in_plan_set": in_set,
        "strict_b_list": [{"composition": n, "phrase": c.phrase, "gap": c.gap,
                           "dur_p": x.dur_p, "dur_g": x.dur_g, "gap_in_plan_set": x.gap_in_plan_set}
                          for (n, c, _), x in strict],
    })
    with open(PROCESSED / "phase7_tihai_checks.json", "w") as f:
        json.dump([{
            "composition": n, "start_slot_index": c.start_slot_index,
            "phrase": c.phrase, "gap": c.gap,
            **{k: (float(v) if isinstance(v, (float, Fraction)) else v)
               for k, v in vars(x[TOL]).items()},
            "strict_b": x[TOL].strict_b,
        } for n, c, x in records], f, indent=2)

    # -----------------------------------------------------------------
    section("5. Generation: body cycles + tihai cycle + closing sam")
    shapes = valid_tihai_shapes()
    print(f"valid (dur_p, dur_g) shapes: {len(shapes)}")
    rng = random.Random(42)
    n_ok_body = n_ok_tihai = n_copy = n_redisc = 0
    redisc_kinds = Counter()
    examples = []
    for i in range(N_GENERATED):
        root, info = generate_composition(g_rest, rng, n_body_avartans=2)
        body_ok = all(is_well_formed_avartan(a)[0] for a in root.children[:info["n_body_avartans"]])
        seq = timed_sequence(root)
        tokens = [t for t, _, _ in seq]
        pos = [s for _, s, _ in seq]
        x = check_tihai(pos, info["tihai_first_token"], info["phrase_tokens"], info["gap_tokens"], tol=0)
        start = info["tihai_first_token"]
        p, gl = info["phrase_tokens"], info["gap_tokens"]
        phrases = [tokens[start:start + p], tokens[start + p + gl:start + 2 * p + gl],
                   tokens[start + 2 * p + 2 * gl:start + 3 * p + 2 * gl]]
        copy_ok = phrases[0] == phrases[1] == phrases[2]
        cands = find_tihai_candidates(tokens, _ShimRep(pos))
        redisc = any(cnd.start_slot_index == start and cnd.phrase_len == p and cnd.gap_len == gl
                     for cnd in cands)
        end = start + 3 * p + 2 * gl
        if redisc:
            redisc_kinds["exact"] += 1
        elif any(cnd.start_slot_index == start - 1 and cnd.phrase_len == p + 1 and cnd.gap_len == 0
                 and tokens[start - 1] == REST_TOKEN for cnd in cands):
            redisc_kinds["rotated one token earlier (preceding '-' read as part of the phrase, no gap)"] += 1
        elif p > 12:
            redisc_kinds["phrase longer than the detector's 12-token limit"] += 1
        elif any(cnd.start_slot_index < end and cnd.end_slot_index >= start for cnd in cands):
            redisc_kinds["other overlapping candidate"] += 1
        else:
            redisc_kinds["not found"] += 1
        n_ok_body += body_ok
        n_ok_tihai += x.strict_b and x.lands_b_formula and x.gap_in_plan_set and not x.lands_a
        n_copy += copy_ok
        n_redisc += redisc
        if i < 3:
            examples.append({
                "dur_p": _fmt(info["dur_p"]), "dur_g": _fmt(info["dur_g"]),
                "tihai_start_matra_in_cycle": _fmt(info["tihai_start_matra"]),
                "timeline": [[t, _fmt(s), _fmt(d)] for t, s, d in seq],
                "tree": tree_to_dict(root),
                "rule_sequence": rule_sequence(root),
                "rendered_tihai_cycle": render(root.children[-2]) + render(root.children[-1]),
            })
    print(f"generated {N_GENERATED}: body cycles well-formed {n_ok_body}/{N_GENERATED}; "
          f"tihai exact (regular, lands on next sam by observation AND formula, gap in plan set) "
          f"{n_ok_tihai}/{N_GENERATED}; three identical phrases {n_copy}/{N_GENERATED}; "
          f"Phase 4 detector rediscovers the exact tihai {n_redisc}/{N_GENERATED}")
    print(f"detector outcome breakdown: {dict(redisc_kinds)}")
    print("\nExample tihai cycle (first generated composition):")
    print("\n".join(examples[0]["rendered_tihai_cycle"]))
    summary.update({"n_generated": N_GENERATED, "gen_body_wellformed": n_ok_body,
                    "gen_tihai_exact": n_ok_tihai, "gen_copy": n_copy,
                    "gen_rediscovered": n_redisc, "gen_detector_breakdown": dict(redisc_kinds),
                    "n_shapes": len(shapes)})

    # -----------------------------------------------------------------
    section("6. Do tihais appear spontaneously without the attribute layer?")
    rng = random.Random(99)
    n_cand = n_land = 0
    for _ in range(N_SPONTANEOUS):
        root = DerivNode(label=START, children=[sample_avartan_constrained(g_rest, rng) for _ in range(3)])
        annotate(root, Fraction(0))
        seq = timed_sequence(root)
        tokens = [t for t, _, _ in seq]
        pos = [s for _, s, _ in seq]
        for cnd in find_tihai_candidates(tokens, _ShimRep(pos)):
            n_cand += 1
            x = check_tihai(pos, cnd.start_slot_index, cnd.phrase_len, cnd.gap_len, tol=0)
            n_land += x.strict_b
    print(f"{N_SPONTANEOUS} generated 3-cycle sequences with no tihai inserted: "
          f"{n_cand} symbolic tihai candidates, {n_land} of them regular and landing exactly on sam")
    summary.update({"n_spontaneous_sequences": N_SPONTANEOUS,
                    "spontaneous_candidates": n_cand, "spontaneous_landing": n_land})

    with open(PROCESSED / "phase7_generated_examples.json", "w") as f:
        json.dump(examples, f, indent=2)
    with open(PROCESSED / "phase7_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=float)
    print("\nWrote data/processed/phase7_summary.json, phase7_tihai_checks.json, "
          "phase7_generated_examples.json")


if __name__ == "__main__":
    main()

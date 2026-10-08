# Phase 7 — Attribute Layer, Tihāī Constraint, Generation

Code: [`src/attributes.py`](../src/attributes.py) (positions/durations on
trees, cycle well-formedness check, tihāī arithmetic check),
[`src/generation.py`](../src/generation.py) (constrained sampling, tihāī
generator), [`src/run_phase7_attributes.py`](../src/run_phase7_attributes.py)
(runs everything below). Small opt-in addition to
[`src/pcfg.py`](../src/pcfg.py) (`include_rests`). Reproduce with
`python3 src/run_phase7_attributes.py`. Tests:
`tests/test_attributes.py` (12 passing; 52/52 total across Phases 1–7).

All numbers below are copied from that script's output.

---

## 1. What this phase is for

The plan (`docs/PROJECT_PLAN.md` §7–§8) asks for three things on top of the
context-free grammar:

1. **An attribute layer**: every node of a derivation tree carries a start
   position and a duration (in mātrā), so "does this land on sam?" becomes
   checkable.
2. **The tihāī constraint**:
   `Tihai(target) → Phrase(p) Gap(g) Phrase(p) Gap(g) Phrase(p) Sam`,
   where `3·dur(p) + 2·dur(g) + 1 ≡ target (mod cycle_length)` and
   `dur(g) ∈ {¼, ½, ¾, 1, 1½, 2}`.
3. **A generation pipeline** that produces a sequence, its derivation tree,
   its rule sequence, and its timing together.

## 2. Three measurements made before building, which changed the design

### 2.1 The grammar alone essentially never produces a valid tīntāl cycle

Sampling 2,000 āvartans freely from the Phase 5 grammar: **0/2000** had 16
mātrā, in vibhāg order, with sam first. Durations were scattered (the most
common were 7, 8, 6, 9 and 10 mātrā). The cause is structural, not a
training problem: the grammar's list rules reuse one label
(`Avartan -> Vibhag0 Avartan`, `Vibhag0 -> Matra Vibhag0`), so nothing in a
rule "remembers" how many mātrā have been placed. **A grammar that cannot
count needs the cycle length enforced from outside, which is exactly what
the attribute layer does.** With a 0/2000 acceptance rate, rejection sampling
(one of the plan's named options) is unusable, so the constraint is
propagated during generation instead (§5).

### 2.2 Empty mātrā disappeared from the Phase 5 derivations

Only **117/351** real āvartans have a stroke in all 16 mātrā. **893 of 5,616
mātrā (15.9%) contain no onset.** Phase 5 built its trees from onsets
only, so an empty mātrā simply vanished, and the tree lost the cycle's real
length. Under the attribute check, only 117/351 real Phase 5 derivations
come out as a well-formed 16-mātrā cycle.

The plan (§4) already requires "an explicit rest symbol", and Phase 3 (§5)
explicitly forwarded the rest question to Phase 7. So this phase adds it:
an empty mātrā becomes `Matra -> Rest`, `Rest -> "-"`, using `-`, the score
files' own rest token. Two honest limits:
- `-` cannot tell **silence** from a **sustained stroke**. Onset data
  contains nothing that distinguishes them.
- It is **opt-in** (`include_rests=True`). The default still builds exactly
  the Phase 5 grammar (9 non-terminals, 44 rules), which a test now guards,
  so every number in the Phase 5 and 6 reports stays reproducible.

With rests, **351/351** real āvartans are well-formed 16-mātrā cycles, and
their strokes (ignoring rests) reproduce the original onset sequence exactly.

**A correction to how Phase 5's grammar should be read.** With rests, the
`Avartan` non-terminal collapses from 6 rules to exactly 3, each used 351
times:

| Phase 5 (onsets only) | Phase 7 (with rests) |
|---|---|
| Vibhag0 Avartan (350), Vibhag0 Vibhag1 (1), Vibhag1 Avartan (323), Vibhag1 Vibhag2 (7), Vibhag1 Vibhag3 (15), Vibhag2 Vibhag3 (328) | Vibhag0 Avartan (351), Vibhag1 Avartan (351), Vibhag2 Vibhag3 (351) |

So the "rare, irregular" rules that Phase 5 used as its MLE-vs-MAP smoothing
example, and that Phase 6's EM table tracked, **were not real structural
variation.** They came entirely from vibhāgs whose mātrā were all empty and
got dropped. For example, `Vibhag1 -> Vibhag3` (15 times) means vibhāg 2,
the khālī vibhāg, had no onsets at all in those 15 cycles. The Phase 5 and
6 numbers are still correct for the grammar they describe, but that
grammar's irregular rules encode silence, not alternative cycle shapes.

### 2.3 Positions inside a mātrā are imprecise — a correction to Phase 3

Phase 3's report says onsets "cluster strongly at the on-beat position, with
a secondary cluster near the half-mātrā point". Measured directly
(within ±0.05 mātrā):

| Position | Share of 8,245 strokes | If positions were random |
|---|---|---|
| On the beat | 0.175 | 0.100 |
| Half-mātrā | 0.108 | 0.100 |
| Quarter / three-quarter | 0.157 | 0.200 |

The on-beat cluster is real but modest. **The half-mātrā cluster is not
supported, and quarter positions are less common than chance.** The likely
reason is Phase 3's stated assumption that all 16 mātrā in an āvartan have
equal length, which is only approximately true in a real performance. This
does not affect which mātrā a stroke belongs to, but it means **fractional
positions from real data are approximate**. Every real-data tihāī result
below is therefore reported at three tolerances, not one. (The Phase 3
document itself has not been edited; see §9.)

## 3. The attribute layer

`attributes.annotate(tree)` sets `start` (inherited, top-down) and `dur`
(synthesized, bottom-up) on every node. Two sources of duration are kept
separate on purpose:

- **Real data** uses measured positions (Phase 3:
  `16·āvartan + mātrā + offset`, from timestamps).
- **Generated data** uses a notational convention: every mātrā lasts 1, and
  the *k* strokes written in one mātrā share it equally (1/*k* each). This
  is how bol notation is normally read. It is **not** a fitted model of
  real timing. Measured against real strokes it is off by a median of
  **0.193 mātrā** (90th percentile 0.515), the same imprecision as §2.3.

Generated durations use exact fractions (`fractions.Fraction`), so a
"lands on sam" check on generated output is exactly true or false, with no
rounding.

## 4. The tihāī constraint, checked against real data

### 4.1 The formula is ambiguous as written

`3·dur(p) + 2·dur(g) + 1 ≡ target (mod cycle_length)` does not say what
`target` is measured from, or what the `+1` is. Two concrete readings were
implemented and **both were tested on the corpus, instead of picking one by
assumption**:

- **Reading A:** the *last stroke of the third phrase* is the sam stroke.
- **Reading B:** the stroke *immediately after* the third phrase is the sam
  stroke. This matches the template's separate trailing `Sam`, with `+1`
  read as that sam stroke.

### 4.2 Results on Phase 4's 115 symbolic candidates

Positions come from real timing. "Regular" means the gap between phrase 1
and phrase 2 matches the gap between phrase 2 and phrase 3. "Strict" means
reading B observed *and* regular.

| Tolerance (mātrā) | A: last stroke on sam | B: next stroke on sam (observed) | B: via the formula | Regular | **Strict** |
|---|---|---|---|---|---|
| 0.10 | 8 | 17 | 7 | 53 | **4** |
| 0.15 | 8 | 18 | 10 | 65 | **5** |
| 0.25 | 9 | 19 | 12 | 87 | **12** |

Chance baseline: 4.3% of *all* onsets fall within 0.15 mātrā of a sam, so
about **5 of 115** candidates would land there by accident.

What this shows:
- **The corpus favours reading B.** 18 candidates land under B, about 3.6×
  chance, against 8 under A, about 1.6× chance. Generation therefore uses
  reading B (§5), but `check_tihai` keeps both readings available.
- **The symbolic detector over-generates by a wide margin.** Of 115
  "three repeats, equal gaps" candidates, only 5 also satisfy the metrical
  constraint at 0.15 mātrā. The attribute check is a strong filter, which
  is exactly its job.
- "Via the formula" (10) is lower than "observed" (18) because the formula
  extrapolates from the *first* phrase and gap only, and real timing is not
  perfectly regular.
- At 0.25 mātrā the strict count jumps to 12, so the result is sensitive to
  tolerance. Given §2.3, **0.15 is a judgment call, not a measured
  optimum.**

The 5 strict candidates at 0.15 mātrā:

| Composition | Phrase | Gap | dur(p) | dur(g) |
|---|---|---|---|---|
| luc_18 | TA KA | (none) | 1.34 | 0 |
| luc_18 | KI TA TA KA | TAA TI RA | 1.28 | 1.44 |
| luc_18 | TA KA | (none) | 1.32 | 0 |
| ben_23 | TI RA KI TA GHI | DI NA DHA GE | 1.20 | 1.59 |
| ben_25 | DHE RE DHE RE KI TA TA KA DHA TA KI TA | DHA | 4.01 | 0.95 |

Read honestly: **3 of the 5 come from `luc_18`'s long repeating passage,
which Phase 4 already flagged** as probably a kāydā-like vamp rather than a
climactic tihāī. The two that look most like the textbook pattern are
`ben_23`, and especially `ben_25` (phrase ≈ 4 mātrā, gap ≈ 1 mātrā,
3·4 + 2·1 = 14). **Whether any of these is musically a tihāī needs a tabla
expert or a cited source.** This phase only shows that they satisfy the
formal definition.

### 4.3 The plan's gap set against real candidates

- **55 of 115** candidates have no gap at all. The plan's set excludes 0, so
  whether a gapless triple repetition counts as a tihāī is not settled by
  the plan's own definition. Flagged for you, not decided here.
- Of the 60 with a gap, **35** have a measured gap within 0.15 of
  {¼, ½, ¾, 1, 1½, 2}. The others sit at 2.5 (6), 3.0 (5), 2.25 / 2.75 (3
  each), and some longer values, all outside the plan's set. Many of these
  candidates are probably not real tihāīs, so this is weak evidence either
  way. It does show the set was not derived from this corpus.
- 6 candidates end at the very end of a composition, so reading B cannot be
  checked for them (there is no following stroke).

## 5. Generation

### 5.1 Cycles: constraint propagation, not rejection

`generation.sample_avartan_constrained` passes an inherited attribute down
the derivation: which vibhāgs are still to place, how many mātrā are left in
this vibhāg, and whether the next mātrā is sam. At each step only the
learned productions consistent with that attribute are allowed, and their
learned probabilities are renormalized among them.

For tīntāl this leaves **no freedom at the vibhāg level**. The constraint
fully determines the skeleton. All generative freedom is inside the mātrā
(which strokes, how many, or a rest), and that comes from the learned
grammar. This is a direct consequence of the constraint, not a
simplification.

Result: **2000/2000** constrained samples are well-formed cycles, against
**0/2000** unconstrained.

### 5.2 Tihāī cycle

`generate_tihai_avartan` follows the template under reading B:

- **Phrase:** *p* whole mātrā (1–4) sampled from the grammar, beginning with
  a stroke and containing at least 2 strokes (the same 2-token minimum
  Phase 4's detector uses).
- **Gap:** a rest of duration *g* from the plan's set.
- **Placement:** the tihāī starts at mātrā `16 − (3p + 2g)` of its cycle, so
  the stroke after it falls exactly on the next sam. 23 (p, g) shapes fit
  after the cycle's own sam.
- **Sam:** a closing mātrā on the next sam, whose first token must be a real
  stroke, not a rest.
- **The three phrases are identical copies.** That is a copy dependency a
  context-free grammar cannot express for phrases of unbounded length (see
  §7), so it is enforced here directly.

A full output is: 2 constrained body cycles + the tihāī cycle + the closing
sam. It comes with the token timeline, an annotated tree, and the rule
sequence (`data/processed/phase7_generated_examples.json`).

Example (first of the 200, p = 2, g = ¾; the tihāī starts at mātrā 8½ of
its cycle, so the stroke after it lands on 48 = 3 × 16):

```
TihaiAvartan [32, 48)
  Prefix [32, 81/2)
    SamMatra [32, 33): DHA KI DHA
    Matra [33, 34): DHA DHA
    ...
    Matra [39, 40): KI
    Rest '-' [40, 81/2)
  Tihai [81/2, 48)
    Phrase [81/2, 85/2)
      Matra [81/2, 83/2): KI -
      Matra [83/2, 85/2): NA TA TA -
    Gap [85/2, 173/4)
      Rest '-' [85/2, 173/4)
    Phrase [173/4, 181/4)   (same strokes)
    Gap [181/4, 46)
    Phrase [46, 48)         (same strokes)
Sam [48, 49)
  SamMatra [48, 49): DHA
```

### 5.3 Checking the generated output

Each check uses the **same** `check_tihai` function that was used on real
data, run on the generated timeline. It is not the generator's own
arithmetic.

| Check (200 generated compositions) | Result |
|---|---|
| Body cycles well-formed | 200/200 |
| Tihāī regular, next stroke exactly on sam (observed and by formula), gap in plan's set | 200/200 |
| Three phrases identical | 200/200 |
| Phase 4 detector finds the tihāī at exactly the right boundaries | 94/200 |

The 94/200 is worth explaining, because the reason is informative:

- **93:** the detector found the same repetition shifted one token earlier.
  The token just before the tihāī is also a rest (`-`), and on symbols alone
  `-P -P -P` (no gap) matches as well as `P - P - P`. Only the rest
  *durations* tell them apart.
- **12:** the detector found another overlapping candidate.
- **1:** the phrase was longer than the detector's 12-token limit.

So the detector found the structure in some form in 199/200 cases.
Matching on symbols alone cannot always recover the correct boundaries,
which is a small, concrete example of why the duration layer is needed.

### 5.4 Without the attribute layer, tihāīs do not appear on their own

300 generated 3-cycle sequences with **no** tihāī inserted contained 12
symbolic triple-repetition candidates. **None** were regular and landed on
sam. The grammar does not produce sam-resolving tihāīs unless the
constraint is enforced.

## 6. Known weaknesses of the generated output, stated plainly

- **Too few empty mātrā, and rests in the wrong places.** Constrained
  samples have 9.9% empty mātrā against 15.9% in real data. They also put
  rests *inside* mātrā (e.g. `GE -`, `KI -`), which never happens in the
  training trees. Both have the same cause as §2.1: `Matra -> BolSlot Matra`
  reuses the label `Matra` for "the rest of this mātrā". So
  `P(Matra -> Rest)` is shared between "this mātrā is empty" and "this list
  ends with a rest". A fix exists: give the list tail its own label (e.g.
  `MatraTail`). It is **not applied**, because it changes the Phase 5
  grammar design, so it is your call (§9).
- **Mātrā contents are close to random strokes.** The grammar has no
  stroke-to-stroke context below the mātrā, so generated phrases are
  rhythmically structured but not musically convincing. Nothing here claims
  musical quality. That needs expert review (plan §10, RQ2).
- **Simplifications in the tihāī generator:** phrases are whole mātrā only,
  and gaps are rests only (real gaps are often strokes, §4.2).
- **Inside the tihāī cycle, the tree is organised by tihāī structure
  (Prefix / Tihai / Phrase / Gap), not by vibhāg.** The tihāī cuts across
  vibhāg boundaries, so the metrical hierarchy and the phrase hierarchy
  overlap. Vibhāg position is still recoverable from the `start` attribute.
  Two overlapping hierarchies are a known difficulty for a single CFG tree,
  and the plan's own named fallback, tree-adjoining grammar (§8 of the
  plan), is aimed at this. This is recorded as an observation, not resolved.

## 7. What this says about formal power (RQ4) — labelled per the plan's rules

- **Cycle length and vibhāg order** — *standard formal-language fact*: a
  bounded counting constraint is expressible by a CFG if every position gets
  its own non-terminal. *Implementation observation*: Phase 5's grammar did
  not do that (label reuse), and produces 0/2000 valid cycles. The attribute
  layer enforces it without changing the grammar.
- **Three identical phrases** — *standard result*: the copy language
  {www} is not context-free when the phrase length is unbounded. With phrase
  length capped (here at most 4 mātrā), it becomes finite, so it is
  technically expressible, but only by listing every possible phrase.
  *Observation*: enforced directly as a copy in the generator.
- **Landing on sam** — *implementation observation*: with bounded durations
  this is a finite arithmetic check. It works as an attribute condition at
  generation time (200/200) and as a filter on parses (115 → 5 real
  candidates at 0.15 mātrā).

Nothing above is a new proof. The first two are textbook facts, and the
rest are observations from this implementation.

## 8. Files and tests

- `data/processed/phase7_summary.json`: every number in this document.
- `data/processed/phase7_tihai_checks.json`: per-candidate checks for all
  115 real candidates.
- `data/processed/phase7_generated_examples.json`: 3 full generated
  compositions (timeline, annotated tree, rule sequence, rendered view).

`tests/test_attributes.py` (12 tests):
- Hand-checkable attribute tests: exact equal split within a mātrā, a
  well-formed cycle is accepted and a 15-mātrā one is rejected, and a
  standalone rest with no duration is refused.
- Hand-checkable tihāī tests: an exact reading-B landing; the same tihāī
  moved by ¼ mātrā is rejected; reading A detected; a gap outside the plan's
  set is flagged; the 23 valid shapes all fit.
- Real corpus: the default grammar is still exactly Phase 5's (44 rules);
  all 351 real cycles are well-formed with rests and reproduce their
  onsets; 100 constrained samples are all well-formed; 30 generated tihāīs
  land exactly on sam with identical phrases and a real stroke on sam.

## 9. Open items for you

1. **Phase 3 correction (§2.3).** Phase 3's "secondary cluster near the
   half-mātrā" claim is not supported by the measurement. I have not edited
   `docs/PHASE3_REPRESENTATION.md`. I can append a clearly marked
   correction note there if you want, without changing its original text.
2. **`MatraTail` fix (§6).** It would fix the empty-mātrā rate and
   misplaced rests, but it changes the Phase 5 grammar design. Apply it,
   and as opt-in or as the new default?
3. **Gapless tihāīs (§4.3).** 55 of 115 candidates have no gap. The plan's
   set excludes 0. Should a gapless triple repetition count as a tihāī?
   This needs a source or your judgment.
4. **Expert check of `ben_23` and `ben_25` (§4.2).** These are the cleanest
   formal matches in the corpus, and the natural first items for the
   expert-review step (plan §10).
5. Still open from earlier: mukh / viśrām / adhā-viśrām / palṭā (Phase 4),
   and Mode B (40-symbol) runs (Phases 5–7 all use Mode A).

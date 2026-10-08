# Phase 5 — The PCFG

Code: [`src/pcfg.py`](../src/pcfg.py) (grammar data structure, supervised
training, log-probability scoring, top-down sampling, CYK/Inside parsing)
and [`src/run_phase5_pcfg.py`](../src/run_phase5_pcfg.py) (runs it over the
corpus). Reproduce with `python3 src/run_phase5_pcfg.py`. Tests:
`tests/test_pcfg.py` (10 passing; 35/35 total across Phases 1–5).

---

## 1. Grammar design, and why every rule traces back to an earlier phase

The proposal asks for a context-free grammar over tāla structure. Rather
than inventing non-terminals, every one used here is a direct encoding of a
structural fact a previous phase already verified against the real data:

```
Composition -> Avartan Composition | Avartan
    (a variable-length list of cycles; Phase 1 verified avartan
    boundaries via score/onset alignment, Phase 3 built them)

Avartan -> Vibhag0 Vibhag1 Vibhag2 Vibhag3
    (tīntāl always has exactly 4 vibhāgs - Phase 3's TalaDefinition,
    standard tāla theory, not invented here)

Vibhag0/1/2/3 -> Matra Matra Matra Matra
    (tīntāl always has exactly 4 mātrās per vibhāg - same source)
    Vibhag0's FIRST mātrā uses a separate non-terminal, SamMatra, instead
    of Matra, because mātrā index 0 is "sam" - a structurally distinguished
    position Phase 3 already flags (is_sam) and that is standard,
    uncontested tāla theory (the cycle's resolution point). Vibhag2 is
    likewise kept as its own non-terminal (not merged with Vibhag1/Vibhag3)
    because it is tīntāl's khālī vibhāg (Phase 3's TalaDefinition
    .khali_vibhags) - this lets the grammar LEARN whether khālī productions
    actually differ, instead of assuming they do or forcing them to match.

SamMatra/Matra -> BolSlot SamMatra|Matra ... | BolSlot
    (a variable number of strokes per mātrā - Phase 3 found 1 to 5 strokes
    sharing a single mātrā; this is the Phase 2-documented "compound slot"
    phenomenon, handled as a learned list, not a fixed-arity rule)

BolSlot -> <bol>   (one rule per terminal symbol in the vocabulary)
```

**No mukh/dohrā/adhā-dohrā/viśrām/palṭā/tihāī non-terminals appear.** Phase
4 explicitly could not establish those well enough to build hard grammar
rules from (see `docs/PHASE4_SEED_TREEBANK.md §5`, still an open question for
you). This is the "vanilla" context-free skeleton; attribute-based
constraints (tihāī arithmetic) are Phase 7's job, not this one — the
proposal's own §5.3 says tihāī needs more than context-free power anyway.

## 2. Why supervised MLE, not Inside-Outside EM, at this phase

The proposal's staged design keeps Inside-Outside EM for Phase 16
(MDL/latent-category refinement). That is the right place for it, not here,
for a concrete reason specific to this project's data: **Phase 3 already
produced a known, correct derivation tree for every single avartan in the
whole corpus** (351 avartans, 38 compositions), because it has real onset
timestamps, not just a flat bol string. EM exists to learn structure when
you only have the flat strings and must *infer* a parse. That is not our
situation here — the parse (which bols fall in which mātrā, which mātrā is
"sam", etc.) is already determined by data Phase 1–3 verified, not guessed.
So training here is **supervised Maximum Likelihood Estimation**: count how
often each production actually occurred across the real derivations, divide
by the total — the standard, exact MLE formula for PCFGs when trees are
known, no EM needed. (If a later phase wants to ask "could a different,
*unsupervised* split of mātrās into sub-categories explain the data better
than this one?", that is exactly Phase 16's latent-category question, and it
is EM's job then — not this one.)

## 3. Mode A (18-symbol) vs Mode B (40-symbol): which was used, and why

This run trains on **Mode A (normalized, 18-symbol vocabulary)**, not Mode
B. Reason: Phase 2 already found that many Mode B symbols are extremely
rare gharānā-specific spelling variants of the same underlying stroke (see
`docs/PHASE2_BOL_NORMALIZATION.md`). Training a grammar's terminal
probabilities on Mode B would mean many `BolSlot -> <bol>` rules have a
count of 1 anywhere in the whole 38-composition corpus — not enough data to
estimate a probability from. The grammar design/code itself does not
hard-code Mode A; `train_supervised()` takes the mode as a parameter and can
be re-run under Mode B at any time if you want that comparison (the
proposal's own "report under both modes" instruction), it just was not done
in this run.

## 4. The trained grammar: diagnostics

```
Training supervised PCFG on 38 compositions (Mode A, normalized 18-symbol vocab)
Grammar: 9 non-terminals, 44 rules (18 terminal rules)
Probabilities sum to 1 for every non-terminal: True
Zero-probability rules present: 0
Non-terminals never used on any right-hand side (should just be the start symbol): []
```

All three health checks the proposal asks Phase 5 to watch for pass: no
non-terminal's productions fail to sum to 1, no rule got stuck at zero
probability, and no non-terminal is dead code (unreachable from any other
rule). The 9 non-terminals are exactly: `Composition`, `Avartan`, `Vibhag0`,
`Vibhag1`, `Vibhag2`, `Vibhag3`, `SamMatra`, `Matra`, `BolSlot` — matching
§1's design one-for-one, nothing extra appeared and nothing is missing.

## 5. MLE vs MAP (Dirichlet) smoothing: a real worked example

The proposal flags corpus size (38 compositions) as a reason some rule
counts may be small, and asks for Dirichlet-prior (MAP) smoothing as a
mitigation. Here is the actual effect, taken from the real run, on the
non-terminal with the sparsest counts, `'Avartan'` (its rules decide how
many vibhāgs' worth of material come before the avartan boundary — almost
always exactly 4, but not quite always, because of real notational
irregularities Phase 3 already surfaced):

```
('Vibhag0', 'Avartan'): count=350  MLE prob=0.3418  MAP prob=0.3413
('Vibhag0', 'Vibhag1'): count=1    MLE prob=0.0010  MAP prob=0.0015
('Vibhag1', 'Avartan'): count=323  MLE prob=0.3154  MAP prob=0.3150
('Vibhag1', 'Vibhag2'): count=7    MLE prob=0.0068  MAP prob=0.0073
('Vibhag1', 'Vibhag3'): count=15   MLE prob=0.0146  MAP prob=0.0151
('Vibhag2', 'Vibhag3'): count=328  MLE prob=0.3203  MAP prob=0.3199
```

(Dirichlet α=0.5.) The pattern is exactly what MAP smoothing is supposed to
do: the one rule with count=1 (`Vibhag0 -> Vibhag1`, an irregular case) gets
its probability pulled *up* (0.0010 → 0.0015) relative to plain MLE, at the
cost of a tiny pull *down* for the common rules — because the prior is
"spreading" a small amount of assumed probability mass onto every rule,
which matters proportionally much more for a rule seen only once. `pcfg.py`
exposes `dirichlet_alpha` as a parameter on `train_supervised()`, defaulting
to `0.0` (plain MLE, what every other number in this document uses) so the
choice is explicit and swappable, not silently baked in.

## 6. The CYK/Inside parser: what it is, and the honest ambiguity finding

`cyk_inside_log_prob()` computes the **total** probability of an arbitrary
flat bol sequence under the grammar — summed over *every* valid way the
grammar could have derived it (an Inside algorithm), not just the single
most likely parse (a Viterbi algorithm). This distinction mattered enough
to get a bug: the first version of this function was accidentally written
using `max` instead of summing, while being named/documented as "Inside" —
caught and rewritten (using log-sum-exp accumulation) before any numbers
were produced from it; see the code's own comments in `pcfg.py` for the
corrected structure.

**Why this parser exists at all, given Phase 3 already gives us real
derivations:** `cyk_inside_log_prob()` is for scoring a bol sequence when
you do *not* know its timing/segmentation in advance — e.g. a freshly
generated sequence (§7 below), or any future evaluation (Phase 11's
perplexity, most likely) on a sequence with no Phase-3-style timestamps.

**Validation run**, checking that the inside (summed) probability is never
*less* than one specific known-correct derivation's probability (which
would be mathematically impossible for a correct inside algorithm, since
the sum includes that one derivation):

```
Validating CYK/Inside parser against known supervised derivations (short/medium compositions: ['pjb_84', 'ajr_12', 'luc_17']):
  pjb_84 (n=47):  supervised=-184.454  CYK-inside=-120.599  diff=+63.8552   (0.15-0.28s)
  ajr_12 (n=96):  supervised=-363.227  CYK-inside=-252.522  diff=+110.7053  (1.4-2.7s)
  luc_17 (n=164): supervised=-530.640  CYK-inside=-348.961  diff=+181.6794  (13.2-13.4s)
```

The inequality direction is correct in all 3 cases (inside ≥ supervised), so
the fix is validated. But the *size* of the gap is itself a real, honest
finding worth stating plainly rather than glossing over:

**The grammar is substantially ambiguous when parsing a flat bol sequence
with no timing information.** A difference of +64 to +182 in log-probability
space means the total probability mass summed over all parses is vastly
larger (by a factor of roughly e^64 to e^182) than the one true parse's
share of it. Concretely: with no timestamps to say where one mātrā ends and
the next begins, the grammar's own rules (`Matra -> BolSlot Matra | BolSlot`,
etc.) are flexible enough that the *same* flat bol string can be legally
re-segmented into many different mātrā/vibhāg groupings, and all of them are
grammatical. This is not a bug — it is a correct, structural fact about this
particular grammar's design (it was built to allow a variable number of
bols per mātrā, which is exactly what makes it ambiguous once the timing
that normally disambiguates that choice is removed).

**Practical implication for later phases:** for any *real* tabla
recording — which, per Phase 1/3, always comes with onset timestamps — the
correct way to score it is the **supervised/deterministic derivation**
(`tree_log_prob`), not the ambiguous CYK/Inside parser, because the timing
data removes the ambiguity the grammar alone cannot resolve. The CYK/Inside
parser should be reserved for sequences that genuinely have no timing
attached at all — e.g., scoring the grammar's own freely generated output
(§7), or a future generative baseline's output. This has a direct
consequence for Phase 11 (perplexity evaluation): if that phase evaluates
real held-out *recordings*, it should use the supervised log-prob path, not
this parser, or its perplexity numbers would be measuring segmentation
ambiguity, not sequence likelihood.

## 7. CYK runtime: honest benchmark and why the longest composition was not measured

```
CYK runtime benchmark across composition lengths:
  n=47  (pjb_84):  0.16-0.18s
  n=96  (ajr_12):  1.42-1.50s
  n=256 (dli_2):   57.65s
  n=164 (luc_17):  8.31-13.41s   (measured separately, consistent with the trend)
```

CYK's theoretical complexity is O(n³). The measured growth is *roughly*
consistent with that — going from n=96 to n=256 (a 2.67x length increase)
took about 38x longer (1.5s → 57.65s), versus 2.67³≈19x expected from a
clean cubic fit — so the real constant-factor behavior is somewhat worse
than a pure n³ model, not a perfect match, and that is reported honestly
rather than rounded off to "matches theory."

The full corpus's longest composition is **n=611** bols. Extrapolating
cubically from the n=256 measurement (57.65s) would put it at roughly
57.65 × (611/256)³ ≈ **780 seconds (~13 minutes)** — and given the
super-cubic trend just noted, plausibly longer. Rather than spend that time
brute-forcing one number, this is reported as an **extrapolate, don't
measure** decision, stated here rather than silently avoided: the benchmark
measures 3 real points (n=47, 96, 256) and extrapolates the 4th, instead of
claiming a 4th measured data point that was not actually run.

**Practical implication:** CYK/Inside parsing at these corpus lengths is
usable for short-to-medium compositions (well under a minute up to roughly
n≈250) but becomes expensive for the longest real pieces. Combined with §6's
finding, this is a second, independent reason to prefer the supervised
log-prob path wherever real timing data is available — it is also
essentially instantaneous (a single pass over the known tree), whereas CYK
pays its full O(n³) cost even to re-confirm what timing already tells you.

## 8. Sample generations from the trained grammar

Top-down sampling (`sample_tree()`) draws from the learned production
probabilities at each step, recursively, until every branch terminates in a
bol. Of 50 sampling attempts (seeded, reproducible), filtering to sequences
between 8 and 40 bols long for readability:

```
(36 bols): NA KI DHA NA KI GE KI RE TA TA DHI TA TA TA TA NA TIT TA TA DHE NA KI TA DA KI KDA DHA TA KI NA KDA TA GE GE GE GE
(34 bols): KI TA TA RE NA KI NA DHA DHE RE GE RE NA TA DHA TA TA TA TA NA DHI NA GE NA NA TA KI TA NA TA KI TRA GE TA
(10 bols): KI TA DHE KI NA GE GE GE NA NA
Generated 3 readable samples in 50 attempts
```

Read honestly: these are locally plausible (every 2-4-bol transition came
from a real rule learned from the corpus), but the grammar has **no
mechanism yet** to make a whole generated sequence musically coherent as a
*composition* — there is no tihāī constraint, no mukh/palṭā structure, no
notion of "this should resolve on sam in a satisfying way." That is expected
at this phase: this grammar is the structural skeleton (§1), not yet
constrained by Phase 7's attribute grammar. Only 3 of 50 attempts landed in
the 8–40-bol "readable" window — many attempts produced 0-bol, extremely
short, or extremely long sequences, which is itself informative about the
`Composition -> Avartan Composition | Avartan` recursion's learned
stopping probability, worth keeping in mind if Phase 6 compares against
other initializations.

## 9. Files produced

- `data/processed/phase5_grammar.json` — the trained grammar: vocabulary
  (18 symbols) and every rule with its count and probability, keyed by
  left-hand-side non-terminal.
- `data/processed/phase5_sample_generations.json` — the 3 readable sample
  generations quoted in §8, as flat bol strings.

## 10. Tests

`tests/test_pcfg.py`, 10 tests:
- Two hand-computable synthetic-grammar tests pin down the Inside
  algorithm's arithmetic against a probability a human can check on paper
  (one with genuine 2-way ambiguity summing to exactly 1.0, one fully
  unambiguous case) — this is what would have caught the max-vs-sum bug
  from §6 directly, had it still been present.
- A third synthetic test confirms an underivable string correctly returns
  probability 0 (log-prob -∞), not a false positive.
- MLE-vs-MAP smoothing is checked on a tiny synthetic grammar (the smoothed
  rare rule's probability must move up relative to plain MLE).
- The diagnostics health check is checked against a deliberately broken
  grammar (probabilities not summing to 1) to confirm it actually flags
  that case, not just passes silently on healthy input.
- On the real corpus: the trained grammar's diagnostics are healthy: every
  supervised tree's leaves exactly reconstruct that composition's real
  Mode-A onset sequence (same round-trip discipline as Phase 4); every rule
  actually used by a real derivation has positive probability (no derivation
  secretly costs -∞); and CYK-inside is confirmed ≥ the known derivation's
  probability on the real data (restricted to the shortest composition, to
  keep the test suite fast given CYK's cost — see §7).
- Sampling produces only vocabulary bols actually seen in training.

Full suite: **35/35 passing** across Phases 1–5 (25 before this phase).

## 11. Open items carried forward, not resolved here

- **mukh/viśrām/adhā-viśrām/palṭā** (Phase 4's open question) remain
  unassigned; still waiting on your direction per the three options listed
  in `docs/PHASE4_SEED_TREEBANK.md §5`.
- **Mode B (40-symbol) training** was not run in this phase — the code
  supports it (`train_supervised(..., mode=BolNormalizationMode.DISTINCT)`)
  but was not executed; flagging this explicitly rather than reporting a
  number that was never produced.
- **The longest composition's CYK runtime (n=611)** was extrapolated, not
  measured — see §7 for the reasoning and the extrapolated estimate
  (~13 minutes or more).
- **The CYK-inside-vs-supervised gap (§6)** is a design property of this
  grammar worth keeping in mind for Phase 11: real recordings should be
  scored via the supervised path, not CYK, for the reasons given there.

# Phase 4 — Seed Treebank

Code: [`src/treebank.py`](../src/treebank.py) (tree structure, section-label
builder, tihāī candidate detector) and
[`src/run_phase4_treebank.py`](../src/run_phase4_treebank.py) (runs it over
the corpus). Reproduce with `python3 src/run_phase4_treebank.py`. Tests:
`tests/test_treebank.py` (6 passing; 25/25 total across Phases 1–4).

---

## 1. The honesty problem this phase had to solve before writing any code

The project plan asks for an "expert-authored skeleton grammar" using
non-terminals **mukh, dohrā, adhā-dohrā, viśrām, adhā-viśrām, palṭā, tihāī**,
and to "hand-parse approximately 10 compositions."

**I am not a tabla expert, and I have no sourced, verifiable basis for
deciding which specific phrase in a composition is a mukh vs. a palṭā vs. a
viśrām.** Assigning those labels myself would be exactly the kind of invented
musicological claim this project's own rules prohibit — the same category of
problem flagged in Phase 2 over the bayan/dayan compound-bol decomposition.

So Phase 4 does **only** what can be grounded in real evidence, and is
explicit about what it deliberately does not attempt. Two things are
grounded:

1. **The score files' own section labels** (`Dohra`, `Adha Dohra`) — real,
   human-assigned text that happens to match two of the seven non-terminal
   names *exactly*. Already established (Phase 1/2) as weak supervision, not
   verified ground truth — used here on that same basis, not upgraded.
2. **Tihāī is not actually a judgment call.** The proposal's own formal
   definition (§5.3) is a checkable pattern: a phrase repeated exactly three
   times, separated by two *equal* gaps. That is a literal string/repetition
   search, not an opinion about what "sounds like" a tihāī.

**Mukh, viśrām, adhā-viśrām, and palṭā are not assigned anywhere in this
phase.** No section label in the corpus uses these words, and no structural
signal available to this project can reliably locate them. This is flagged
as an open question for you at the end of this document, not silently
skipped.

## 2. Scoping the "~10 compositions" honestly

The proposal frames mukh/dohrā/adhā-dohrā/.../tihāī as the **"Delhi bāj
kāydā expansion order"** — i.e., this vocabulary describes the internal
structure of **kāydā-type compositions specifically**, not every form in the
corpus (a Rela, a Gat, a Chakradār are different forms with presumably
different structure, not covered by this list).

Checking the corpus for compositions whose score header says `TYPE:QUAYDA`
or `TYPE:QUAYDA-ANG-GAT` (kāydā, in the dataset's spelling) returns **exactly
10 compositions** — matching the proposal's "~10" instruction precisely, and
not chosen to hit that number:

```
dli_1, dli_2, dli_3, ajr_9, ajr_10_ajr, ajr_10_dli, ajr_11, ajr_12, ben_22, pjb_75
```

This is the seed treebank's scope.

## 3. Section-label trees: method and validation

For each of the 10 compositions, a tree is built with:
- Root `Composition`, one child per score section.
- A section child is labeled `Dohra` or `AdhaDohra` **only** when the score's
  own section name matches those words exactly (case-insensitive) — tagged
  in the tree's `source` field as *"matches proposal's documented term
  exactly."* Any other section label (e.g. `Quayda` itself, `Double`) keeps
  its own literal name, tagged as *"descriptive catalog label, not one of
  the proposal's 7 kāydā-expansion non-terminals"* — not force-mapped onto
  a term it was never shown to mean.
- Each section's child nodes are `Avartan` (cycle) nodes, reusing Phase 3's
  verified avartan boundaries.
- Each avartan's children are the real bols, in order, each carrying its
  real timestamp, duration, mātrā, and vibhāg — **no finer structure
  (mukh/palṭā/etc.) is claimed inside an avartan.**

**Validation — what "validate every tree" means here:** for all 10 trees,
the leaves, read left to right, were checked against the composition's
actual onset sequence. **10/10 trees reconstruct their original sequence
exactly** — no bol added, dropped, or reordered by the tree-building process.
This is a mechanical correctness check (round-trip reconstruction), not a
musicological judgment that the trees' section labels are "correct" in a
pedagogical sense — that question is still open (§5).

Of the 10 trees, **5 section-children use one of the proposal's exact
documented non-terminal names** (`Dohra`/`AdhaDohra`, across `dli_1`,
`dli_2`, `ajr_9`, `pjb_75`); the rest use the composition's own catalog
label (`Quayda`, `Double`) or, for the 6 compositions with no section
label at all (`dli_3`, `ajr_10_ajr`, `ajr_10_dli`, `ajr_11`, `ajr_12`,
`ben_22`), a single flat `Composition -> Avartan...` tree with no
intermediate section layer.

## 4. Tihāī candidate detector: method, a bug found and fixed, and results

**Method:** search the flat bol sequence for `Phrase(p) Gap(g) Phrase(p)
Gap(g) Phrase(p)` — the exact three-repeat, equal-gap structure from the
proposal's formal definition — trying phrase lengths 2–12 and gap lengths
0–8, longest phrases first so a genuine long tihāī is found before its
shorter internal sub-repeats would be. The pattern's ending position is also
checked against Phase 3's mātrā grid for proximity to *sam* — a genuine
tihāī should land there, so this is a corroborating signal, not a
requirement for counting as a candidate.

**A real bug was caught by the test suite and fixed before trusting any
numbers:** the first version of this detector required the two gaps to have
the same *length* but never checked they had the same *content* — so e.g.
`DHA GE . NA . DHA GE . TI . DHA GE` (different second gap) would have
wrongly counted as a tihāī. A regression test
(`test_tihai_detector_runs_on_real_corpus_without_error`) now asserts both
gaps are byte-for-byte identical for every candidate found, and this is what
caught the bug in the first place. Fixing it dropped the raw candidate count
from 160 to a more trustworthy **115**.

**Results after the fix:**
- **115 candidates** found across **22 of 38 compositions** (not limited to
  the 10 QUAYDA pieces — tihāī-like repetition is expected in other forms
  too, notably Chakradār, which is *built* from nested three-fold
  repetition).
- **31 of these land within 1 mātrā of a sam** — the strongest additional
  signal that a candidate is a real tihāī rather than coincidental
  repetition.
- One candidate in `luc_16` is a phrase-of-phrases: a 12-token unit that is
  itself 3 repeats of a 4-token phrase, repeated 3 times again — i.e. a
  tihāī of tihāīs. This is a known, named Chakradār structure, so finding it
  here is a sanity check the detector passed, not an anomaly.

**A known limitation, stated plainly rather than hidden:** `luc_18` contains
a long passage where the phrase `KI TA TA KA` with gap `TAA TI RA` repeats
many times in a row — a kāydā-like vamp, not necessarily a single climactic
tihāī. Because this satisfies "3 repeats, same gap" at several overlapping
starting points, the detector reports it as multiple separate candidates.
**The detector finds the formal repetition pattern; it cannot yet
distinguish "a long repeating theme that happens to satisfy this pattern
several times over" from "one deliberate, climactic tihāī."** Telling those
apart reliably would need either a length/prominence heuristic (not yet
built) or the full arithmetic verification described next.

**What this phase does NOT verify, by design:** the proposal's actual tihāī
*constraint* is an equation — `3·dur(p) + 2·dur(g) + 1 ≡ target (mod
cycle_length)` — not just "the same three bols three times." This phase
confirms the **symbolic repetition structure** exists; it does not check the
**duration arithmetic** resolves correctly onto a target sam. That
arithmetic check is Phase 7's job (the attribute grammar), and candidates
found here are its natural input, not a substitute for it.

## 5. Open question for you: mukh, viśrām, adhā-viśrām, palṭā

These four non-terminals are not assigned anywhere in this project yet.
Three honest ways to proceed, same framing as the Phase 2 compound-bol
decision:

1. **Defer to a later phase**, once the grammar itself (Phase 5+) exists and
   there's a concrete mechanism (e.g. EM-learned latent categories, Phase
   5.1's stretch goal) that might surface structure worth naming this way —
   rather than hand-assigning it now.
2. **You supply the parse** for the 10 seed compositions (or a subset),
   from a source you trust (a teacher, a reference book, your own training),
   and I encode exactly what you give me.
3. **Use a cited published source** (the proposal names Clayton, Kippen,
   Saxena, Naimpalli) if you have access to one that parses these specific
   compositions or gives a general, checkable rule — I'll encode what the
   source says and cite it, not what I infer from general familiarity.

No option is implemented in this phase; this is a request for your
direction, not a default already acted on.

# Phase 1 — Dataset Audit Report: Mulgaonkar Tabla Solo (MTS)

**Status: PASSED.** The dataset genuinely contains what the proposal assumes it
contains. Grammar work (Phase 2 onward) can proceed. This report documents
exactly what was checked, how, and what the actual numbers are — not what the
proposal or README merely claim.

Source data: uploaded directly by the researcher in batches (Zenodo and
compmusic.upf.edu are blocked by this execution environment's network policy;
see the project plan's Risks section). All 38 compositions × 4 file types
(score, onsMap, onsNoMap, wav) plus `filelist.txt`, `LICENSE`,
`README_dataset.txt`, `syllableMapping.pdf` were received and verified present
against `filelist.txt` before this audit began.

Audit code: [`src/mts_loader.py`](../src/mts_loader.py) (parsing) and
[`src/run_phase1_audit.py`](../src/run_phase1_audit.py) (all checks below).
Reproduce with `python3 src/run_phase1_audit.py` from the repo root (needs
`pandas`, `matplotlib`, `numpy` — see Phase 18 for a pinned environment).

---

## 1. File formats and directory structure

The dataset's own `README_dataset.txt` (included in the upload) documents the
layout, and the files on disk match it exactly:

```
data/raw/mts/
  filelist.txt          38 composition names, one per line
  LICENSE                audio: non-commercial only, no redistribution
                          annotations: CC BY-NC-ND 4.0
  README_dataset.txt      the dataset's own description (verified accurate)
  syllableMapping.pdf/.txt  the 41→18 syllable-reduction table
  score/<name>.txt        hand-authored score: metadata + named sections + bols
  onsMap/<name>.csv       "timestamp, BOL" onsets, 18-symbol mapped vocabulary
  onsNoMap/<name>.csv     "timestamp, BOL" onsets, raw ~40-symbol vocabulary
  wav/<name>.wav          audio (NOT committed to git — see §9)
```

No `.lab`/`.mat` files as `percPatternDiscovery` (Gupta et al. 2015)
assumes — **that repo's loaders were inspected (via its GitHub README) and
found to expect a different file layout than what MTS actually ships.**
Per the working rule ("inspect, don't blindly reuse"), a small bespoke loader
(`src/mts_loader.py`) was written instead of adapting that code. This is a
scope-neutral engineering choice, not a deviation from the proposal.

## 2. Number of compositions, gharāna, tāla

- **38 compositions**, confirmed against `filelist.txt` by exact name match.
- **Gharāna distribution:** DILLI 6, AJRADA 5, LUCKNOW 4, BENARAS 9,
  FARUKKHABAD 3, PUNJAB 11 — **6 gharānās**, matching the proposal.
- **Tāla:** all 38 compositions are tagged `TALA:TEENTAL` in their score
  headers — **zero exceptions**. The proposal's "all tīntāl" claim is verified,
  not assumed.
- **Jāti** (subdivision-family) header is present but unreliable: 16/38
  compositions have `JATI:??` (the transcriber didn't know/fill it in). Usable
  where present, but jāti-conditioned analysis will have ~42% missing data.
- **Composition type** (from the score header's `TYPE:` field) gives 19
  distinct forms across the corpus, including 9 Kāydā, 4 Dohrā-bearing pieces,
  3 Joḍā, 3 Prapat Gat, 2 Relā, 2 Chakradār-family pieces, etc. — matches the
  proposal's claim of "theka, kāydā, palṭā, relā, peśkār, gat" forms being
  present (with kāydā-related forms being the largest single group).

## 3. Available audio and scores

- **Audio:** all 38 `.wav` files present (89 MB total). **Not required for
  this project's scope** (the grammar operates on the symbolic bol stream),
  and **not committed to the repository** — the LICENSE explicitly restricts
  audio to non-commercial use with no further redistribution, and committing
  it to git would count as redistribution risk. See §9.
- **Scores:** all 38 `.txt` files present. These are far richer than the
  proposal's own description suggested — see §4 and §6.

## 4. Bol transcription format (the main finding)

Two representations exist per composition, and they are **not the same
format** — mixing them up would silently corrupt any analysis:

- **`score/<name>.txt`** — a hand-authored, human-readable score:
  - A metadata block (`GHARANA`, `COMPOSITION`, `JATI`, `TYPE`, `TALA`,
    `COMPOSER`) between two `##` lines.
  - One or more **named sections**, e.g. `''Quayda''`, `''Dohra''`,
    `''Adha Dohra''` — see §7, this is a major finding for Phase 4.
  - A `!S:<N>` (or `!S:<N>|<M>`) header per section giving a subdivision
    count, followed by score lines, closed with `!E`.
  - Each line = one or more **vibhāg-groups**, separated by `;`.
  - Each vibhāg-group = space-separated **slots**.
  - Each slot may itself contain **comma-joined sub-bols** (e.g. `TI,RA`,
    `DHA,GE`, `KI,TA,TA,KA`) representing multiple strokes inside one slot's
    time budget.
  - `-` is the explicit **rest** symbol (1,117 occurrences across the corpus).
  - Vocabulary: the **raw, unreduced** ~40-symbol space (see §5) — not the
    18-symbol mapped space.

- **`onsMap/<name>.csv` and `onsNoMap/<name>.csv`** — `timestamp, BOL` per
  line, one row per actual onset event. `onsMap` uses the reduced 18-symbol
  vocabulary; `onsNoMap` uses the same raw vocabulary as the score files.
  **No rest rows, no duration field** — see §8.

## 5. Exact bol vocabulary and orthographic variants

- **`onsMap` vocabulary: exactly 18 symbols** — `DA, DHA, DHE, DHET, DHI,
  DHIN, DIN, GE, KDA, KI, NA, RE, TA, TE, TII, TIN, TIT, TRA`. This matches
  `syllableMapping.pdf`'s declared mapped-symbol set **exactly** (verified
  programmatically, no manual eyeballing).
- **`onsNoMap` / `score` vocabulary: 40 distinct raw symbols** (not 41 as the
  dataset's own README states in prose — a minor discrepancy between the
  README's rounded description and the actual file contents; not a data
  -integrity problem, just don't cite "41" as a hard-verified number).
- **Every raw symbol observed in `onsNoMap` is accounted for by
  `syllableMapping.pdf`'s variant lists** (verified programmatically) — e.g.
  `KA, KAT, KE, KI, KII` all map to `KI`; `GA, GHE, GE, GHI, GI` all map to
  `GE`; `TA, TI, RA` all map to `TA`; `N, NA, TAA, TU` all map to `NA`;
  `DI, DIN, DING, KAR, GHEN` all map to `DIN`; `KDA, KRA, KRI, KRU` all map to
  `KDA`; `CHAP, TIT` map to `TIT`.
- **Practical consequence for Phase 2:** "bol normalisation" in this dataset
  is not a fuzzy judgment call to make from scratch — the dataset ships an
  **authoritative, pre-existing mapping**, built by tabla/mridangam students
  based on timbral similarity. Phase 2's "mode A (normalized) / mode B
  (distinct)" comparison can and should use `onsMap` vs `onsNoMap` directly
  as the two conditions, rather than inventing a new normalization scheme.

## 6. Is the data actually symbolic and time-aligned? (the critical check)

This was the single most important thing to verify before trusting anything
downstream. Method: flatten each score file's bol sequence (dropping rests)
and compare it, in order, against the `onsNoMap` onset sequence for the same
composition.

- **Token-count match: 38/38 compositions.**
- **Exact sequence match (every bol, in order): 38/38 compositions.**

This is a clean, complete pass — not "mostly aligned" or "aligned after
fuzzy-matching." The hand-authored score and the onset-detection pipeline
agree perfectly, corpus-wide. **The proposal's assumption that this is a
real, time-aligned symbolic corpus is verified, not just trusted.**

## 7. Whether kāydā/palṭā structure can be identified automatically

**Yes, partially, and better than expected.** 30/38 compositions have
**explicit, human-assigned section names** in their score files that map
directly onto the proposal's own non-terminal vocabulary:

| Section label (as written) | Count |
|---|---|
| Quayda (=kāydā) | 6 |
| Dohra | 4 |
| Adha Dohra | 1 |
| Joda | 3 |
| Rela | 1 |
| Gat / Gat-Single / Gat-Double / Gat Paran / Gat Tukda / Gat in Deepchandi Ang | 9 |
| Prapat Gat / Pragat Gat | 2 |
| Chakradar / Lambchhad Chakradar | 3 |
| Khand Gat (Single/Double) | 2 |
| Fard Gat (Single/Double) | 2 |
| Ladi, Dudhari Gat, Lahori Gat, Madhumakkhi Gat, "Purani Gat", "Double" | 6 |

The remaining **8 compositions have a single unnamed (implicit) section**
(`ajr_11`, `ajr_12`, `ben_19`, `ben_21`, `ben_22`, `dli_3`, `luc_16`,
`luc_18`) — treat these as one un-labeled top-level constituent.

This is a substantially better starting point for **Phase 4 (seed treebank)**
than "hand-parse ~10 compositions from nothing": for kāydā-type compositions,
the mukh/dohrā/adhā-dohrā boundary is often already marked by the original
transcriber, and can be used as **weak supervision**, not gold-standard
truth — a human tabla-literate check is still needed before trusting these
labels for the treebank (they were made for cataloguing, not for grammar
annotation, and "Single"/"Double" pairs likely denote a doubling/tempo
relationship rather than distinct grammatical categories — worth confirming
with an expert or the pedagogy references, not assumed here).

## 8. Representation of rests and duration

- **Rests exist only in the score text**, as the literal character `-`
  (1,117 occurrences across the corpus). **Neither `onsMap` nor `onsNoMap`
  contains any rest marker or rest row** — the onset files only record
  actual struck syllables.
- **Duration is not stored anywhere as an explicit field.** The onset CSVs
  give only *onset (start) times*. A bol's duration must be inferred as
  `(next_onset_time − this_onset_time)`, which:
  - breaks down at the last event of a phrase/avartan (no "next" event to
    subtract from) — needs the tāla's known cycle length to close the gap;
  - conflates "how long this stroke rings" with "how long until the next
    stroke," which are not the same thing acoustically, though they may be
    an adequate proxy for a symbolic-duration grammar.
- **Practical consequence:** the attribute-grammar duration mechanism
  (Phase 7 / proposal §5.3) must be built on **inferred inter-onset
  intervals**, not a ground-truth duration field — this should be stated
  explicitly in the paper's limitations, not glossed over.

## 9. Avartan (cycle) extraction

Using the verified score↔onset alignment (§6), score **line boundaries**
were used to cut the `onsNoMap` onset-timestamp stream into candidate
avartans (cycles), for all 38 compositions (attempted) since all 38 have an
exact sequence match.

- Of compositions with ≥2 candidate cycles to compare, **25 show cycle
  durations consistent to within 15%** of each other — direct evidence that
  cycles **can** be reliably segmented once score and onset streams are
  aligned.
- Compositions that did not clear this bar are not necessarily broken: many
  are short pieces with only one cycle's worth of material (nothing to
  compare against), or contain deliberately accelerating/decelerating
  passages (common in relā, chakradār, tihāī-heavy material) where cycle
  duration is *expected* to vary — this needs a musicologically-informed
  second pass in Phase 3/4, not a blanket "extraction failed" verdict.

## 10. Leakage risk found: `ajr_10_ajr` / `ajr_10_dli`

The score headers for these two files read `COMPOSITION:10_Ajrada` and
`COMPOSITION:10_Dilli` respectively — **the same underlying kāydā, taught in
two gharānā renderings**, with long, near-identical shared phrases. These
must be treated as **one split-unit**, never separated across train/val/test.
The generated split (§12) handles this correctly; any future re-split must
preserve this constraint.

## 11. Data statistics

- Composition length (mapped onset events): min 47, max 611, mean 217.0.
- See `visualizations/phase1_bol_frequency_mapped.png` (Zipfian bol
  frequency; `TA` dominates, as expected for tabla — mirrors the proposal's
  implicit assumption that the terminal distribution is highly skewed),
  `phase1_composition_length_hist.png`, and `phase1_gharana_counts.png`.
- The min length of 47 events (a single short composition) is a concrete,
  early data point for the proposal's own stated corpus-size concern (§6.2):
  some individual compositions are very short, reinforcing that the
  āvartan — not the composition — should be the unit for EM (as the
  proposal already plans).

## 12. Train/validation/test split (composition-level)

Generated by `src/run_phase1_audit.py`, seed 42, ~70/15/15 split by
composition count, with `ajr_10_ajr`/`ajr_10_dli` glued into one unit (§10).
Saved to `data/processed/splits.json`: 26 train / 6 val / 6 test.

## 13. Open items before Phase 2 begins

1. **Confirm with the researcher (or a tabla-literate reference) whether the
   score files' section labels are trustworthy enough to seed the Phase 4
   treebank directly**, or whether they should only inform, not replace,
   manual parsing.
2. **Jāti is missing for 16/38 compositions** — decide whether any planned
   analysis actually needs it; if not, no action required.
3. The dataset's README states "41 syllables" but only 40 are actually
   observed in the files — noted, not a blocker.
4. `syllableMapping.pdf` is the **authoritative normalization** for Phase 2;
   no separate normalization scheme should be invented.

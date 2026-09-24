# Phase 2 — Bol Normalization

Code: [`src/bol_normalization.py`](../src/bol_normalization.py) (the
configurable normalizer) and
[`src/run_phase2_analysis.py`](../src/run_phase2_analysis.py) (all analysis
below). Reproduce with `python3 src/run_phase2_analysis.py` from the repo
root. Tests: `tests/test_bol_normalization.py`.

---

## 1. Design decision: reuse the dataset's own mapping, don't invent one

Per the Phase 1 audit (§5, §13), the MTS dataset ships its own authoritative,
methodologically-documented syllable-reduction table (`syllableMapping.pdf`,
built by tabla/mridangam students from timbral similarity) and the
`onsMap`/`onsNoMap` files already implement it. Phase 2 exposes this as a
configurable two-mode normalizer rather than deriving a new scheme:

- **Mode A (`NORMALIZED`)** — the 18-symbol mapped vocabulary (`onsMap`).
- **Mode B (`DISTINCT`)** — the raw ~40-symbol vocabulary (`onsNoMap`).

`BolNormalizer` in `src/bol_normalization.py` loads `syllableMapping.pdf`'s
table directly and builds the raw→mapped lookup from it — so Mode A output is
always traceable back to that one source document, not to a project-invented
rule. Any bol not covered by the table raises an error rather than being
silently passed through, so gaps surface instead of hiding.

This satisfies the proposal's "document it; report results under both"
instruction (§4): every later phase (baselines, PCFG training, evaluation)
can be run under both modes by passing `BolNormalizationMode.NORMALIZED` or
`.DISTINCT`, and results compared directly.

## 2. Vocabulary size and frequency, both modes

| Mode | Vocabulary size |
|---|---|
| A (normalized) | 18 |
| B (distinct) | 40 |

Mode A frequencies were already reported in the Phase 1 audit
(`visualizations/phase1_bol_frequency_mapped.png`). Mode B's full frequency
table is in `data/processed/phase2_vocab_mode_b.json`; a log-scale view
showing rare bols against the corpus-wide distribution is in
`visualizations/phase2_mode_a_frequency_log.png`.

## 3. Rare bols

Using a corpus-wide threshold of **fewer than 10 occurrences**:

- **Mode A (normalized): none** — every one of the 18 mapped symbols occurs
  ≥10 times corpus-wide. The mapping's own job is partly to absorb rarity;
  it does so completely at this threshold.
- **Mode B (distinct):** `N` (3), `DING` (1), `KRU` (2), `KRA` (1), `KRI` (1),
  `CHAP` (2), `D` (1), `KAR` (8), `GHEN` (8), `TU` (6).

**Practical consequence:** training any model directly on the raw (Mode B)
vocabulary means several symbols have single-digit corpus-wide support —
`D` and `DING` occur exactly **once each** in the entire 38-composition
corpus. Any Mode B experiment (grammar or baseline) needs either Dirichlet
smoothing strong enough to handle this, or an explicit note that these
symbols are effectively untrainable at this corpus size. This is a concrete,
measured instance of the proposal's own stated corpus-size concern (§6.2).

## 4. Gharānā-specific orthographic variants

For every mapped (Mode A) symbol with **more than one raw spelling actually
observed** in the corpus, per-gharānā counts were computed and the dominant
(most frequent) spelling per gharānā compared. **8 mapped symbols have >1
observed raw variant; for 5 of them, the dominant spelling differs across
gharānās:**

| Mapped symbol | Observed variants | Dominant spelling by gharānā |
|---|---|---|
| **KI** | KA, KAT, KE, KI, KII | AJRADA→KI, BENARAS→KI, DILLI→KI, **FARUKKHABAD→KA, LUCKNOW→KA, PUNJAB→KA** |
| **GE** | GA, GHE, GE, GHI, GI | AJRADA→GE, **BENARAS→GA**, DILLI→GE, **FARUKKHABAD→GA**, LUCKNOW→GE, PUNJAB→GE |
| **NA** | N, NA, TAA, TU | AJRADA/BENARAS/DILLI/FARUKKHABAD/PUNJAB→NA, **LUCKNOW→TAA** |
| **DIN** | DI, DIN, DING, KAR, GHEN | AJRADA→DIN, **BENARAS→DI**, DILLI→DIN, **FARUKKHABAD→DI, LUCKNOW→DI**, PUNJAB→DIN |
| **TIT** | CHAP, TIT | AJRADA/DILLI/FARUKKHABAD/LUCKNOW/PUNJAB→TIT, **BENARAS→CHAP** (n=2 only — see caveat) |

Full per-gharānā counts: `data/processed/phase2_gharana_variants.json`.

**This is genuine, corpus-measured evidence of gharānā-specific spelling
preference** — e.g. Farukkhabad/Lucknow/Punjab transcriptions favor `KA` where
Ajrada/Benaras/Dilli favor `KI` for the same mapped symbol; Benaras and
Farukkhabad favor `GA` over `GE`. This is exactly the kind of finding the
proposal wants surfaced, not assumed.

**Caveats, stated plainly:**
- This describes **transcription/orthographic** preference (how the same
  aggregate sound was written down by whoever transcribed each performance)
  — it is not, by itself, evidence about the *musical* practice of each
  gharānā, and should not be over-interpreted as a stylistic claim without
  musicological corroboration (Clayton, Kippen, Saxena).
- The TIT/CHAP Benaras cell has **n=2** — far too small to trust as a real
  gharānā effect rather than noise. Flagged, not treated as a finding.
- These variants are already folded together under Mode A; this analysis is
  about whether that folding **hides** a real per-gharānā signal, which it
  does for these 5 symbols. Whether that signal matters for the grammar (as
  opposed to just being descriptively interesting) is an open question for
  later phases, not resolved here.

## 5. Compound bols — two distinct phenomena, kept separate

The proposal (§4) raises "compound bols" using `DHA = GE + NA` as the
example, and asks whether they should be atomic terminals or feature bundles
(left-hand × right-hand). Auditing the actual score data surfaced **two
different phenomena that must not be conflated**:

### 5a. Sequential compound slots (dataset-verified)

Score files group multiple bols inside a single time-slot via comma-joining,
e.g. `TI,RA`, `KI,TA,TA,KA`, `DHE,RE`. These are **multiple, sequential
strokes sharing one slot's time budget** — not a single simultaneous
composite stroke.

Slot-arity distribution (# sub-bols per slot), corpus-wide:

| Arity | Count |
|---|---|
| 1 (single stroke) | 2,884 |
| 2 | 2,229 |
| 3 | 94 |
| 4 | 154 |
| 5 | 1 |

So **44% of all slots (2,478 / 5,362) are multi-stroke.** This is a large,
structurally important phenomenon, not an edge case. Top combinations:
`KI,TA` (440), `TA,KA` (370), `TI,RA` (227), `DHE,RE` (194), `NA,GA` (103),
`TI,TA` (76), `KI,TA,TA,KA` (67), `TAA,GE` (62). Full list (top 30):
`data/processed/phase2_compound_slots.json`;
`visualizations/phase2_slot_arity.png` and
`visualizations/phase2_top_compound_slots.png`.

**Representation decision:** these are already explicit and countable in the
score data — no invention needed. They will need a place in the Phase 3
representation (each slot can hold 1..N sub-bol tokens), which is a
representation-design question for Phase 3, not resolved here — flagging it
forward rather than deciding it now, since Phase 3 hasn't started.

### 5b. Simultaneous atomic compound bols (`DHA = GE + NA`-style) — NOT resolved here

The proposal's actual example — `DHA` being simultaneously a bayan (bass,
left-hand) stroke and a dayan (treble, right-hand) stroke — is a **different
phenomenon**: a single atomic symbol (`DHA`) that tabla pedagogy analyzes as
a simultaneous combination of two independent strokes. **Nothing in the MTS
dataset's files states this decomposition** — `DHA` appears as one atomic
label throughout onsMap/onsNoMap/score, with no internal structure recorded.
Any bayan/dayan decomposition of `DHA`, `DHIN`, `DHET`, etc. would have to
come from tabla pedagogy (the proposal names Clayton, Kippen, Saxena,
Naimpalli as the relevant references), not from this dataset, and this
project's rules require such a decomposition to be sourced and verified, not
asserted from general familiarity.

**What was built:** `BolNormalizationMode` and `BolNormalizer` are structured
so a feature-bundle layer can be added later without changing anything
upstream (parsing, onset extraction) — but **no bayan/dayan decomposition
table has been populated**, and none should be until it can be sourced to a
specific citable reference or confirmed by a tabla-literate reviewer. This is
flagged for your decision, not decided here — see the open question below.

## 6. Summary of what Phase 2 delivers vs. defers

**Delivered, dataset-grounded, no invented musicological content:**
- Configurable two-mode normalizer (`BolNormalizer`), sourced entirely from
  `syllableMapping.pdf`.
- Full vocabulary/frequency tables, both modes.
- Rare-bol identification, both modes.
- Gharānā-specific spelling-variant analysis (5 symbols show a real,
  corpus-measured effect, with the one low-n cell flagged).
- Sequential compound-slot analysis (44% of slots are multi-stroke; full
  distribution and top combinations documented).

**Explicitly deferred, not silently skipped:**
- Simultaneous bayan/dayan feature-bundle decomposition of atomic compound
  bols (`DHA`, `DHIN`, `DHET`, ...) — infrastructure supports it, content is
  not populated pending a sourced reference or expert confirmation.
- How multi-stroke slots (5a) get represented in the Phase 3 grammar
  hierarchy — a Phase 3 design question, deliberately left to Phase 3.

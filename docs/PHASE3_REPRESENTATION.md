# Phase 3 — Rhythmic Representation

Code: [`src/representation.py`](../src/representation.py) (hierarchy +
builder) and [`src/run_phase3_representation.py`](../src/run_phase3_representation.py)
(corpus-wide build, validation, visualizations). Reproduce with
`python3 src/run_phase3_representation.py`. Tests:
`tests/test_representation.py` (8 passing).

---

## 1. The hierarchy

```
Composition -> Avartan (cycle) -> Vibhag -> Matra (beat) -> BolSlot (subdivision/onset)
```

Implemented as plain dataclasses (`RepresentedComposition`, `Avartan`,
`Vibhag`, `Matra`, `BolSlot`) in `src/representation.py`. Each `BolSlot`
carries: `bol`, `start_time`, `duration` (inferred, see §4), position in
three forms (`slot_index_in_avartan`, `matra_index`, `subdivision_offset`),
`vibhag_index`, `is_sam`, `is_khali`.

Tāla structure is a separate, explicit `TalaDefinition` object (name,
matra count, vibhāg count, matras-per-vibhāg, which vibhāgs are khālī), kept
in a small registry (`TALA_REGISTRY`) so a new tāla is added by adding a new
`TalaDefinition` instance, not by changing the builder logic — this is the
"extensible to jhaptāl and ektāl later" requirement. **Only `TEENTAL` is
populated**, since it is the only tāla in this corpus (Phase 1: 38/38
compositions). `TEENTAL`'s numbers (16 mātrā, 4 vibhāg, khālī on the 3rd
vibhāg) are standard tāla theory, stated as such in the code's `source`
field — **not derived from the dataset's files**, which never state this
explicitly; asserting it was necessary to build any representation at all,
and it is uncontested structural fact, not a judgment call.

## 2. Why matra/vibhāg position is computed from timestamps, not token counts

This is the central design decision of Phase 3, and the reason it took
investigation before implementation.

The score notation groups each line into 4 semicolon-separated "vibhāg
-groups," and each section has a `!S:<N>` (or `!S:<N>|<M>`) header. The
natural-looking approach would be: assume each vibhāg-group's tokens map
onto its 4 mātrā in a fixed pattern derived from `N`. **This does not work in
general.** A corpus-wide diagnostic (in `run_phase3_representation.py`,
output reproduced below) shows:

| `!S:` header | Group-length pattern(s) observed |
|---|---|
| `2` | `(2,2,2,2)` — 17 lines; one truncated final line `(2,2)` |
| `3` | `(3,3,3,3)` — 8 lines |
| `4` | `(4,4,4,4)` — 141 lines |
| `6` | `(6,6,6,6)` — 28 lines |
| `8` | `(8,8,8,8)` — 40 lines |
| `3\|4` (mixed) | `(3,3,3,3)` **and** `(3,3,4,4)` |
| `4\|3` (mixed) | six different patterns, including `(3,4,3,4)` and `(4,3,3,3)` |

For a fixed (non-mixed) header, the group length is uniform across all 4
vibhāg-groups of a line — but `N` is **not always a multiple of 4** (`3` and
`6` are not), so there is no arithmetic rule for "which of the 4 mātrā does
token *k* belong to" without assuming a specific phrasing convention (e.g.
that a 6-token vibhāg splits 1+1+2+2, or 2+1+2+1, etc.). **That convention is
not stated anywhere in the dataset's files or README**, and asserting one
would be exactly the kind of invented musicological claim this project's
rules prohibit. Mixed headers (`N|M`) compound this further — group lengths
even vary *within* a single line.

**What was verified and is used instead:** the score and `onsNoMap` onset
streams match exactly, token-for-token, for all 38 compositions (Phase 1
audit §6). This means every score token has a real, measured onset
timestamp. Matra and vibhāg position are computed from those timestamps:
each avartan is divided into 16 equal-duration mātrā (tīntāl's own defining
structure — not a per-composition convention), and each onset's mātrā index
is `floor((onset_time − avartan_start) / (avartan_duration / 16))`. Vibhāg
follows directly (`matra_index // 4`). This sidesteps the token-counting
ambiguity entirely, using only (a) verified timestamps and (b) tīntāl's
uncontested structural definition.

**This is a real assumption, stated plainly, not hidden:** it assumes mātrā
are isochronous (equal duration) within an avartan. The Phase 1 audit (§9)
already found this holds within 15% for 25/38 compositions when checking
whole-avartan durations, and does *not* hold as tightly for compositions
with likely deliberate tempo variation (relā, chakradār, tihāī-heavy
material). For those compositions, mātrā-position labels from this method
are an **approximation of metrical position, not a precise measurement** —
this should be stated in any later phase that relies on exact mātrā-level
timing for those pieces, not glossed over.

The score's own vibhāg-groups are still used for one thing: locating
**avartan (line) boundaries** — reusing the exact method the Phase 1 audit
validated (§9: 25/38 compositions show consistent cycle durations under this
segmentation). Their count (4 per line) was also cross-checked: **all but 1
of 220 lines in the corpus have exactly 4 vibhāg-groups**, matching tīntāl's
4 vibhāgs — the one exception (`pjb_77`, "Joda" section, final line, 2
groups) is a truncated final phrase, not a data error.

## 3. Build results

- **38/38 compositions** successfully built into the full hierarchy.
- **351 avartans** total across the corpus.
- **Zero invariant violations** across every onset slot in every
  composition: mātrā index always in `[0,16)`, vibhāg index always in
  `[0,4)`, `is_sam` flag always exactly `(matra_index == 0)`, `is_khali`
  flag always exactly `(vibhag_index == 2)`.
- **No onset data lost**: slot count equals onset count for all 38
  compositions (verified as a regression test, not just a one-off check).

See `visualizations/phase3_subdivision_offset_hist.png` (onsets cluster
strongly at the on-beat position, with a secondary cluster near the
half-mātrā point — consistent with tabla phrasing being dominantly on full-
and half-mātrā subdivisions, a sanity check the timestamp-based method
passes rather than assumes), `phase3_matra_position_hist.png` (roughly even
coverage across all 16 mātrā, sam elevated as expected), and
`phase3_vibhag_onset_counts.png`.

## 4. Duration and the last-avartan/last-slot problem

Per the Phase 1 audit (§8), there is no explicit duration field anywhere in
the source data. Duration is inferred as the gap to the next onset:

- For all but the last slot of an avartan: `duration = next_onset_time − this_onset_time`.
- For the last slot of a **non-final** avartan: `duration = next_avartan_start_time − this_onset_time`.
- For the last slot of a composition's **final** avartan: there is no
  following onset at all. `Avartan.end_time_is_extrapolated = True` marks
  this case (one per composition, 38 total); the avartan's end time is
  extrapolated from that avartan's own mean inter-onset gap, and the very
  last slot's `duration` is left as `None` rather than guessed a second time
  on top of an already-extrapolated boundary. Code calling this
  representation must handle `duration is None` explicitly, not assume a
  value.

## 5. What Phase 3 does not attempt (forwarded, not silently dropped)

- **Rests** are not reconstructed into the time-based hierarchy. They exist
  in the score text (1,117 occurrences, Phase 1 §8) but have no onset
  timestamp, so their exact timing is not directly measurable the way real
  onsets are; representing them would require interpolating a time from
  neighboring real onsets, which is a modeling choice for whichever later
  phase needs it (attribute grammar, Phase 7), not decided here.
- **Compound slots** (score comma-joined tokens like `TI,RA`) are handled
  correctly as separate, sequential `BolSlot`s (each gets its own real onset
  timestamp and matra position) — no special-casing was needed, since the
  score/onset alignment already treats each sub-bol as its own token.
- **Simultaneous bayan/dayan feature-bundle decomposition** of atomic
  compound bols (`DHA = GE + NA`-style) remains deferred to Phase 4+, per
  your decision after the Phase 2 report.
- **Jhaptāl/ektāl**: the `TalaDefinition`/`TALA_REGISTRY` architecture
  supports adding them (a new instance, no logic change), but no numbers are
  populated — there is no jhaptāl/ektāl data in this corpus to verify
  against, and inventing the structural constants without that check would
  repeat the mistake Phase 3 was designed to avoid for tīntāl itself.

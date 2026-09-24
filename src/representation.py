"""
Phase 3 — rhythmic representation hierarchy.

    Composition -> Avartan (cycle) -> Vibhag -> Matra (beat) -> BolSlot (subdivision)

Design note on HOW matra/vibhag boundaries are assigned (read before changing
this file): the score notation's "!S:<N>" header and its semicolon-separated
vibhag-groups do NOT, by themselves, tell you how N tokens in a vibhag-group
map onto that vibhag's 4 matras. Diagnostic across the whole corpus
(see docs/PHASE3_REPRESENTATION.md §2) shows N is uniform per line when
jati is fixed (e.g. every !S:4 line has exactly 4 tokens in every one of its
4 vibhag-groups) but is NOT a multiple of 4 for several jatis actually
present (!S:3, !S:6, mixed !S:4|3), so there is no single arithmetic rule
for "which matra does token k of this group belong to" without assuming a
specific phrasing convention that is not stated in the dataset's files or
README. Guessing one would be exactly the kind of invented musicological
claim this project's rules prohibit.

Instead, matra and vibhag are assigned from the VERIFIED ONSET TIMESTAMPS
(Phase 1: score and onset streams match exactly, 38/38 compositions) plus
one foundational, uncontested structural fact about tintal — 16 matras of
equal nominal duration per avartan, grouped 4+4+4+4 into vibhags — not from
parsing token positions. This is a real assumption (isochronous matras
within an avartan) and is stated as such, not hidden; see the Limitations
section of docs/PHASE3_REPRESENTATION.md for where it is known to be
imprecise (compositions with deliberate tempo variation, already flagged in
the Phase 1 audit §9).

The score's own vibhag-groups (semicolon-separated) are still used for one
thing: locating avartan (line) boundaries, and are cross-checked to number
exactly 4 per line across the corpus (see the diagnostic script output) —
that count matches tintal's 4 vibhags and is corroborating evidence for the
avartan segmentation, not a source of matra-level timing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mts_loader import Composition as RawComposition, flatten_score_bols


@dataclass
class TalaDefinition:
    name: str
    n_matras: int
    n_vibhags: int
    matras_per_vibhag: int
    khali_vibhags: tuple[int, ...]  # 0-indexed vibhag indices that are khali (silent/wave)
    source: str  # where this structural definition comes from — never "the dataset"

    def __post_init__(self):
        assert self.n_vibhags * self.matras_per_vibhag == self.n_matras, (
            f"{self.name}: {self.n_vibhags} vibhags x {self.matras_per_vibhag} "
            f"matras/vibhag != {self.n_matras} matras"
        )


# Only TEENTAL is populated with real numbers: it is the only tala present in
# this corpus (Phase 1 audit: 38/38 compositions tagged TALA:TEENTAL), and its
# 16-matra / 4-vibhag / khali-on-3rd-vibhag structure is standard, widely
# documented tala theory (not a contested judgment call, and not derived from
# this dataset's files). JHAPTAL and EKTAL are deliberately left UNPOPULATED
# here, per the proposal's "make extensible, don't implement yet" instruction
# for other talas — adding one later means adding a TalaDefinition instance,
# not changing this module's logic.
TEENTAL = TalaDefinition(
    name="TEENTAL",
    n_matras=16,
    n_vibhags=4,
    matras_per_vibhag=4,
    khali_vibhags=(2,),  # 3rd vibhag (0-indexed 2) is khali in standard tintal theka
    source="standard tintal theory (not derived from the MTS dataset files)",
)

TALA_REGISTRY: dict[str, TalaDefinition] = {"TEENTAL": TEENTAL}


@dataclass
class BolSlot:
    """One onset event, located in the metrical grid."""
    bol: str
    start_time: float
    duration: float | None      # inferred from inter-onset interval; None if unknown (see builder)
    slot_index_in_avartan: int  # 0-based position among this avartan's onset events
    matra_index: int            # 0-based, within [0, n_matras)
    subdivision_offset: float   # fractional position within the matra, in [0, 1)
    vibhag_index: int           # 0-based, within [0, n_vibhags)
    is_sam: bool                # matra_index == 0
    is_khali: bool              # vibhag_index in tala.khali_vibhags


@dataclass
class Vibhag:
    index: int
    is_khali: bool
    matras: list["Matra"] = field(default_factory=list)


@dataclass
class Matra:
    index: int
    is_sam: bool
    slots: list[BolSlot] = field(default_factory=list)


@dataclass
class Avartan:
    index: int
    start_time: float
    end_time: float
    duration: float
    end_time_is_extrapolated: bool  # True for a composition's final avartan (see builder)
    vibhags: list[Vibhag] = field(default_factory=list)

    def all_slots(self) -> list[BolSlot]:
        return [s for v in self.vibhags for m in v.matras for s in m.slots]


@dataclass
class RepresentedComposition:
    name: str
    gharana: str | None
    tala: str | None
    avartans: list[Avartan] = field(default_factory=list)

    def all_slots(self) -> list[BolSlot]:
        return [s for a in self.avartans for s in a.all_slots()]


def _avartan_boundaries(comp: RawComposition) -> list[tuple[int, int]]:
    """Return (start_onset_index, n_onsets) per avartan, using score line
    boundaries against the onsNoMap onset stream — the same method verified
    in the Phase 1 audit (score/onset exact match, 38/38 compositions)."""
    bounds = []
    idx = 0
    for sec in comp.sections:
        for line in sec.lines:
            n_tokens = 0
            for group in line:
                for slot in group:
                    for sub in slot:
                        if sub.strip() != "-" and sub.strip():
                            n_tokens += 1
            if n_tokens == 0:
                continue
            bounds.append((idx, n_tokens))
            idx += n_tokens
    return bounds


def build_representation(comp: RawComposition, tala: TalaDefinition = TEENTAL) -> RepresentedComposition:
    """Build the full Composition->Avartan->Vibhag->Matra->BolSlot hierarchy
    for one composition, using its onsNoMap onset stream (raw vocabulary;
    callers wanting the normalized vocabulary should re-label BolSlot.bol
    afterwards via bol_normalization.BolNormalizer, not re-run this builder).
    """
    onset_times = [e.time for e in comp.onsets_unmapped]
    onset_bols = [e.bol for e in comp.onsets_unmapped]
    score_flat = flatten_score_bols(comp.sections, drop_rests=True)
    if score_flat != onset_bols:
        raise ValueError(
            f"{comp.name}: score/onset sequences do not match exactly — "
            f"refusing to build a representation on unverified alignment "
            f"(see Phase 1 audit §6 for the corpus-wide check this assumes)."
        )

    bounds = _avartan_boundaries(comp)
    avartans: list[Avartan] = []

    for a_idx, (start_idx, n_onsets) in enumerate(bounds):
        end_idx = start_idx + n_onsets
        a_start = onset_times[start_idx]
        is_last = a_idx == len(bounds) - 1
        if not is_last:
            next_start_idx = bounds[a_idx + 1][0]
            a_end = onset_times[next_start_idx]
            end_extrapolated = False
        else:
            # No following avartan to bound the end: extrapolate using this
            # avartan's own mean inter-onset interval, scaled to a full cycle.
            # This is an approximation, not a measurement — see docs.
            span = onset_times[end_idx - 1] - a_start
            mean_gap = span / max(n_onsets - 1, 1)
            a_end = onset_times[end_idx - 1] + mean_gap
            end_extrapolated = True

        a_duration = a_end - a_start
        matra_duration = a_duration / tala.n_matras if a_duration > 0 else None

        vibhags = [Vibhag(index=v, is_khali=(v in tala.khali_vibhags),
                           matras=[Matra(index=m, is_sam=(v * tala.matras_per_vibhag + m == 0))
                                   for m in range(tala.matras_per_vibhag)])
                   for v in range(tala.n_vibhags)]

        for slot_pos, onset_i in enumerate(range(start_idx, end_idx)):
            t = onset_times[onset_i]
            bol = onset_bols[onset_i]
            if matra_duration and matra_duration > 0:
                raw_matra = (t - a_start) / matra_duration
                matra_index = min(int(raw_matra), tala.n_matras - 1)
                subdivision_offset = raw_matra - int(raw_matra) if raw_matra < tala.n_matras else 0.0
            else:
                matra_index = 0
                subdivision_offset = 0.0
            vibhag_index = matra_index // tala.matras_per_vibhag
            duration = None
            if onset_i + 1 < end_idx:
                duration = onset_times[onset_i + 1] - t
            elif not is_last:
                duration = a_end - t
            # last slot of the last avartan: duration stays None (unknowable
            # without extrapolation beyond what's already an extrapolated
            # avartan end) — left explicit rather than guessed twice over.

            slot = BolSlot(
                bol=bol, start_time=t, duration=duration,
                slot_index_in_avartan=slot_pos,
                matra_index=matra_index, subdivision_offset=subdivision_offset,
                vibhag_index=vibhag_index,
                is_sam=(matra_index == 0),
                is_khali=(vibhag_index in tala.khali_vibhags),
            )
            local_matra = matra_index % tala.matras_per_vibhag
            vibhags[vibhag_index].matras[local_matra].slots.append(slot)

        avartans.append(Avartan(index=a_idx, start_time=a_start, end_time=a_end,
                                 duration=a_duration, end_time_is_extrapolated=end_extrapolated,
                                 vibhags=vibhags))

    return RepresentedComposition(name=comp.name, gharana=comp.gharana, tala=comp.tala, avartans=avartans)

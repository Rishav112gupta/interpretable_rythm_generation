"""
Phase 2 — configurable bol normalization.

Per the Phase 1 audit finding (docs/PHASE1_DATASET_AUDIT.md §5): the MTS
dataset ships its own authoritative, methodologically-documented raw-to-mapped
syllable table (syllableMapping.pdf, built by tabla/mridangam students from
timbral similarity), and the onsMap/onsNoMap onset files already implement it.
Phase 2 therefore does NOT invent a new normalization scheme — it exposes the
dataset's own mapping as an explicit, swappable, two-mode configuration, so
every later phase can be run under both modes and compared, per the proposal's
"document it; report results under both" instruction (proposal §4).

Two modes, matching the proposal's "mode A / mode B" language exactly:
    Mode.NORMALIZED  ("mode A")  -> the 18-symbol mapped vocabulary (onsMap)
    Mode.DISTINCT     ("mode B")  -> the raw ~40-symbol vocabulary (onsNoMap)

Nothing here merges variants "without evidence": the merge table IS the
evidence (syllableMapping.pdf), sourced from the dataset itself, not asserted
by this project.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path

from mts_loader import Composition, load_syllable_mapping


class BolNormalizationMode(Enum):
    NORMALIZED = "normalized"  # mode A: 18-symbol mapped vocabulary
    DISTINCT = "distinct"      # mode B: raw ~40-symbol vocabulary


class BolNormalizer:
    """Wraps the dataset's own syllableMapping table as a raw->mapped lookup.

    This is the ONLY normalization table used anywhere in this project for
    the MTS corpus — it is not re-derived or overridden, so results under
    Mode.NORMALIZED are always traceable back to syllableMapping.pdf.
    """

    def __init__(self, mapping_txt_path: Path):
        self.mapped_to_raw: dict[str, list[str]] = load_syllable_mapping(mapping_txt_path)
        self.raw_to_mapped: dict[str, str] = {}
        for mapped_symbol, raw_variants in self.mapped_to_raw.items():
            for raw in raw_variants:
                self.raw_to_mapped[raw] = mapped_symbol
            # a mapped symbol always normalizes to itself too (e.g. "DHA" -> "DHA")
            self.raw_to_mapped.setdefault(mapped_symbol, mapped_symbol)

    def normalize(self, raw_bol: str) -> str:
        """Map a raw bol to its mapped (18-symbol) form.

        Raises KeyError for any bol not covered by syllableMapping.pdf, rather
        than silently passing it through — an uncovered symbol is a data
        question to surface, not something to guess about.
        """
        return self.raw_to_mapped[raw_bol]

    def apply(self, bols: list[str], mode: BolNormalizationMode) -> list[str]:
        if mode is BolNormalizationMode.DISTINCT:
            return list(bols)
        return [self.normalize(b) for b in bols]


def onset_bols(comp: Composition, mode: BolNormalizationMode) -> list[str]:
    """Return a composition's onset bol sequence under the requested mode.

    Composition already carries BOTH pre-computed streams (from onsMap and
    onsNoMap respectively), so for the corpus's own compositions this is a
    direct lookup, not a recomputation — kept as a thin wrapper so calling
    code can request either mode uniformly, including for bols that did not
    come from the corpus (e.g. future hand-encoded compositions, proposal
    §6.3), where BolNormalizer.apply() would be used directly instead.
    """
    if mode is BolNormalizationMode.NORMALIZED:
        return [e.bol for e in comp.onsets_mapped]
    return [e.bol for e in comp.onsets_unmapped]

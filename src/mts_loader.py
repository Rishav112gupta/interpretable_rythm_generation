"""
Loaders for the Mulgaonkar Tabla Solo (MTS) dataset.

This module is deliberately small and literal: it parses the dataset's own
file formats (score .txt files, onset .csv files) exactly as the dataset's
own README describes them, without assuming anything the README/files do
not actually state. See docs/PHASE1_DATASET_AUDIT.md for what was verified
and what was not.

Directory layout expected (matches the dataset's own README_dataset.txt):
    <root>/filelist.txt
    <root>/onsMap/<name>.csv      onsets WITH the 41->18 syllable mapping applied
    <root>/onsNoMap/<name>.csv    onsets WITHOUT mapping (raw ~41-syllable space)
    <root>/score/<name>.txt       hand-authored score with metadata + section labels
    <root>/wav/<name>.wav         audio (not used by anything in this module)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OnsetEvent:
    time: float
    bol: str


@dataclass
class ScoreSection:
    name: str | None          # e.g. "Quayda", "Dohra", or None if the score has no named sections
    subdivisions: str         # raw value of the "!S:" header, e.g. "6" or "4|3"
    lines: list[list[list[str]]]  # lines -> vibhag-groups (split on ';') -> slot-tokens (split on whitespace)
                                    # each slot-token is itself a list of sub-bols (split on ',')


@dataclass
class Composition:
    name: str                 # filename stem, e.g. "ajr_9", "dli_1"
    gharana: str | None
    composition_id: str | None
    jati: str | None
    comp_type: str | None
    tala: str | None
    composer: str | None
    sections: list[ScoreSection] = field(default_factory=list)
    onsets_mapped: list[OnsetEvent] = field(default_factory=list)
    onsets_unmapped: list[OnsetEvent] = field(default_factory=list)


def load_filelist(root: Path) -> list[str]:
    names = []
    with open(root / "filelist.txt") as f:
        for line in f:
            line = line.strip()
            if line:
                names.append(line)
    return names


def load_syllable_mapping(txt_path: Path) -> dict[str, list[str]]:
    """Parse the pdftotext dump of syllableMapping.pdf into {mapped_symbol: [raw_variants]}."""
    mapping = {}
    with open(txt_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("The table") or line.startswith("row each") or line.startswith("each"):
                continue
            parts = re.split(r"\s{2,}", line)
            if len(parts) == 2 and parts[0].strip() != "Symbol":
                symbol, variants = parts
                variant_list = [v.strip() for v in variants.split(",")]
                mapping[symbol.strip()] = variant_list
    return mapping


def load_onsets(csv_path: Path) -> list[OnsetEvent]:
    events = []
    with open(csv_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            time_str, bol = line.split(",", 1)
            events.append(OnsetEvent(time=float(time_str), bol=bol.strip()))
    return events


_HEADER_FIELD_RE = re.compile(r"^([A-Z]+):(.*)$")


def parse_score(txt_path: Path) -> tuple[dict, list[ScoreSection]]:
    """Parse a score .txt file: metadata block + one or more sections."""
    with open(txt_path) as f:
        raw_lines = [l.rstrip("\n") for l in f]

    # --- metadata block: between the two '##' lines ---
    meta: dict[str, str] = {}
    i = 0
    while i < len(raw_lines) and raw_lines[i].strip() != "##":
        i += 1
    i += 1
    while i < len(raw_lines) and raw_lines[i].strip() != "##":
        m = _HEADER_FIELD_RE.match(raw_lines[i].strip())
        if m:
            meta[m.group(1)] = m.group(2).strip()
        i += 1
    i += 1  # skip closing '##'

    # --- sections: optional ''Name'' line, then !S:<spec>, then bol lines, then !E ---
    sections: list[ScoreSection] = []
    current_name = None
    while i < len(raw_lines):
        line = raw_lines[i].strip()
        if not line:
            i += 1
            continue
        name_match = re.match(r"^''(.+)''$", line)
        if name_match:
            current_name = name_match.group(1)
            i += 1
            continue
        s_match = re.match(r"^!S:(.+)$", line)
        if s_match:
            subdivisions = s_match.group(1)
            i += 1
            body_lines: list[list[list[str]]] = []
            while i < len(raw_lines) and raw_lines[i].strip() != "!E":
                body_line = raw_lines[i].strip()
                if body_line:
                    groups = [g.strip() for g in body_line.split(";") if g.strip()]
                    parsed_groups = []
                    for g in groups:
                        tokens = g.split()
                        parsed_groups.append([t.split(",") for t in tokens])
                    body_lines.append(parsed_groups)
                i += 1
            sections.append(ScoreSection(name=current_name, subdivisions=subdivisions, lines=body_lines))
            current_name = None
            i += 1  # skip '!E'
            continue
        i += 1

    return meta, sections


def flatten_score_bols(sections: list[ScoreSection], drop_rests: bool = True) -> list[str]:
    """Flatten all sections' bols into a single ordered list of individual bol tokens."""
    out = []
    for sec in sections:
        for line in sec.lines:
            for group in line:
                for slot in group:
                    for sub in slot:
                        sub = sub.strip()
                        if sub == "-":
                            if not drop_rests:
                                out.append("-")
                            continue
                        if sub:
                            out.append(sub)
    return out


def load_composition(root: Path, name: str) -> Composition:
    meta, sections = parse_score(root / "score" / f"{name}.txt")
    onsets_mapped = load_onsets(root / "onsMap" / f"{name}.csv")
    onsets_unmapped = load_onsets(root / "onsNoMap" / f"{name}.csv")
    return Composition(
        name=name,
        gharana=meta.get("GHARANA"),
        composition_id=meta.get("COMPOSITION"),
        jati=meta.get("JATI"),
        comp_type=meta.get("TYPE"),
        tala=meta.get("TALA"),
        composer=meta.get("COMPOSER"),
        sections=sections,
        onsets_mapped=onsets_mapped,
        onsets_unmapped=onsets_unmapped,
    )


def load_all_compositions(root: Path) -> list[Composition]:
    return [load_composition(root, name) for name in load_filelist(root)]

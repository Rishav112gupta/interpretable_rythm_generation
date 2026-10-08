"""
Phase 4 - seed treebank: data structure, a section-label-based tree builder,
and an algorithmic tihai (tihāī) candidate detector.

SCOPE, stated up front: the proposal's non-terminal vocabulary (mukh, dohrā,
adhā-dohrā, viśrām, adhā-viśrām, palṭā, tihāī) is explicitly framed as the
"Delhi bāj kāydā expansion order" - i.e. it describes the internal structure
of KĀYDĀ-type compositions specifically, not every form in the corpus. Per
the Phase 1 audit, exactly 10 compositions are tagged TYPE:QUAYDA or
QUAYDA-ANG-GAT - matching the proposal's "hand-parse ~10 compositions"
instruction. This module scopes the seed treebank to those 10.

WHAT THIS MODULE DOES NOT DO, stated up front: it does not assign mukh,
viśrām, adhā-viśrām, or palṭā labels to any phrase. Doing so would require
real tabla pedagogical judgment this project has no reliable, sourced basis
for (see docs/PHASE4_SEED_TREEBANK.md for the open question this raises).
What it does instead, and only this:
  1. Uses the score's own section labels (Quayda/Dohra/Adha Dohra - real,
     human-assigned, already verified as "weak supervision, not ground
     truth" in the Phase 1/2 audit record) as the top level of each tree.
  2. Detects tihāī CANDIDATES algorithmically: a tihāī is not a judgment
     call, it is a checkable arithmetic/repetition pattern (a phrase
     repeated exactly 3 times, separated by two equal-length gaps). This
     module searches for that pattern directly in the verified bol
     sequence and timing data - it does not guess at musical meaning.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mts_loader import Composition as RawComposition
from representation import RepresentedComposition, Avartan, build_representation, TEENTAL


@dataclass
class TreeNode:
    """A node in a derivation tree.

    Terminal nodes (bol == a real bol) are leaves and carry no children.
    Non-terminal nodes carry `rule` (e.g. "Composition -> Quayda Dohra")
    and children; their start_time/duration/matra/vibhag are SYNTHESIZED
    (computed) from their children, not stored independently - exactly the
    "attributes carried upward" mechanism the proposal's attribute grammar
    (§5.3) describes, scoped here to position/duration only (Phase 7 will
    extend this for tihai arithmetic verification).
    """
    label: str
    children: list["TreeNode"] = field(default_factory=list)
    rule: str | None = None
    bol: str | None = None
    start_time: float | None = None
    duration: float | None = None
    matra_index: int | None = None
    vibhag_index: int | None = None
    source: str = ""  # provenance: how this node was decided, never left implicit

    def is_leaf(self) -> bool:
        return not self.children

    def leaves(self) -> list["TreeNode"]:
        if self.is_leaf():
            return [self]
        out = []
        for c in self.children:
            out.extend(c.leaves())
        return out

    def bol_sequence(self) -> list[str]:
        return [leaf.bol for leaf in self.leaves()]

    def compute_synthesized_attributes(self) -> None:
        """Fill in start_time/duration/matra/vibhag for non-terminal nodes
        from their children, bottom-up. Leaves must already have these set.
        """
        if self.is_leaf():
            return
        for c in self.children:
            c.compute_synthesized_attributes()
        first_leaf = self.children[0].leaves()[0]
        last_leaf = self.children[-1].leaves()[-1]
        self.start_time = first_leaf.start_time
        self.matra_index = first_leaf.matra_index
        self.vibhag_index = first_leaf.vibhag_index
        if last_leaf.start_time is not None and last_leaf.duration is not None \
                and self.start_time is not None:
            self.duration = (last_leaf.start_time + last_leaf.duration) - self.start_time

    def to_dict(self) -> dict:
        d = {"label": self.label, "source": self.source}
        if self.rule:
            d["rule"] = self.rule
        if self.is_leaf():
            d["bol"] = self.bol
            d["start_time"] = self.start_time
            d["duration"] = self.duration
            d["matra_index"] = self.matra_index
            d["vibhag_index"] = self.vibhag_index
        else:
            d["start_time"] = self.start_time
            d["duration"] = self.duration
            d["children"] = [c.to_dict() for c in self.children]
        return d


def _leaf_from_slot(slot) -> TreeNode:
    return TreeNode(
        label=slot.bol, bol=slot.bol,
        start_time=slot.start_time, duration=slot.duration,
        matra_index=slot.matra_index, vibhag_index=slot.vibhag_index,
        source="terminal",
    )


def build_avartan_node(avartan: Avartan, index: int) -> TreeNode:
    """An avartan becomes a non-terminal wrapping its flat bol sequence.
    No finer internal structure (mukh/palta/etc.) is claimed - see module
    docstring."""
    leaves = [_leaf_from_slot(s) for s in avartan.all_slots()]
    node = TreeNode(
        label="Avartan", rule=f"Avartan -> {' '.join(l.bol for l in leaves)}",
        children=leaves, source="avartan_boundary (Phase 3, score-line-verified)",
    )
    node.compute_synthesized_attributes()
    return node


# Section labels that match the proposal's documented kayda-expansion
# non-terminal names exactly (case-insensitive). Anything else keeps its
# own literal label rather than being force-mapped onto a non-terminal it
# was never verified to mean.
_CANONICAL_SECTION_MAP = {
    "dohra": "Dohra",
    "adha dohra": "AdhaDohra",
}


def build_section_tree(comp: RawComposition, rep: RepresentedComposition) -> TreeNode:
    """Build a top-level tree from the score's own section labels.

    Each score section (e.g. "Quayda", "Dohra", "Adha Dohra") becomes one
    child of the Composition root; each avartan within that section becomes
    a child Avartan node. Sections with no label get a generic "Section"
    non-terminal rather than a guessed name.
    """
    avartan_idx = 0
    section_children = []
    for sec in comp.sections:
        n_avartans_in_section = sum(1 for line in sec.lines if line)
        section_avartans = []
        for _ in range(n_avartans_in_section):
            if avartan_idx >= len(rep.avartans):
                break
            section_avartans.append(build_avartan_node(rep.avartans[avartan_idx], avartan_idx))
            avartan_idx += 1
        if not section_avartans:
            continue
        raw_name = (sec.name or "").strip().lower()
        label = _CANONICAL_SECTION_MAP.get(raw_name, sec.name or "Section")
        source = ("score_section_label (matches proposal's documented term exactly)"
                   if raw_name in _CANONICAL_SECTION_MAP
                   else "score_section_label (descriptive catalog label, not one of the "
                        "proposal's 7 kayda-expansion non-terminals)")
        node = TreeNode(
            label=label,
            rule=f"{label} -> " + " ".join(f"Avartan{i}" for i in range(len(section_avartans))),
            children=section_avartans,
            source=source,
        )
        node.compute_synthesized_attributes()
        section_children.append(node)

    root = TreeNode(
        label="Composition",
        rule="Composition -> " + " ".join(c.label for c in section_children),
        children=section_children,
        source="score_structure",
    )
    root.compute_synthesized_attributes()
    return root


@dataclass
class TihaiCandidate:
    composition: str
    phrase: list[str]
    gap: list[str]
    start_slot_index: int   # index into the composition's flat onset sequence
    end_slot_index: int
    phrase_len: int
    gap_len: int
    lands_near_sam: bool
    sam_distance_matras: float | None


def find_tihai_candidates(
    bols: list[str],
    rep: RepresentedComposition,
    min_phrase_len: int = 2,
    max_phrase_len: int = 12,
    max_gap_len: int = 8,
) -> list[TihaiCandidate]:
    """Search a flat bol sequence for the tihai pattern: phrase, gap, phrase
    (same gap length), phrase - three exact repeats of a phrase separated by
    two equal-length gaps. This is a literal pattern search against the
    proposal's own formal definition (§5.3), not a musical judgment call.

    Only maximal, non-overlapping matches are kept (the longest phrase found
    at each starting position), to avoid flooding the result with every
    short sub-repeat of a longer real tihai.
    """
    n = len(bols)
    all_slots = [s for a in rep.avartans for s in a.all_slots()]
    matches: list[TihaiCandidate] = []
    claimed = [False] * n

    # search longest phrases first so a real long tihai is found before its
    # shorter internal sub-repeats would be
    for phrase_len in range(max_phrase_len, min_phrase_len - 1, -1):
        for start in range(0, n - 3 * phrase_len):
            if any(claimed[start:start + phrase_len]):
                continue
            phrase = bols[start:start + phrase_len]
            for gap_len in range(0, max_gap_len + 1):
                p2_start = start + phrase_len + gap_len
                p2_end = p2_start + phrase_len
                p3_start = p2_end + gap_len
                p3_end = p3_start + phrase_len
                if p3_end > n:
                    continue
                if bols[p2_start:p2_end] != phrase:
                    continue
                if bols[p3_start:p3_end] != phrase:
                    continue
                gap = bols[start + phrase_len:p2_start]
                gap2 = bols[p2_end:p3_start]
                if gap2 != gap:
                    # same LENGTH gap but different CONTENT is not the proposal's
                    # Tihai(target) -> Phrase(p) Gap(g) Phrase(p) Gap(g) Phrase(p) -
                    # both gaps must be the same gap, not just the same length
                    continue
                span = list(range(start, p3_end))
                if any(claimed[i] for i in span):
                    continue
                # sam-proximity: where does the pattern end, relative to a sam (matra 0)?
                lands_near_sam = False
                sam_distance = None
                if p3_end - 1 < len(all_slots):
                    end_slot = all_slots[p3_end - 1]
                    sam_distance = float(min(
                        end_slot.matra_index, TEENTAL.n_matras - end_slot.matra_index
                    ))
                    lands_near_sam = sam_distance <= 1.0
                matches.append(TihaiCandidate(
                    composition="", phrase=phrase, gap=gap,
                    start_slot_index=start, end_slot_index=p3_end - 1,
                    phrase_len=phrase_len, gap_len=gap_len,
                    lands_near_sam=lands_near_sam, sam_distance_matras=sam_distance,
                ))
                for i in span:
                    claimed[i] = True
                break  # stop searching gap lengths once one match is claimed here
    matches.sort(key=lambda m: m.start_slot_index)
    return matches

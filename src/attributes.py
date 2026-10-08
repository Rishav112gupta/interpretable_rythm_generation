"""
Phase 7 - attribute layer: positions/durations on derivation trees, a
well-formedness check for a tintal avartan, and the tihai arithmetic check.

Units are matras. Generated trees use exact Fractions so the sam-landing
check is exact rather than "close enough"; real data uses measured float
positions from Phase 3 and needs a tolerance.

Two duration sources, kept separate on purpose:
  - real data: measured positions (Phase 3: matra_index + subdivision_offset,
    from timestamps). Phase 7 found sub-matra precision is weak (see
    docs/PHASE7_ATTRIBUTES.md), so whole-matra positions are reliable and
    fractional ones are approximate.
  - generated data: a notational convention - every matra lasts 1, and the k
    strokes written in one matra split it equally (1/k each). This is how bol
    notation is conventionally read; it is not a fitted model of real timing.

THE TIHAI FORMULA AND ITS TWO READINGS. The plan's constraint is
    3*dur(p) + 2*dur(g) + 1 = target (mod cycle_length)
with template Tihai -> Phrase Gap Phrase Gap Phrase Sam. It does not say what
`target` is measured from or what unit "+1" is. Two concrete, checkable
readings, both implemented:
  A: the LAST stroke of the third phrase is the sam stroke.
  B: the stroke immediately AFTER the third phrase is the sam stroke (the
     template's separate trailing Sam; "+1" is that sam stroke).
Phase 7 evaluates both on real data instead of picking one by assumption.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from pcfg import DerivNode, MATRA, SAM_MATRA, VIBHAG, REST_TOKEN
from representation import RepresentedComposition, TalaDefinition, TEENTAL

MATRA_LABELS = (MATRA, SAM_MATRA)
GAP_SET_FROM_PLAN = tuple(Fraction(x) for x in ("1/4", "1/2", "3/4", "1", "3/2", "2"))


# ---------------------------------------------------------------------
# Synthesized/inherited attributes on derivation trees
# ---------------------------------------------------------------------

def leaf_nodes(node: DerivNode) -> list[DerivNode]:
    if node.bol is not None:
        return [node]
    out = []
    for ch in node.children:
        out.extend(leaf_nodes(ch))
    return out


def _synthesize(node: DerivNode) -> None:
    if node.bol is not None:
        return
    for ch in node.children:
        _synthesize(ch)
    node.start = node.children[0].start
    node.dur = sum((ch.dur for ch in node.children), Fraction(0))


def annotate(node: DerivNode, start=Fraction(0)):
    """Set node.start/node.dur on every node, top-down start (inherited),
    bottom-up duration (synthesized). A Matra/SamMatra subtree lasts exactly
    1 matra, split equally among its strokes. A standalone leaf outside any
    matra (a gap rest, a fractional filler rest) must carry a preset dur.
    Returns this node's duration."""
    if node.label in MATRA_LABELS:
        leaves = leaf_nodes(node)
        k = len(leaves)
        for i, lf in enumerate(leaves):
            lf.start = start + Fraction(i, k)
            lf.dur = Fraction(1, k)
        _synthesize(node)
        return node.dur
    if node.bol is not None:
        if node.dur is None:
            raise ValueError(f"leaf {node.label}:{node.bol} outside a matra has no preset duration")
        node.start = start
        return node.dur
    t = start
    for ch in node.children:
        t += annotate(ch, t)
    node.start = start
    node.dur = t - start
    return node.dur


def timed_sequence(node: DerivNode) -> list[tuple]:
    """(token, start, dur) for every leaf, in order. Call annotate() first."""
    return [(lf.bol, lf.start, lf.dur) for lf in leaf_nodes(node)]


def matra_tops(node: DerivNode, vibhag: str | None = None, out=None) -> list[tuple]:
    """(enclosing vibhag label, matra label, node) for each top-level matra
    node, without descending into a matra's own internal chain."""
    if out is None:
        out = []
    if node.label in VIBHAG:
        vibhag = node.label
    if node.label in MATRA_LABELS:
        out.append((vibhag, node.label, node))
        return out
    for ch in node.children:
        matra_tops(ch, vibhag, out)
    return out


def is_well_formed_avartan(node: DerivNode, tala: TalaDefinition = TEENTAL) -> tuple[bool, str]:
    """Does this (annotated) derivation describe exactly one tala cycle:
    n_matras matras, grouped into vibhags in order, sam first, total
    duration n_matras? Returns (ok, reason-if-not)."""
    tops = matra_tops(node)
    if len(tops) != tala.n_matras:
        return False, f"{len(tops)} matras, expected {tala.n_matras}"
    expected_vibhags = [VIBHAG[i // tala.matras_per_vibhag] for i in range(tala.n_matras)]
    if [v for v, _, _ in tops] != expected_vibhags:
        return False, "vibhag order/grouping wrong"
    expected_labels = [SAM_MATRA] + [MATRA] * (tala.n_matras - 1)
    if [lab for _, lab, _ in tops] != expected_labels:
        return False, "sam is not exactly the first matra"
    if node.dur is not None and node.dur != tala.n_matras:
        return False, f"duration {node.dur}, expected {tala.n_matras}"
    return True, ""


# ---------------------------------------------------------------------
# Real-data positions
# ---------------------------------------------------------------------

def real_positions(rep: RepresentedComposition, tala: TalaDefinition = TEENTAL) -> list[float]:
    """Absolute metrical position (matras from the start of the composition)
    of every onset, from Phase 3's timestamp-based placement."""
    return [tala.n_matras * a.index + s.matra_index + s.subdivision_offset
            for a in rep.avartans for s in a.all_slots()]


# ---------------------------------------------------------------------
# Tihai arithmetic check
# ---------------------------------------------------------------------

def near_sam(x, tol, cycle: int = TEENTAL.n_matras) -> bool:
    if x is None:
        return False
    r = x % cycle
    return min(r, cycle - r) <= tol


@dataclass
class TihaiCheck:
    dur_p: object                 # measured: first phrase start -> first gap start
    dur_g: object                 # measured: first gap start -> second phrase start
    period_1: object              # phrase 1 start -> phrase 2 start
    period_2: object              # phrase 2 start -> phrase 3 start
    regular: bool                 # period_1 == period_2 within tol
    gap_in_plan_set: bool         # dur_g within tol of the plan's {1/4,1/2,3/4,1,3/2,2}
    lands_a: bool                 # reading A: last stroke of phrase 3 on sam
    lands_b_observed: bool        # reading B: the next stroke after phrase 3 on sam
    lands_b_formula: bool         # reading B via the formula: start + 3*dur_p + 2*dur_g on sam
    has_following_stroke: bool    # False at a composition's very end (reading B uncheckable)

    @property
    def strict_b(self) -> bool:
        return self.regular and self.lands_b_observed


def check_tihai(positions: list, start: int, phrase_len: int, gap_len: int,
                tol=0.15, tala: TalaDefinition = TEENTAL) -> TihaiCheck:
    """Check a symbolic tihai (token indices, as Phase 4's detector reports
    them) against its METRICAL positions. Pass tol=0 with exact Fraction
    positions for generated data."""
    p, g = phrase_len, gap_len
    i_g1 = start + p
    i_p2 = start + p + g
    i_p3 = start + 2 * p + 2 * g
    i_end = start + 3 * p + 2 * g          # first index after the tihai
    pos = positions
    dur_p = pos[i_g1] - pos[start]
    dur_g = pos[i_p2] - pos[i_g1]
    period_1 = pos[i_p2] - pos[start]
    period_2 = pos[i_p3] - pos[i_p2]
    after = pos[i_end] if i_end < len(pos) else None
    cycle = tala.n_matras
    return TihaiCheck(
        dur_p=dur_p, dur_g=dur_g, period_1=period_1, period_2=period_2,
        regular=abs(period_1 - period_2) <= tol,
        gap_in_plan_set=g > 0 and min(abs(dur_g - x) for x in GAP_SET_FROM_PLAN) <= tol,
        lands_a=near_sam(pos[i_end - 1], tol, cycle),
        lands_b_observed=near_sam(after, tol, cycle),
        lands_b_formula=near_sam(pos[start] + 3 * dur_p + 2 * dur_g, tol, cycle),
        has_following_stroke=after is not None,
    )


# ---------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------

def _fmt(x) -> str:
    if x is None:
        return "?"
    if isinstance(x, Fraction):
        return str(x) if x.denominator != 1 else str(x.numerator)
    return f"{x:.3f}"


def tree_to_dict(node: DerivNode) -> dict:
    d = {"label": node.label, "start": _fmt(node.start), "dur": _fmt(node.dur)}
    if node.bol is not None:
        d["token"] = node.bol
    else:
        d["children"] = [tree_to_dict(c) for c in node.children]
    return d


def render(node: DerivNode, depth: int = 0, max_depth: int = 99, collapse_matras: bool = True) -> list[str]:
    """Indented text view: label [start, end) and, for a matra, its strokes."""
    pad = "  " * depth
    end = node.start + node.dur if node.start is not None and node.dur is not None else None
    span = f"[{_fmt(node.start)}, {_fmt(end)})"
    if node.bol is not None:
        return [f"{pad}{node.label} '{node.bol}' {span}"]
    if collapse_matras and node.label in MATRA_LABELS:
        return [f"{pad}{node.label} {span}: {' '.join(lf.bol for lf in leaf_nodes(node))}"]
    lines = [f"{pad}{node.label} {span}"]
    if depth < max_depth:
        for ch in node.children:
            lines.extend(render(ch, depth + 1, max_depth, collapse_matras))
    return lines


def rule_sequence(node: DerivNode) -> list[str]:
    """Top-down, left-to-right production history (n-ary safe)."""
    if node.bol is not None:
        return [f"{node.label} -> '{node.bol}'"]
    out = [f"{node.label} -> {' '.join(c.label for c in node.children)}"]
    for c in node.children:
        out.extend(rule_sequence(c))
    return out

"""
Phase 8 - structural priors as parameter tying, evaluated on held-out data.

The grammar here is the Phase 7 attribute-constrained grammar (rests + tail
labels): the cycle skeleton (Avartan -> 4 vibhags -> 4 matras each) is fixed
by the attribute layer, so it costs no probability, and all free parameters
live in two places:
  - SHAPE: how a matra expands - empty (rest), one stroke, or more
    (and, inside the matra, whether the stroke list continues);
  - STROKE: which bol each stroke is.
A "variant" decides which positions in the cycle SHARE each of those
tables (tying) and which get their own (splitting). The positions used are
only the ones already grounded in Phase 3's TalaDefinition: sam, the khali
vibhag, and the vibhag index. Nothing here encodes a claim about which
strokes belong where - held-out likelihood decides whether a split helps.

A tied model is still a PCFG: Matra@group -> BolSlot@group ... with the
probabilities indexed by tie class. For speed it is scored as a sequence of
rule-choice "events" (one per non-deterministic rule application), which is
exactly the derivation's log-probability under constrained generation;
tests/test_tying.py checks this against pcfg.tree_log_prob.
"""
from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass

from representation import TEENTAL, RepresentedComposition

KHALI_VIBHAG = TEENTAL.khali_vibhags[0]

GROUPINGS = {
    "one":        lambda v, sam: "all",
    "sam":        lambda v, sam: "sam" if sam else "other",
    "khali":      lambda v, sam: "khali" if v == KHALI_VIBHAG else "bhari",
    "sam+khali":  lambda v, sam: "sam" if sam else ("khali" if v == KHALI_VIBHAG else "bhari"),
    "vibhag":     lambda v, sam: f"v{v}",
    "vibhag+sam": lambda v, sam: "sam" if sam else f"v{v}",
}

TOP_EVENTS = ("rest", "single", "continue")
TAIL_EVENTS = ("stop", "continue")
COMP_EVENTS = ("stop", "continue")


@dataclass(frozen=True)
class Variant:
    stroke_grouping: str = "one"
    shape_grouping: str = "sam"
    tails: bool = True

    def name(self) -> str:
        return f"strokes={self.stroke_grouping}, shapes={self.shape_grouping}" + (
            "" if self.tails else ", no tails")

    def n_groups(self, grouping: str) -> int:
        return len({GROUPINGS[grouping](v, m == 0 and v == 0)
                    for v in range(TEENTAL.n_vibhags) for m in range(TEENTAL.matras_per_vibhag)})

    def n_free_parameters(self, vocab_size: int) -> int:
        shape_g = self.n_groups(self.shape_grouping)
        stroke_g = self.n_groups(self.stroke_grouping)
        shape = shape_g * ((len(TOP_EVENTS) - 1) + ((len(TAIL_EVENTS) - 1) if self.tails else 0))
        return shape + stroke_g * (vocab_size - 1) + (len(COMP_EVENTS) - 1)


@dataclass
class MatraRecord:
    vibhag: int
    is_sam: bool
    bols: list[str]


def matra_records(rep: RepresentedComposition) -> list[MatraRecord]:
    """One record per matra of every avartan, in order (bols as in `rep`)."""
    out = []
    for a in rep.avartans:
        for v in a.vibhags:
            for m in v.matras:
                out.append(MatraRecord(vibhag=v.index, is_sam=m.is_sam, bols=[s.bol for s in m.slots]))
    return out


def events(records: list[MatraRecord], n_avartans: int, variant: Variant) -> Counter:
    """Count of (table, event) for one composition under `variant`."""
    c: Counter = Counter()
    c[(("comp",), "continue")] += n_avartans - 1
    c[(("comp",), "stop")] += 1
    shape_of = GROUPINGS[variant.shape_grouping]
    stroke_of = GROUPINGS[variant.stroke_grouping]
    for r in records:
        g = shape_of(r.vibhag, r.is_sam)
        k = stroke_of(r.vibhag, r.is_sam)
        n = len(r.bols)
        if n == 0:
            c[(("top", g), "rest")] += 1
            continue
        if variant.tails:
            c[(("top", g), "single" if n == 1 else "continue")] += 1
            for j in range(1, n):
                c[(("tail", g), "continue" if j < n - 1 else "stop")] += 1
        else:
            for j in range(n):
                c[(("top", g), "continue" if j < n - 1 else "single")] += 1
        for b in r.bols:
            c[(("stroke", k), b)] += 1
    return c


class TiedModel:
    """Probability tables fitted from event counts.

    beta=None (or 0): each group's table is estimated on its own, with
    symmetric Dirichlet(alpha) smoothing (a hard split).
    beta>0: each group's table is also shrunk toward the table pooled over
    all groups - p_g(e) = (c_g(e) + alpha + beta * p_pooled(e)) /
    (n_g + alpha*K + beta) - a soft tie, where beta is how many "virtual
    observations" the shared table is worth. beta -> infinity approaches the
    shared table, beta = 0 is exactly the hard split. (Without the alpha
    term, an event never seen in a group gets ~p_pooled/n_g, which is
    badly over-penalized for rare strokes.)
    """

    def __init__(self, counts: Counter, vocab: list[str], alpha: float, beta: float | None = None):
        self.alpha = alpha
        self.beta = beta
        self.inventory = {"comp": COMP_EVENTS, "top": TOP_EVENTS, "tail": TAIL_EVENTS, "stroke": tuple(vocab)}
        self.by_table: dict[tuple, Counter] = defaultdict(Counter)
        self.pooled: dict[str, Counter] = defaultdict(Counter)
        for (table, e), n in counts.items():
            self.by_table[table][e] += n
            self.pooled[table[0]][e] += n
        self._cache: dict[tuple, dict] = {}

    def _pooled_prob(self, kind: str) -> dict:
        inv = self.inventory[kind]
        c = self.pooled[kind]
        total = sum(c[e] for e in inv) + self.alpha * len(inv)
        return {e: (c[e] + self.alpha) / total for e in inv}

    def table(self, table: tuple) -> dict:
        if table not in self._cache:
            kind = table[0]
            inv = self.inventory[kind]
            c = self.by_table.get(table, Counter())
            n = sum(c[e] for e in inv)
            beta = 0.0 if self.beta is None or kind == "comp" else self.beta
            pool = self._pooled_prob(kind) if beta else {e: 0.0 for e in inv}
            total = n + self.alpha * len(inv) + beta
            self._cache[table] = {e: (c[e] + self.alpha + beta * pool[e]) / total for e in inv}
        return self._cache[table]

    def log2_prob(self, counts: Counter) -> float:
        total = 0.0
        for (table, e), n in counts.items():
            p = self.table(table).get(e, 0.0)
            if p <= 0:
                return float("-inf")
            total += n * math.log2(p)
        return total


def cross_validate(units: list[list[str]], comp_events: dict[str, Counter], comp_strokes: dict[str, int],
                   vocab: list[str], alpha: float, beta: float | None = None) -> dict[str, tuple]:
    """Leave-one-unit-out: for each unit (one composition, or ajr_10's two
    variants together), fit on every other unit and score the held-out one.
    Returns {composition: (bits, n_strokes)} where bits = -log2 P."""
    total = Counter()
    for comps in units:
        for c in comps:
            total.update(comp_events[c])
    out = {}
    for comps in units:
        held = Counter()
        for c in comps:
            held.update(comp_events[c])
        train = total.copy()
        train.subtract(held)
        train = +train
        model = TiedModel(train, vocab, alpha, beta)
        for c in comps:
            out[c] = (-model.log2_prob(comp_events[c]), comp_strokes[c])
    return out


def bits_per_stroke(scores: dict[str, tuple]) -> float:
    return sum(b for b, _ in scores.values()) / sum(n for _, n in scores.values())


def paired_bootstrap(a: dict[str, tuple], b: dict[str, tuple], n_boot: int = 2000,
                     seed: int = 0) -> tuple[float, float, float]:
    """(observed, low, high): difference in bits/stroke, a minus b, with a
    95% percentile interval from resampling compositions with replacement.
    Negative means `a` predicts held-out data better."""
    names = sorted(a)
    rng = random.Random(seed)

    def diff(sample):
        bits = sum(a[c][0] - b[c][0] for c in sample)
        n = sum(a[c][1] for c in sample)
        return bits / n

    observed = diff(names)
    boots = sorted(diff([rng.choice(names) for _ in names]) for _ in range(n_boot))
    return observed, boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot) - 1]

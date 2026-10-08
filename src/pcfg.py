"""
Phase 5 - the probabilistic context-free grammar (PCFG) itself.

GRAMMAR DESIGN, explained before the code: every non-terminal here is
directly traceable to a structural fact already VERIFIED in an earlier
phase - nothing is invented for this phase.

    Composition -> Avartan Composition | Avartan
        (variable-length list of cycles; Phase 1 verified avartan
        boundaries via score/onset alignment, Phase 3 built them)

    Avartan -> Vibhag0 Vibhag1 Vibhag2 Vibhag3   (right-branching chain)
        (tintal always has exactly 4 vibhags - Phase 3's TalaDefinition,
        standard tala theory, not invented here)

    Vibhag0/1/2/3 -> Matra Matra Matra Matra     (right-branching chain)
        (tintal always has exactly 4 matras per vibhag - same source)
        Vibhag0's FIRST matra uses the separate non-terminal SamMatra
        instead of Matra, because matra index 0 is "sam" - a structurally
        distinguished position Phase 3 already flags (is_sam) and that is
        standard, uncontested tala theory (the cycle's resolution point).
        Vibhag2 is similarly kept as its own non-terminal (not merged with
        Vibhag1/Vibhag3) because it is tintal's khali vibhag (Phase 3's
        TalaDefinition.khali_vibhags) - letting the grammar learn whether
        khali productions actually differ, rather than assuming they do
        or forcing them to look the same.

    SamMatra/Matra -> BolSlot SamMatra|Matra ... | BolSlot
        (variable number of strokes per matra - Phase 3 found 1 to 5
        strokes sharing a single matra; this is the Phase 2-documented
        "compound slot" phenomenon, handled here as a learned list, not a
        single fixed-arity rule)

    BolSlot -> <bol>   (one rule per terminal symbol in the vocabulary)

No mukh/dohra/adha-dohra/visram/palta/tihai non-terminals appear here -
Phase 4 explicitly did not establish those well enough to build hard
grammar rules from them (see docs/PHASE4_SEED_TREEBANK.md). This grammar
is the "vanilla" context-free skeleton; attribute-based constraints
(tihai arithmetic) are Phase 7's job, not this one - see §5.3 of the
proposal, which itself states tihai needs more than context-free power.
"""
from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from mts_loader import Composition as RawComposition
from representation import RepresentedComposition, Avartan, Matra as RepMatra, build_representation, TEENTAL
from bol_normalization import BolNormalizer, BolNormalizationMode

START = "Composition"
COMP_TAIL = "Composition"  # list recursion reuses the same symbol (A -> X A | X)
AVARTAN = "Avartan"
VIBHAG = ["Vibhag0", "Vibhag1", "Vibhag2", "Vibhag3"]
SAM_MATRA = "SamMatra"
MATRA = "Matra"
BOLSLOT = "BolSlot"
# Phase 7: an empty matra (no onset at all) is represented as Matra -> Rest,
# Rest -> "-" (the dataset score's own rest token). Opt-in only
# (include_rests=True), so Phase 5/6's reported grammar stays reproducible.
# "-" cannot distinguish silence from a sustained stroke: onset data has no
# way to tell them apart.
REST = "Rest"
REST_TOKEN = "-"
# Phase 8: with tail_labels=True a matra's list of strokes continues under a
# separate label (Matra -> BolSlot MatraTail, MatraTail -> BolSlot MatraTail |
# BolSlot). Without it, "is this matra empty / how many strokes" and "does
# this list continue" share one label and one set of probabilities, which
# Phase 7 showed distorts generation. Opt-in, like include_rests.
TAIL_SUFFIX = "Tail"
# Phase 9: with sam_strokes=True the strokes of the sam matra get their own
# stroke table (SamBolSlot) - the "strokes split by sam" tie Phase 8 selected
# on held-out data. Opt-in, like the options above.
SAM_BOLSLOT = "SamBolSlot"


@dataclass
class Rule:
    lhs: str
    rhs: tuple  # (NT, NT) for binary, (NT,) for unary-nonterminal, ("TERM", bol) for terminal
    count: int = 0
    prob: float = 0.0

    def is_terminal(self) -> bool:
        return self.rhs[0] == "TERM"

    def is_binary(self) -> bool:
        return len(self.rhs) == 2 and self.rhs[0] != "TERM"

    def is_unary_nt(self) -> bool:
        return len(self.rhs) == 1 and self.rhs[0] != "TERM"


@dataclass
class PCFG:
    rules: dict[str, list[Rule]] = field(default_factory=lambda: defaultdict(list))
    vocabulary: set[str] = field(default_factory=set)

    def add_count(self, lhs: str, rhs: tuple):
        for r in self.rules[lhs]:
            if r.rhs == rhs:
                r.count += 1
                return
        self.rules[lhs].append(Rule(lhs=lhs, rhs=rhs, count=1))

    def normalize(self, dirichlet_alpha: float = 0.0):
        """Turn counts into MLE (or MAP, if dirichlet_alpha > 0) probabilities."""
        for lhs, rule_list in self.rules.items():
            n_rules = len(rule_list)
            total = sum(r.count for r in rule_list) + dirichlet_alpha * n_rules
            for r in rule_list:
                r.prob = (r.count + dirichlet_alpha) / total if total > 0 else 0.0

    def log_prob_of_rule(self, lhs: str, rhs: tuple) -> float:
        for r in self.rules.get(lhs, []):
            if r.rhs == rhs:
                return math.log(r.prob) if r.prob > 0 else float("-inf")
        return float("-inf")

    def diagnostics(self) -> dict:
        """Checks for the degenerate-grammar problems the project plan asks
        Phase 5 to monitor for."""
        issues = []
        zero_prob_rules = 0
        for lhs, rule_list in self.rules.items():
            total_prob = sum(r.prob for r in rule_list)
            if rule_list and abs(total_prob - 1.0) > 1e-6:
                issues.append(f"{lhs}: production probabilities sum to {total_prob:.6f}, not 1.0")
            for r in rule_list:
                if r.prob == 0.0:
                    zero_prob_rules += 1
        unreachable = [lhs for lhs in self.rules if lhs != START and
                       not any(lhs in r.rhs for rules in self.rules.values() for r in rules)]
        return {
            "n_nonterminals": len(self.rules),
            "n_rules": sum(len(v) for v in self.rules.values()),
            "n_terminal_rules": sum(1 for v in self.rules.values() for r in v if r.is_terminal()),
            "probabilities_sum_to_one": len(issues) == 0,
            "issues": issues,
            "zero_prob_rules_present": zero_prob_rules,
            "non_terminals_never_used_on_a_rhs": unreachable,
        }


# ---------------------------------------------------------------------
# Supervised tree construction from Phase 3's verified representation
# ---------------------------------------------------------------------

@dataclass
class DerivNode:
    label: str
    children: list["DerivNode"] = field(default_factory=list)
    bol: str | None = None
    start: object = None  # Phase 7 synthesized attribute (matra units), set by attributes.annotate
    dur: object = None

    def rules(self) -> list[tuple]:
        """Flatten this derivation into (lhs, rhs) pairs, matching the
        grammar's rule shapes exactly."""
        out = []
        if self.bol is not None:
            out.append((self.label, ("TERM", self.bol)))
            return out
        if len(self.children) == 1:
            out.append((self.label, (self.children[0].label,)))
        elif len(self.children) == 2:
            out.append((self.label, (self.children[0].label, self.children[1].label)))
        else:
            raise ValueError(f"DerivNode {self.label} has {len(self.children)} children; expected 1 or 2")
        for c in self.children:
            out.extend(c.rules())
        return out

    def leaves(self) -> list[str]:
        if self.bol is not None:
            return [self.bol]
        out = []
        for c in self.children:
            out.extend(c.leaves())
        return out


def _bolslot_list_node(label_base: str, bols: list[str], tail_label: str | None = None,
                       slot_label: str = BOLSLOT) -> DerivNode:
    """Build a right-branching list node: X -> BolSlot X | BolSlot, or with
    tail_label T: X -> BolSlot T | BolSlot, T -> BolSlot T | BolSlot."""
    assert bols, f"{label_base} must have at least one bol"
    leaf = DerivNode(label=slot_label, bol=bols[0])
    if len(bols) == 1:
        return DerivNode(label=label_base, children=[leaf])
    next_label = tail_label or label_base
    rest = _bolslot_list_node(next_label, bols[1:], tail_label, slot_label)
    return DerivNode(label=label_base, children=[leaf, rest])


def _matra_bols(matra: RepMatra) -> list[str]:
    return [s.bol for s in matra.slots]


def build_avartan_deriv(avartan: Avartan, include_rests: bool = False,
                        tail_labels: bool = False, sam_strokes: bool = False) -> DerivNode:
    vibhag_nodes = []
    for v in avartan.vibhags:
        matra_nodes = []
        for m_idx, matra in enumerate(v.matras):
            bols = _matra_bols(matra)
            label = SAM_MATRA if (v.index == 0 and m_idx == 0) else MATRA
            if not bols:
                if include_rests:
                    matra_nodes.append(DerivNode(label=label, children=[
                        DerivNode(label=REST, bol=REST_TOKEN)]))
                continue
            slot = SAM_BOLSLOT if (sam_strokes and label == SAM_MATRA) else BOLSLOT
            matra_nodes.append(_bolslot_list_node(
                label, bols, label + TAIL_SUFFIX if tail_labels else None, slot))
        if not matra_nodes:
            continue
        # fixed-arity right-branching chain of this vibhag's matras
        node = matra_nodes[-1]
        for m in reversed(matra_nodes[:-1]):
            node = DerivNode(label=VIBHAG[v.index], children=[m, node])
        if len(matra_nodes) == 1:
            node = DerivNode(label=VIBHAG[v.index], children=[matra_nodes[0]])
        vibhag_nodes.append(node)
    if not vibhag_nodes:
        raise ValueError("avartan has no non-empty vibhags")
    node = vibhag_nodes[-1]
    for v in reversed(vibhag_nodes[:-1]):
        node = DerivNode(label=AVARTAN, children=[v, node])
    if len(vibhag_nodes) == 1:
        node = DerivNode(label=AVARTAN, children=[vibhag_nodes[0]])
    return node


def build_composition_deriv(rep: RepresentedComposition, include_rests: bool = False,
                            tail_labels: bool = False, sam_strokes: bool = False) -> DerivNode:
    avartan_nodes = [build_avartan_deriv(a, include_rests=include_rests, tail_labels=tail_labels,
                                         sam_strokes=sam_strokes)
                     for a in rep.avartans]
    node = avartan_nodes[-1]
    node = DerivNode(label=START, children=[node])
    for a in reversed(avartan_nodes[:-1]):
        node = DerivNode(label=START, children=[a, node])
    return node


def train_supervised(
    raw_comps: list[RawComposition],
    mode: BolNormalizationMode,
    normalizer: BolNormalizer,
    dirichlet_alpha: float = 0.0,
    include_rests: bool = False,
    tail_labels: bool = False,
    sam_strokes: bool = False,
) -> tuple[PCFG, list[DerivNode]]:
    grammar = PCFG()
    trees = []
    for c in raw_comps:
        rep = build_representation(c, TEENTAL)
        if mode is BolNormalizationMode.NORMALIZED:
            for a in rep.avartans:
                for s in a.all_slots():
                    s.bol = normalizer.normalize(s.bol)
        tree = build_composition_deriv(rep, include_rests=include_rests, tail_labels=tail_labels,
                                       sam_strokes=sam_strokes)
        trees.append(tree)
        for lhs, rhs in tree.rules():
            grammar.add_count(lhs, rhs)
            if rhs[0] == "TERM":
                grammar.vocabulary.add(rhs[1])
    grammar.normalize(dirichlet_alpha=dirichlet_alpha)
    return grammar, trees


def tree_log_prob(grammar: PCFG, tree: DerivNode) -> float:
    total = 0.0
    for lhs, rhs in tree.rules():
        total += grammar.log_prob_of_rule(lhs, rhs)
    return total


# ---------------------------------------------------------------------
# Top-down sampling (generation)
# ---------------------------------------------------------------------

def sample_tree(grammar: PCFG, start: str = START, rng: random.Random | None = None,
                 max_depth: int = 500, _depth: int = 0) -> DerivNode | None:
    rng = rng or random.Random()
    if _depth > max_depth:
        return None
    rule_list = grammar.rules.get(start, [])
    if not rule_list:
        return None
    weights = [r.prob for r in rule_list]
    if sum(weights) <= 0:
        return None
    chosen = rng.choices(rule_list, weights=weights, k=1)[0]
    if chosen.is_terminal():
        return DerivNode(label=start, bol=chosen.rhs[1])
    children = []
    for sym in chosen.rhs:
        child = sample_tree(grammar, sym, rng, max_depth, _depth + 1)
        if child is None:
            return None
        children.append(child)
    return DerivNode(label=start, children=children)


# ---------------------------------------------------------------------
# CYK / Inside algorithm: total probability of an arbitrary bol sequence
# under the grammar, in log-space (needed to score sequences whose
# structure is NOT known in advance - e.g. generated sequences, or any
# future held-out evaluation in Phase 11 that doesn't carry Phase 3-style
# timing information).
# ---------------------------------------------------------------------

_NEG_INF = float("-inf")


def _logsumexp(values: list[float]) -> float:
    finite = [v for v in values if v != _NEG_INF]
    if not finite:
        return _NEG_INF
    m = max(finite)
    return m + math.log(sum(math.exp(v - m) for v in finite))


def _unary_closure(grammar: PCFG) -> dict[str, list[tuple]]:
    """Precompute, for each RHS non-terminal, which LHS symbols can reach it
    via a (possibly empty) chain of unary rules, with the summed log-prob of
    that chain. Index: rhs_symbol -> [(lhs_symbol, log_prob), ...]."""
    unary_rules = [
        (r.lhs, r.rhs[0], math.log(r.prob))
        for rules in grammar.rules.values() for r in rules
        if r.is_unary_nt() and r.prob > 0
    ]
    # start with the identity (every symbol reaches itself at log-prob 0)
    reach: dict[str, dict[str, float]] = defaultdict(dict)
    for nt in grammar.rules:
        reach[nt][nt] = 0.0
    changed = True
    while changed:
        changed = False
        for lhs, rhs, lp in unary_rules:
            for target, sub_lp in list(reach[rhs].items()):
                new_lp = lp + sub_lp
                if target not in reach[lhs] or new_lp > reach[lhs][target]:
                    reach[lhs][target] = new_lp
                    changed = True
    # invert: for a given "reached" symbol, which LHS can reach it
    inverted: dict[str, list[tuple]] = defaultdict(list)
    for lhs, targets in reach.items():
        for target, lp in targets.items():
            inverted[target].append((lhs, lp))
    return inverted


def cyk_inside_log_prob(grammar: PCFG, bols: list[str], start: str = START) -> float:
    """Total log-probability of `bols` under the grammar (sum over every
    valid derivation, not just the single most likely one)."""
    n = len(bols)
    if n == 0:
        return _NEG_INF

    binary_by_rhs: dict[tuple, list[tuple]] = defaultdict(list)
    for lhs, rules in grammar.rules.items():
        for r in rules:
            if r.is_binary():
                binary_by_rhs[r.rhs].append((lhs, math.log(r.prob))) if r.prob > 0 else None

    term_log_prob: dict[str, dict[str, float]] = defaultdict(dict)
    for lhs, rules in grammar.rules.items():
        for r in rules:
            if r.is_terminal() and r.prob > 0:
                term_log_prob[lhs][r.rhs[1]] = math.log(r.prob)

    unary_closure = _unary_closure(grammar)

    # chart[i][span][symbol] = TOTAL log-prob of symbol deriving bols[i:i+span],
    # summed (log-sum-exp) over every distinct way of doing so - this is what
    # makes it an Inside algorithm rather than a Viterbi (best-parse) parser.
    # Each cell is collapsed to a single scalar per symbol as soon as it is
    # finished, so later lookups never recompute a log-sum-exp.
    accum: list[list[dict[str, list]]] = [
        [defaultdict(list) for _ in range(n + 1)] for _ in range(n)
    ]
    chart: list[list[dict[str, float]]] = [[{} for _ in range(n + 1)] for _ in range(n)]

    for i in range(n):
        for lhs, lp_map in term_log_prob.items():
            if bols[i] in lp_map:
                lp = lp_map[bols[i]]
                for target, chain_lp in unary_closure.get(lhs, [(lhs, 0.0)]):
                    accum[i][1][target].append(lp + chain_lp)
        chart[i][1] = {sym: _logsumexp(lps) for sym, lps in accum[i][1].items()}

    for span in range(2, n + 1):
        for i in range(0, n - span + 1):
            cell_accum = accum[i][span]
            for split in range(1, span):
                left = chart[i][split]
                right = chart[i + split][span - split]
                if not left or not right:
                    continue
                for (b_sym, c_sym), lhs_list in binary_by_rhs.items():
                    lp_b = left.get(b_sym, _NEG_INF)
                    lp_c = right.get(c_sym, _NEG_INF)
                    if lp_b == _NEG_INF or lp_c == _NEG_INF:
                        continue
                    base_lp = lp_b + lp_c
                    for lhs, rule_lp in lhs_list:
                        for target, chain_lp in unary_closure.get(lhs, [(lhs, 0.0)]):
                            cell_accum[target].append(base_lp + rule_lp + chain_lp)
            chart[i][span] = {sym: _logsumexp(lps) for sym, lps in cell_accum.items()}

    return chart[0][n].get(start, _NEG_INF)


# ---------------------------------------------------------------------
# Phase 6 - Inside-Outside EM.
#
# WHY this exists, given Phase 5 already trained a grammar: the project
# plan's own learning algorithm (proposal SS6 / docs/PROJECT_PLAN.md SS6)
# specifies Inside-Outside EM as the way production probabilities are
# learned, with supervised MLE on a hand-parsed subset used only to
# INITIALIZE EM "to avoid poor local optima" - EM itself was never
# actually run. Phase 5 used full supervised MLE instead, which is exact
# and valid because Phase 3's timestamps give a known derivation for
# EVERY avartan in the whole corpus - but that means the plan's own claim
# ("supervised init avoids poor local optima") was asserted, not tested.
# This phase actually runs EM - from supervised, uniform, and random
# initializations - and reports what really happens, instead of taking
# that claim on faith.
#
# SCOPE DECISION, stated explicitly: EM here is run with each AVARTAN
# (not each whole composition) as one training example. Two reasons,
# both honest trade-offs rather than a silent shortcut:
#   1. Phase 5's own CYK/Inside validation found that parsing a FLAT bol
#      sequence with no timing is highly ambiguous (the whole reason
#      cyk_inside_log_prob exists) - and that ambiguity is what EM's
#      Inside-Outside E-step would have to sum over. At the full
#      composition level (up to 611 bols) this is computationally
#      infeasible (Phase 5 extrapolated ~13+ minutes for ONE inside pass
#      on the longest composition; EM needs an inside AND an outside pass
#      per example, per iteration). At the avartan level (max 63 bols,
#      median 21, across 351 avartans) it is tractable - see the
#      benchmark in docs/PHASE6_EM.md.
#   2. The Composition -> Avartan Composition | Avartan recursion itself
#      is not ambiguous (it is a simple linear chain over already-settled
#      avartan boundaries - Phase 1/3 verified those from the score/onset
#      alignment) - so nothing interesting is lost by not re-learning it
#      via EM; the real production-probability question is entirely
#      inside the Vibhag/Matra/BolSlot layer, which this scope keeps.
# ---------------------------------------------------------------------

def _build_rule_tables(grammar: PCFG):
    """Index a grammar's positive-probability rules for fast inside/outside
    lookup: binary rules by (B, C) RHS pair, unary rules by their single RHS
    symbol (and, inverted, by LHS), terminal rules by LHS; plus a fixed
    topological order over non-terminals for the unary closures below."""
    binary_by_rhs: dict[tuple, list[tuple]] = defaultdict(list)
    unary_by_rhs: dict[str, list[tuple]] = defaultdict(list)
    unary_by_lhs: dict[str, list[tuple]] = defaultdict(list)
    term_by_lhs: dict[str, dict[str, float]] = defaultdict(dict)
    for lhs, rules in grammar.rules.items():
        for r in rules:
            if r.prob <= 0:
                continue
            lp = math.log(r.prob)
            if r.is_binary():
                binary_by_rhs[r.rhs].append((lhs, lp))
            elif r.is_unary_nt():
                unary_by_rhs[r.rhs[0]].append((lhs, lp))
                unary_by_lhs[lhs].append((r.rhs[0], lp))
            else:
                term_by_lhs[lhs][r.rhs[1]] = lp
    order = _unary_topo_order(unary_by_lhs, grammar.rules.keys())
    return binary_by_rhs, unary_by_rhs, unary_by_lhs, term_by_lhs, order


def _unary_topo_order(unary_by_lhs: dict[str, list[tuple]], all_symbols) -> list[str]:
    """A topological order over non-terminals for the unary-rule dependency
    graph (edge lhs -> target for each unary rule lhs -> target), such that
    every target appears before the lhs symbols that point to it. Computed
    ONCE per grammar (it does not depend on any particular chart cell), then
    reused for every cell's closure - this is what makes the closure a
    single linear pass per cell instead of an iterate-until-stable loop
    (an earlier version of this code used such a loop and double-counted
    contributions across passes; a plain topological pass cannot, since
    each symbol's value is written exactly once, after all its dependencies
    are already final). Assumes the unary-rule graph is acyclic, which holds
    for this grammar (Composition -> Avartan -> Vibhag -> Matra/SamMatra ->
    BolSlot is strictly depth-decreasing - see the grammar design in this
    module's docstring)."""
    order: list[str] = []
    visited: set[str] = set()

    def visit(sym: str) -> None:
        if sym in visited:
            return
        visited.add(sym)
        for target, _ in unary_by_lhs.get(sym, ()):
            visit(target)
        order.append(sym)

    for sym in all_symbols:
        visit(sym)
    return order


def _apply_unary_fixpoint(cell: dict[str, float], unary_by_lhs: dict[str, list[tuple]],
                           order: list[str]) -> None:
    """In place, extend `cell` (an inside chart cell) to include every
    symbol reachable via a chain of unary rules from a symbol already in
    `cell` - summing (log-sum-exp) every distinct chain into a symbol, not
    keeping only the best one. Processes symbols in dependency order
    (each unary rule's RHS target before its LHS), so every symbol's final
    value is computed in a single pass, with no double-counting."""
    for sym in order:
        contributions = [cell[target] + lp for target, lp in unary_by_lhs.get(sym, ())
                          if target in cell]
        if not contributions:
            continue
        if sym in cell:
            contributions.append(cell[sym])
        cell[sym] = _logsumexp(contributions)


def _apply_unary_outside_fixpoint(cell: dict[str, float], unary_by_lhs: dict[str, list[tuple]],
                                   order: list[str]) -> None:
    """The outside-direction mirror of _apply_unary_fixpoint: propagates an
    outside value from a unary rule's LHS down onto its RHS target, at the
    same (i, span) cell. Processes symbols in REVERSE dependency order
    (each unary rule's LHS before its RHS target - the opposite direction
    from the inside closure, since here a target's value depends on its
    parent's outside value, not the other way around), again in one pass."""
    for sym in reversed(order):
        if sym not in cell:
            continue
        base = cell[sym]
        for target, lp in unary_by_lhs.get(sym, ()):
            contributions = [base + lp]
            if target in cell:
                contributions.append(cell[target])
            cell[target] = _logsumexp(contributions)


def _inside_chart(grammar: PCFG, bols: list[str]):
    """Full inside chart: inside[i][span][symbol] = total log-probability of
    `symbol` deriving bols[i:i+span], via ANY rule type (terminal, unary, or
    binary), summed over every distinct way of doing so. Unlike Phase 5's
    cyk_inside_log_prob (which only needed the chart's final scalar and so
    could use a precomputed closure shortcut), this keeps the complete
    per-symbol table at every cell, which inside_outside_expected_counts
    needs to attribute probability mass to each individual rule."""
    n = len(bols)
    binary_by_rhs, unary_by_rhs, unary_by_lhs, term_by_lhs, order = _build_rule_tables(grammar)
    inside: list[list[dict[str, float]]] = [[{} for _ in range(n + 1)] for _ in range(n)]
    for i in range(n):
        cell: dict[str, float] = {}
        for lhs, bol_map in term_by_lhs.items():
            if bols[i] in bol_map:
                cell[lhs] = bol_map[bols[i]]
        _apply_unary_fixpoint(cell, unary_by_lhs, order)
        inside[i][1] = cell
    for span in range(2, n + 1):
        for i in range(0, n - span + 1):
            cell_accum: dict[str, list[float]] = defaultdict(list)
            for split in range(1, span):
                left = inside[i][split]
                right = inside[i + split][span - split]
                if not left or not right:
                    continue
                for (b_sym, c_sym), lhs_list in binary_by_rhs.items():
                    lp_b = left.get(b_sym)
                    lp_c = right.get(c_sym)
                    if lp_b is None or lp_c is None:
                        continue
                    base = lp_b + lp_c
                    for lhs, rule_lp in lhs_list:
                        cell_accum[lhs].append(base + rule_lp)
            cell = {sym: _logsumexp(lps) for sym, lps in cell_accum.items()}
            _apply_unary_fixpoint(cell, unary_by_lhs, order)
            inside[i][span] = cell
    return inside, (binary_by_rhs, unary_by_rhs, term_by_lhs, unary_by_lhs, order)


def _outside_chart(grammar: PCFG, bols: list[str], inside, rule_tables, start: str = START):
    """Full outside chart: outside[i][span][symbol] = total log-probability
    of generating everything OUTSIDE bols[i:i+span] from `start`, given that
    `symbol` is the node spanning exactly that range. Computed top-down
    (largest spans first), since a cell's outside value only depends on
    outside values of strictly larger spans that have already been finalized."""
    n = len(bols)
    binary_by_rhs, unary_by_rhs, term_by_lhs, unary_by_lhs, order = rule_tables
    binary_by_lhs: dict[str, list[tuple]] = defaultdict(list)
    for (b_sym, c_sym), lhs_list in binary_by_rhs.items():
        for lhs, lp in lhs_list:
            binary_by_lhs[lhs].append((b_sym, c_sym, lp))

    accum: list[list[dict[str, list]]] = [
        [defaultdict(list) for _ in range(n + 1)] for _ in range(n)
    ]
    outside: list[list[dict[str, float]]] = [[{} for _ in range(n + 1)] for _ in range(n)]
    if n > 0:
        accum[0][n][start].append(0.0)  # log(1): the root is "start", outside everything is certain

    for span in range(n, 0, -1):
        for i in range(0, n - span + 1):
            cell = {sym: _logsumexp(lps) for sym, lps in accum[i][span].items()}
            _apply_unary_outside_fixpoint(cell, unary_by_lhs, order)
            outside[i][span] = cell
            if span == 1 or not cell:
                continue
            for lhs, lp_val in cell.items():
                for b_sym, c_sym, rule_lp in binary_by_lhs.get(lhs, []):
                    for split in range(1, span):
                        left_span, right_span = split, span - split
                        in_left = inside[i][left_span].get(b_sym)
                        in_right = inside[i + left_span][right_span].get(c_sym)
                        if in_left is None or in_right is None:
                            continue
                        accum[i][left_span][b_sym].append(lp_val + rule_lp + in_right)
                        accum[i + left_span][right_span][c_sym].append(lp_val + rule_lp + in_left)
    return outside


def _expected_counts(bols: list[str], inside, outside, rule_tables, log_z: float) -> dict[tuple, float]:
    """The standard Inside-Outside expected-count formulas: for every rule,
    sum outside(parent) * P(rule) * inside(children) over every (position,
    span) it could apply to, normalized by the example's total probability
    (log_z). This is exactly the E-step of EM."""
    n = len(bols)
    binary_by_rhs, unary_by_rhs, term_by_lhs, _unary_by_lhs, _order = rule_tables
    counts: dict[tuple, float] = defaultdict(float)
    if log_z == _NEG_INF:
        return counts

    for i in range(n):
        bol = bols[i]
        out_cell = outside[i][1]
        for lhs, bol_map in term_by_lhs.items():
            if bol in bol_map and lhs in out_cell:
                lp = out_cell[lhs] + bol_map[bol] - log_z
                counts[(lhs, ("TERM", bol))] += math.exp(lp)

    for span in range(1, n + 1):
        for i in range(0, n - span + 1):
            in_cell = inside[i][span]
            out_cell = outside[i][span]
            if not in_cell or not out_cell:
                continue
            for rhs_sym, lhs_list in unary_by_rhs.items():
                if rhs_sym not in in_cell:
                    continue
                in_val = in_cell[rhs_sym]
                for lhs, rule_lp in lhs_list:
                    if lhs not in out_cell:
                        continue
                    lp = out_cell[lhs] + rule_lp + in_val - log_z
                    counts[(lhs, (rhs_sym,))] += math.exp(lp)

    for span in range(2, n + 1):
        for i in range(0, n - span + 1):
            out_cell = outside[i][span]
            if not out_cell:
                continue
            for split in range(1, span):
                left = inside[i][split]
                right = inside[i + split][span - split]
                if not left or not right:
                    continue
                for (b_sym, c_sym), lhs_list in binary_by_rhs.items():
                    lp_b = left.get(b_sym)
                    lp_c = right.get(c_sym)
                    if lp_b is None or lp_c is None:
                        continue
                    for lhs, rule_lp in lhs_list:
                        if lhs not in out_cell:
                            continue
                        lp = out_cell[lhs] + rule_lp + lp_b + lp_c - log_z
                        counts[(lhs, (b_sym, c_sym))] += math.exp(lp)
    return counts


def inside_outside_expected_counts(grammar: PCFG, bols: list[str],
                                    start: str = START) -> tuple[float, dict[tuple, float]]:
    """Run the full Inside-Outside algorithm on one bol sequence under the
    current grammar. Returns (log P(bols), expected_counts) where
    expected_counts maps (lhs, rhs) -> the fractional number of times that
    rule was used, in expectation, across every possible parse - the E-step
    of EM for a single training example."""
    n = len(bols)
    if n == 0:
        return _NEG_INF, {}
    inside, rule_tables = _inside_chart(grammar, bols)
    log_z = inside[0][n].get(start, _NEG_INF)
    outside = _outside_chart(grammar, bols, inside, rule_tables, start=start)
    counts = _expected_counts(bols, inside, outside, rule_tables, log_z)
    return log_z, counts


def uniform_init_grammar(template: PCFG) -> PCFG:
    """A fresh grammar with the same non-terminals/rule shapes as `template`
    but every LHS's productions given equal probability - the "no prior
    knowledge at all" EM starting point."""
    g = PCFG()
    g.vocabulary = set(template.vocabulary)
    for lhs, rules in template.rules.items():
        g.rules[lhs] = [Rule(lhs=lhs, rhs=r.rhs, count=0) for r in rules]
        k = len(g.rules[lhs])
        for r in g.rules[lhs]:
            r.prob = 1.0 / k if k > 0 else 0.0
    return g


def random_init_grammar(template: PCFG, rng: random.Random) -> PCFG:
    """A fresh grammar with the same shape as `template` but each LHS's
    productions given probabilities drawn uniformly at random from the
    probability simplex (via normalized Gamma(1,1) draws - an exact
    Dirichlet(1,...,1) sample), to test whether EM can recover good
    probabilities with NO informative starting point at all."""
    g = PCFG()
    g.vocabulary = set(template.vocabulary)
    for lhs, rules in template.rules.items():
        g.rules[lhs] = [Rule(lhs=lhs, rhs=r.rhs, count=0) for r in rules]
        draws = [rng.gammavariate(1.0, 1.0) for _ in g.rules[lhs]]
        total = sum(draws)
        k = len(g.rules[lhs])
        for r, d in zip(g.rules[lhs], draws):
            r.prob = (d / total) if total > 0 else (1.0 / k if k > 0 else 0.0)
    return g


def em_train(examples: list[list[str]], grammar: PCFG, n_iterations: int = 10,
             dirichlet_alpha: float = 0.01, start: str = START) -> tuple[PCFG, list[float]]:
    """Run Inside-Outside EM for `n_iterations`, starting from `grammar`'s
    current probabilities. Each iteration: E-step accumulates expected rule
    counts over every example under the CURRENT grammar; M-step renormalizes
    those counts (with Dirichlet/MAP smoothing, per the proposal's own
    degenerate-grammar mitigation) into the next grammar. Returns the final
    grammar and the per-iteration total corpus log-likelihood, so convergence
    (or a poor local optimum) can be read off directly."""
    log_likelihoods: list[float] = []
    current = grammar
    for _ in range(n_iterations):
        total_counts: dict[tuple, float] = defaultdict(float)
        total_log_likelihood = 0.0
        for bols in examples:
            log_z, counts = inside_outside_expected_counts(current, bols, start=start)
            total_log_likelihood += log_z
            for key, val in counts.items():
                total_counts[key] += val
        log_likelihoods.append(total_log_likelihood)

        new_grammar = PCFG()
        new_grammar.vocabulary = set(current.vocabulary)
        for lhs, rules in current.rules.items():
            new_grammar.rules[lhs] = [Rule(lhs=lhs, rhs=r.rhs, count=0) for r in rules]
        for (lhs, rhs), val in total_counts.items():
            for r in new_grammar.rules[lhs]:
                if r.rhs == rhs:
                    r.count = val
                    break
        new_grammar.normalize(dirichlet_alpha=dirichlet_alpha)
        current = new_grammar
    return current, log_likelihoods

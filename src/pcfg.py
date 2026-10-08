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


def _bolslot_list_node(label_base: str, bols: list[str]) -> DerivNode:
    """Build a right-branching list node: X -> BolSlot X | BolSlot."""
    assert bols, f"{label_base} must have at least one bol"
    leaf = DerivNode(label=BOLSLOT, bol=bols[0])
    if len(bols) == 1:
        return DerivNode(label=label_base, children=[leaf])
    rest = _bolslot_list_node(label_base, bols[1:])
    return DerivNode(label=label_base, children=[leaf, rest])


def _matra_bols(matra: RepMatra) -> list[str]:
    return [s.bol for s in matra.slots]


def build_avartan_deriv(avartan: Avartan) -> DerivNode:
    vibhag_nodes = []
    for v in avartan.vibhags:
        matra_nodes = []
        for m_idx, matra in enumerate(v.matras):
            bols = _matra_bols(matra)
            if not bols:
                continue
            label = SAM_MATRA if (v.index == 0 and m_idx == 0) else MATRA
            matra_nodes.append(_bolslot_list_node(label, bols))
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


def build_composition_deriv(rep: RepresentedComposition) -> DerivNode:
    avartan_nodes = [build_avartan_deriv(a) for a in rep.avartans]
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
) -> tuple[PCFG, list[DerivNode]]:
    grammar = PCFG()
    trees = []
    for c in raw_comps:
        rep = build_representation(c, TEENTAL)
        if mode is BolNormalizationMode.NORMALIZED:
            for a in rep.avartans:
                for s in a.all_slots():
                    s.bol = normalizer.normalize(s.bol)
        tree = build_composition_deriv(rep)
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

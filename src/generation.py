"""
Phase 7 - generation with attribute constraints.

Why not plain sampling or rejection sampling: Phase 7 measured that the
Phase 5 grammar, sampled freely, essentially never yields a valid tintal
cycle (its list rules reuse one label, e.g. Avartan -> Vibhag0 Avartan, so
it cannot count matras). Rejection sampling with a near-zero acceptance rate
is not a usable generator. Instead the cycle constraint is PROPAGATED during
the derivation: an inherited attribute (vibhags still to place, matras still
to place in this vibhag, is-the-next-matra-sam) filters which learned
productions are allowed at each step, and the learned probabilities are
renormalized over the allowed ones. Matra contents (which strokes, how many)
stay fully free and come from the learned grammar.

The tihai is generated from the plan's template
    Tihai -> Phrase Gap Phrase Gap Phrase  ... Sam
under reading B (see attributes.py), which the real corpus supported better
than reading A. Two constraints a context-free grammar cannot express are
enforced here directly: the three phrases are IDENTICAL copies (a copy
dependency), and the arithmetic places the stroke after the third phrase
exactly on the next sam.
"""
from __future__ import annotations

import copy
import random
from fractions import Fraction

from pcfg import (
    PCFG, DerivNode, AVARTAN, VIBHAG, MATRA, SAM_MATRA, REST, REST_TOKEN,
    START, sample_tree,
)
from attributes import GAP_SET_FROM_PLAN, annotate, leaf_nodes
from representation import TalaDefinition, TEENTAL


class UnsatisfiableConstraint(Exception):
    pass


def _pick(rules, rng: random.Random):
    weights = [r.prob for r in rules]
    if not rules or sum(weights) <= 0:
        raise UnsatisfiableConstraint("no allowed production with positive probability")
    return rng.choices(rules, weights=weights, k=1)[0]


def sample_matra(grammar: PCFG, label: str, rng: random.Random, max_tries: int = 50) -> DerivNode:
    for _ in range(max_tries):
        t = sample_tree(grammar, label, rng=rng, max_depth=60)
        if t is not None:
            return t
    raise UnsatisfiableConstraint(f"could not sample a finite {label}")


def _sample_vibhag(grammar: PCFG, vib: str, remaining: int, next_is_sam: bool,
                   rng: random.Random) -> DerivNode:
    first = SAM_MATRA if next_is_sam else MATRA
    # recursing with exactly 2 left is only safe if the 1-left unary rule exists
    has_unary_tail = any(r.prob > 0 and r.rhs == (MATRA,) for r in grammar.rules.get(vib, []))
    allowed = []
    for r in grammar.rules.get(vib, []):
        if r.prob <= 0 or r.rhs[0] != first:
            continue
        if len(r.rhs) == 2 and r.rhs[1] == vib and (remaining >= 3 or (remaining == 2 and has_unary_tail)):
            allowed.append(r)
        elif len(r.rhs) == 2 and r.rhs[1] == MATRA and remaining == 2:
            allowed.append(r)
        elif len(r.rhs) == 1 and remaining == 1:
            allowed.append(r)
    chosen = _pick(allowed, rng)
    children = [sample_matra(grammar, first, rng)]
    if len(chosen.rhs) == 2 and chosen.rhs[1] == vib:
        children.append(_sample_vibhag(grammar, vib, remaining - 1, False, rng))
    elif len(chosen.rhs) == 2:
        children.append(sample_matra(grammar, MATRA, rng))
    return DerivNode(label=vib, children=children)


def _sample_avartan(grammar: PCFG, remaining_vibhags: list[int], tala: TalaDefinition,
                    rng: random.Random) -> DerivNode:
    head = VIBHAG[remaining_vibhags[0]]
    left = len(remaining_vibhags)
    has_unary_tail = left == 2 and any(
        r.prob > 0 and r.rhs == (VIBHAG[remaining_vibhags[1]],) for r in grammar.rules.get(AVARTAN, []))
    allowed = []
    for r in grammar.rules.get(AVARTAN, []):
        if r.prob <= 0 or r.rhs[0] != head:
            continue
        if len(r.rhs) == 2 and r.rhs[1] == AVARTAN and (left >= 3 or has_unary_tail):
            allowed.append(r)
        elif len(r.rhs) == 2 and len(remaining_vibhags) == 2 and r.rhs[1] == VIBHAG[remaining_vibhags[1]]:
            allowed.append(r)
        elif len(r.rhs) == 1 and len(remaining_vibhags) == 1:
            allowed.append(r)
    chosen = _pick(allowed, rng)

    def vib_node(idx):
        return _sample_vibhag(grammar, VIBHAG[idx], tala.matras_per_vibhag, idx == 0, rng)

    children = [vib_node(remaining_vibhags[0])]
    if len(chosen.rhs) == 2 and chosen.rhs[1] == AVARTAN:
        children.append(_sample_avartan(grammar, remaining_vibhags[1:], tala, rng))
    elif len(chosen.rhs) == 2:
        children.append(vib_node(remaining_vibhags[1]))
    return DerivNode(label=AVARTAN, children=children)


def sample_avartan_constrained(grammar: PCFG, rng: random.Random,
                               tala: TalaDefinition = TEENTAL) -> DerivNode:
    """One tala cycle whose skeleton is forced by the inherited attributes and
    whose matra contents are sampled from the learned grammar."""
    return _sample_avartan(grammar, list(range(tala.n_vibhags)), tala, rng)


# ---------------------------------------------------------------------
# Tihai cadence
# ---------------------------------------------------------------------

def valid_tihai_shapes(tala: TalaDefinition = TEENTAL, phrase_matras=(1, 2, 3, 4)) -> list[tuple]:
    """(dur_p, dur_g) pairs that fit inside one cycle after its own sam:
    phrases are whole matras, gaps come from the plan's gap set, and
    3p + 2g <= n_matras - 1 so the cycle's own sam stroke precedes the tihai."""
    return [(Fraction(p), g) for p in phrase_matras for g in GAP_SET_FROM_PLAN
            if 3 * p + 2 * g <= tala.n_matras - 1]


def _starts_with_stroke(node: DerivNode) -> bool:
    return leaf_nodes(node)[0].bol != REST_TOKEN


def _sample_stroke_matra(grammar: PCFG, label: str, rng: random.Random, max_tries: int = 200) -> DerivNode:
    for _ in range(max_tries):
        m = sample_matra(grammar, label, rng)
        if _starts_with_stroke(m):
            return m
    raise UnsatisfiableConstraint(f"no {label} beginning with a stroke")


def _rest_leaf(dur: Fraction) -> DerivNode:
    return DerivNode(label=REST, bol=REST_TOKEN, dur=dur)


def generate_tihai_avartan(grammar: PCFG, rng: random.Random, dur_p: Fraction, dur_g: Fraction,
                           tala: TalaDefinition = TEENTAL, min_phrase_strokes: int = 2,
                           max_tries: int = 200) -> tuple[DerivNode, dict]:
    """A cycle whose final 3p+2g matras are a tihai resolving on the NEXT
    cycle's sam (reading B). Returns (node, info) where info gives the token
    offsets needed to check it independently."""
    n = tala.n_matras
    length = 3 * dur_p + 2 * dur_g
    s = n - length
    if s < 1:
        raise UnsatisfiableConstraint("tihai does not fit after the cycle's own sam")

    for _ in range(max_tries):
        phrase_matras = [_sample_stroke_matra(grammar, MATRA, rng) if i == 0
                         else sample_matra(grammar, MATRA, rng) for i in range(int(dur_p))]
        phrase = DerivNode(label="Phrase", children=phrase_matras)
        if len(leaf_nodes(phrase)) >= min_phrase_strokes:
            break
    else:
        raise UnsatisfiableConstraint("could not sample a phrase with enough strokes")

    prefix_children = [_sample_stroke_matra(grammar, SAM_MATRA, rng)]
    whole = int(s)
    prefix_children += [sample_matra(grammar, MATRA, rng) for _ in range(whole - 1)]
    if s - whole:
        prefix_children.append(_rest_leaf(s - whole))
    prefix = DerivNode(label="Prefix", children=prefix_children)

    tihai = DerivNode(label="Tihai", children=[
        phrase,
        DerivNode(label="Gap", children=[_rest_leaf(dur_g)]),
        copy.deepcopy(phrase),
        DerivNode(label="Gap", children=[_rest_leaf(dur_g)]),
        copy.deepcopy(phrase),
    ])
    node = DerivNode(label="TihaiAvartan", children=[prefix, tihai])
    info = {
        "prefix_tokens": len(leaf_nodes(prefix)),
        "phrase_tokens": len(leaf_nodes(phrase)),
        "gap_tokens": 1,
        "dur_p": dur_p, "dur_g": dur_g, "tihai_start_matra": s,
    }
    return node, info


def generate_composition(grammar: PCFG, rng: random.Random, n_body_avartans: int = 2,
                         shape: tuple | None = None, tala: TalaDefinition = TEENTAL) -> tuple[DerivNode, dict]:
    """Body cycles, then a tihai cycle, then the closing sam stroke - with the
    whole tree annotated (start/dur on every node)."""
    body = [sample_avartan_constrained(grammar, rng, tala) for _ in range(n_body_avartans)]
    if shape is None:
        shape = rng.choice(valid_tihai_shapes(tala))
    tihai_av, info = generate_tihai_avartan(grammar, rng, shape[0], shape[1], tala)
    closing = DerivNode(label="Sam", children=[_sample_stroke_matra(grammar, SAM_MATRA, rng)])
    root = DerivNode(label=START, children=body + [tihai_av, closing])
    annotate(root, Fraction(0))
    body_tokens = sum(len(leaf_nodes(a)) for a in body)
    info = dict(info)
    info["tihai_first_token"] = body_tokens + info["prefix_tokens"]
    info["n_body_avartans"] = n_body_avartans
    return root, info

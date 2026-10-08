# Learning an Interpretable Probabilistic Grammar of Hindustani Tāla

Rishav Kumar Gupta (2023A7PS0526P), BITS Pilani, Pilani Campus —
under the guidance of Prof. Yash Sinha.

A probabilistic grammar of tabla rhythm in tīntāl, learned from the
Mulgaonkar Tabla Solo corpus, whose derivation trees are the explanation of
every generated or analysed composition. Full plan:
[`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md). Mid-semester report (ACL
format): [`report/main.pdf`](report/main.pdf).

## Status

Phases 1–9 are complete. Every number in the reports comes from a script in
`src/` that can be re-run. The test split (6 compositions) has not been used
yet; it is reserved for the grammar-vs-baseline comparison (Phase 11).

| Phase | What it does | Report | Script |
|---|---|---|---|
| 1 | Dataset audit, splits | [`PHASE1_DATASET_AUDIT.md`](docs/PHASE1_DATASET_AUDIT.md) | `src/run_phase1_audit.py` |
| 2 | Bol normalization (18 vs 40 symbols) | [`PHASE2_BOL_NORMALIZATION.md`](docs/PHASE2_BOL_NORMALIZATION.md) | `src/run_phase2_analysis.py` |
| 3 | Timing-based representation (āvartan → vibhāg → mātrā → stroke) | [`PHASE3_REPRESENTATION.md`](docs/PHASE3_REPRESENTATION.md) | `src/run_phase3_representation.py` |
| 4 | Seed treebank, tihāī candidates | [`PHASE4_SEED_TREEBANK.md`](docs/PHASE4_SEED_TREEBANK.md) | `src/run_phase4_treebank.py` |
| 5 | Supervised PCFG, CYK/Inside parser | [`PHASE5_PCFG.md`](docs/PHASE5_PCFG.md) | `src/run_phase5_pcfg.py` |
| 6 | Inside–Outside EM study | [`PHASE6_EM.md`](docs/PHASE6_EM.md) | `src/run_phase6_em.py` (~25 min), `src/plot_phase6_em.py` |
| 7 | Attribute layer, tihāī arithmetic, constrained generation | [`PHASE7_ATTRIBUTES.md`](docs/PHASE7_ATTRIBUTES.md) | `src/run_phase7_attributes.py` |
| 8 | Parameter tying, held-out ablations | [`PHASE8_PRIORS.md`](docs/PHASE8_PRIORS.md) | `src/run_phase8_priors.py` |
| 9 | Generation examples and figures | [`PHASE9_GENERATION.md`](docs/PHASE9_GENERATION.md) | `src/run_phase9_generation.py` |

Outputs go to `data/processed/` (results, JSON) and `visualizations/`
(figures).

## Setup and running

Python 3.10 or newer.

    pip3 install -r requirements.txt
    python3 src/run_phase5_pcfg.py        # any phase script, from the repo root

Tests (65 across all phases):

    for f in tests/test_*.py; do python3 "$f"; done
    # or: python3 -m pytest tests

## Data

`data/raw/mts/` holds the dataset's scores, onset files and syllable mapping
(annotations licensed CC BY-NC-ND 4.0, see `data/raw/mts/LICENSE`;
source: Gupta et al., ISMIR 2015). The audio (`data/raw/mts/wav/`) is
copyrighted and not redistributable, so it is not included; nothing in
Phases 1–9 needs it.

## Layout

```
src/             all code: loaders, representation, grammar, EM, attributes,
                 generation, tying, and one run script per phase
tests/           regression tests for every phase
docs/            project plan and one report per phase
data/processed/  every result file the reports quote
visualizations/  every figure
report/          ACL-format mid-semester report (PDF + LaTeX source)
```

The empty folders (`baselines/`, `evaluation/`, `experiments/`, ...) are
placeholders for the remaining phases (baselines, RQ1–RQ3 evaluation).

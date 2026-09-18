# Learning an Interpretable Probabilistic Grammar of Hindustani Tāla

Research project: learn a probabilistic, hierarchically structured grammar of
Hindustani tāla from symbolic tabla data, with an expert-authored rule skeleton,
corpus-learned probabilities, native derivation-tree explanations, and a
quantitative comparison against black-box sequence models.

Full project plan (research questions, methodology, timeline, risks):
see [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md).

## Status

**Phase 0 (planning) in progress.** Dataset audit (Phase 1) is currently blocked:
the primary dataset (Mulgaonkar Tabla Solo, hosted on Zenodo) has not yet been
verified against the proposal's assumptions — see the Risks section of the
project plan. No grammar training or modeling work has started, and none will
until the dataset is inspected and confirmed to actually contain what the
proposal assumes.

## Repository structure

```
data/            Raw, interim, and processed dataset files; data dictionary; splits
src/             Shared utilities (I/O, representation classes, config loading)
grammar/         PCFG implementation: non-terminals, productions, EM, attribute grammar
models/          Trained grammar checkpoints and their configs
baselines/       N-gram, LSTM, Transformer, FST baselines, and post-hoc explanation code
evaluation/      Metrics: perplexity, bracketing F1, constraint-satisfaction checks
experiments/     Experiment runner scripts, one per phase/RQ
visualizations/  Figure-generation scripts (architecture, trees, results plots)
notebooks/       Exploratory analysis (not for pipeline code)
tests/           Unit and regression tests for every component above
configs/         YAML/JSON configs for reproducible runs
results/         Output tables, logs, and figures from actual experiment runs
paper/           Paper draft and supporting material
docs/            Project plan, dataset audit reports, data dictionary, design notes
```

## Setup

Environment setup instructions will be added once the first working component
(the dataset loader) exists and its dependencies are known — see Phase 18
(Reproducibility) in the project plan. No `requirements.txt` yet: we don't want
to declare dependencies before we know we need them.

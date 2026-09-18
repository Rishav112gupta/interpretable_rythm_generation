# Project Plan — Learning an Interpretable Probabilistic Grammar of Hindustani Tāla

Source of truth: `Interpretable_Rhythm_Generation_v2.pdf` ("Research Proposal, Revised
Draft v2"), provided by the researcher. This document restates the proposal as an
execution plan. It does not change the research question, methodology, terminology,
or scope. Where the proposal leaves a decision open, that is flagged explicitly
below as **OPEN DECISION** rather than resolved silently.

---

## 1. Research Objective

Learn a probabilistic, hierarchically structured grammar of Hindustani tāla from
symbolic tabla data, such that:

1. structure is represented explicitly (not recovered post-hoc);
2. the non-terminal skeleton comes from documented tabla theory (mukh, dohrā,
   adhā-dohrā, viśrām, adhā-viśrām, palṭā, tihāī — the Delhi bāj kāydā expansion
   order), not invented categories;
3. production probabilities are *learned* from a corpus (Inside–Outside / EM),
   not hand-elicited from a musician (this is the delta over Bel & Kippen's Bol
   Processor, which is the direct historical precedent and must be cited as such,
   not ignored);
4. generation yields a rhythmic sequence *and* its derivation tree simultaneously
   — the explanation is the production history, not a post-hoc account;
5. duration/arithmetic constraints (tihāī) are handled via an attribute grammar
   layer on top of the CFG backbone;
6. the grammar is compared against statistical and neural black-box baselines
   of matched capacity, including a post-hoc explanation baseline on the neural
   model — without this, "built-in beats post-hoc" is an assertion, not a result;
7. predictive quality and structural validity are evaluated quantitatively;
8. whether derivation trees give humans a measurable edge on rhythm-related tasks
   is tested behaviourally (forced-choice, pre-registered), not asked as opinion.

**Central scientific question:** what is the actual trade-off between built-in
structural transparency and predictive quality, relative to black-box sequence
models?

---

## 2. Research Questions and Hypotheses

| # | Question | What would count as a positive result | What would count as a negative/partial result (still publishable) |
|---|---|---|---|
| RQ1 (Fit) | Can a corpus-fit probabilistic grammar reach held-out predictive performance competitive with matched-capacity black-box models (n-gram, LSTM, Transformer)? | Grammar's held-out cross-entropy/perplexity is within the black-box models' confidence intervals | Grammar is measurably worse — report the gap honestly; this is RQ1's real answer either way |
| RQ2 (Validity) | Do learned high-probability rules/constituents correspond to pedagogically recognized units? | High bracketing F1 against expert/treebank annotations; high-probability rules map onto named tabla operations | Learned categories diverge from pedagogy — report divergence, do not force alignment |
| RQ3 (Utility) | Do derivation trees measurably help humans (next-variation prediction, error localisation, rule articulation, Turing-style check) vs. surface sequence alone or post-hoc neural explanation? | Significant accuracy/time improvement with tree condition | No measurable improvement — itself an interpretability-research finding |
| RQ4 (Expressivity) | What formal power does tāla actually require? | Formal characterization: which phenomena are CF, which need attributes, which resist grammatical treatment | Any answer is a contribution per the proposal — this RQ does not have a "failure" mode |

No hypothesis is assumed to be true in advance. In particular, RQ1's outcome is
not pre-determined — Phase 11 must report the real number.

---

## 3. Required Datasets

### 3.1 Primary — Mulgaonkar Tabla Solo (MTS)
- Source: CompMusic/MTG-UPF, Zenodo DOI `10.5281/zenodo.1267024`.
- Per the proposal: 38 solo tīntāl (16-mātrā) compositions, 6 gharānās, performed
  by Pt. Arvind Mulgaonkar (*Shades of Tabla* DVD), audio + scores + time-aligned
  bol transcriptions.
- **Status as of this writing: NOT YET VERIFIED.** See §13 Risks — this environment's
  network policy blocks Zenodo and compmusic.upf.edu, so the actual files have not
  been inspected yet. Phase 1 cannot be marked complete, and grammar training
  (Phase 5+) must not start, until real files are opened and the claims above are
  checked against them.

### 3.2 Reference code
- `github.com/swapnilgt/percPatternDiscovery` (Gupta et al., ISMIR 2015). Confirmed
  reachable. Contains `.lab` (syllable-per-line) label files, `.csv` onset/timestamp
  files, `.mat` similarity matrices, and an RLCS pattern-search pipeline — but this
  is the *code* repo, not the dataset itself, and it ships with a placeholder
  `data/` directory. We reuse the loader logic only after confirming it matches
  the actual MTS file layout.

### 3.3 Secondary / contingency (per proposal §6.3 — use only if primary proves
data-starved, and only after verifying content)
- CompMusic Carnatic Music Rhythm Dataset — **flagged in the proposal itself** as
  possibly beat/sama annotations on audio only, not symbolic strokes. Must verify
  before any use.
- Mridangam Stroke / Tani-avarthanam Datasets, Saraga, Hindustani Music Rhythm
  Dataset, El Bongosero.
- Pedagogical notation corpora (digitabla.com, 52kaidas, Varma's *The Art of Tabla
  Playing*) — proposal names hand-encoding 100–200 further compositions from these
  as possibly "the single highest-leverage data action available."

### 3.4 Planned data contribution
- A **Tabla Derivation Treebank**: gold derivation trees over a compositions
  subset, released openly (modeled on the Jazz Harmony Treebank, ISMIR 2020).

---

## 4. Representation

```
Composition
  └─ Āvartan (cycle; tīntāl = 16 mātrā)
        └─ Vibhāg (4 × 4 mātrā)
              └─ Mātrā (beat)
                    └─ Bol-slot (subdivision: 1, 2, or 4 per mātrā)
```

- Terminal alphabet: bols from the MTS corpus (DHA, DHE, DHET, DHIN, GE, KE, NA,
  TA, TE, TII, TIN, TRA, RE, …) — **the exact vocabulary must come from the actual
  corpus, not this illustrative list** — plus an explicit rest symbol and a
  duration-extension symbol.
- Every non-terminal carries `(start_position, duration)` as synthesized
  attributes — this is what makes sam-resolution checkable.
- Extensible to jhaptāl and ektāl later (proposal treats tīntāl as the Week 1–13
  scope; other tālas are Week 13+ extension).

**OPEN DECISIONS the proposal explicitly defers to Weeks 1–3 (i.e., to us, now)：**
1. **Bol normalisation** — merge gharānā-specific orthographic variants, or keep
   distinct? Proposal says: document the decision, report results under *both*
   configurations. → Phase 2 implements both modes (A: normalized, B: distinct).
2. **Compound bols** (e.g. DHA = GE + NA) — atomic terminal vs. feature bundle
   (left-hand × right-hand)? Proposal recommends feature bundles because they let
   khālī/bharī rules fall out naturally (khālī = bass component suppressed), but
   says to keep it configurable for comparison.

---

## 5. Grammar Architecture

**Stage A (core, proposal Weeks 4–9):** expert-authored non-terminal skeleton
from the documented Delhi bāj kāydā expansion order, + production probabilities
estimated by Inside–Outside/EM over the corpus. Supervised MLE on a hand-parsed
subset initializes EM, to avoid poor local optima.

**Stage B (stretch, proposal Weeks 13+):** MDL-based latent subcategory
refinement (split-merge, à la latent-variable PCFGs; Mavromatis 2009). Explicitly
a stretch goal — must not delay Stage A / the core RQ1–RQ3 experiments.

The skeleton itself is treated as a **documented prior**, not a hidden
researcher-intuition fit — its categories come from published pedagogy — but this
framing is itself an assumption the proposal asks us to defend, not something to
assert uncritically in the paper.

---

## 6. Learning Algorithm

- Inside–Outside (EM) for PCFG production probabilities, in log-space for
  numerical stability.
- Supervised initialization from the seed treebank (Phase 4) where available.
- Dirichlet priors / MAP estimation (not plain MLE) to address the corpus-size
  problem (§3.2 above / proposal §6.2).
- Aggressive parameter tying across structurally analogous rules (repetition,
  symmetry, khālī/bharī alternation, dugun/tigun) — both a data-sparsity
  mitigation and, per the proposal, itself an interpretability feature (a tied
  parameter is a measurable claim about style).
- Diagnostics required (Phase 5/6): degenerate grammars, zero probabilities,
  underflow, poor local optima, generated-sequence validity.

---

## 7. Generation Algorithm

- Top-down sampling from the PCFG, yielding sequence + derivation tree + rule
  sequence + duration/metrical info together.
- Ordinary sampling, rejection sampling, and constrained beam search (proposal
  names both as options for enforcing hard attribute constraints).

---

## 8. Attribute Grammar / Duration Mechanism

Core formal claim to test (not assume): tāla structure is context-free *modulo a
decidable arithmetic constraint layer* — mildly context-sensitive, like
cross-serial dependencies in natural language.

Tihāī production template (from the proposal, verbatim structure):

```
Tihai(target) → Phrase(p) Gap(g) Phrase(p) Gap(g) Phrase(p) Sam
    where  3·dur(p) + 2·dur(g) + 1 ≡ target (mod cycle_length)
           dur(g) ∈ {¼, ½, ¾, 1, 1½, 2} mātrā
```

Parsing strategy: parse context-free, then filter by attribute satisfaction, or
propagate constraints during chart construction.

**Named fallback if attributes prove unwieldy:** probabilistic tree-adjoining
grammar (PTAG), with adjunction handling insertion of expansion material into a
fixed cyclic frame. If we hit this wall, the plan is to say so explicitly and
implement the smallest defensible alternative — not quietly swap formalisms.

---

## 9. Baselines

| Baseline | Purpose | Matching requirement |
|---|---|---|
| Bol n-gram (n = 3–7, Kneser–Ney) | surface-statistics floor | — |
| Small LSTM | matched-capacity neural baseline | parameter count documented, comparable to grammar |
| Small Transformer | contemporary black-box reference | parameter count documented |
| TālaGen-style FST | tests whether CF power is actually needed over finite-state | reasonable equivalent if exact system unavailable |
| Post-hoc explanation on the neural baseline (attention/probing) | the direct comparison the paper is built on | explicitly named "essential" in the proposal |

All baselines: document parameter count, training data, training procedure,
hyperparameters, compute, and random seeds (Phase 10).

---

## 10. Evaluation Metrics

- **RQ1:** held-out cross-entropy / perplexity per bol, composition-level splits,
  bootstrap CIs, full-corpus and per-gharānā.
- **RQ2:** bracketing precision/recall/F1 against the treebank subset; plus
  qualitative comparison of high-probability rules against Clayton, Kippen,
  Saxena, and standard pedagogy; expert review of generated compositions
  (sam resolution, khālī/bharī integrity, palṭā coherence, tihāī arithmetic).
- **RQ4:** formal-language-theoretic analysis, clearly labeled as proven result /
  implementation observation / hypothesis / future work — no overclaiming.

---

## 11. Human Evaluation (RQ3)

Four pre-registered, forced-choice behavioural tasks (not Likert ratings — the
proposal explicitly rejects "do people find explanations useful" as
unmeasurable):

1. **Next-variation prediction** — pick the correct next palṭā from 4 candidates,
   with vs. without derivation tree.
2. **Error localisation** — locate structural failure in a corrupted
   composition, with vs. without tree; accuracy + time-to-answer.
3. **Rule articulation** — free-text statement of which operation produced a
   variation, blind-coded against the actual rule.
4. **Turing-style quality check** — generated vs. human-composed, forced choice,
   blind cohort.

Participants: ~20–30 tabla students + a smaller expert group. Requires
pre-registration of hypotheses/metrics/exclusion criteria and ethics approval
**filed early** (proposal: "do not defer"). **If participants are not available
in this project's execution, the full experiment infrastructure (task UI,
randomization, materials, analysis scripts) will be built and validated with
placeholder/pilot data clearly marked, but results will be labeled NOT YET
COLLECTED — never fabricated.**

---

## 12. Expected Deliverables

1. Verified, cleaned, machine-readable MTS corpus + data dictionary + audit report.
2. Seed treebank (~10 hand-parsed compositions) in a validated machine-readable format.
3. Working PCFG implementation (parsing, sampling, EM, log-space, diagnostics).
4. Attribute-grammar layer with tihāī constraint checking.
5. Trained grammar + all baselines, each reproducible from a config file.
6. RQ1–RQ4 results with real numbers, figures, and honest reporting of negative results.
7. Human-study infrastructure (+ real results if data collection is feasible; otherwise clearly marked as not collected).
8. Ablation results (Phase 14).
9. Publication-quality figures (Phase 19).
10. Paper draft (Phase 20), reviewer-style audit (Phase 21).
11. Open-source, reproducible repository with fixed seeds, configs, and a single master experiment runner.

---

## 13. Risks

| Risk | Source | Mitigation |
|---|---|---|
| **Dataset not accessible from this execution environment** (Zenodo, compmusic.upf.edu, and arxiv.org are all blocked by network egress policy here) | discovered during Phase 0/1 audit | User needs to supply the dataset files directly (upload, or commit into the repo) — see the question raised alongside this plan |
| Corpus too small (38 compositions) for EM | proposal §6.2, stated not hidden | āvartan-level units, Dirichlet/MAP priors, parameter tying, composition-level CV, honest learning-curve reporting; hand-encode more compositions from pedagogical sources if needed |
| EM collapses to degenerate grammars | proposal risk register | supervised init from seed treebank + Dirichlet priors |
| Tihāī arithmetic constraint impractical as pure attribute grammar | proposal §5.3 | fall back to PTAG, state the problem explicitly, do not silently swap formalisms |
| Expert access falls through | proposal risk register | substitute published musicological analyses; recruit advanced students |
| Ethics approval delayed | proposal risk register | run RQ1/RQ2 first; paper can stand on those alone |
| Carnatic/secondary datasets don't actually contain symbolic content | proposal §6.3, self-flagged | verify file contents before relying on any secondary corpus |
| Neural baselines too large/small to be a fair comparison | our own scope discipline | document parameter counts explicitly, match capacity, justify choices |

---

## 14. Timeline

Following the proposal's own 13-week (+ extension) structure; phase numbers below
are the task's 21-phase breakdown mapped onto those weeks:

| Weeks (proposal) | Phases here | Deliverable |
|---|---|---|
| 1–2 | Phase 0 (this plan) | Roadmap, repo scaffold |
| 2–4 | Phases 1–3 | Verified corpus, bol normalization, representation |
| 4–5 | (parallel) | Ethics application filed, if human study is in scope |
| 4–7 | Phase 4 | Seed treebank |
| 6–8 | Phases 5–6 | Trained PCFG |
| 8–9 | Phase 7 | Attribute layer, tihāī constraint, generation pipeline |
| 8–9 (priors) | Phase 8 | Structural priors + ablations |
| — | Phase 9 | Generation examples + visualizations |
| 9–10 | Phase 10–11 | Baselines, RQ1 results |
| 10–12 | Phases 12–13 | RQ2, RQ3 results |
| 12–13 | Phases 14–15 | Ablations, expressivity analysis (RQ4) |
| 13+ | Phases 16–17 | MDL refinement, graph critic (stretch) |
| — | Phases 18–21 | Reproducibility, visualization, paper, final audit |

Work proceeds **incrementally, phase by phase**, with explicit stop-and-review
points — no phase after Phase 1 begins until the prior phase's output has been
shown, run, tested, and reviewed.

# Data Dictionary — MTS Cleaned Dataset

Source: `data/raw/mts/` (see `docs/PHASE1_DATASET_AUDIT.md` for how this was
verified). Produced by `src/run_phase1_audit.py`.

## `data/processed/compositions.jsonl`

One JSON object per line, one line per composition (38 total).

| Field | Type | Meaning |
|---|---|---|
| `name` | string | Filename stem, e.g. `"dli_1"`. Matches `filelist.txt`. |
| `gharana` | string | From the score header's `GHARANA:` field. One of DILLI, AJRADA, LUCKNOW, BENARAS, FARUKKHABAD, PUNJAB. |
| `composition_id` | string | Raw `COMPOSITION:` header value (a number, sometimes with a gharānā suffix like `"10_Ajrada"`). Not a unique key by itself — use `name` for that. |
| `jati` | string or `"??"` | Subdivision family. `"??"` means the transcriber left it unknown — treat as missing, not a real category. |
| `type` | string | Composition form, e.g. `"QUAYDA"`, `"RELA"`, `"CHAKRADAR"`. 19 distinct values across the corpus. |
| `tala` | string | Always `"TEENTAL"` for this corpus (verified, not assumed). |
| `composer` | string or `"??"` | Attributed composer/source ustad; `"??"` = unknown. |
| `n_sections` | int | Number of named or implicit sections in the score (e.g. Quayda + Dohra = 2). |
| `section_names` | list[string or null] | Section labels in order, e.g. `["Quayda", "Dohra", "Adha Dohra"]`. `null` = unnamed/implicit section. |
| `onsets_mapped` | list[{t, bol}] | Onset stream using the **18-symbol mapped** vocabulary (`onsMap`). `t` = onset time in seconds (float, from the original audio). |
| `onsets_unmapped` | list[{t, bol}] | Onset stream using the **raw ~40-symbol** vocabulary (`onsNoMap`), same timestamps as `onsets_mapped`. |
| `score_bol_count` | int | Number of non-rest bol tokens recovered by flattening the score file. |
| `onset_bol_count` | int | Number of rows in the `onsNoMap` CSV. |
| `score_onset_count_match` | bool | Whether `score_bol_count == onset_bol_count`. True for all 38 in this corpus. |
| `score_onset_exact_match` | bool | Whether the flattened score sequence equals the `onsNoMap` sequence token-for-token, in order. True for all 38. |

**Not included in this file** (available in `data/raw/mts/` if needed later):
the score's raw vibhāg/slot/sub-bol structure (parse with
`src.mts_loader.parse_score` if you need the hierarchy, not just the flat
sequence), and audio.

## `data/processed/splits.json`

| Field | Meaning |
|---|---|
| `train` / `val` / `test` | Lists of composition `name`s. Disjoint, cover all 38. |
| `seed` | RNG seed used to generate the split (42) — re-running `run_phase1_audit.py` reproduces it exactly. |
| `unit` | Documents that `ajr_10_ajr` and `ajr_10_dli` are treated as one inseparable unit (same underlying kāydā in two gharānā renderings — see audit report §10). |

## Vocabulary reference

- **Mapped (18 symbols):** `DA, DHA, DHE, DHET, DHI, DHIN, DIN, GE, KDA, KI,
  NA, RE, TA, TE, TII, TIN, TIT, TRA` — from `syllableMapping.pdf`, verified
  to exactly match the `onsMap` files.
- **Raw (40 symbols):** see `data/raw/mts/syllableMapping.txt` for the full
  raw→mapped variant table (this *is* the dataset's official normalization —
  don't invent a separate one for Phase 2).
- **Rest:** `-`, present only in `score/*.txt`, absent from both onset CSVs.

## Known limitations (see audit report for full detail)

- No explicit duration field anywhere; must be inferred from inter-onset
  intervals.
- `jati` missing (`"??"`) for 16/38 compositions.
- Section labels in `score/*.txt` are transcriber-assigned for cataloguing,
  not grammar-annotated — usable as weak supervision for Phase 4, not as
  gold treebank labels without further review.

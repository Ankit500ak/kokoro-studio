# Evals

A small, committed evaluation harness for Kokoro Studio's TTS text
pipeline. It exists so that "the narration sounds better now" can be
checked against numbers in git history instead of impressions.

## What it measures

The deterministic TTS-prep stage — `app.services.kokoro_service._normalize_numbers`,
which turns digits into spoken words before synthesis:

- **Correctness** — exact match of the normalised output against
  hand-written gold expectations (`gold.json`) over 10 fixed narration
  samples (`samples.json`): years spoken as years in year contexts
  ("in 2024" → "in twenty twenty four") while bare quantities stay
  cardinal ("2000 items" → "two thousand items"), ordinals, fractions,
  phone numbers, money, decimals, percentages, times.
- **Latency** — wall-clock per normalisation call (mean of 25 runs per
  sample, plus mean/p50/p95 across samples).
- **Cost per finished video** — a documented estimate model
  (narration pace, CPU-seconds per spoken word, core-hour price).
  The assumptions are printed in `RESULTS.md`; the TTS model itself
  is not executed by this harness, and no LLM provider is called.

## Run it

From the repository root, in an environment with the backend
requirements installed (the harness imports the real service module):

```sh
python -m evals.run_evals
```

This regenerates `evals/RESULTS.md` and exits non-zero if any sample
misses its gold expectation.

## Adding a sample

1. Add the raw narration text to `samples.json` with a unique `id`.
2. Write the expected spoken form in `gold.json` under the same `id`,
   derived from the spoken-form rules — not by copying current output.
3. Re-run the harness. If the run fails, either the code or the gold
   is wrong; fix the one that is, and say which in the commit message.

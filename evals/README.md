# evals — Trace Regression Dataset + Golden Dataset

Two concerns live here:

1. **Trace regression dataset** (`evals/runs/`) — replay tricky Orchestrator
   sessions to catch regressions when skills or models are tweaked.
2. **Golden dataset** (`evals/golden/`) — labelled synthetic campaign cases for
   testing the Nirite eval layer and Layer 3 qualification pipeline.

## Trace regression dataset (`evals/runs/`)

Purpose: replay tricky prompts whenever skills or models are tweaked, to catch
regressions before they reach the user.

```
evals/
  runs/
    <YYYY-MM-DD>-<slug>/
      prompt.txt    # the raw user request (sanitized)
      spec.md       # the rewritten Execution Spec
      outcome.md    # pass/fail + deterministic check output
      trace.jsonl   # tool calls + stdout/stderr per subtask
  fixtures/         # reusable inputs (prospect CSVs, etc.)
```

## Golden dataset (`evals/golden/`)

Purpose: labelled synthetic campaign cases for testing the Nirite eval layer and
Layer 3 qualification pipeline. All data is synthetic — no real prospect data,
no scraped LinkedIn data, no API keys.

```
evals/golden/
  schema.json           # JSON schema for golden cases
  README.md             # dataset documentation
  thresholds.json       # precision/recall thresholds for master evals
  campaigns/
    <slug>/
      prompt.txt        # Original natural-language campaign description
      expected.json     # Expected campaign definition characteristics
      candidates.json   # 8-15 synthetic prospect records
      labels.json       # Expected qualification label per candidate index
```

## How to add a trace run

After any session that exercised the Orchestrator pipeline, export the session:

    hermes sessions export <session_id> evals/runs/<date>-<slug>/

Then add prompt.txt, spec.md, and outcome.md by hand from the exported
transcript. Record both successful runs (regression baselines) and failed runs
(fixes to verify).

## Zero-cost rule

All replays and golden-case tests run against free models only
(nvidia/nemotron via NIM, ollama fallback). No paid-model regression checks.
Golden-case tests run offline with `FakeLLMProvider` — zero network, zero LLM
cost. Live runs against real NIM Nemotron require `pytest -m live`.

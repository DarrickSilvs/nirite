# evals — Trace Regression Dataset

Purpose: replay tricky prompts whenever skills or models are tweaked, to catch
regressions before they reach the user.

## Structure
evals/
  runs/
    <YYYY-MM-DD>-<slug>/
      prompt.txt    # the raw user request (sanitized)
      spec.md       # the rewritten Execution Spec
      outcome.md    # pass/fail + deterministic check output
      trace.jsonl   # tool calls + stdout/stderr per subtask
  fixtures/         # reusable inputs (prospect CSVs, etc.)

## How to add a run
After any session that exercised the Orchestrator pipeline, export the session:

    hermes sessions export <session_id> evals/runs/<date>-<slug>/

Then add prompt.txt, spec.md, and outcome.md by hand from the exported
transcript. Record both successful runs (regression baselines) and failed runs
(fixes to verify).

## When to replay
- Before and after editing any skill in ~/.hermes/skills/.
- Before and after switching the main or delegation model.
- Before and after changing SOUL.md or .hermes.md verifier commands.

## Zero-cost rule
All replays run against free models only (nvidia/nemotron via NIM, ollama
fallback). No paid-model regression checks.

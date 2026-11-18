# Nirite Golden Dataset

Golden campaign/evaluation cases for testing the eval layer and Layer 3
qualification pipeline. All data is synthetic — no real prospect data, no
scraped LinkedIn data, no API keys.

## Structure

```
evals/golden/
  schema.json           # JSON schema for golden cases
  README.md             # this file
  campaigns/
    <slug>/
      prompt.txt        # Original natural-language campaign description
      expected.json     # Expected campaign definition characteristics
      candidates.json   # 8-15 synthetic prospect records
      labels.json       # Expected qualification label per candidate index
  thresholds.json       # Precision/recall thresholds for master evals
```

## Case conventions

- Every case states which integrity dimension it tests (see `integrity_tests` in schema)
- At least 2 company-target and 2 person-target cases
- At least one positive (qualified) and one negative (not_qualified) label per case
- All prospect fields are synthetic

## Integrity dimensions tested

| Dimension | What it validates |
|---|---|
| `dropped_criterion` | Eval catches criteria present in analysis but missing from definition |
| `weak_query_facets` | Eval catches criteria with no query facet coverage |
| `exclusion_trap` | Qualification correctly disqualifies on exclusion match |
| `ambiguous_seniority` | Ambiguous criteria produce bordered verdicts, not false positives |
| `geo_expansion` | country=X matches state/city within X via GEO_HIERARCHY |
| `alias_resolution` | Variant column names (town→city) resolve correctly |

## Cost policy

All golden-case tests run offline with `FakeLLMProvider` — zero network,
zero LLM cost. Live runs against real NIM Nemotron require `pytest -m live`.

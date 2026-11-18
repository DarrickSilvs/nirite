# Nirite

AI-powered prospect qualification CLI. Turn natural-language campaign
descriptions into qualified prospect lists through a three-layer pipeline:

```
Layer 0: Ingestion     CSV/XLSX → normalized prospects (zero LLM cost)
Layer 1: Campaign spec → structured criteria + search queries (LLM)
Layer 2: Retrieval     Deterministic filter + keyword + TF-IDF + RRF (zero LLM cost)
Layer 3: Qualification → Jev-style bounded judging → qualified/not-qualified/bordered
```

## Installation

```bash
uv pip install -e .
```

## Usage

### Layer 0 — Ingest prospects

```bash
nirite ingest data/raw/prospects.csv --kind individual -o data/raw/prospects.json
nirite ingest data/raw/companies.csv --kind company -o data/raw/companies.json
```

### Layer 1 — Define a campaign

```bash
nirite campaign "Find mid-sized SaaS companies in Australia for our sales outreach" -o campaign.json
```

The campaign definition is validated by a strict eval layer before being saved. If the LLM output fails structural or semantic checks, the command exits with an error and no file is written.

### Layer 2 — Retrieve candidates

```bash
nirite retrieve data/raw/prospects.json campaign.json -o results.json
```

### Layer 3 — Qualify prospects

```bash
nirite qualify data/raw/prospects.json campaign.json -o qualified.json
```

The `qualify` command runs Layer 2 retrieval then applies per-criterion Jev-style
bounded judging to produce `qualified` / `not-qualified` / `bordered` verdicts
with per-criterion breakdowns.

## Eval layer

Nirite includes a strict eval layer that validates Layer 1 LLM outputs before
they reach retrieval:

- **Deterministic checks**: schema validity, unique IDs, query count, weight
  constraints, predicate pairing, clarification references
- **Cross-artifact consistency**: detects dropped/invented/kind-flipped criteria,
  uncovered facets, contradictory predicates
- **Quality judge**: bounded yes/no/unknown rubric judging of definition fidelity
  against the original prompt

All evals run in strict mode — any ERROR finding blocks output.

## Master evals

Run end-to-end evals with the master eval orchestrator:

```bash
python -m nirite.eval.master
```

This builds campaign definitions, runs retrieval and qualification, computes
precision/recall@K metrics, and triggers a bounded Layer 1 re-run if thresholds
are breached.

## Test suite

```bash
uv run pytest -q
```

Live tests against real NIM Nemotron APIs (opt-in):

```bash
uv run pytest -m live tests/evals/live/
```

## Project structure

```
src/nirite/
  campaign/     Layer 1: campaign spec (analyser, parser, service, eval)
  eval/         Eval layer: deterministic checks, bounded judge, master eval
  ingestion/    Layer 0: CSV/XLSX ingestion
  qualification/Layer 3: qualified/not-qualified/bordered verdicts
  retrieval/    Layer 2: Tier 1 filter + keyword + TF-IDF + RRF
  cli.py        CLI: ingest, map, campaign, retrieve, qualify
evals/
  golden/       Golden dataset: synthetic campaigns + labels
  runs/         Trace regression dataset
tests/          Unit tests
```

## Zero-cost

Nirite is designed to run entirely on free models:
- Ministral-3B and Gemini-3.1-Flash-Lite via NVIDIA NIM / OpenRouter
- TF-IDF + numpy for semantic retrieval (no vector DB required)
- No paid models, no vector database, no paid APIs
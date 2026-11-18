# Nirite

Finds the needle in your haystack.

AI-powered prospect qualification CLI. Turn a natural-language campaign description into a qualified prospect list from thousands of candidates.

## What Nirite does

Helps businesses find the right person to contact for their campaign — without manually sorting through thousands of prospects.

## Three-layer pipeline

**Layer 0 — Ingest** (zero LLM cost)
- Load CSV/XLSX prospects → normalized JSON

**Layer 1 — Campaign spec** (LLM)
- Turn a prompt like *"Find mid-sized SaaS companies in Australia"* into structured criteria + search queries
- Validated by a strict eval layer before saving

**Layer 2 — Retrieve** (zero LLM cost)
- Deterministic filter + keyword search + TF-IDF semantic search + RRF ranking
- Returns top-N ranked candidates

**Layer 3 — Qualify** (LLM)
- Per-criterion structured checks + Jev-style bounded yes/no/unknown judging
- Output: `qualified` / `not-qualified` / `bordered` verdicts with per-criterion breakdown

## Installation

```bash
uv pip install -e .
```

## Setup

Create a `.env` file in the project root:

```
MISTRAL_OPENROUTER_API_KEY=your_openrouter_key
GEMINI_FLASH_LITE_API_KEY=your_openrouter_key
```

Both keys go through OpenRouter (Ministral-3B and Gemini-3.1-Flash-Lite are free-tier models).

## Usage

### 1. Ingest prospects
```bash
nirite ingest data/raw/prospects.csv --kind individual -o data/raw/prospects.json
```

### 2. Define a campaign
```bash
nirite campaign "Find mid-sized SaaS companies in Australia" -o campaign.json
```

### 3. Retrieve candidates
```bash
nirite retrieve data/raw/prospects.json campaign.json -o results.json -n 30
```

### 4. Qualify prospects
```bash
nirite qualify data/raw/prospects.json campaign.json -o qualified.json
```

## Zero-cost design

- Ministral-3B and Gemini-3.1-Flash-Lite via OpenRouter (free tier)
- TF-IDF + numpy for semantic retrieval — no vector DB, no paid APIs
- Deterministic Tier 1 filter — zero LLM cost for screening

## Tests

```bash
uv run pytest -q
```

## Project structure

```
src/nirite/
  campaign/     Layer 1: campaign spec + eval
  eval/         Eval layer: deterministic checks, bounded judge, master evals
  ingestion/    Layer 0: CSV/XLSX ingestion
  qualification/Layer 3: qualified / not-qualified / bordered verdicts
  retrieval/    Layer 2: Tier 1 filter + keyword + TF-IDF + RRF
  cli.py        CLI: ingest, campaign, retrieve, qualify
evals/
  golden/       Golden dataset: synthetic campaigns + labels
tests/          Unit tests
```

## License

MIT — free to use, modify, and distribute.

## Repository

https://github.com/DarrickSilvs/nirite

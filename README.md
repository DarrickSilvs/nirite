# Nirite

A CLI tool that finds the right prospects for your campaign out of thousands of candidates.

Nirite helps you go from a raw list of prospects to a shortlist of people actually worth contacting. You describe your campaign in plain language, and Nirite turns that into structured criteria, filters your prospect list, and scores each candidate against your criteria.

## What it does

You start with a CSV or Excel file of prospects. Nirite normalizes it into JSON. Then you describe your campaign — for example, "find mid-sized SaaS companies in Australia looking for sales outreach." Nirite converts that into structured criteria (country, industry, company size, job title, etc.) and search queries.

Next, it runs those queries against your prospect list using a mix of deterministic filtering and keyword search, returning a ranked set of candidates. Finally, it evaluates each candidate against your criteria using structured checks and a bounded yes/no judge model, giving each prospect a verdict: qualified, not qualified, or bordered.

## Three steps

**Step 1: Ingest your prospects**

```bash
uv run python -m nirite ingest data/raw/prospects.csv --kind individual -o data/raw/prospects.json
uv run python -m nirite ingest data/raw/companies.csv --kind company -o data/raw/companies.json
```

Load a CSV or XLSX file of individual or company prospects. Nirite normalizes the columns into a standard JSON format.

**Step 2: Define your campaign**

```bash
uv run python -m nirite campaign "Find mid-sized SaaS companies in Australia" -o campaign.json
```

Describe your campaign in plain language. Nirite converts it into structured criteria and search queries, then runs them through a strict eval layer to make sure nothing was dropped or invented before saving.

**Step 3: Retrieve and qualify**

```bash
uv run python -m nirite retrieve data/raw/prospects.json campaign.json -o results.json -n 30
uv run python -m nirite qualify data/raw/prospects.json campaign.json -o qualified.json
```

The `retrieve` command filters and ranks your prospects based on the campaign criteria. The `qualify` command takes those candidates and evaluates each one against your criteria, producing qualified, not qualified, or bordered verdicts with reasons for each.

After installing with `uv pip install -e .`, you can also run `nirite` directly instead of `uv run python -m nirite`.

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

Both keys go through OpenRouter. Ministral-3B and Gemini-3.1-Flash-Lite are free-tier models, so you can run Nirite without paying for LLM API calls.

## How it works

Nirite uses three layers:

1. **Ingest** — CSV/XLSX to normalized JSON. No LLM calls.
2. **Campaign spec** — plain language to structured criteria. Uses an LLM with a strict eval gate.
3. **Retrieve and qualify** — filter, rank, and score candidates. Uses deterministic checks for structured criteria and a yes/no judge model for semantic criteria.

The retrieval layer uses TF-IDF and numpy for semantic search, so you do not need a vector database. The Tier 1 filter uses deterministic rules, keeping LLM costs low.

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

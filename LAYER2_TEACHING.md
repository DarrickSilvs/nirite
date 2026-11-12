# Nirite Layer 2 — Retrieval: Teaching Guide

**Audience:** you (Darrick), builder of Nirite  
**Repo:** `/workspace` (branch `v1/1.2/campaign-spec`)  
**Goal:** understand what changed, how everything connects, and specifically how Layer 2 (retrieval) works — the code, the theory, and how it fits the product.

---

## 1. The three-layer architecture (and where Layer 2 fits)

Nirite is a campaign-aware prospect qualification CLI. Data flows through three layers:

| Layer | Module | Responsibility | LLM cost |
|---|---|---|---|
| **Layer 0** | `src/nirite/ingestion/` | Ingest CSV/XLSX, clean headers, map alias columns → canonical fields, preserve extras, derive country, normalise names | Zero |
| **Layer 1** | `src/nirite/campaign/` + `models/` | Turn natural-language campaign description into a structured `CampaignDefinition` (spec + query plan + criteria) | Yes (Ministral/Gemini via LiteLLM) |
| **Layer 2** | `src/nirite/retrieval/` | Match ingested prospects against the campaign: deterministic filter → two retrieval agents → Reciprocal Rank Fusion → ranked candidates | Zero |

**Entry point:** `src/nirite/cli.py` (typer) with commands `ingest`, `map`, `campaign`, `retrieve`.  
`python -m nirite` → `src/nirite/__main__.py` → `cli:app`.

Layer 2's inputs are the **Layer 0 output** (ingested `Prospect`/`CompanyProspect` JSON) and the **Layer 1 output** (`CampaignDefinition` JSON). Its output is a `RetrievalOutput` of ranked, deduplicated `Candidate`s.

---

## 2. What changed recently

### Committed (branch `v1/1.2/campaign-spec`)
```
ef9c142 fix: removed nemotron 550B parser, replaced with gemini + ministral fallback
831e5ea fix: replaced parallel analyser LLMs with single ministral llm with gemini fallback
44a79a7 feat: added more model tests in weight criterias
b370bb6 Major fix: stable ID, safer field reassignment, .tmp atomic saves
```
Key point: the LLM stack (Layer 1) moved from a single expensive Nemotron-550B parser to a **cheap primary + fallback** pattern (Ministral→Gemini for analysis; Gemini→Ministral for parsing). Layer 2 itself was deliberately kept **LLM-free** — zero-cost retrieval.

### Uncommitted in the working tree (in flight)
Big refactor across 14 files (+831 / −248 lines):
- `ingestion/normalizer.py` — generic `_normalise_file_core` shared by individual + company normalisation; `company_normalizer.py` split out as a dedicated module.
- `cli.py` — `retrieve` command now displays company-appropriate fields (Company, Industry, Description, Region, LinkedIn).
- `campaign/parser.py` — stable ID assignment (`c1..cn`, `q1..qn`), JSON + schema validation with one retry each.
- Tests updated accordingly.

These are **not committed** — do not treat them as final until you review and approve.

---

## 3. How everything connects (data flow)

```
CSV/XLSX (Layer 0 input)
    │
    ▼
ingestion.normalizer / company_normalizer
    ├─ cleanup_header()            (camel/Pascal/snake/underscore → lower-case words)
    ├─ build_alias_mapping()       (ALIASES / COMPANY_ALIASES → canonical field)
    ├─ split_record_fields()       (canonical vs extra_fields)
    ├─ derive_country()            (GEO_HIERARCHY: city/state → country)
    └─ normalise_name_values()     (emoji strip, first/last inference)
    ▼
Prospect / CompanyProspect  (Pydantic v2, with source_file + source_row)
    │  saved as JSON (atomic .tmp write)  ──►  data/processed/*.json
    ▼
cli retrieve  ──►  nirite.retrieval.pipeline.run(prospects, campaign, top_n)
    │
    ├─ Tier 1: tier1_filter()                              (structured requirements/exclusions)
    │
    ├─ Tier 2: for each SearchQuery in query_plan:
    │      ├─ ListRetrievalAgent   (keyword overlap, zero-cost)
    │      └─ SemanticRetrievalAgent (TF-IDF + cosine, numpy, zero-cost)
    │      └─ per-query merge: union, best rank wins
    │
    └─ rrf_merge()                                    (Reciprocal Rank Fusion + dedup)
        ▼
RetrievalOutput  [Candidate{prospect_data, final_score, rank, queries_found, match_reasons}]
    │
    ▼  cli prints Rich table  (optional JSON save)
```

`prospect_data` is stored as a **plain dict** (not a Pydantic union) inside `ProspectEntry`/`Candidate` specifically to avoid Pydantic union ambiguity between `Prospect` and `CompanyProspect` while staying serialisable (retrieval/models.py docstring).

---

## 4. Layer 2 deep dive — file by file

### 4.1 `src/nirite/retrieval/models.py` — the data contracts

```python
class ProspectEntry(BaseModel):
    """A prospect with its per-query rank and score from a single retrieval agent."""
    prospect_data: dict          # model_dump(mode="json") of the Prospect/CompanyProspect
    prospect_type: str           # "individual" or "company"
    score: float = Field(ge=0.0)
    rank: int = Field(ge=1)

class QueryResult(BaseModel):
    query_id: str
    query: str
    facet: str
    entries: list[ProspectEntry]

class Candidate(BaseModel):
    """A deduplicated prospect with final RRF score and retrieval metadata."""
    prospect_data: dict
    prospect_type: str
    final_score: float = Field(ge=0.0)
    rank: int = Field(ge=1)
    queries_found: list[str] = Field(default_factory=list)   # which queries surfaced it
    match_reasons: list[str] = Field(default_factory=list)   # e.g. "matched 'Sydney engineer' (rank 1)"

class RetrievalOutput(BaseModel):
    candidates: list[Candidate]
    total_scanned: int = 0
    tier1_passed: int = 0
    queries_executed: int = 0
```

**Theory:** The `dict`-based `prospect_data` is a deliberate interface boundary. Layer 0 produces Pydantic models; Layer 2 flattens them to dicts so retrieval code never has to handle `Prospect | CompanyProspect` unions, and the output is JSON-serialisable for the CLI and any future UI/API.

### 4.2 `src/nirite/retrieval/tier1_filter.py` — Tier 1: deterministic filter

**Purpose:** Apply the *structured* requirements and exclusions from the campaign spec to cut a large prospect list down to a manageable subset before any scoring. Zero LLM cost, O(n), no mutation.

**Theory:** This is a precision-first prefilter. Requirements and exclusions are hard rules (boolean), so they belong in a deterministic tier. Preferences and semantic/hybrid criteria are intentionally *skipped* here — they belong to ranking (Tier 2), not gating, because a preference shouldn't disqualify a prospect and a semantic criterion can't be evaluated by field matching.

#### Key function: `get_field_value` (field resolution with alias fallback)
```python
def get_field_value(prospect, field_name):
    value = getattr(prospect, field_name, None)          # canonical field
    if value is not None: return value
    extra_fields = prospect.extra_fields
    value = extra_fields.get(field_name)                  # stored under canonical name in extras
    if value is not None: return value
    # ALIAS resolution: canonical + listed aliases as exact extra_fields keys
    for canonical, aliases in ALIASES.items():
        if field_name == canonical or field_name in aliases:
            names = [canonical, *aliases]; break
    for name in names:
        value = extra_fields.get(name)
        if value is not None: return value
    # Token-overlap fallback: predicate "city" reads "town", "city name", "person city", ...
    if names:
        wanted = {word for name in names for word in name.lower().split()}
        for key, value in extra_fields.items():
            if {word for word in key.lower().split()} & wanted:
                return value
    return None
```

**Theory:** Real-world prospect lists are messy — the same logical field appears under many header names. Layer 0 already maps known aliases to canonical fields, but anything unmapped lands in `extra_fields`. `get_field_value` resolves reads across three layers: canonical attribute → extra_fields exact alias → extra_fields token overlap. This makes Tier 1 robust to column-name variance without requiring the user to remap everything.

#### Key function: `evaluate_predicate`
Operators: `eq`, `neq`, `contains`, `in`, `exists`, `gt`, `gte`, `lt`, `lte`, `between`. String ops are case-insensitive; numeric ops convert both sides via `_to_float` and return `False` on non-numeric values (a prospect whose "company_name" is `"not_a_number"` is excluded from `gt` comparisons rather than crashing).

#### Key function: `_expand_geo_predicate` (legacy unenriched records)
```python
def _expand_geo_predicate(field, operator, value):
    if field != "country" or operator not in ("eq", "in"):
        return [(field, operator, value)]
    checks = [(field, operator, value)]
    countries = [value] if operator == "eq" else list(value)
    for country in countries:
        hierarchy = GEO_HIERARCHY.get(country, {})
        for state in hierarchy.get("states", set()):
            checks.append(("state", "eq", state))
        for city in hierarchy.get("cities", set()):
            checks.append(("city", "eq", city))
    return checks
```

**Theory:** Some legacy records were never enriched with a country but still have state/city. A country requirement like `country = Australia` should still match a prospect with `state = "Victoria"` or `city = "Melbourne"`. So the predicate expands into an OR of checks: country=Australia OR state∈{victoria, nsw, qld, vic} OR city∈{melbourne, sydney, brisbane, taringa}. Only `country` eq/in triggers expansion; everything else passes through unchanged. Unknown countries (e.g. Canada) produce just the original check.

#### `tier1_filter` itself
```python
requirements = [c for c in spec.criteria if _criterion_applies(c) and c.kind == REQUIREMENT]
exclusions   = [c for c in spec.criteria if _criterion_applies(c) and k.kind == EXCLUSION]

for prospect in prospects:
    if requirements and not all(_prospect_passes(c.predicate, prospect) for c in requirements):
        continue          # AND across requirements
    if exclusions and any(_prospect_passes(c.predicate, prospect) for c in exclusions):
        continue          # OR across exclusions (any match = out)
    result.append(prospect)
```

`_criterion_applies` gates on `evaluation_mode == STRUCTURED` AND kind in {requirement, exclusion} AND predicate is not None. So semantic requirements, hybrid criteria, and preferences all pass through Tier 1 untouched.

### 4.3 `src/nirite/retrieval/agents.py` — Tier 2: two retrieval agents

Both agents run **per query** over the Tier-1-passed subset and return `ProspectEntry`s. Neither mutates input. Both are deterministic and zero-cost.

#### Agent A: `ListRetrievalAgent` — lexical keyword match
```python
terms = _tokenise(query)                       # re.findall(r"\w+", text.lower())
for prospect in prospects:
    text = _prospect_text(prospect)            # all non-source fields joined
    text_counter = Counter(_tokenise(text))
    match_count = sum(text_counter.get(t, 0) for t in terms)
    if match_count == 0: continue
    score = float(match_count)                 # raw term-frequency overlap
    ...
scored.sort(key=lambda item: (-item[1], item[0]))   # desc score, stable by discovery order
```

**Theory:** Bag-of-words term overlap. Cheap, interpretable, handles exact keyword matches (e.g. query "SaaS company" matches a prospect whose industry/description contains "saas"). Weakness: no synonym handling, no weighting by term rarity — every token counts equally.

`_prospect_text` combines every field (sorted by name, skipping `source_file`/`source_row`/`extra_fields` keys themselves but including extra field *values*), so the agent searches the whole record, not just one column.

#### Agent B: `SemanticRetrievalAgent` — TF-IDF + cosine similarity (numpy only)
```python
# Build shared vocabulary from documents + query
# tf[d_idx, vocab[token]] = count / doc_len        (term frequency, length-normalised)
# doc_freq[vocab[token]] += 1                       (document frequency)
# idf = log((n_docs + 1) / (doc_freq + 1)) + 1.0    (smoothed IDF)
# tfidf = tf * idf
# q_vec = TF-IDF of query tokens over same vocabulary
# similarities = cosine(tfidf matrix, q_vec)
# rank by similarity desc, stable tie-break by original order; skip similarity == 0
```

**Theory:** Classic vector-space retrieval (Salton, 1970s). TF-IDF downweights terms that appear in every document (e.g. "company", "engineer") and upweights rare, distinctive terms. Cosine similarity measures the angle between the query vector and each prospect document — direction matters, magnitude doesn't, so longer records aren't automatically favoured. Smoothed IDF (`+1`) avoids division-by-zero and negative IDF for terms in all docs.

**Design note (from the module docstring):** The agent is written so a sentence-transformers / embedding backend can be swapped in later without changing the interface — `retrieve(prospects, query, query_id) -> list[ProspectEntry]` stays the same. This keeps Nirite zero-cost today (numpy only, no vector DB, no paid embedding API) while leaving an upgrade path.

#### Why two agents per query?
List (lexical) and semantic retrieval have complementary failure modes: lexical misses synonyms; semantic can miss exact brand/model names. Running both and taking the **union, best rank wins** (pipeline.py lines 49-53) gives higher recall with no LLM cost:

```python
merged: dict[str, ProspectEntry] = {}
for entry in list_entries + semantic_entries:
    key = dedup_key(entry.prospect_data)
    if key not in merged or entry.rank < merged[key].rank:
        merged[key] = entry
```

### 4.4 `src/nirite/retrieval/rrf.py` — Reciprocal Rank Fusion + dedup

**Theory:** RRF (Cormack, Clarke, Cormack — SIGIR 2009) combines multiple ranked result lists **without needing score calibration**. Each list contributes `1 / (k + rank)` where `k = 60` (a constant that dampens the influence of low ranks). A result ranked 1st contributes ~1/61 ≈ 0.0164; ranked 10th contributes ~1/70 ≈ 0.0143; ranked 100th ≈ 1/160 ≈ 0.0062. Because it's rank-based, it's robust to the fact that ListRetrievalAgent scores are raw counts (0..N) while SemanticRetrievalAgent scores are cosines (0..1) — the two agents' raw scores aren't directly comparable, but their *ranks* are.

**Cross-query consensus:** A prospect surfaced by multiple independent queries gets multiple RRF terms, so consensus across queries naturally rises to the top.

Nirite's implementation (`rrf_merge`):
```python
scores[key] = scores.get(key, 0.0) + 1.0 / (k + entry.rank)   # RRF accumulation
# ... per query, per entry ...

# Cross-query bonus:
num_queries = len(query_buckets.get(key, []))
bonus = 1.0 + 0.25 * max(0, num_queries - 1)   # 1st query = 1.0x, 2nd = 1.25x, 3rd = 1.5x
final_score = base_score * bonus

scored.sort(key=lambda item: (-item[1], -item[2], item[0]))  # desc score, desc #queries, asc key
```

**Dedup key:** `f"{source_file}:{source_row}"` — the Layer 0 source tracking fields. The same physical prospect (same file + row) surfaced by query "Sydney engineer" and query "engineer Australia" collapses into one `Candidate` with `queries_found = ["q1", "q2"]` and aggregated `match_reasons`.

**Ticket D / E guard:** entries with `score <= 0` are skipped entirely — zero-score prospects never accumulate RRF score.

**Output:** top-N after sorting, ranks reassigned sequentially (1, 2, 3…). `RetrievalOutput.total_scanned` counts all entries across query results (for observability), `tier1_passed` and `queries_executed` are recorded.

### 4.5 `src/nirite/retrieval/pipeline.py` — the orchestrator

```python
def run(prospects, campaign, top_n=20) -> RetrievalOutput:
    spec = campaign.spec
    query_plan = campaign.query_plan

    # Step 1: Tier 1 deterministic filter
    tier1_passed = tier1_filter(prospects, spec)
    total_scanned = len(prospects)

    # Step 2: Tier 2 — both agents per query; per-query merge (best rank wins)
    list_agent = ListRetrievalAgent()
    semantic_agent = SemanticRetrievalAgent()
    query_results = []
    for query in query_plan.queries:
        list_entries   = list_agent.retrieve(tier1_passed, query.query, query.id)
        semantic_entries = semantic_agent.retrieve(tier1_passed, query.query, query.id)
        merged = {}
        for entry in list_entries + semantic_entries:
            key = dedup_key(entry.prospect_data)
            if key not in merged or entry.rank < merged[key].rank:
                merged[key] = entry
        query_results.append(QueryResult(query.id, query.query, query.facet.value, list(merged.values())))

    # Step 3: RRF merge + dedup → top-N
    output = rrf_merge(query_results, top_n=top_n, tier1_passed=len(tier1_passed))
    output.total_scanned = total_scanned
    return output
```

**Theory:** This is the "funnel" — narrow deterministically (Tier 1), then score broadly but cheaply (Tier 2 × both agents × all queries), then fuse and deduplicate (RRF). Input is never mutated (tests assert `prospects == original` after `run`). Each query's facet is recorded on the `QueryResult` for potential future UI grouping.

---

## 5. Worked example

Campaign: *"Find SaaS companies in Australia, prioritise ones investing in AI."*

Layer 1 produces:
- c1: requirement, structured, `company_domain`/`industry` contains SaaS (structured predicate)
- c2: requirement, structured, `country` = Australia
- c3: preference, semantic, "investing in AI" (no predicate — skipped by Tier 1)
- queries: q1="SaaS company Australia", q2="AI investing SaaS", q3="Sydney software company"

Given 1,000 ingested prospects:
1. **Tier 1:** keep only structured requirement matches → maybe 40 companies pass (SaaS + Australia). Preferences and the semantic "investing in AI" criterion are skipped here.
2. **Tier 2 per query:** ListRetrievalAgent and SemanticRetrievalAgent each score the 40 against q1/q2/q3 → e.g. 12 + 15 entries per query, merged to ~20 unique per query.
3. **RRF:** fuse the 3 per-query lists. A company ranked highly by both q1 and q2 (cross-query consensus) gets a bonus and ranks #1. Dedup by `source_file:source_row` ensures each company appears once.
4. **Output:** top-20 `Candidate`s, each with `final_score`, `queries_found`, `match_reasons` — the CLI prints these and you can see *why* each prospect qualified.

---

## 6. Key design principles (the "why")

1. **Zero-cost retrieval.** No embeddings, no vector DB, no paid API in Layer 2. TF-IDF + cosine runs on numpy. Consistent with the product constraint (free models only; expensive model = overkill — GBrain fact #44).

2. **Deterministic first, probabilistic second.** Tier 1 gives explainable, auditable hard filtering. Tier 2 gives soft ranking. You can always inspect *why* a prospect passed Tier 1 (predicate + field value) and why it ranked where it did (RRF score + queries_found + match_reasons).

3. **Rank fusion over score fusion.** RRF avoids having to calibrate keyword counts against cosine similarities. It also naturally rewards multi-query appearance — a core product insight from GBrain fact #23 ("reward prospects appearing across multiple relevant query results").

4. **No input mutation.** Every Layer 2 function returns new lists/objects. This makes the pipeline safe to call repeatedly and easy to test.

5. **Interface stability for the semantic agent.** `SemanticRetrievalAgent` is written so a sentence-transformers backend can be swapped in later without changing `retrieve()`'s signature — but nothing is added until there's demonstrated value (GBrain fact #23: "avoid prematurely introducing complicated AI agents").

6. **Layer 0 provenance carries through.** `source_file` + `source_row` flow from ingestion → `Prospect` → `model_dump` dict → dedup key → `Candidate`. This is how a candidate can be traced back to its original spreadsheet row.

---

## 7. Running it

```bash
# From /workspace, with the venv activated:
uv run python -m nirite ingest data/raw/leads.csv -o data/processed/leads.json -k individual
uv run python -m nirite campaign "Find SaaS companies in Australia" -o data/campaign.json
uv run python -m nirite retrieve data/processed/leads.json data/campaign.json -n 20 -o data/results.json
```

Tests:
```bash
uv run pytest tests/retrieval/ -q        # Layer 2 tests
uv run pytest -q                         # full suite (152 tests pass per PLANNER_PROMPT.md)
uv run ruff check src/nirite tests
uv run mypy src/nirite
```

---

## 8. What to watch next (backlog)

From `PLANNER_PROMPT.md` and the working tree:
- **Item 3:** `CampaignAnalyser` retries only on HTTP 503 — decide whether to broaden retry (likely leave as-is; document).
- **Item 6:** five empty `__init__.py` files — decide whether to add exports (be consistent).
- **Item 5:** persistence/cross-session dedup store — **deferred, needs your approval** (SQLite recommended if revisited; zero-cost, single file).

No commits have been made on the working-tree changes yet — review them before committing.

---

## 9. Quick reference: Layer 2 call graph

```
cli.retrieve
└── retrieval.pipeline.run
    ├── retrieval.tier1_filter.tier1_filter
    │   ├── get_field_value          (canonical → extra_fields alias → token overlap)
    │   ├── evaluate_predicate       (eq/neq/contains/in/exists/gt/gte/lt/lte/between)
    │   └── _expand_geo_predicate    (country → state/city OR checks via GEO_HIERARCHY)
    ├── retrieval.agents.ListRetrievalAgent.retrieve      (token overlap count)
    ├── retrieval.agents.SemanticRetrievalAgent.retrieve  (TF-IDF + cosine, numpy)
    └── retrieval.rrf.rrf_merge
        ├── dedup_key                (source_file:source_row)
        └── cross-query bonus        (1 + 0.25 × (n_queries − 1))
```

If you want, I can next walk you through a specific file line-by-line, add a test for a gap you've spotted, or sketch the semantic-agent → embeddings swap path.
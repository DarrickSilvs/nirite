"""Tier 2 retrieval agents.

Two pluggable agents run per search query:

* ``ListRetrievalAgent`` — keyword + field search over the Tier 1 filtered
  subset (fast, zero-cost).
* ``SemanticRetrievalAgent`` — TF-IDF + cosine similarity over prospect text
  using numpy only (zero-cost, no vector DB, no paid API).

Both are deterministic and return ``ProspectEntry`` objects without mutating
their inputs.  The semantic agent is designed so a sentence-transformers
backend can be swapped in later without changing the interface.
"""

from __future__ import annotations

import re
from collections import Counter

import numpy as np

from nirite.models.company import CompanyProspect
from nirite.models.prospect import Prospect

from nirite.retrieval.models import ProspectEntry


def _tokenise(text: str) -> list[str]:
    return [t for t in re.findall(r"\w+", text.lower()) if t]


def _prospect_text(prospect: Prospect | CompanyProspect) -> str:
    """Combine all text fields of a prospect into one document for search."""

    parts: list[str] = []
    for name in sorted(vars(prospect)):
        if name in ("source_file", "source_row", "extra_fields"):
            continue
        value = getattr(prospect, name, None)
        if value:
            parts.append(str(value))
    for value in prospect.extra_fields.values():
        if value:
            parts.append(str(value))
    return " ".join(parts)


def _entry_from_prospect(
    prospect: Prospect | CompanyProspect, rank: int, score: float
) -> ProspectEntry:
    """Build a ProspectEntry from a prospect, rank, and score."""
    return ProspectEntry(
        prospect_data=prospect.model_dump(mode="json"),
        prospect_type="company"
        if isinstance(prospect, CompanyProspect)
        else "individual",
        score=score,
        rank=rank,
    )


class ListRetrievalAgent:
    """Keyword + field search within the filtered subset."""

    def retrieve(
        self,
        prospects: list[Prospect | CompanyProspect],
        query: str,
        query_id: str,
    ) -> list[ProspectEntry]:
        terms = _tokenise(query)
        scored: list[tuple[int, float, Prospect | CompanyProspect]] = []

        for prospect in prospects:
            text = _prospect_text(prospect)
            text_tokens = _tokenise(text)
            text_counter = Counter(text_tokens)

            match_count = sum(text_counter.get(t, 0) for t in terms)
            if match_count == 0:
                continue
            score = float(match_count)
            scored.append((len(scored), score, prospect))

        scored.sort(key=lambda item: (-item[1], item[0]))

        entries: list[ProspectEntry] = []
        for rank, (_, score, prospect) in enumerate(scored, start=1):
            entries.append(_entry_from_prospect(prospect, rank, score))
        return entries


class SemanticRetrievalAgent:
    """TF-IDF + cosine similarity over prospect text (numpy only)."""

    def retrieve(
        self,
        prospects: list[Prospect | CompanyProspect],
        query: str,
        query_id: str,
    ) -> list[ProspectEntry]:
        if not prospects:
            return []

        query_tokens = _tokenise(query)
        documents = [_prospect_text(p) for p in prospects]

        # Build shared vocabulary from documents and query.
        vocab: dict[str, int] = {}
        index = 0
        for doc in documents:
            for token in _tokenise(doc):
                if token not in vocab:
                    vocab[token] = index
                    index += 1
        for token in query_tokens:
            if token not in vocab:
                vocab[token] = index
                index += 1

        n_docs = len(documents)
        vocab_size = len(vocab)
        if vocab_size == 0:
            return []

        # Term frequency per document.
        tf = np.zeros((n_docs, vocab_size))
        doc_freq = np.zeros(vocab_size)

        for d_idx, doc in enumerate(documents):
            tokens = _tokenise(doc)
            counter = Counter(tokens)
            doc_len = len(tokens)
            for token, count in counter.items():
                tf[d_idx, vocab[token]] = count / doc_len if doc_len else 0.0
                doc_freq[vocab[token]] += 1

        # IDF with smoothing.
        idf = np.log((n_docs + 1) / (doc_freq + 1)) + 1.0
        tfidf = tf * idf[None, :]

        # Query vector: TF-IDF of query tokens against the same vocabulary.
        q_vec = np.zeros(vocab_size)
        q_len = len(query_tokens)
        q_counter = Counter(query_tokens)
        for token, count in q_counter.items():
            if token in vocab:
                q_vec[vocab[token]] = (
                    (count / q_len if q_len else 0.0) * idf[vocab[token]]
                )

        similarities = self._cosine_similarity(tfidf, q_vec)

        # Rank by similarity descending; tie-break by original order.
        order = np.argsort(-similarities, kind="stable")

        entries: list[ProspectEntry] = []
        for rank, d_idx in enumerate(order, start=1):
            similarity = float(similarities[d_idx])
            if similarity == 0.0:
                continue
            prospect = prospects[d_idx]
            entries.append(
                _entry_from_prospect(prospect, rank, similarity)
            )
        return entries

    @staticmethod
    def _cosine_similarity(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(matrix, axis=1)
        q_norm = np.linalg.norm(vector)
        if q_norm == 0 or np.all(norms == 0):
            return np.zeros(matrix.shape[0])
        return (matrix @ vector) / (norms * q_norm)

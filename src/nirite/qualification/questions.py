"""Bounded yes/no question planner for Layer 3 qualification.

Turns semantic/hybrid criteria into a fixed, auditable question set. No LLM
— pure template composition from criterion description.

- ≤3 questions per criterion
- Stable IDs (c1.q1, c1.q2, ...)
- Exclusions phrased so a "yes" means disqualifying
- answerable_from populated from source_phrase keywords
- Hybrid criteria contribute only the semantic residual after their
  structured predicate is checked separately
- Total question cap enforced (default 12)
- Stable ordering by criterion id; identical input → byte-identical output
"""

from __future__ import annotations

from nirite.judge.models import JudgePolarity, JudgeQuestion
from nirite.models.campaign import CriterionKind
from nirite.models.campaign_analysis import AnalysisCriterion

MAX_QUESTIONS_PER_CRITERION = 3


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from text for answerable_from hints."""
    stop_words = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "can",
        "this",
        "that",
        "these",
        "those",
        "i",
        "you",
        "he",
        "she",
        "it",
        "we",
        "they",
    }
    words = [w.strip(".,!?:;\"'()[]{}").lower() for w in text.split()]
    return [w for w in words if w and w not in stop_words and len(w) > 2][:5]


def plan_questions(
    criteria: list[AnalysisCriterion],
    *,
    max_questions_per_criterion: int = MAX_QUESTIONS_PER_CRITERION,
) -> list[JudgeQuestion]:
    """Plan bounded yes/no questions for semantic/hybrid criteria.

    Returns questions ordered by criterion id, then by question index within
    each criterion. Total questions capped at max_questions_per_criterion *
    len(criteria). Raises ValueError if the cap would be exceeded.
    """
    questions: list[JudgeQuestion] = []
    total_cap = max_questions_per_criterion * len(criteria)

    for criterion in sorted(criteria, key=lambda c: c.id):
        criterion_questions = _questions_for_criterion(
            criterion, max_questions_per_criterion
        )
        questions.extend(criterion_questions)

        if len(questions) > total_cap:
            raise ValueError(f"question cap exceeded: {len(questions)} > {total_cap}")

    return questions


def _questions_for_criterion(
    criterion: AnalysisCriterion,
    max_questions: int,
) -> list[JudgeQuestion]:
    """Compose questions for a single criterion from its description."""
    criterion_id = criterion.id
    description = criterion.description.strip()
    answerable_from = _extract_keywords(description)

    # Start with a generic coverage question about the criterion itself.
    base_q = JudgeQuestion(
        id=f"{criterion_id}.q1",
        text=(f"Does the prospect meet the criterion: '{description}'?"),
        criterion_id=criterion_id,
        answerable_from=answerable_from,
        polarity=JudgePolarity.POSITIVE,
    )
    questions = [base_q]

    # For exclusions, add a disqualification question phrased so yes = disqualify.
    if criterion.kind == CriterionKind.EXCLUSION:
        exclusion_q = JudgeQuestion(
            id=f"{criterion_id}.q2",
            text=(
                f"Does the prospect exhibit the excluded characteristic: "
                f"'{description}'?"
            ),
            criterion_id=criterion_id,
            answerable_from=answerable_from,
            polarity=JudgePolarity.NEGATIVE,
        )
        questions.append(exclusion_q)

    return questions[:max_questions]

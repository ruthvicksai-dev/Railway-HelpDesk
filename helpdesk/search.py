"""
Search and Retrieval Module

Responsible for:
1. BM25 keyword search over document chunks
2. Document-name matching boost
3. Recency boost for newer railway rules
4. Query-specific filtering for fare questions
5. Railway policy query expansion
6. Returning the most relevant chunks for answer generation

Called by pipeline.py as: search(question, k=5)

Owner: Member 3 - Search & Retrieval
"""

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent

INDEX_DIR = PROJECT_ROOT / "index"
CHUNKS_PATH = INDEX_DIR / "chunks.json"
SEARCH_INDEX_PATH = INDEX_DIR / "search_index.json"


# BM25 parameters

BM25_K1 = 1.5
BM25_B = 0.75


# Small boost when query words appear in the document filename.
DOC_NAME_BOOST = 0.5


# Newer documents receive a small ranking boost.
RECENCY_WEIGHT = 0.15


# Normal BM25 score required for a result.
MIN_SCORE = 3.0


# Policy queries can use a lower threshold because railway rules
# often use wording different from the passenger's wording.
POLICY_FALLBACK_MIN_SCORE = 0.75

# Stopwords

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "am",
    "of", "to", "in", "on", "for", "at", "by", "with", "from", "as",
    "and", "or", "not", "no", "if", "then", "than", "that", "this",
    "these", "those", "it", "its", "i", "me", "my", "we", "our", "you",
    "your", "he", "she", "they", "them", "their", "what", "which", "who",
    "whom", "when", "where", "why", "how", "do", "does", "did", "can",
    "could", "will", "would", "shall", "should", "may", "might", "must",
    "there", "here", "about", "into", "any", "all", "some", "such",
    "so", "also", "get", "got", "has", "have", "had", "per",

    # Metadata added by ingest.py.
    "document", "page", "date", "ocr", "extracted", "pdf", "html",
}


# Text cleaning/tokenization

_HEADER_RE = re.compile(
    r"^Document:.*?\|.*?Page:.*?\|.*?(?:\n|$)",
    re.IGNORECASE,
)

_OCR_TAG_RE = re.compile(
    r"\[OCR Extracted Page\]",
    re.IGNORECASE,
)

_TOKEN_RE = re.compile(
    r"[a-z0-9]+(?:[.\-/][a-z0-9]+)*"
)


# Fare query detection

FARE_QUERY_PATTERNS = [
    r"\bfare\b",
    r"\bprice\b",
    r"\bcost\b",
    r"\bticket\s+price\b",
    r"\bticket\s+fare\b",
]

FARE_EVIDENCE_PATTERNS = [
    r"\bfare\s+table\b",
    r"\bfare\s+chart\b",
    r"\bpassenger\s+fare\b",
    r"\bticket\s+fare\b",
    r"\bticket\s+price\b",
    r"\bbase\s+fare\b",
    r"\btariff\b",
    r"\bpricing\b",
    r"\bprice\s+of\s+(?:a\s+)?ticket\b",
]


# Policy query detection

POLICY_QUERY_PATTERNS = [
    r"\brefund\b",
    r"\bcancel\b",
    r"\bcancellation\b",
    r"\bcancelled\b",
    r"\bclerkage\b",
    r"\btdr\b",
    r"\btatkal\b",
    r"\bwaitlisted\b",
    r"\bwaitlisted\b",
    r"\bwait-list\b",
    r"\bwaitlist\b",
    r"\bwaiting\s+list\b",
    r"\bconfirmed\b",
    r"\bbooking\b",
    r"\breservation\b",
    r"\bdeducted\b",
    r"\bdeduction\b",
]


# Railway policy vocabulary expansion
# The source documents and passenger questions may use different words
# for the same railway concept. These are intentionally small and
# domain-specific rather than a general synonym dictionary.

POLICY_EXPANSIONS = {
    "deducted": {
        "deduction",
        "deducting",
        "deduct",
        "clerkage",
        "charge",
        "charges",
    },
    "deduction": {
        "deducted",
        "deducting",
        "deduct",
        "clerkage",
        "charge",
        "charges",
    },
    "deduct": {
        "deduction",
        "deducted",
        "deducting",
        "clerkage",
        "charge",
        "charges",
    },
    "clerkage": {
        "deduction",
        "deducted",
        "charge",
        "charges",
    },

    "waitlisted": {
        "waitlisted",
        "wait-list",
        "waitlist",
        "waiting",
        "list",
        "wl",
        "rac",
    },
    "wait-list": {
        "waitlisted",
        "waitlist",
        "waiting",
        "list",
        "wl",
        "rac",
    },
    "waitlist": {
        "waitlisted",
        "wait-list",
        "waiting",
        "list",
        "wl",
        "rac",
    },

    "cancel": {
        "cancellation",
        "cancelled",
        "cancelling",
    },
    "cancelled": {
        "cancel",
        "cancellation",
        "cancelling",
    },
    "cancellation": {
        "cancel",
        "cancelled",
        "cancelling",
    },

    "refund": {
        "refundable",
        "fare",
        "cancellation",
        "cancel",
    },

    "vande": {
        "vande",
        "bharat",
        "sleeper",
    },
    "bharat": {
        "vande",
        "bharat",
        "sleeper",
    },
    "sleeper": {
        "vande",
        "bharat",
    },

    "confirmed": {
        "reservation",
        "reserved",
        "ticket",
    },

    "tatkal": {
        "tatkal",
        "cancellation",
        "refund",
    },
}


# Helpers

_INDEX: Optional[Dict[str, Any]] = None


def tokenize(text: str) -> List[str]:
    """
    Convert text into lowercase search tokens.

    Compound tokens are kept as well as their individual parts.

    Examples:
        e-ticket -> e-ticket, e, ticket
        12.11.2015 -> 12.11.2015, 12, 11, 2015
        wait-listed -> wait-listed, wait, listed
    """

    tokens = []

    for tok in _TOKEN_RE.findall(text.lower()):
        parts = re.split(r"[.\-/]", tok)

        candidates = [tok] + parts if len(parts) > 1 else [tok]

        for token in candidates:
            if token and token not in STOPWORDS:
                tokens.append(token)

    return tokens


def clean_for_index(text: str) -> str:
    """
    Remove metadata/header text added during document ingestion.
    """

    text = _HEADER_RE.sub("", text, count=1)
    text = _OCR_TAG_RE.sub("", text)

    return text


def _date_to_year(date_str: Optional[str]) -> Optional[float]:
    """
    Convert YYYY-MM-DD into a fractional year.
    """

    if not date_str:
        return None

    match = re.match(
        r"(\d{4})-(\d{2})-(\d{2})",
        date_str,
    )

    if not match:
        return None

    year, month, day = (
        int(value)
        for value in match.groups()
    )

    return year + (month - 1) / 12 + (day - 1) / 365


def _is_fare_query(question: str) -> bool:
    """
    Check whether the user is asking about the original ticket fare
    or ticket price.

    "How much" by itself is not enough because policy questions such
    as "How much is deducted?" are not fare questions.
    """

    question_lower = question.lower()

    # Explicit fare/price terminology.
    if any(
        re.search(pattern, question_lower)
        for pattern in [
            r"\bfare\b",
            r"\bprice\b",
            r"\bcost\b",
            r"\bticket\s+price\b",
            r"\bticket\s+fare\b",
        ]
    ):
        return True

    # "How much" is a fare question only when the question also
    # clearly refers to buying/paying for a ticket.
    if re.search(r"\bhow\s+much\b", question_lower):
        fare_context_terms = [
            "ticket",
            "3ac",
            "2ac",
            "1ac",
            "sleeper",
            "chair car",
            "executive chair car",
            "second class",
            "first class",
            "rajdhani",
            "shatabdi",
            "train ticket",
            "pay",
            "purchase",
            "buy",
        ]

        policy_terms = [
            "deduct",
            "deducted",
            "deduction",
            "clerkage",
            "refund",
            "cancel",
            "cancellation",
            "waitlisted",
            "wait-listed",
            "waitlist",
            "tdr",
        ]

        has_fare_context = any(
            term in question_lower
            for term in fare_context_terms
        )

        has_policy_context = any(
            term in question_lower
            for term in policy_terms
        )

        # Policy meaning wins.
        if has_policy_context:
            return False

        return has_fare_context

    return False


def _is_policy_query(question: str) -> bool:
    """
    Check whether the question is about railway rules,
    refunds, cancellation, reservation, or related policy.
    """

    question_lower = question.lower()

    return any(
        re.search(pattern, question_lower)
        for pattern in POLICY_QUERY_PATTERNS
    )


def _has_fare_evidence(text: str) -> bool:
    """
    Check whether a document chunk contains actual ticket fare
    information, not refund or cancellation charges.
    """

    cleaned_text = clean_for_index(text).lower()

    # These indicate that the amount is related to refund/cancellation
    # rather than the original ticket fare.
    exclusion_terms = [
        "refund",
        "refundable",
        "cancellation",
        "cancelled",
        "cancel",
        "clerkage",
        "tdr",
        "deduction",
        "deducted",
    ]

    if any(
        term in cleaned_text
        for term in exclusion_terms
    ):
        return False

    return any(
        re.search(pattern, cleaned_text)
        for pattern in FARE_EVIDENCE_PATTERNS
    )


def _expand_policy_terms(
    question: str,
    query_terms: List[str],
) -> List[str]:
    """
    Add controlled railway-policy synonyms to the query.

    This does not replace the original query terms. It only adds
    closely related railway terminology that may appear in the
    source document.
    """

    expanded = list(query_terms)

    for term in query_terms:
        expanded.extend(
            POLICY_EXPANSIONS.get(term, set())
        )

    # Handle common hyphenated/word-form variations explicitly.
    question_lower = question.lower()

    if "waitlisted" in question_lower:
        expanded.extend(
            [
                "waitlisted",
                "wait-listed",
                "waitlist",
                "waiting",
                "list",
                "wl",
                "rac",
            ]
        )

    if "deducted" in question_lower:
        expanded.extend(
            [
                "deducted",
                "deducting",
                "deduction",
                "clerkage",
            ]
        )

    if any(
        word in question_lower
        for word in [
            "cancel",
            "cancellation",
            "cancelled",
        ]
    ):
        expanded.extend(
            [
                "cancel",
                "cancellation",
                "cancelled",
                "charges",
                "charge",
            ]
        )

    if "vande bharat" in question_lower:
        expanded.extend(
            [
                "vande",
                "bharat",
                "sleeper",
                "express",
            ]
        )

    # A passenger asking about a number of hours is often asking
    # which cancellation time band the rule falls into.
    if re.search(r"\b\d+\s*hours?\b", question_lower):
        expanded.extend(
            [
                "hours",
                "hour",
                "before",
                "scheduled",
                "departure",
            ]
        )

    # Remove duplicates while preserving order.
    return list(
        dict.fromkeys(
            token
            for token in expanded
            if token
        )
    )


def build_search_index(
    chunks: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Build BM25 statistics and ranking metadata.
    """

    term_freqs = []
    doc_lengths = []
    doc_freq: Counter = Counter()

    for chunk in chunks:
        text = clean_for_index(
            chunk.get("text", "")
        )

        tokens = tokenize(text)

        tf = Counter(tokens)

        term_freqs.append(dict(tf))
        doc_lengths.append(len(tokens))
        doc_freq.update(tf.keys())

    number_of_chunks = len(chunks)

    avgdl = (
        sum(doc_lengths) / number_of_chunks
        if number_of_chunks
        else 0.0
    )

    idf = {
        term: math.log(
            1 + (number_of_chunks - df + 0.5)
            / (df + 0.5)
        )
        for term, df in doc_freq.items()
    }

    # Calculate recency boost.
    years = [
        _date_to_year(
            chunk.get("document_date")
        )
        for chunk in chunks
    ]

    known_years = [
        year
        for year in years
        if year is not None
    ]

    if known_years:
        oldest = min(known_years)
        newest = max(known_years)
    else:
        oldest = 0.0
        newest = 0.0

    recency = []

    for year in years:
        if year is None or oldest == newest:
            recency.append(1.0)
        else:
            boost = (
                (year - oldest)
                / (newest - oldest)
            )

            recency.append(
                1.0 + RECENCY_WEIGHT * boost
            )

    # Tokenize document filenames for a small filename boost.
    doc_name_tokens = [
        sorted(
            set(
                tokenize(
                    chunk.get("doc", "")
                    .replace("_", " ")
                )
            )
        )
        for chunk in chunks
    ]

    return {
        "chunks": chunks,
        "term_freqs": term_freqs,
        "doc_lengths": doc_lengths,
        "avgdl": avgdl,
        "idf": idf,
        "recency": recency,
        "doc_name_tokens": doc_name_tokens,
    }


def save_search_index(
    index: Dict[str, Any],
    path: Path = SEARCH_INDEX_PATH,
) -> None:
    """
    Save the search index to disk.
    """

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            index,
            file,
            ensure_ascii=False,
        )


def _load_index() -> Dict[str, Any]:
    """
    Load the search index once and cache it.

    Uses search_index.json when available.
    Otherwise builds an index from chunks.json.
    """

    global _INDEX

    if _INDEX is not None:
        return _INDEX

    if SEARCH_INDEX_PATH.exists():
        with open(
            SEARCH_INDEX_PATH,
            "r",
            encoding="utf-8",
        ) as file:
            _INDEX = json.load(file)

    elif CHUNKS_PATH.exists():
        with open(
            CHUNKS_PATH,
            "r",
            encoding="utf-8",
        ) as file:
            chunks = json.load(file)

        _INDEX = build_search_index(chunks)

    else:
        raise FileNotFoundError(
            "No search index found. Run "
            "'python build_index.py' first."
        )

    return _INDEX


def _calculate_bm25_score(
    query_terms: List[str],
    term_frequency: Dict[str, int],
    document_length: int,
    average_document_length: float,
    idf: Dict[str, float],
) -> float:
    """
    Calculate BM25 score for one document chunk.
    """

    score = 0.0

    for term in query_terms:
        frequency = term_frequency.get(term)

        if not frequency:
            continue

        denominator = (
            frequency
            + BM25_K1
            * (
                1
                - BM25_B
                + BM25_B
                * document_length
                / average_document_length
            )
        )

        score += (
            idf.get(term, 0.0)
            * frequency
            * (BM25_K1 + 1)
            / denominator
        )

    return score


def _policy_relevance_boost(
    question: str,
    chunk_text: str,
    doc_name: str,
) -> float:
    """
    Add a small, controlled relevance boost for railway policy concepts.

    This is intentionally separate from BM25. It helps when the user
    and source use different but well-known railway terminology.
    """

    question_lower = question.lower()
    text_lower = chunk_text.lower()
    doc_lower = doc_name.lower()

    boost = 0.0

    # Waitlisted/RAC cancellation policy.
    if any(
        term in question_lower
        for term in [
            "waitlisted",
            "wait-listed",
            "waitlist",
            "waiting list",
            "rac",
        ]
    ):
        if any(
            term in text_lower
            for term in [
                "wait-listed",
                "waitlisted",
                "wait list",
                "wait-list",
                "rac",
                "clerkage",
            ]
        ):
            boost += 2.0

    # Deduction/clerkage terminology.
    if any(
        term in question_lower
        for term in [
            "deducted",
            "deduction",
            "clerkage",
        ]
    ):
        if any(
            term in text_lower
            for term in [
                "deduct",
                "clerkage",
                "cancellation charge",
            ]
        ):
            boost += 2.0

    # Vande Bharat Sleeper is a very strong document identifier.
    if "vande bharat" in question_lower:
        if (
            "vande bharat" in text_lower
            or (
                "vande" in text_lower
                and "bharat" in text_lower
            )
        ):
            boost += 3.0

        if "vande_bharat_sleeper" in doc_lower:
            boost += 2.0

    # Cancellation/refund policy.
    if any(
        term in question_lower
        for term in [
            "refund",
            "cancel",
            "cancellation",
        ]
    ):
        if any(
            term in text_lower
            for term in [
                "refund",
                "cancellation",
                "cancel",
            ]
        ):
            boost += 1.0

    # Time-window questions should prefer chunks that explicitly
    # discuss hours before scheduled departure.
    if re.search(
        r"\b\d+\s*hours?\b",
        question_lower,
    ):
        if any(
            term in text_lower
            for term in [
                "hours",
                "hour",
                "before the scheduled",
                "scheduled departure",
            ]
        ):
            boost += 1.0

    return boost


def _rank_results(
    question: str,
    index: Dict[str, Any],
) -> List[Any]:
    """
    Calculate BM25 scores and return ranked results.

    Policy queries use controlled terminology expansion and
    policy-specific relevance boosts.
    """

    original_terms = list(
        dict.fromkeys(
            tokenize(question)
        )
    )

    if not original_terms:
        return []

    policy_query = _is_policy_query(question)

    if policy_query:
        query_terms = _expand_policy_terms(
            question,
            original_terms,
        )
    else:
        query_terms = original_terms

    average_document_length = (
        index["avgdl"] or 1.0
    )

    fare_query = _is_fare_query(question)

    scored = []

    for i, term_frequency in enumerate(
        index["term_freqs"]
    ):
        chunk = index["chunks"][i]

        # Fare questions require actual fare/pricing evidence.
        if fare_query:
            chunk_text = chunk.get("text", "")

            if not _has_fare_evidence(chunk_text):
                continue

        document_length = index["doc_lengths"][i]

        score = _calculate_bm25_score(
            query_terms=query_terms,
            term_frequency=term_frequency,
            document_length=document_length,
            average_document_length=average_document_length,
            idf=index["idf"],
        )

        if score <= 0:
            continue

        # Original query terms receive the normal filename boost.
        name_hits = sum(
            1
            for term in original_terms
            if term in index["doc_name_tokens"][i]
        )

        score += DOC_NAME_BOOST * name_hits

        # Policy-specific relevance boost.
        if policy_query:
            score += _policy_relevance_boost(
                question=question,
                chunk_text=chunk.get("text", ""),
                doc_name=chunk.get("doc", ""),
            )

        # Apply document recency boost.
        score *= index["recency"][i]

        scored.append(
            (score, i)
        )

    scored.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return scored


def _format_results(
    scored: List[Any],
    index: Dict[str, Any],
    k: int,
) -> List[Dict[str, Any]]:
    """
    Convert ranked chunk indexes into search result dictionaries.
    """

    results = []
    seen_texts = set()

    for score, i in scored:
        if len(results) >= k:
            break

        chunk = index["chunks"][i]

        text_key = clean_for_index(
            chunk.get("text", "")
        ).strip()

        if text_key in seen_texts:
            continue

        seen_texts.add(text_key)

        results.append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "doc": chunk.get("doc"),
                "page": chunk.get("page"),
                "document_date": chunk.get("document_date"),
                "text": chunk.get("text", ""),
                "score": round(score, 4),
            }
        )

    return results


def search(
    question: str,
    k: int = 5,
) -> List[Dict[str, Any]]:
    """
    Return the top-k document chunks relevant to the question.

    Fare questions are strictly filtered so that refund/cancellation
    charges are not mistaken for ticket fares.

    Policy questions receive controlled terminology expansion and
    policy-specific relevance boosts.

    An empty list means no sufficiently relevant evidence was found.
    """

    if (
        not isinstance(question, str)
        or not question.strip()
        or k <= 0
    ):
        return []

    index = _load_index()

    fare_query = _is_fare_query(question)
    policy_query = _is_policy_query(question)

    scored = _rank_results(
        question,
        index,
    )

    if not scored:
        return []

    # Normal retrieval threshold.
    if scored[0][0] >= MIN_SCORE:
        return _format_results(
            scored,
            index,
            k,
        )

    # Never weaken fare-query filtering.
    # This keeps S05 unanswered because the dataset has no fare table.
    if fare_query:
        return []

    # Policy/refund queries can use the lower threshold because
    # terminology expansion and policy boosts have already been applied.
    if (
        policy_query
        and scored[0][0] >= POLICY_FALLBACK_MIN_SCORE
    ):
        return _format_results(
            scored,
            index,
            k,
        )

    return []


if __name__ == "__main__":
    import sys

    question = (
        " ".join(sys.argv[1:])
        or "What is the refund for cancelling a Tatkal ticket?"
    )

    print(f"Query: {question}\n")

    results = search(
        question,
        k=5,
    )

    if not results:
        print("No relevant evidence found.")
    else:
        for result in results:
            print(
                f"[{result['score']}] "
                f"{result['doc']} "
                f"p{result['page']} "
                f"({result['document_date']}) "
                f"{result['chunk_id']}"
            )

            preview = (
                result["text"][:160]
                .replace("\n", " ")
            )

            print(f"   {preview}...\n")
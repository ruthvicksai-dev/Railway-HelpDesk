"""
Search and Retrieval Module

Responsible for:
1. Keyword (BM25) search over the document chunks produced by ingest.py
2. A small boost for chunks whose document name matches the question
3. A small recency boost so newer rules rank above older ones
4. Returning the top-k chunks for answer generation (Member 4)

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

# BM25 parameters (standard defaults)
BM25_K1 = 1.5
BM25_B = 0.75

# Extra weight when a question word appears in the document filename
# (e.g. "tatkal" -> rb_cc08_2025_tatkal.pdf)
DOC_NAME_BOOST = 0.5

# Newest document gets up to +15% score; relevance still dominates
RECENCY_WEIGHT = 0.15

# If the best chunk scores below this, treat it as "nothing relevant"
# so the pipeline answers "I don't know". Tune with eval/test_set.json.
MIN_SCORE = 3.0

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
    # words from the ingest.py page header, present in every PDF chunk
    "document", "page", "date", "ocr", "extracted", "pdf", "html",
}

# Header line that ingest.py adds to every PDF chunk
_HEADER_RE = re.compile(r"^Document:.*?\|\s*Page:.*?\|\s*Date:.*?(\n|$)", re.IGNORECASE)
_OCR_TAG_RE = re.compile(r"\[OCR Extracted Page\]", re.IGNORECASE)
# Keeps numbers like 12.11.2015, codes like cc-08 and 2a, plain words
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.\-/][a-z0-9]+)*")

_INDEX: Optional[Dict[str, Any]] = None


def tokenize(text: str) -> List[str]:
    """Lowercase, split into word/number tokens and drop stopwords.

    Compound tokens like "e-ticket" or "12.11.2015" are kept whole and
    their parts are added too, so "e ticket" still matches "e-ticket".
    """
    tokens = []
    for tok in _TOKEN_RE.findall(text.lower()):
        parts = re.split(r"[.\-/]", tok)
        candidates = [tok] + parts if len(parts) > 1 else [tok]
        for t in candidates:
            if t and t not in STOPWORDS:
                tokens.append(t)
    return tokens


def clean_for_index(text: str) -> str:
    """Remove the ingest.py header line and OCR tag before indexing."""
    text = _HEADER_RE.sub("", text, count=1)
    return _OCR_TAG_RE.sub("", text)


def _date_to_year(date_str: Optional[str]) -> Optional[float]:
    """Convert "YYYY-MM-DD" to a fractional year, e.g. 2025.3."""
    if not date_str:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", date_str)
    if not m:
        return None
    year, month, day = (int(x) for x in m.groups())
    return year + (month - 1) / 12 + (day - 1) / 365


def build_search_index(chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build BM25 statistics and boosts from ingest.py chunks."""
    term_freqs = []
    doc_lengths = []
    doc_freq: Counter = Counter()

    for chunk in chunks:
        tokens = tokenize(clean_for_index(chunk.get("text", "")))
        tf = Counter(tokens)
        term_freqs.append(dict(tf))
        doc_lengths.append(len(tokens))
        doc_freq.update(tf.keys())

    n = len(chunks)
    avgdl = (sum(doc_lengths) / n) if n else 0.0
    idf = {
        term: math.log(1 + (n - df + 0.5) / (df + 0.5))
        for term, df in doc_freq.items()
    }

    # Recency boost: oldest document -> 1.0, newest -> 1 + RECENCY_WEIGHT
    years = [_date_to_year(c.get("document_date")) for c in chunks]
    known = [y for y in years if y is not None]
    lo, hi = (min(known), max(known)) if known else (0.0, 0.0)
    recency = []
    for y in years:
        if y is None or hi == lo:
            recency.append(1.0)
        else:
            recency.append(1.0 + RECENCY_WEIGHT * (y - lo) / (hi - lo))

    doc_name_tokens = [sorted(set(tokenize(c.get("doc", "").replace("_", " ")))) for c in chunks]

    return {
        "chunks": chunks,
        "term_freqs": term_freqs,
        "doc_lengths": doc_lengths,
        "avgdl": avgdl,
        "idf": idf,
        "recency": recency,
        "doc_name_tokens": doc_name_tokens,
    }


def save_search_index(index: Dict[str, Any], path: Path = SEARCH_INDEX_PATH) -> None:
    """Write the search index to disk as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)


def _load_index() -> Dict[str, Any]:
    """Load the index once and cache it.

    Uses index/search_index.json if build_index.py has been run;
    otherwise builds it in memory from index/chunks.json.
    """
    global _INDEX
    if _INDEX is not None:
        return _INDEX

    if SEARCH_INDEX_PATH.exists():
        with open(SEARCH_INDEX_PATH, "r", encoding="utf-8") as f:
            _INDEX = json.load(f)
    elif CHUNKS_PATH.exists():
        with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
            _INDEX = build_search_index(json.load(f))
    else:
        raise FileNotFoundError(
            f"No index found. Run 'python build_index.py' first "
            f"(looked for {SEARCH_INDEX_PATH} and {CHUNKS_PATH})."
        )
    return _INDEX


def search(question: str, k: int = 5) -> List[Dict[str, Any]]:
    """
    Return the top-k chunks most relevant to the question.

    Args:
        question: The passenger's question.
        k: Maximum number of chunks to return.

    Returns:
        List of chunk dicts, best first, each with:
            chunk_id, doc, page, document_date, text, score
        An empty list means nothing relevant was found.
    """
    if not isinstance(question, str) or not question.strip() or k <= 0:
        return []

    index = _load_index()
    query_terms = list(dict.fromkeys(tokenize(question)))  # unique, keep order
    if not query_terms:
        return []

    idf = index["idf"]
    avgdl = index["avgdl"] or 1.0
    scored = []

    for i, tf in enumerate(index["term_freqs"]):
        dl = index["doc_lengths"][i]
        score = 0.0
        for term in query_terms:
            f = tf.get(term)
            if not f:
                continue
            denom = f + BM25_K1 * (1 - BM25_B + BM25_B * dl / avgdl)
            score += idf.get(term, 0.0) * f * (BM25_K1 + 1) / denom

        if score <= 0:
            continue

        name_hits = sum(1 for t in query_terms if t in index["doc_name_tokens"][i])
        score += DOC_NAME_BOOST * name_hits
        score *= index["recency"][i]
        scored.append((score, i))

    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored or scored[0][0] < MIN_SCORE:
        return []

    results = []
    seen_texts = set()
    for score, i in scored:
        if len(results) >= k:
            break
        chunk = index["chunks"][i]
        # Skip exact duplicate chunks (the PIB page repeats its sections)
        text_key = clean_for_index(chunk.get("text", "")).strip()
        if text_key in seen_texts:
            continue
        seen_texts.add(text_key)
        results.append({
            "chunk_id": chunk.get("chunk_id"),
            "doc": chunk.get("doc"),
            "page": chunk.get("page"),
            "document_date": chunk.get("document_date"),
            "text": chunk.get("text", ""),
            "score": round(score, 4),
        })
    return results


if __name__ == "__main__":
    import sys

    q = " ".join(sys.argv[1:]) or "What is the refund for cancelling a Tatkal ticket?"
    print(f"Query: {q}\n")
    for r in search(q, k=5):
        print(f"[{r['score']}] {r['doc']} p{r['page']} ({r['document_date']}) {r['chunk_id']}")
        print("   " + r["text"][:160].replace("\n", " ") + "...\n")

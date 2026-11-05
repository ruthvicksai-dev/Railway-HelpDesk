"""
Build the searchable index from processed railway documents.

Steps:
1. Load chunks from index/chunks.json (created by helpdesk/ingest.py).
   If it does not exist, or --reingest is passed, run ingest_documents().
2. Build BM25 statistics and boosts (helpdesk/search.py).
3. Save to index/search_index.json.

Usage:
    python build_index.py             # use existing index/chunks.json
    python build_index.py --reingest  # re-run ingestion + OCR first

Implementation owner: Member 3
"""

import json
import sys

from helpdesk.search import (
    CHUNKS_PATH,
    SEARCH_INDEX_PATH,
    build_search_index,
    save_search_index,
)


def load_chunks(reingest: bool = False):
    """Return chunks from chunks.json, or run ingestion to create them."""
    if not reingest and CHUNKS_PATH.exists():
        print(f"Loading chunks from {CHUNKS_PATH}")
        with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    # Imported here so the PDF/OCR libraries are only needed when re-ingesting
    from helpdesk.ingest import ingest_documents

    chunks = ingest_documents()
    CHUNKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(chunks)} chunks to {CHUNKS_PATH}")
    return chunks


def main():
    chunks = load_chunks(reingest="--reingest" in sys.argv)
    if not chunks:
        print("Error: no chunks to index. Check that the documents are in data/documents/.")
        sys.exit(1)

    index = build_search_index(chunks)
    save_search_index(index)

    print(f"Indexed {len(chunks)} chunks, {len(index['idf'])} unique terms.")
    print(f"Search index saved to {SEARCH_INDEX_PATH}")


if __name__ == "__main__":
    main()

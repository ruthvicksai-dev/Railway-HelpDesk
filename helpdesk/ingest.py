"""
Document Ingestion and OCR Module

Responsible for:
1. Extracting text from PDFs (both digital and scanned via OCR)
2. Parsing HTML circulars and press releases
3. Keeping rules and tables whole in chunks
4. Annotating each chunk with doc, page, date, and chunk_id

Owner: Member 2 - Document Ingestion & OCR
"""

import os
import re
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pymupdf
from bs4 import BeautifulSoup

# Document publication / effective dates (newer documents override older rules)
DOC_DATES = {
    "indianrail_refund_rules_2015.html": "2015-11-12",
    "irctc_refund_rules_jan2026.pdf": "2026-01-01",
    "rb_cc10_2024_advance_reservation.pdf": "2024-10-16",
    "rb_cc08_2025_tatkal.pdf": "2025-04-24",
    "rb_cc10_2025_reservation_charts.pdf": "2025-06-06",
    "rb_cc08_2026_vande_bharat_sleeper_refund.pdf": "2026-01-16",
    "pib_2026-03-24_reform_express.html": "2026-03-24",
}

# OCR engine cache
_ocr_engine = None


def get_ocr_engine():
    """Lazily load RapidOCR engine to avoid startup latency if not needed."""
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _ocr_engine = RapidOCR()
        except Exception as e:
            print(f"Warning: Could not initialize RapidOCR: {e}")
            _ocr_engine = None
    return _ocr_engine


def ocr_page(page: pymupdf.Page) -> str:
    """Render a scanned PDF page to high-res image and extract text via OCR."""
    engine = get_ocr_engine()
    if not engine:
        return ""

    try:
        # Render at 200 DPI for high OCR accuracy
        pix = page.get_pixmap(dpi=200)
        img_bytes = pix.tobytes("png")
        result, _ = engine(img_bytes)
        if not result:
            return ""
        lines = [item[1] for item in result if len(item) > 1 and item[1].strip()]
        return "\n".join(lines)
    except Exception as e:
        print(f"Error during OCR: {e}")
        return ""


def clean_text(text: str) -> str:
    """Normalize whitespace and control characters."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Replace non-breaking spaces and excessive spacing
    text = re.sub(r"[\t\u00a0]+", " ", text)
    # Condense 3+ newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_indianrail_html(file_path: Path) -> List[Dict[str, Any]]:
    """
    Parse indianrail_refund_rules_2015.html preserving introductory rules
    and individual table rows (Rule 1, Rule 2, etc.) as whole chunks.
    """
    doc_name = file_path.name
    doc_date = DOC_DATES.get(doc_name, "2015-11-12")
    chunks = []

    with open(file_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    # Table 1: Background & Objectives
    tables = soup.find_all("table")
    if tables:
        t1_text = clean_text(tables[0].get_text(separator="\n"))
        if t1_text:
            chunks.append({
                "chunk_id": f"{doc_name}_intro",
                "doc": doc_name,
                "page": None,
                "document_date": doc_date,
                "text": f"Indian Railways Refund Rules (effective 12.11.2015) - Overview & Objectives:\n\n{t1_text}",
            })

    # Table 2: Comparative Rules Table (Pre-revised vs. Revised)
    if len(tables) > 1:
        rows = tables[1].find_all("tr")
        if len(rows) > 1:
            headers = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
            h_str = " | ".join(headers)

            for idx, r in enumerate(rows[1:], 1):
                cols = [c.get_text(separator=" ", strip=True) for c in r.find_all(["th", "td"])]
                if not cols:
                    continue
                row_text = []
                for h, val in zip(headers, cols):
                    row_text.append(f"{h}: {val}")

                formatted_row = f"Refund Rules 2015 Revision Table - Item {idx}:\n" + "\n".join(row_text)
                chunks.append({
                    "chunk_id": f"{doc_name}_rule_{idx}",
                    "doc": doc_name,
                    "page": None,
                    "document_date": doc_date,
                    "text": clean_text(formatted_row),
                })

    return chunks


def parse_pib_html(file_path: Path) -> List[Dict[str, Any]]:
    """
    Parse pib_2026-03-24_reform_express.html by section headings, keeping
    reform topics (such as ticket cancellation, boarding point change) whole.
    """
    doc_name = file_path.name
    doc_date = DOC_DATES.get(doc_name, "2026-03-24")
    chunks = []

    with open(file_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    full_text = soup.get_text(separator="\n", strip=True)
    lines = [clean_text(line) for line in full_text.splitlines() if clean_text(line)]

    # Sections of interest in the press release
    section_headers = [
        "Reform in Salt Transportation",
        "Reform in Automobile Transportation",
        "Improving Quality of Construction",
        "Ticket cancellation and refund",
        "Change of Train Boarding Point",
        "Update on Previous Reforms",
    ]

    current_title = "PIB Release: Reform Express Overview"
    current_lines = []
    chunk_idx = 0

    for line in lines:
        matched_header = next((h for h in section_headers if h.lower() in line.lower()), None)
        if matched_header:
            if current_lines:
                chunk_text = f"PIB Press Release (24 Mar 2026) - {current_title}:\n\n" + "\n".join(current_lines)
                chunks.append({
                    "chunk_id": f"{doc_name}_sec_{chunk_idx}",
                    "doc": doc_name,
                    "page": None,
                    "document_date": doc_date,
                    "text": clean_text(chunk_text),
                })
                chunk_idx += 1
                current_lines = []
            current_title = matched_header
        current_lines.append(line)

    if current_lines:
        chunk_text = f"PIB Press Release (24 Mar 2026) - {current_title}:\n\n" + "\n".join(current_lines)
        chunks.append({
            "chunk_id": f"{doc_name}_sec_{chunk_idx}",
            "doc": doc_name,
            "page": None,
            "document_date": doc_date,
            "text": clean_text(chunk_text),
        })

    return chunks


def parse_pdf(file_path: Path) -> List[Dict[str, Any]]:
    """
    Parse a PDF file page by page.
    Uses native digital text extraction first; if text is empty/insufficient,
    falls back to RapidOCR.
    """
    doc_name = file_path.name
    doc_date = DOC_DATES.get(doc_name, "2026-01-01")
    chunks = []

    doc = pymupdf.open(file_path)
    total_pages = len(doc)

    for page_num in range(1, total_pages + 1):
        page = doc[page_num - 1]
        text = clean_text(page.get_text())

        # If digital text extraction yielded almost nothing, use OCR
        if len(text) < 50:
            ocr_text = clean_text(ocr_page(page))
            if ocr_text:
                text = f"[OCR Extracted Page]\n{ocr_text}"

        if not text:
            continue

        chunk_id = f"{doc_name}_p{page_num}"
        header = f"Document: {doc_name} | Page: {page_num} | Date: {doc_date}\n\n"

        chunks.append({
            "chunk_id": chunk_id,
            "doc": doc_name,
            "page": page_num,
            "document_date": doc_date,
            "text": clean_text(header + text),
        })

    doc.close()
    return chunks


def ingest_documents(docs_dir: Optional[str | Path] = None) -> List[Dict[str, Any]]:
    """
    Main ingestion function.
    Reads all PDF and HTML documents from the data/documents directory,
    performs text extraction and OCR, and returns clean structured chunks.

    Returns:
        List[Dict[str, Any]]: List of chunk dictionaries containing:
            - chunk_id (str)
            - doc (str)
            - page (int or None)
            - document_date (str: YYYY-MM-DD)
            - text (str)
    """
    if docs_dir is None:
        docs_dir = Path(__file__).resolve().parent.parent / "data" / "documents"
    else:
        docs_dir = Path(docs_dir)

    if not docs_dir.exists():
        print(f"Warning: Documents directory not found at {docs_dir}")
        return []

    all_chunks = []
    supported_files = sorted(os.listdir(docs_dir))

    for fname in supported_files:
        fpath = docs_dir / fname
        if not fpath.is_file():
            continue

        print(f"Ingesting {fname}...")
        if fname.lower().endswith(".pdf"):
            chunks = parse_pdf(fpath)
            all_chunks.extend(chunks)
        elif fname.lower().endswith(".html"):
            if "indianrail" in fname.lower():
                chunks = parse_indianrail_html(fpath)
            else:
                chunks = parse_pib_html(fpath)
            all_chunks.extend(chunks)

    print(f"\nIngestion complete! Total chunks created: {len(all_chunks)}")
    return all_chunks


def main():
    """CLI runner to test ingestion and cache chunks to index/chunks.json."""
    project_root = Path(__file__).resolve().parent.parent
    index_dir = project_root / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    chunks = ingest_documents()
    output_path = index_dir / "chunks.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(chunks)} chunks to {output_path}")


if __name__ == "__main__":
    main()

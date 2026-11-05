"""
Answer generation module for the railway passenger help desk.

This module prepares retrieved document chunks as evidence, sends them
to the Gemini LLM, and returns the generated answer with source details.
"""

from helpdesk.llm import generate_text


def _build_context(chunks):
    """
    Convert retrieved search chunks into evidence for Gemini.
    """

    context_parts = []

    for i, chunk in enumerate(chunks, start=1):
        doc = chunk.get("doc", "Unknown document")
        page = chunk.get("page")
        date = chunk.get("document_date")
        text = chunk.get("text", "").strip()

        source_info = f"Document: {doc}"

        if page is not None:
            source_info += f", Page: {page}"

        if date:
            source_info += f", Date: {date}"

        context_parts.append(
            f"[Evidence {i}]\n"
            f"{source_info}\n"
            f"{text}"
        )

    return "\n\n".join(context_parts)


def generate_answer(question, chunks):
    """
    Generate an answer from the user's question and retrieved chunks.

    Returns:
        dict: Answer, source information, and don't-know status.
    """

    if not chunks:
        return {
            "answer": (
                "I don't know based on the available railway documents."
            ),
            "sources": [],
            "dont_know": True,
        }

    context = _build_context(chunks)

    try:
        answer = generate_text(question, context)
    except Exception as exc:
        return {
            "answer": f"Unable to generate an answer: {exc}",
            "sources": [],
            "dont_know": True,
        }

    sources = []

    for chunk in chunks:
        source = {
            "doc": chunk.get("doc"),
            "page": chunk.get("page"),
        }

        if source not in sources:
            sources.append(source)

    lower_answer = answer.lower()

    dont_know = (
        "i don't know" in lower_answer
        or "i do not know" in lower_answer
        or "not enough information" in lower_answer
        or "not available in the provided" in lower_answer
    )

    return {
        "answer": answer,
        "sources": sources,
        "dont_know": dont_know,
    }


answer = generate_answer
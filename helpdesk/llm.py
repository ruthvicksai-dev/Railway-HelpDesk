"""
Gemini LLM integration for railway passenger answer generation.

This module configures the Gemini API and provides a function to
generate answers using retrieved railway document evidence.
"""

import os

from dotenv import load_dotenv
import google.generativeai as genai


load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is not set. Add it to your .env file."
    )

genai.configure(api_key=API_KEY)

model = genai.GenerativeModel(MODEL_NAME)


SYSTEM_INSTRUCTION = """
You are a railway passenger help-desk assistant.

Answer the user's question using ONLY the provided evidence.

Rules:
1. Do not invent or guess information.
2. If the evidence does not contain enough information to answer,
   clearly say that you don't know based on the available documents.
3. Give a concise, useful answer.
4. Prefer the most relevant and recent evidence when multiple documents
   contain information.
5. Do not mention information that is not supported by the evidence.
"""


def generate_text(question: str, context: str) -> str:
    """
    Generate an answer using Gemini and retrieved document evidence.
    """

    prompt = f"""
{SYSTEM_INSTRUCTION}

USER QUESTION:
{question}

RETRIEVED EVIDENCE:
{context}

Now answer the user's question.
"""

    response = model.generate_content(prompt)

    if not response or not response.text:
        raise RuntimeError("Gemini returned an empty response.")

    return response.text.strip()
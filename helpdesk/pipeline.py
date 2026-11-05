"""
Railway Passenger Help Desk - Main Pipeline

This module coordinates:
1. Query routing (Timetable vs. Document Rules vs. Out-of-Scope)
2. Timetable queries via SQL (Member 5)
3. Document retrieval and answer generation (Members 2, 3, 4)
4. Schema validation and "I don't know" handling

Owner: Member 1 - Team Lead & Integration
"""

import re
import importlib
from typing import Any, Dict, List, Optional
from helpdesk.sql import query_timetable

# Pre-compiled patterns for query classification
RE_5DIGIT = re.compile(r"\b\d{5}\b")
RE_ROUTE = re.compile(r"\b(from\s+.+?\s+to\s+.+|between\s+.+?\s+and\s+.+)\b", re.IGNORECASE)

# Keywords indicating questions the system CANNOT know
# (Rubric: 10 points for saying "I don't know" when it can't know, e.g. waitlist confirmation, live status)
UNANSWERABLE_PATTERNS = [
    # Waitlist / RAC confirmation predictions
    r"\b(will\s+my|chance\w*|probability|guarantee)\b.*\b(wl|waitlist\w*|waiting\s*list\w*|rac)\b",
    r"\b(wl|waitlist\w*|waiting\s*list\w*|rac)\b.*\b(will\s+it\s+confirm|get\s+confirm\w*|confirm\w*|clear|chance\w*|probability)\b",
    # Live / Real-time status
    r"\b(live|current|real-?time)\s+(status|location|running|delay|position|platform)\b",
    r"\b(where\s+is\s+(the\s+)?train\s+now|is\s+train\s+\d+\s+running\s+late|current\s+location)\b",
    r"\b(platform\s+number\s+today|which\s+platform\s+will|current\s+platform)\b",
    # Personal PNR / passenger details
    r"\b(my\s+pnr|check\s+pnr|pnr\s+status|who\s+is\s+(traveling|travelling|sitting|booked))\b",
]

# Keywords indicating timetable queries
TIMETABLE_KEYWORDS = [
    "train", "trains", "schedule", "timetable", "departure", "depart",
    "arrival", "arrive", "route", "stop", "stops", "halt", "halts",
    "running days", "frequency", "distance", "duration", "classes",
    "sleeper", "1ac", "2ac", "3ac", "chair car"
]

# Keywords indicating rules / refund / policy queries
POLICY_KEYWORDS = [
    "refund", "cancel", "cancellation", "clerkage", "tdr", "tatkal",
    "premium tatkal", "chart", "charting", "concession", "senior citizen",
    "luggage", "quota", "aadhaar", "id proof", "rule", "circular",
    "board", "irctc", "ticket deposit", "break journey"
]


def is_unanswerable_query(question: str) -> bool:
    """
    Check if a question is inherently unanswerable from static rules and timetables.
    Examples: Waitlist confirmation predictions, live GPS train running status, personal PNRs.
    """
    q_lower = question.lower()
    for pattern in UNANSWERABLE_PATTERNS:
        if re.search(pattern, q_lower):
            return True
    return False


def is_timetable_query(question: str) -> bool:
    """
    Detect whether the question is primarily asking about train timetables,
    routes, stops, schedules, or train numbers.
    """
    # Contains a 5-digit train number
    if RE_5DIGIT.search(question):
        # Unless it specifically asks about cancellation/refund rules
        q_lower = question.lower()
        if any(kw in q_lower for kw in ["cancel", "refund", "tdr", "rule"]):
            return False
        return True

    # Contains source-destination pattern
    if RE_ROUTE.search(question):
        return True

    q_lower = question.lower()
    timetable_hits = sum(1 for kw in TIMETABLE_KEYWORDS if kw in q_lower)
    policy_hits = sum(1 for kw in POLICY_KEYWORDS if kw in q_lower)

    return timetable_hits > 0 and timetable_hits >= policy_hits


def try_document_pipeline(question: str) -> Optional[Dict[str, Any]]:
    """
    Attempts to call Member 2/3 Search and Member 4 Answer generation modules
    if they are implemented in the project.
    """
    try:
        # Check if search module exists and has a search function
        search_mod = importlib.import_module("helpdesk.search")
        search_fn = getattr(search_mod, "search", None)

        # Check if answer module exists and has an answer generation function
        answer_mod = importlib.import_module("helpdesk.answer")
        answer_fn = getattr(answer_mod, "generate_answer", None) or getattr(answer_mod, "answer", None)

        if callable(search_fn) and callable(answer_fn):
            chunks = search_fn(question, k=5)
            if chunks:
                result = answer_fn(question, chunks)
                if isinstance(result, dict) and "answer" in result:
                    return result
    except (ImportError, AttributeError, Exception):
        # Modules still under development by teammates
        pass

    return None


def ask(question: str) -> Dict[str, Any]:
    """
    Main entry point for answering passenger questions.
    Every question goes through this function and returns the required schema:

    {
        "answer": "the reply, in plain words",
        "sources": [{"doc": "irctc_refund_rules_jan2026.pdf", "page": 3}],
        "sql": "SELECT ..." or None,
        "dont_know": False
    }
    """
    # 1. Basic sanitization
    if not isinstance(question, str) or not question.strip():
        return {
            "answer": "Please provide a valid question.",
            "sources": [],
            "sql": None,
            "dont_know": True,
        }

    question_clean = question.strip()

    # 2. Refusal Guardrail: Unanswerable or predictive queries
    # Rubric: 10 points for saying "I don't know" when it should
    if is_unanswerable_query(question_clean):
        return {
            "answer": "I don't know. The system only provides verified information from official railway rules and static timetables. It cannot predict waitlist confirmation chances, live train running delays, or personal PNR status.",
            "sources": [],
            "sql": None,
            "dont_know": True,
        }

    # 3. Timetable / SQL Route
    if is_timetable_query(question_clean):
        try:
            sql_result = query_timetable(question_clean)
            if isinstance(sql_result, dict):
                # If SQL query produced a confident answer, return it
                if not sql_result.get("dont_know", True):
                    return {
                        "answer": sql_result.get("answer", ""),
                        "sources": sql_result.get("sources", []),
                        "sql": sql_result.get("sql", None),
                        "dont_know": False,
                    }
                # Even if SQL didn't find results, if it was clearly a timetable query with SQL, return it
                if sql_result.get("sql"):
                    return {
                        "answer": sql_result.get("answer", "No timetable records found."),
                        "sources": sql_result.get("sources", []),
                        "sql": sql_result.get("sql"),
                        "dont_know": sql_result.get("dont_know", True),
                    }
        except Exception:
            pass

    # 4. Document / Rules Route (IRCTC rules, circulars, refund table)
    doc_result = try_document_pipeline(question_clean)
    if doc_result and isinstance(doc_result, dict):
        return {
            "answer": str(doc_result.get("answer", "")),
            "sources": list(doc_result.get("sources", [])),
            "sql": doc_result.get("sql", None),
            "dont_know": bool(doc_result.get("dont_know", False)),
        }

    # 5. Fallback for timetable queries that had no matching records
    if is_timetable_query(question_clean):
        return {
            "answer": "I could not find matching train timetable information for your request.",
            "sources": [],
            "sql": None,
            "dont_know": True,
        }

    # 6. Default refusal if information is not found or modules still pending
    return {
        "answer": "I don't know. The requested information could not be found in the railway documents or timetable.",
        "sources": [],
        "sql": None,
        "dont_know": True,
    }

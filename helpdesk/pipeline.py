"""
Railway Passenger Help Desk - Main Pipeline

This module coordinates:
1. Query routing (Timetable vs. Document Rules vs. Out-of-Scope)
2. Timetable queries via SQL (Member 5)
3. Document retrieval and answer generation (Members 2, 3, 4)
4. Schema validation and "I don't know" handling
5. Read-only database protection
6. Mixed timetable + document questions

Owner: Member 1 - Team Lead & Integration
"""

import re
import importlib
from typing import Any, Dict, Optional

from helpdesk.sql import query_timetable


RE_5DIGIT = re.compile(r"\b\d{5}\b")

RE_ROUTE = re.compile(
    r"\b(from\s+.+?\s+to\s+.+|between\s+.+?\s+and\s+.+)\b",
    re.IGNORECASE,
)


UNANSWERABLE_PATTERNS = [
    r"\b(will\s+my|chance\w*|probability|guarantee)\b.*\b(wl|waitlist\w*|waiting\s*list\w*|rac)\b",
    r"\b(wl|waitlist\w*|waiting\s*list\w*|rac)\b.*\b(will\s+it\s+confirm|get\s+confirm\w*|confirm\w*|clear|chance\w*|probability)\b",
    r"\b(live|current|real-?time)\s+(status|location|running|delay|position|platform)\b",
    r"\b(where\s+is\s+(the\s+)?train\s+now|is\s+train\s+\d+\s+running\s+late|current\s+location)\b",
    r"\b(platform\s+number\s+today|which\s+platform\s+will|current\s+platform)\b",
    r"\b(my\s+pnr|check\s+pnr|pnr\s+status|who\s+is\s+(traveling|travelling|sitting|booked))\b",
]


TIMETABLE_KEYWORDS = [
    "train",
    "trains",
    "schedule",
    "timetable",
    "departure",
    "depart",
    "arrival",
    "arrive",
    "route",
    "stop",
    "stops",
    "halt",
    "halts",
    "running days",
    "frequency",
    "distance",
    "duration",
    "classes",
    "sleeper",
    "1ac",
    "2ac",
    "3ac",
    "chair car",
]


POLICY_KEYWORDS = [
    "refund",
    "cancel",
    "cancellation",
    "clerkage",
    "tdr",
    "tatkal",
    "premium tatkal",
    "chart",
    "charting",
    "concession",
    "senior citizen",
    "luggage",
    "quota",
    "aadhaar",
    "id proof",
    "rule",
    "circular",
    "board",
    "irctc",
    "ticket deposit",
    "break journey",
]


FARE_KEYWORDS = [
    "fare",
    "price",
    "cost",
    "how much",
    "ticket price",
    "ticket fare",
    "how much does",
    "how much is",
]


WRITE_KEYWORDS = [
    "change",
    "update",
    "modify",
    "delete",
    "insert",
    "add",
    "remove",
    "edit",
]


def is_unanswerable_query(question: str) -> bool:
    """
    Check if a question is inherently unanswerable from static rules
    and timetables.
    """

    q_lower = question.lower()

    for pattern in UNANSWERABLE_PATTERNS:
        if re.search(pattern, q_lower):
            return True

    return False


def is_write_query(question: str) -> bool:
    """
    Detect requests that attempt to modify the timetable database.

    The timetable database is read-only, so these requests must be
    refused instead of being sent to SQL.
    """

    q_lower = question.lower()

    return any(
        re.search(rf"\b{re.escape(keyword)}\b", q_lower)
        for keyword in WRITE_KEYWORDS
    )


def is_fare_query(question: str) -> bool:
    """
    Detect fare and price questions.

    Fare questions should not be routed to timetable SQL even when
    they mention a train, route, or class such as 3AC.
    """

    q_lower = question.lower()

    return any(
        keyword in q_lower
        for keyword in FARE_KEYWORDS
    )


def is_mixed_query(question: str) -> bool:
    """
    Detect questions that require both timetable/SQL information
    and document/policy information.

    Example:
    "When does train 12002 leave New Delhi, and what is the
    cancellation charge if I cancel my confirmed AC chair car ticket?"
    """

    q_lower = question.lower()

    has_train_number = bool(
        RE_5DIGIT.search(question)
    )

    has_timetable_term = any(
        keyword in q_lower
        for keyword in [
            "departure",
            "depart",
            "arrival",
            "arrive",
            "schedule",
            "timetable",
            "leave",
        ]
    )

    has_policy_term = any(
        keyword in q_lower
        for keyword in POLICY_KEYWORDS
    )

    return (
        has_train_number
        and has_timetable_term
        and has_policy_term
    )


def is_timetable_query(question: str) -> bool:
    """
    Detect whether the question is primarily asking about train
    timetables, routes, stops, schedules, or train numbers.

    Fare/price questions are excluded because they should go through
    the document/LLM pipeline instead of timetable SQL.

    Mixed timetable + policy questions are handled separately.
    """

    q_lower = question.lower()

    if is_fare_query(question):
        return False

    if is_mixed_query(question):
        return False

    if RE_5DIGIT.search(question):
        if any(
            keyword in q_lower
            for keyword in [
                "cancel",
                "refund",
                "tdr",
                "rule",
            ]
        ):
            return False

        return True

    if RE_ROUTE.search(question):
        return True

    timetable_hits = sum(
        1
        for keyword in TIMETABLE_KEYWORDS
        if keyword in q_lower
    )

    policy_hits = sum(
        1
        for keyword in POLICY_KEYWORDS
        if keyword in q_lower
    )

    return (
        timetable_hits > 0
        and timetable_hits >= policy_hits
    )


def try_document_pipeline(
    question: str,
) -> Optional[Dict[str, Any]]:
    """
    Call Member 3 search and Member 4 answer generation modules.
    """

    try:
        search_mod = importlib.import_module(
            "helpdesk.search"
        )

        search_fn = getattr(
            search_mod,
            "search",
            None,
        )

        answer_mod = importlib.import_module(
            "helpdesk.answer"
        )

        answer_fn = (
            getattr(
                answer_mod,
                "generate_answer",
                None,
            )
            or getattr(
                answer_mod,
                "answer",
                None,
            )
        )

        if callable(search_fn) and callable(answer_fn):
            chunks = search_fn(
                question,
                k=5,
            )

            if chunks:
                result = answer_fn(
                    question,
                    chunks,
                )

                if (
                    isinstance(result, dict)
                    and "answer" in result
                ):
                    return result

    except Exception:
        # Keep the pipeline alive if a teammate's module
        # is unavailable.
        pass

    return None


def _extract_train_time_question(
    question: str,
) -> Optional[str]:
    """
    Extract a simple timetable sub-question from a mixed query.

    Example:
    "When does the Bhopal Shatabdi (12002) leave New Delhi, and what
    is the cancellation charge..."

    becomes:

    "When does train 12002 leave New Delhi?"
    """

    match = RE_5DIGIT.search(question)

    if not match:
        return None

    train_number = match.group(0)
    q_lower = question.lower()

    timetable_patterns = [
        r"when\s+does",
        r"when\s+do",
        r"what\s+time",
        r"departure",
        r"depart",
        r"arrival",
        r"arrive",
        r"leave",
    ]

    has_time_question = any(
        re.search(
            pattern,
            q_lower,
        )
        for pattern in timetable_patterns
    )

    if not has_time_question:
        return None

    from_match = re.search(
        r"\bfrom\s+(.+?)(?:,|\band\b|$)",
        question,
        re.IGNORECASE,
    )

    if from_match:
        station = from_match.group(1).strip()

        return (
            f"When does train {train_number} "
            f"leave {station}?"
        )

    leave_match = re.search(
        r"\bleave\s+(.+?)(?:,|\band\b|$)",
        question,
        re.IGNORECASE,
    )

    if leave_match:
        station = leave_match.group(1).strip()

        return (
            f"When does train {train_number} "
            f"leave {station}?"
        )

    return (
        f"What is the departure time "
        f"of train {train_number}?"
    )


def _extract_policy_question(
    question: str,
) -> str:
    """
    Extract the document/policy portion from a mixed question.

    Example:
    "When does train 12002 leave New Delhi, and what is the
    cancellation charge if I cancel my confirmed AC chair car ticket
    5 days before?"

    becomes:

    "What is the cancellation charge if I cancel my confirmed
    AC chair car ticket 5 days before?"
    """

    policy_patterns = [
        r"\band\s+what\s+is\s+the\s+(.+)$",
        r"\bwhat\s+is\s+the\s+(.+)$",
        r"\band\s+(.+?(?:cancel|cancellation|refund|clerkage|tdr).*)$",
    ]

    for pattern in policy_patterns:
        match = re.search(
            pattern,
            question,
            re.IGNORECASE,
        )

        if match:
            policy_part = match.group(1).strip()

            if policy_part:
                return (
                    f"What is {policy_part}"
                    if not policy_part.lower().startswith(
                        ("what ", "how ", "when ", "does ")
                    )
                    else policy_part
                )

    return question


def try_mixed_pipeline(
    question: str,
) -> Optional[Dict[str, Any]]:
    """
    Handle questions that require both SQL timetable information
    and document/policy information.

    The SQL part is answered using the timetable database.
    The policy part is answered using document retrieval + Gemini.
    """

    sql_answer = None
    sql_sources = []
    sql_query = None
    sql_dont_know = True

    timetable_question = _extract_train_time_question(
        question
    )

    if timetable_question:
        try:
            sql_result = query_timetable(
                timetable_question
            )

            if isinstance(sql_result, dict):
                sql_answer = sql_result.get(
                    "answer"
                )

                sql_sources = sql_result.get(
                    "sources",
                    [],
                )

                sql_query = sql_result.get(
                    "sql"
                )

                sql_dont_know = sql_result.get(
                    "dont_know",
                    True,
                )

        except Exception:
            pass

    policy_question = _extract_policy_question(
        question
    )

    doc_result = try_document_pipeline(
        policy_question
    )

    doc_answer = None
    doc_sources = []
    doc_dont_know = True

    if isinstance(doc_result, dict):
        doc_answer = doc_result.get(
            "answer"
        )

        doc_sources = doc_result.get(
            "sources",
            [],
        )

        doc_dont_know = doc_result.get(
            "dont_know",
            True,
        )

    answers = []

    if sql_answer and not sql_dont_know:
        answers.append(
            str(sql_answer).strip()
        )

    if doc_answer and not doc_dont_know:
        answers.append(
            str(doc_answer).strip()
        )

    if not answers:
        return {
            "answer": (
                "I don't know based on the available "
                "railway documents and timetable."
            ),
            "sources": [],
            "sql": sql_query,
            "dont_know": True,
        }

    combined_answer = "\n\n".join(
        answers
    )

    combined_sources = []

    for source in (
        sql_sources + doc_sources
    ):
        if source not in combined_sources:
            combined_sources.append(source)

    return {
        "answer": combined_answer,
        "sources": combined_sources,
        "sql": sql_query,
        "dont_know": False,
    }


def ask(
    question: str,
) -> Dict[str, Any]:
    """
    Main entry point for answering passenger questions.

    Every question returns:

    {
        "answer": "the reply, in plain words",
        "sources": [
            {
                "doc": "irctc_refund_rules_jan2026.pdf",
                "page": 3
            }
        ],
        "sql": "SELECT ..." or None,
        "dont_know": False
    }
    """

    if (
        not isinstance(question, str)
        or not question.strip()
    ):
        return {
            "answer": "Please provide a valid question.",
            "sources": [],
            "sql": None,
            "dont_know": True,
        }

    question_clean = question.strip()

    if is_write_query(question_clean):
        return {
            "answer": (
                "I can't do that. I only run read-only "
                "queries on the timetable."
            ),
            "sources": [],
            "sql": None,
            "dont_know": True,
        }

    if is_unanswerable_query(question_clean):
        return {
            "answer": (
                "I don't know. The system only provides "
                "verified information from official railway "
                "rules and static timetables. It cannot "
                "predict waitlist confirmation chances, "
                "live train running delays, or personal "
                "PNR status."
            ),
            "sources": [],
            "sql": None,
            "dont_know": True,
        }

    if is_mixed_query(question_clean):
        mixed_result = try_mixed_pipeline(
            question_clean
        )

        if mixed_result:
            return mixed_result

    if is_timetable_query(question_clean):
        try:
            sql_result = query_timetable(
                question_clean
            )

            if isinstance(sql_result, dict):

                if not sql_result.get(
                    "dont_know",
                    True,
                ):
                    return {
                        "answer": sql_result.get(
                            "answer",
                            "",
                        ),
                        "sources": sql_result.get(
                            "sources",
                            [],
                        ),
                        "sql": sql_result.get(
                            "sql"
                        ),
                        "dont_know": False,
                    }

                if sql_result.get("sql"):
                    return {
                        "answer": sql_result.get(
                            "answer",
                            "No timetable records found.",
                        ),
                        "sources": sql_result.get(
                            "sources",
                            [],
                        ),
                        "sql": sql_result.get(
                            "sql"
                        ),
                        "dont_know": sql_result.get(
                            "dont_know",
                            True,
                        ),
                    }

        except Exception:
            pass

    doc_result = try_document_pipeline(
        question_clean
    )

    if (
        doc_result
        and isinstance(doc_result, dict)
    ):
        return {
            "answer": str(
                doc_result.get(
                    "answer",
                    "",
                )
            ),
            "sources": list(
                doc_result.get(
                    "sources",
                    [],
                )
            ),
            "sql": doc_result.get(
                "sql"
            ),
            "dont_know": bool(
                doc_result.get(
                    "dont_know",
                    False,
                )
            ),
        }

    if is_timetable_query(question_clean):
        return {
            "answer": (
                "I could not find matching train "
                "timetable information for your request."
            ),
            "sources": [],
            "sql": None,
            "dont_know": True,
        }

    return {
        "answer": (
            "I don't know. The requested information "
            "could not be found in the railway documents "
            "or timetable."
        ),
        "sources": [],
        "sql": None,
        "dont_know": True,
    }
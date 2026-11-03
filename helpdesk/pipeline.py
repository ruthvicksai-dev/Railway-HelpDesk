"""
Railway Passenger Help Desk - Main Pipeline

This module coordinates:
1. Document-based question answering
2. Railway timetable SQL queries
3. Final response generation

Owner: Member 1 - Team Lead
"""


def ask(question):
    """
    Main entry point for answering passenger questions.

    Args:
        question (str): Passenger's question.

    Returns:
        dict: Standard response containing:
            - answer
            - sources
            - sql
            - dont_know
    """
    return {
        "answer": "The system is being developed.",
        "sources": [],
        "sql": None,
        "dont_know": True
    }
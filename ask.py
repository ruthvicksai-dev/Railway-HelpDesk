"""
Command-line interface for the Railway Passenger Help Desk.

Supports:
1. Direct CLI query: python ask.py "your question"
2. Interactive REPL mode: python ask.py

Implementation owner: Member 1 - Team Lead & Integration
"""

import sys
import json
from helpdesk.pipeline import ask


def print_result(result: dict) -> None:
    """Nicely print the standard output dictionary."""
    print("\n" + "=" * 50)
    print("ANSWER:")
    print(result.get("answer", ""))
    print("-" * 50)
    print("SOURCES:", result.get("sources", []))
    if result.get("sql"):
        print("SQL:", result.get("sql"))
    if result.get("dont_know"):
        print("STATUS: System declined to answer (I don't know).")
    print("=" * 50 + "\n")


def main():
    # Mode 1: Passed question as command-line argument (as required by rubric)
    # Example: python ask.py "Which trains go from Chennai to Bengaluru in the evening?"
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:]).strip()
        result = ask(question)
        print_result(result)
        return

    # Mode 2: Interactive loop if no arguments are passed
    print("======================================")
    print("   RAILWAY PASSENGER HELP DESK")
    print("======================================")
    print("Type 'exit' or 'quit' to exit.\n")

    while True:
        try:
            question = input("Enter your question: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            break

        if question.lower() in ("exit", "quit", "q"):
            print("Thank you for using Railway Help Desk!")
            break

        if not question:
            print("Please enter a valid question.\n")
            continue

        try:
            result = ask(question)
            print_result(result)
        except Exception as e:
            print("Error processing question:", e)


if __name__ == "__main__":
    main()

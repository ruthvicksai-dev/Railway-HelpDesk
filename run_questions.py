"""
Process questions from an input file and display answers immediately.

The generated answers are printed to the terminal as each question
is processed. Results are also saved to an output JSON file for
evaluation and record keeping.

Default:
    python run_questions.py

Optional:
    python run_questions.py <questions.json> <results.json>

Implementation owner: Member 1 - Team Lead & Integration
"""

import json
import sys

from helpdesk.pipeline import ask


DEFAULT_INPUT_FILE = "data/questions/sample_questions.json"
DEFAULT_OUTPUT_FILE = "results.json"


def extract_question_text(item) -> str:
    """Extract question text whether the item is a string or dictionary."""

    if isinstance(item, str):
        return item.strip()

    if isinstance(item, dict):
        for key in ["question", "q", "query", "text"]:
            if key in item and isinstance(item[key], str):
                return item[key].strip()

    return str(item).strip()


def print_result(question_number, total, question, result):
    """Display one question and its generated answer."""

    print("=" * 70)
    print(f"QUESTION {question_number}/{total}")
    print("=" * 70)
    print(f"\n{question}\n")

    print("ANSWER:")
    print(result.get("answer", "No answer generated."))

    sources = result.get("sources", [])

    if sources:
        print("\nSOURCES:")

        for source in sources:
            doc = source.get("doc", "Unknown document")
            page = source.get("page")

            if page is not None:
                print(f"- {doc} — Page {page}")
            else:
                print(f"- {doc}")

    sql = result.get("sql")

    if sql:
        print("\nSQL:")
        print(sql.strip())

    print()


def main():
    # Allow both:
    # python run_questions.py
    # python run_questions.py questions.json results.json

    if len(sys.argv) == 1:
        input_file = DEFAULT_INPUT_FILE
        output_file = DEFAULT_OUTPUT_FILE

    elif len(sys.argv) == 3:
        input_file = sys.argv[1]
        output_file = sys.argv[2]

    else:
        print(
            "Usage:\n"
            "  python run_questions.py\n"
            "  python run_questions.py <questions.json> <results.json>"
        )
        sys.exit(1)

    # Load questions.
    try:
        with open(input_file, "r", encoding="utf-8-sig") as file:
            questions_data = json.load(file)

    except Exception as e:
        print(f"Error loading {input_file}: {e}")
        sys.exit(1)

    if not isinstance(questions_data, list):
        print(f"Error: {input_file} must contain a JSON array of questions.")
        sys.exit(1)

    results = []
    total = len(questions_data)

    print(f"Processing {total} questions from {input_file}...\n")

    for idx, item in enumerate(questions_data, 1):
        question = extract_question_text(item)

        try:
            result = ask(question)

        except Exception as e:
            print(f"Warning: exception on question {idx}: {e}")

            result = {
                "answer": (
                    "An error occurred while processing "
                    "this question."
                ),
                "sources": [],
                "sql": None,
                "dont_know": True,
            }

        # Preserve the original question ID when available.
        if isinstance(item, dict) and "id" in item:
            result["id"] = item["id"]

        results.append(result)

        # Show the answer immediately.
        print_result(
            question_number=idx,
            total=total,
            question=question,
            result=result,
        )

    # Save results for evaluation.
    try:
        with open(output_file, "w", encoding="utf-8") as file:
            json.dump(
                results,
                file,
                indent=4,
                ensure_ascii=False,
            )

        print("=" * 70)
        print(f"All {total} questions processed successfully!")
        print(f"Results saved to: {output_file}")
        print("=" * 70)

    except Exception as e:
        print(f"Error saving output to {output_file}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
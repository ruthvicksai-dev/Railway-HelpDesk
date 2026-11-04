"""
Process questions from an input file and save answers to an output file.

Official evaluator runner: python run_questions.py <questions> <results>

Implementation owner: Member 1 - Team Lead & Integration
"""

import json
import sys
from helpdesk.pipeline import ask


def extract_question_text(item) -> str:
    """Extract question string whether the item is a string or dictionary."""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in ["question", "q", "query", "text"]:
            if key in item and isinstance(item[key], str):
                return item[key].strip()
    return str(item).strip()


def main():
    if len(sys.argv) != 3:
        print("Usage: python run_questions.py <questions.json> <results.json>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    # Use utf-8-sig to safely read files both with and without UTF-8 BOM
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
        snippet = question[:70] + "..." if len(question) > 70 else question
        print(f"[{idx}/{total}] Processing: {snippet}")

        try:
            result = ask(question)
        except Exception as e:
            # Prevent a single failure from terminating the batch evaluation
            print(f"  Warning: exception on question {idx}: {e}")
            result = {
                "answer": "An error occurred while processing this question.",
                "sources": [],
                "sql": None,
                "dont_know": True,
            }

        # Keep original item metadata if available (e.g. id)
        if isinstance(item, dict) and "id" in item:
            result["id"] = item["id"]

        results.append(result)

    try:
        with open(output_file, "w", encoding="utf-8") as file:
            json.dump(results, file, indent=4, ensure_ascii=False)

        print(f"\nAll {total} questions processed successfully!")
        print(f"Results saved to: {output_file}")
    except Exception as e:
        print(f"Error saving output to {output_file}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

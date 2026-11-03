"""
Process questions from an input file and save answers
to an output file.

Implementation owner: Member 1
"""
import json
import sys
from helpdesk.pipeline import ask

def main():

    if len(sys.argv) != 3:
        print("Usage: python run_questions.py <questions.json> <results.json>")
        return

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    try:
        with open(input_file, "r", encoding="utf-8") as file:
            questions = json.load(file)

        results = []

        for item in questions:
            question = item["question"]

            print("Processing:", question)

            result = ask(question)
            results.append(result)

        with open(output_file, "w", encoding="utf-8") as file:
            json.dump(results, file, indent=4, ensure_ascii=False)

        print("\nAll questions processed successfully!")
        print("Results saved to:", output_file)

    except Exception as e:
        print("Error:", e)


if __name__ == "__main__":
    main()
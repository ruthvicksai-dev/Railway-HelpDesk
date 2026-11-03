"""
Command-line interface for the Railway Passenger Help Desk.

Implementation owner: Member 1
"""
from helpdesk.pipeline import ask

def main():
    print("======================================")
    print("   RAILWAY PASSENGER HELP DESK")
    print("======================================")
    print("Type 'exit' to quit.\n")
    while True:
        question = input("Enter your question: ").strip()

        if question.lower() == "exit":
            print("Thank you for using Railway Help Desk!")
            break

        if not question:
            print("Please enter a valid question.\n")
            continue

        try:
            result = ask(question)
            print("\nAnswer:", result["answer"])
            print("Sources:", result["sources"])
            if result["sql"]:
                print("SQL:", result["sql"])
            if result["dont_know"]:
                print("The system could not find a reliable answer.")
            print("--------------------------------------\n")
            
        except Exception as e:
            print("Error:", e)


if __name__ == "__main__":
    main()
# Railway Passenger Help Desk

An AI-powered railway passenger assistance system developed as part of the GenAI Nexus Capstone Project.

## Project Overview

The system answers railway passenger questions using official railway documents and timetable data.

## Features

- PDF text extraction and OCR
- Document search and retrieval
- Gemini-powered question answering
- Railway rule and refund information
- SQLite timetable queries
- Source citations
- Safe "I don't know" responses

## Technology Stack

- Python
- Google Gemini API
- OCR and PDF processing
- Keyword-based search and retrieval
- SQLite

## Project Structure

See the project folders for individual modules.

## Setup Instructions

1. Clone the repository.
2. Create a Python 3.12.x virtual environment.
3. Install dependencies using `requirements.txt`.
4. Create an `.env` file using `.env.example`.
5. Add your Gemini API key and model name.
6. Extract the provided data pack into `data/`.

## Running the Project

Ask a question:

```bash
python ask.py
```

Run the built-in sample questions:

```bash
python run_questions.py
```

Run the evaluation questions:

```bash
python run_questions.py eval/test_set.json eval/results.json
```

## Team Members

- Member 1 – Team Lead: Pipeline and Integration
- Member 2 – Document Ingestion and OCR
- Member 3 – Search and Retrieval
- Member 4 – Gemini and Answer Generation
- Member 5 – SQL and Timetable

## Project Status

Evaluation and final integration.
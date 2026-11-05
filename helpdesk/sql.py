"""
SQL and timetable query module.
"""

import re
import sqlite3
from pathlib import Path


DB_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "database"
    / "rail_timetable.db"
)


def get_connection():
    """Connect to the railway timetable database."""
    return sqlite3.connect(DB_PATH)


def query_timetable(question):
    """
    Main timetable question handler.

    Routes passenger questions to the appropriate SQL function.
    """

    question = question.strip()

    if not question:
        return {
            "answer": "Please enter a valid question.",
            "sources": [],
            "sql": None,
            "dont_know": True,
        }

    question_lower = question.lower()

    if "how many" in question_lower and "rajdhani" in question_lower:
        return count_trains_by_name("rajdhani")

    match = re.search(r"\b\d{5}\b", question)
    train_number = match.group() if match else None

    if train_number and any(
        word in question_lower
        for word in ["stop", "stops", "stations", "route", "halt", "via"]
    ):
        return get_train_stops(train_number)

    if train_number and any(
        word in question_lower
        for word in [
            "class",
            "classes",
            "sleeper",
            "1ac",
            "2ac",
            "3ac",
            "chair car",
            "first ac",
            "second ac",
        ]
    ):
        return get_train_classes(train_number)

    route_patterns = [
        r"\bfrom\s+(.+?)\s+to\s+(.+?)(?:[?.!,]|$)",
        r"\bbetween\s+(.+?)\s+and\s+(.+?)(?:[?.!,]|$)",
    ]

    for pattern in route_patterns:
        route_match = re.search(
            pattern,
            question,
            re.IGNORECASE,
        )

        if route_match:
            source = route_match.group(1).strip()
            destination = route_match.group(2).strip()

            return search_trains_between(source, destination)

    if train_number:
        return get_train_details(train_number)

    return {
        "answer": (
            "I could not identify a timetable query. "
            "Please provide a train number or source and destination stations."
        ),
        "sources": [],
        "sql": None,
        "dont_know": True,
    }


def count_trains_by_name(name_keyword):
    """
    Count trains whose name contains the given keyword.
    """

    sql = """
        SELECT COUNT(*)
        FROM trains
        WHERE LOWER(name) LIKE LOWER(?)
    """

    try:
        pattern = f"%{name_keyword}%"

        with get_connection() as conn:
            conn.execute("PRAGMA query_only = ON")
            cursor = conn.cursor()
            cursor.execute(sql, (pattern,))
            result = cursor.fetchone()

        count = result[0] if result else 0

        return {
            "answer": (
                f"There are {count} trains matching "
                f"'{name_keyword}'."
            ),
            "sources": [],
            "sql": sql,
            "dont_know": False,
        }

    except sqlite3.Error:
        return {
            "answer": "Unable to count the trains.",
            "sources": [],
            "sql": None,
            "dont_know": True,
        }


def search_trains_between(source, destination):
    """
    Find trains that stop at the source and destination stations
    in the correct order.

    The source and destination can be station names or station codes.
    The stations do not have to be the train's first and last stations.
    """

    source_code_match = re.search(
        r"\(([A-Za-z0-9]+)\)",
        source,
    )

    destination_code_match = re.search(
        r"\(([A-Za-z0-9]+)\)",
        destination,
    )

    source_code = (
        source_code_match.group(1).upper()
        if source_code_match
        else None
    )

    destination_code = (
        destination_code_match.group(1).upper()
        if destination_code_match
        else None
    )

    source_name = re.sub(
        r"\s*\([A-Za-z0-9]+\)",
        "",
        source,
    ).strip()

    destination_name = re.sub(
        r"\s*\([A-Za-z0-9]+\)",
        "",
        destination,
    ).strip()

    sql = """
        SELECT
            t.number,
            t.name,
            source_station.name,
            destination_station.name,
            source_stop.departure,
            destination_stop.arrival
        FROM schedules source_stop
        JOIN schedules destination_stop
            ON destination_stop.train_number = source_stop.train_number
           AND destination_stop.stop_sequence > source_stop.stop_sequence
        JOIN trains t
            ON t.number = source_stop.train_number
        JOIN stations source_station
            ON source_station.code = source_stop.station_code
        JOIN stations destination_station
            ON destination_station.code = destination_stop.station_code
        WHERE (
            (? IS NOT NULL AND source_stop.station_code = ?)
            OR
            (? IS NULL AND LOWER(source_station.name) LIKE LOWER(?))
        )
        AND (
            (? IS NOT NULL AND destination_stop.station_code = ?)
            OR
            (? IS NULL AND LOWER(destination_station.name) LIKE LOWER(?))
        )
        ORDER BY source_stop.departure
        LIMIT 20
    """

    try:
        source_pattern = f"%{source_name}%"
        destination_pattern = f"%{destination_name}%"

        with get_connection() as conn:
            conn.execute("PRAGMA query_only = ON")
            cursor = conn.cursor()

            cursor.execute(
                sql,
                (
                    source_code,
                    source_code,
                    source_code,
                    source_pattern,
                    destination_code,
                    destination_code,
                    destination_code,
                    destination_pattern,
                ),
            )

            results = cursor.fetchall()

        if not results:
            return {
                "answer": "No trains found between these stations.",
                "sources": [],
                "sql": sql,
                "dont_know": True,
            }

        answer = "Trains found:\n"

        for train in results:
            number = train[0]
            name = train[1]
            source_station_name = train[2]
            destination_station_name = train[3]
            departure = train[4]
            arrival = train[5]

            answer += (
                f"\nTrain Number: {number}"
                f"\nTrain Name: {name}"
                f"\nFrom: {source_station_name}"
                f"\nTo: {destination_station_name}"
                f"\nDeparture: {departure}"
                f"\nArrival: {arrival}\n"
            )

        return {
            "answer": answer,
            "sources": [],
            "sql": sql,
            "dont_know": False,
        }

    except sqlite3.Error:
        return {
            "answer": "Unable to search trains.",
            "sources": [],
            "sql": None,
            "dont_know": True,
        }


def get_train_stops(train_number):
    sql = """
        SELECT
            s.stop_sequence,
            st.name,
            s.arrival,
            s.departure,
            s.halt_min
        FROM schedules s
        JOIN stations st
            ON s.station_code = st.code
        WHERE s.train_number = ?
        ORDER BY s.stop_sequence
    """

    try:
        with get_connection() as conn:
            conn.execute("PRAGMA query_only = ON")
            cursor = conn.cursor()
            cursor.execute(sql, (train_number,))
            results = cursor.fetchall()

        if not results:
            return {
                "answer": f"No schedule found for train {train_number}.",
                "sources": [],
                "sql": sql,
                "dont_know": True,
            }

        answer = f"Stops for train {train_number}:\n"

        for stop in results:
            answer += (
                f"\n{stop[0]}. {stop[1]}"
                f"\nArrival: {stop[2] or 'Not available'}"
                f"\nDeparture: {stop[3] or 'Not available'}"
                f"\nHalt: "
                f"{stop[4] if stop[4] is not None else 'Not available'} minutes\n"
            )

        return {
            "answer": answer,
            "sources": [],
            "sql": sql,
            "dont_know": False,
        }

    except sqlite3.Error:
        return {
            "answer": "Unable to retrieve train schedule.",
            "sources": [],
            "sql": None,
            "dont_know": True,
        }


def get_train_classes(train_number):
    sql = """
        SELECT
            number,
            name,
            has_1a,
            has_2a,
            has_3a,
            has_sl,
            has_cc,
            has_fc
        FROM trains
        WHERE number = ?
        LIMIT 1
    """

    try:
        with get_connection() as conn:
            conn.execute("PRAGMA query_only = ON")
            cursor = conn.cursor()
            cursor.execute(sql, (train_number,))
            result = cursor.fetchone()

        if not result:
            return {
                "answer": f"Train {train_number} not found.",
                "sources": [],
                "sql": sql,
                "dont_know": True,
            }

        number, name, *classes = result

        class_names = [
            "First AC (1A)",
            "Second AC (2A)",
            "Third AC (3A)",
            "Sleeper (SL)",
            "Chair Car (CC)",
            "First Class (FC)",
        ]

        available = [
            class_names[i]
            for i, value in enumerate(classes)
            if value == 1
        ]

        answer = (
            f"Available classes for train {number} - {name}:\n"
            + (
                "\n".join(available)
                if available
                else "No class information available."
            )
        )

        return {
            "answer": answer,
            "sources": [],
            "sql": sql,
            "dont_know": False,
        }

    except sqlite3.Error:
        return {
            "answer": "Unable to retrieve train class information.",
            "sources": [],
            "sql": None,
            "dont_know": True,
        }


def get_train_details(train_number):
    sql = """
        SELECT
            t.number,
            t.name,
            t.departure,
            t.arrival,
            t.duration_min,
            t.distance_km,
            s1.name,
            s2.name
        FROM trains t
        LEFT JOIN stations s1
            ON t.from_station_code = s1.code
        LEFT JOIN stations s2
            ON t.to_station_code = s2.code
        WHERE t.number = ?
        LIMIT 1
    """

    try:
        with get_connection() as conn:
            conn.execute("PRAGMA query_only = ON")
            cursor = conn.cursor()
            cursor.execute(sql, (train_number,))
            result = cursor.fetchone()

        if result is None:
            return {
                "answer": f"No train found with number {train_number}.",
                "sources": [],
                "sql": sql,
                "dont_know": True,
            }

        (
            number,
            name,
            departure,
            arrival,
            duration,
            distance,
            source,
            destination,
        ) = result

        answer = (
            f"Train {number}: {name}\n"
            f"Departure: {departure} from {source}\n"
            f"Arrival: {arrival} at {destination}\n"
            f"Duration: {duration} minutes\n"
            f"Distance: {distance} km"
        )

        return {
            "answer": answer,
            "sources": [],
            "sql": sql,
            "dont_know": False,
        }

    except sqlite3.Error:
        return {
            "answer": "Unable to retrieve train information.",
            "sources": [],
            "sql": None,
            "dont_know": True,
        }

"""
CodeCraftHub - Course Tracking REST API

This Flask application provides CRUD operations for courses and stores
course data in a local JSON file named courses.json.

Run the application with:

    python app.py
"""

from datetime import date, datetime, timezone
from pathlib import Path
import json
import os
import tempfile

from flask import Flask, jsonify, request


# Create the Flask application
app = Flask(__name__)

# Store courses.json in the same directory as this app.py file
DATA_FILE = Path(__file__).parent / "courses.json"

# These are the only status values accepted by the API
VALID_STATUSES = {
    "Not Started",
    "In Progress",
    "Completed",
}


class StorageError(Exception):
    """
    Custom exception used when there is a problem reading from or
    writing to the courses.json file.
    """

    pass


def create_empty_data_file():
    """
    Create courses.json with an empty list if the file does not exist.

    The empty list represents a collection with no courses.
    """
    try:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

        with DATA_FILE.open("w", encoding="utf-8") as file:
            json.dump([], file, indent=4)
            file.write("\n")

    except OSError as error:
        raise StorageError(
            f"Could not create data file: {error}"
        ) from error


def load_courses():
    """
    Read and return all courses from courses.json.

    Returns:
        list: A list of course dictionaries.

    Raises:
        StorageError: If the file cannot be read or contains invalid JSON.
    """

    # Automatically create the file if it does not exist
    if not DATA_FILE.exists():
        create_empty_data_file()

    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            courses = json.load(file)

    except json.JSONDecodeError as error:
        raise StorageError(
            "courses.json contains invalid JSON"
        ) from error

    except OSError as error:
        raise StorageError(
            f"Could not read courses.json: {error}"
        ) from error

    # Make sure the JSON file contains a list
    if not isinstance(courses, list):
        raise StorageError(
            "courses.json must contain a JSON list"
        )

    return courses


def save_courses(courses):
    """
    Save all courses to courses.json.

    A temporary file is used first. Once writing succeeds, it replaces
    the original file. This helps reduce the risk of corrupting the
    original file if writing is interrupted.
    """

    temporary_path = None

    try:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Create a temporary file in the same directory
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=DATA_FILE.parent,
            delete=False,
        ) as temporary_file:

            json.dump(courses, temporary_file, indent=4)
            temporary_file.write("\n")
            temporary_path = temporary_file.name

        # Replace the old file with the newly written file
        os.replace(temporary_path, DATA_FILE)

    except (OSError, TypeError) as error:
        # Remove the temporary file if something went wrong
        if temporary_path and os.path.exists(temporary_path):
            try:
                os.remove(temporary_path)
            except OSError:
                pass

        raise StorageError(
            f"Could not write courses.json: {error}"
        ) from error


def get_next_course_id(courses):
    """
    Generate the next course ID.

    IDs start at 1. The next ID is one greater than the current
    highest ID. If there are no courses, the next ID is 1.
    """

    existing_ids = [
        course.get("id")
        for course in courses
        if isinstance(course.get("id"), int)
        and not isinstance(course.get("id"), bool)
    ]

    if not existing_ids:
        return 1

    return max(existing_ids) + 1


def validate_course_data(data):
    """
    Validate the data supplied for creating or replacing a course.

    Returns:
        str or None:
            An error message if validation fails, otherwise None.
    """

    if not isinstance(data, dict):
        return "Request body must be a JSON object"

    # All of these fields are required when creating or replacing a course
    required_fields = [
        "name",
        "description",
        "target_date",
        "status",
    ]

    missing_fields = [
        field for field in required_fields
        if field not in data
    ]

    if missing_fields:
        return (
            "Missing required field(s): "
            + ", ".join(missing_fields)
        )

    # Validate name
    if not isinstance(data["name"], str) or not data["name"].strip():
        return "name must be a non-empty string"

    # Validate description
    if (
        not isinstance(data["description"], str)
        or not data["description"].strip()
    ):
        return "description must be a non-empty string"

    # Validate target_date
    if not isinstance(data["target_date"], str):
        return "target_date must be a string in YYYY-MM-DD format"

    try:
        date.fromisoformat(data["target_date"])
    except ValueError:
        return "target_date must use YYYY-MM-DD format"

    # Validate status
    if data["status"] not in VALID_STATUSES:
        return (
            "status must be one of: "
            '"Not Started", "In Progress", or "Completed"'
        )

    return None


def find_course(courses, course_id):
    """
    Find a course by its integer ID.

    Returns:
        dict or None: The matching course, if found.
    """

    for course in courses:
        if course.get("id") == course_id:
            return course

    return None


def parse_course_id(course_id_text):
    """
    Convert a URL course ID from text to an integer.

    Returns:
        int or None: The integer ID, or None if the value is invalid.
    """

    try:
        course_id = int(course_id_text)

        # Course IDs must be positive integers
        if course_id < 1:
            return None

        return course_id

    except (TypeError, ValueError):
        return None


def storage_error_response(error):
    """
    Create a consistent response for file-related errors.

    The full internal error is logged by Flask, while the API returns
    a simpler message to the client.
    """
    app.logger.error(str(error))

    return jsonify({
        "error": "There was a problem reading or writing courses.json"
    }), 500


@app.post("/api/courses")
def create_course():
    """
    Add a new course.

    Endpoint:
        POST /api/courses
    """

    # Parse the JSON request body
    data = request.get_json(silent=True)

    if data is None:
        return jsonify({
            "error": "Request body must contain valid JSON"
        }), 400

    # Validate the required fields
    validation_error = validate_course_data(data)

    if validation_error:
        return jsonify({"error": validation_error}), 400

    try:
        courses = load_courses()

        # Build a new course with generated fields
        new_course = {
            "id": get_next_course_id(courses),
            "name": data["name"].strip(),
            "description": data["description"].strip(),
            "target_date": data["target_date"],
            "status": data["status"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        courses.append(new_course)
        save_courses(courses)

        return jsonify(new_course), 201

    except StorageError as error:
        return storage_error_response(error)


@app.get("/api/courses")
def get_courses():
    """
    Get all courses.

    Endpoint:
        GET /api/courses
    """

    try:
        courses = load_courses()

        return jsonify(courses), 200

    except StorageError as error:
        return storage_error_response(error)


@app.get("/api/courses/<course_id>")
def get_course(course_id):
    """
    Get one course by ID.

    Endpoint:
        GET /api/courses/<id>
    """

    parsed_id = parse_course_id(course_id)

    if parsed_id is None:
        return jsonify({
            "error": "Course ID must be a positive integer"
        }), 400

    try:
        courses = load_courses()
        course = find_course(courses, parsed_id)

        if course is None:
            return jsonify({
                "error": "Course not found"
            }), 404

        return jsonify(course), 200

    except StorageError as error:
        return storage_error_response(error)


@app.put("/api/courses/<course_id>")
def update_course(course_id):
    """
    Replace all editable fields of an existing course.

    The id and created_at fields cannot be changed.

    Endpoint:
        PUT /api/courses/<id>
    """

    parsed_id = parse_course_id(course_id)

    if parsed_id is None:
        return jsonify({
            "error": "Course ID must be a positive integer"
        }), 400

    # Parse the JSON request body
    data = request.get_json(silent=True)

    if data is None:
        return jsonify({
            "error": "Request body must contain valid JSON"
        }), 400

    # PUT requires all course fields to be supplied
    validation_error = validate_course_data(data)

    if validation_error:
        return jsonify({"error": validation_error}), 400

    try:
        courses = load_courses()
        course = find_course(courses, parsed_id)

        if course is None:
            return jsonify({
                "error": "Course not found"
            }), 404

        # Update only the editable fields
        course["name"] = data["name"].strip()
        course["description"] = data["description"].strip()
        course["target_date"] = data["target_date"]
        course["status"] = data["status"]

        # Keep the original ID and created_at timestamp
        save_courses(courses)

        return jsonify(course), 200

    except StorageError as error:
        return storage_error_response(error)


@app.delete("/api/courses/<course_id>")
def delete_course(course_id):
    """
    Delete a course by ID.

    Endpoint:
        DELETE /api/courses/<id>
    """

    parsed_id = parse_course_id(course_id)

    if parsed_id is None:
        return jsonify({
            "error": "Course ID must be a positive integer"
        }), 400

    try:
        courses = load_courses()
        course = find_course(courses, parsed_id)

        if course is None:
            return jsonify({
                "error": "Course not found"
            }), 404

        # Create a new list without the course being deleted
        remaining_courses = [
            item for item in courses
            if item.get("id") != parsed_id
        ]

        save_courses(remaining_courses)

        return jsonify({
            "message": "Course deleted successfully",
            "id": parsed_id,
        }), 200

    except StorageError as error:
        return storage_error_response(error)


@app.errorhandler(404)
def handle_not_found(error):
    """
    Handle requests to endpoints that do not exist.
    """
    return jsonify({
        "error": "Endpoint not found"
    }), 404


@app.errorhandler(405)
def handle_method_not_allowed(error):
    """
    Handle requests using an unsupported HTTP method.
    """
    return jsonify({
        "error": "HTTP method not allowed for this endpoint"
    }), 405


@app.errorhandler(500)
def handle_internal_server_error(error):
    """
    Handle unexpected server errors.
    """
    app.logger.exception("Unexpected server error")

    return jsonify({
        "error": "An unexpected server error occurred"
    }), 500


if __name__ == "__main__":
    # Create courses.json when the application starts if needed
    if not DATA_FILE.exists():
        try:
            create_empty_data_file()
            print(f"Created data file: {DATA_FILE}")
        except StorageError as error:
            print(f"Could not create courses.json: {error}")

    # debug=True is useful while learning and developing.
    # Disable debug mode in a production deployment.
    app.run(debug=True)

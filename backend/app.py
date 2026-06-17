"""
app.py
------
Flask web server exposing the code analyzer as a REST API.

Endpoints:
    GET  /                health check
    POST /analyze          body: { "code": "...", "language": "python" }
                            returns: structured JSON from analyzer.analyze_code
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from analyzer import analyze_code

app = Flask(__name__)
CORS(app)  # allows the frontend (served from a different port) to call this API

MAX_CODE_LENGTH = 20000  # characters; keeps requests fast and within free-tier token limits


@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "message": "Code Reviewer API is running."})


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json(silent=True)

    if not data or "code" not in data:
        return jsonify({"error": "Request body must include a 'code' field."}), 400

    code = data.get("code", "")
    language = data.get("language", "auto-detect")

    if not isinstance(code, str) or not code.strip():
        return jsonify({"error": "'code' must be a non-empty string."}), 400

    if len(code) > MAX_CODE_LENGTH:
        return jsonify({
            "error": f"Code too long ({len(code)} chars). Max is {MAX_CODE_LENGTH}."
        }), 400

    try:
        result = analyze_code(code, language)
        return jsonify(result), 200
    except ValueError as e:
        # Errors we raised ourselves (bad input, model returned bad JSON, etc.)
        return jsonify({"error": str(e)}), 502
    except Exception as e:
        # Catch-all for unexpected issues (network errors, API key problems, etc.)
        return jsonify({"error": f"Unexpected server error: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
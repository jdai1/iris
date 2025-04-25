from flask import Flask, request, jsonify
from flask_cors import CORS
from sqlalchemy import or_
from db import EntryDriver

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})


@app.route("/api/search")
def search():
    query = request.args.get("q", "") or request.args.get("keyword", "")
    if not query:
        return jsonify({"error": "No search query provided"}), 400

    print(f"Searching for {query}")

    entries = EntryDriver().search(query=query)
    results = [
        {
            "id": entry.id,
            "name": entry.name,
            "summary": entry.summary,
            "topics": entry.topics,
            "author": entry.author,
            "date": entry.date,
            "url": entry.entry_url,
        }
        for entry in entries
    ]
    return jsonify({"results": results})


if __name__ == "__main__":
    app.run(debug=True, port=5000)

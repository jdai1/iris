from flask import Flask, request, jsonify
from flask_cors import CORS
from sqlalchemy import or_
from db import Link, Session, DBEntry

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})


@app.route("/api/search")
def search():
    keyword = request.args.get("q", "") or request.args.get("keyword", "")
    if not keyword:
        return jsonify({"error": "No search query provided"}), 400

    session = Session()
    try:
        # Search across multiple fields
        entries = (
            session.query(DBEntry)
            .filter(
                or_(
                    DBEntry.name.ilike(f"%{keyword}%"),
                    DBEntry.summary.ilike(f"%{keyword}%"),
                    DBEntry.topics.ilike(f"%{keyword}%"),
                    DBEntry.author.ilike(f"%{keyword}%"),
                )
            )
            .limit(100)
        )

        # Convert entries to dictionary format
        results = [
            {
                "id": entry.id,
                "blog": entry.blog,
                "name": entry.name,
                "summary": entry.summary,
                "topics": entry.topics,
                "author": entry.author,
                "date": entry.date,
                "url": entry.url,
            }
            for entry in entries
        ]

        return jsonify({"results": results})

    finally:
        session.close()


@app.route("/api/urls")
def get_urls():
    session = Session()
    try:
        links = session.query(Link).distinct().filter(Link.url.isnot(None)).all()
        result = [
            {
                "id": l.id,
                "url": l.url,
                "external_domains": l.external_domains,
                "external_links": l.external_links,
            }
            for l in links
        ]
        return jsonify(result)
    finally:
        session.close()


if __name__ == "__main__":
    app.run(debug=True, port=5000)

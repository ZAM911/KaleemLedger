import json
import os
import sqlite3
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_from_directory

APP_KEY = "myLedger.v1"

ROOT_DIR = Path(__file__).resolve().parent


def _db_path() -> Path:
    return Path(os.environ.get("DB_PATH", str(ROOT_DIR / "data" / "ledger.db"))).expanduser()


def _get_conn() -> sqlite3.Connection:
    db = _db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kv (
            k TEXT PRIMARY KEY,
            v TEXT NOT NULL
        )
        """
    )
    return conn


def _load_state() -> dict:
    conn = _get_conn()
    try:
        row = conn.execute("SELECT v FROM kv WHERE k = ?",
                           (APP_KEY,)).fetchone()
        if not row:
            return {}
        try:
            return json.loads(row["v"]) if row["v"] else {}
        except json.JSONDecodeError:
            return {}
    finally:
        conn.close()


def _save_state(state: dict) -> None:
    payload = json.dumps(state, ensure_ascii=False)
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO kv (k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v",
            (APP_KEY, payload),
        )
        conn.commit()
    finally:
        conn.close()


app = Flask(__name__)


@app.get("/api/health")
def health():
    return jsonify({"ok": True})


@app.get("/api/state")
def get_state():
    return jsonify(_load_state())


@app.put("/api/state")
def put_state():
    data = request.get_json(force=True, silent=False)
    if not isinstance(data, dict):
        return jsonify({"error": "state must be a JSON object"}), 400
    # keep it simple: accept whatever the frontend sends (it's one-user)
    _save_state(data)
    return jsonify({"ok": True})


@app.get("/")
def index():
    return send_from_directory(str(ROOT_DIR), "index.html")


_ALLOWED_EXTS = {
    ".html",
    ".js",
    ".css",
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".ico",
    ".webmanifest",
    ".json",
    ".txt",
}


@app.get("/<path:filename>")
def static_files(filename: str):
    # Only serve typical static asset extensions.
    path = (ROOT_DIR / filename).resolve()
    if ROOT_DIR not in path.parents and path != ROOT_DIR:
        abort(404)
    if not path.is_file():
        abort(404)
    if path.suffix.lower() not in _ALLOWED_EXTS:
        abort(404)
    return send_from_directory(str(ROOT_DIR), filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3000"))
    app.run(host="0.0.0.0", port=port, debug=False)

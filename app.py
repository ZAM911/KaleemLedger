import json
import os
import sqlite3
from pathlib import Path
from functools import wraps

from flask import Flask, abort, jsonify, request, send_from_directory, redirect

APP_KEY = "myLedger.v1"

# Hardcoded credentials
ADMIN_USERNAME = "ad"
ADMIN_PASSWORD = "kaleemaslamnhshiredndsol"
ADMIN_TOKEN = "ledger_session_token_v1"
P_PASSWORD = "p"
PAGES_TOKEN = "pages_session_token_v1"

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
    conn.commit()
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


def _require_auth(f):
    """Decorator to require authentication for API endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if token != ADMIN_TOKEN:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function


@app.get("/api/state")
@_require_auth
def get_state():
    return jsonify(_load_state())


@app.put("/api/state")
@_require_auth
def put_state():
    data = request.get_json(force=True, silent=False)
    if not isinstance(data, dict):
        return jsonify({"error": "state must be a JSON object"}), 400
    # keep it simple: accept whatever the frontend sends (it's one-user)
    _save_state(data)
    return jsonify({"ok": True})


@app.post("/api/login")
def login():
    """Authenticate user and return session token"""
    data = request.get_json(force=True, silent=False)
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        response = jsonify({"ok": True, "token": ADMIN_TOKEN})
        response.set_cookie("session_token", ADMIN_TOKEN, httponly=True, samesite="Lax")
        return response
    elif username == ADMIN_USERNAME and password == P_PASSWORD:
        response = jsonify({"ok": True, "token": PAGES_TOKEN, "redirect": "/pages-list"})
        response.set_cookie("session_token", PAGES_TOKEN, httponly=True, samesite="Lax")
        return response
    else:
        return jsonify({"error": "Invalid credentials"}), 401


@app.post("/api/logout")
def logout():
    """Logout (no-op for hardcoded auth)"""
    response = jsonify({"ok": True})
    response.delete_cookie("session_token")
    return response


@app.get("/pages-list")
def serve_pages_list():
    token = request.cookies.get("session_token")
    if token not in (ADMIN_TOKEN, PAGES_TOKEN):
        return redirect("/")
    return send_from_directory(str(ROOT_DIR), "pages_list.html")


@app.get("/api/pages")
def list_pages():
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if token not in (ADMIN_TOKEN, PAGES_TOKEN):
        return jsonify({"error": "Unauthorized"}), 401
    
    pages_dir = ROOT_DIR / "pages"
    if not pages_dir.exists():
      return jsonify({"pages": []})
    pages = []
    for f in pages_dir.glob("*.html"):
        if f.is_file() and f.name.lower() != "index.html":
            pages.append({
                "name": f.name,
                "size": f.stat().st_size
            })
    pages.sort(key=lambda x: x["name"])
    return jsonify({"pages": pages})


@app.get("/pages/<path:filename>")
def serve_protected_page(filename: str):
    token = request.cookies.get("session_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if token not in (ADMIN_TOKEN, PAGES_TOKEN):
        return redirect("/")
        
    pages_dir = (ROOT_DIR / "pages").resolve()
    path = (pages_dir / filename).resolve()
    if pages_dir not in path.parents:
        abort(404)
    if not path.is_file():
        abort(404)
    return send_from_directory(str(pages_dir), filename)


@app.get("/api/health")
def health():
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
    # Prevent direct access to protected pages directory via this route
    if filename.startswith("pages/") or filename.startswith("pages\\"):
        abort(403)
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

"""SQLite persistence: books, chapters, and small key/value meta."""
import json
import sqlite3
import time

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS books(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner INTEGER, chat_id INTEGER,
    title TEXT, genre TEXT, status TEXT,
    created REAL, updated REAL, data TEXT
);
CREATE TABLE IF NOT EXISTS chapters(
    book_id INTEGER, n INTEGER,
    title TEXT, text TEXT, summary TEXT, scores TEXT,
    words INTEGER, hook_type TEXT, ledger_after TEXT,
    PRIMARY KEY(book_id, n)
);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(config.DB_PATH), timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _q(sql, args=(), one=False, write=False):
    c = _conn()
    try:
        cur = c.execute(sql, args)
        if write:
            c.commit()
            return cur.lastrowid
        rows = cur.fetchall()
        if one:
            return rows[0] if rows else None
        return rows
    finally:
        c.close()


def init() -> None:
    c = _conn()
    try:
        c.executescript(SCHEMA)
        c.commit()
    finally:
        c.close()


# ---- meta ---------------------------------------------------------------------
def meta_get(key, default=None):
    r = _q("SELECT value FROM meta WHERE key=?", (key,), one=True)
    return r["value"] if r else default


def meta_set(key, value) -> None:
    _q("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key, str(value)), write=True)


# ---- books --------------------------------------------------------------------
def _book(row):
    if not row:
        return None
    d = dict(row)
    d["data"] = json.loads(d["data"] or "{}")
    return d


def create_book(owner, chat_id, genre, title, data) -> int:
    now = time.time()
    return _q("INSERT INTO books(owner,chat_id,title,genre,status,created,updated,data) "
              "VALUES(?,?,?,?,?,?,?,?)",
              (owner, chat_id, title, genre, "building", now, now, json.dumps(data)), write=True)


def get_book(book_id):
    return _book(_q("SELECT * FROM books WHERE id=?", (book_id,), one=True))


def save_book(book) -> None:
    _q("UPDATE books SET title=?, genre=?, status=?, updated=?, data=? WHERE id=?",
       (book["title"], book["genre"], book["status"], time.time(),
        json.dumps(book["data"], ensure_ascii=False), book["id"]), write=True)


def list_books(owner):
    return [_book(r) for r in _q("SELECT * FROM books WHERE owner=? ORDER BY updated DESC", (owner,))]


def books_auto():
    """Books that were in auto-write mode (used to resume after a redeploy)."""
    return [b for b in (_book(r) for r in _q("SELECT * FROM books")) if b["data"].get("auto")]


def delete_book(book_id) -> None:
    _q("DELETE FROM chapters WHERE book_id=?", (book_id,), write=True)
    _q("DELETE FROM books WHERE id=?", (book_id,), write=True)


# ---- chapters -----------------------------------------------------------------
def save_chapter(book_id, n, title, text, summary, scores, hook_type, ledger) -> None:
    _q("INSERT OR REPLACE INTO chapters(book_id,n,title,text,summary,scores,words,hook_type,ledger_after) "
       "VALUES(?,?,?,?,?,?,?,?,?)",
       (book_id, n, title, text, summary, json.dumps(scores), len(text.split()), hook_type,
        json.dumps(ledger, ensure_ascii=False)), write=True)


def _chapter(row):
    d = dict(row)
    d["scores"] = json.loads(d.get("scores") or "{}")
    if d.get("ledger_after"):
        d["ledger_after"] = json.loads(d["ledger_after"])
    return d


def get_chapters(book_id, with_text=True):
    cols = ("n,title,text,summary,scores,words,hook_type,ledger_after" if with_text
            else "n,title,summary,scores,words,hook_type")
    rows = _q(f"SELECT {cols} FROM chapters WHERE book_id=? ORDER BY n", (book_id,))
    return [_chapter(r) for r in rows]


def get_chapter(book_id, n):
    r = _q("SELECT * FROM chapters WHERE book_id=? AND n=?", (book_id, n), one=True)
    return _chapter(r) if r else None


def count_chapters(book_id) -> int:
    return _q("SELECT COUNT(*) c FROM chapters WHERE book_id=?", (book_id,), one=True)["c"]


def delete_chapter(book_id, n) -> None:
    _q("DELETE FROM chapters WHERE book_id=? AND n=?", (book_id, n), write=True)

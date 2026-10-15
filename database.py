"""Database connection, setup, and helper functions for the to-do list.

All SQL uses "?" placeholders so user input is never pasted into a query.
"""
import sqlite3
from datetime import datetime, timezone

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    description TEXT,
    completed   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);
"""


def get_db():
    """Return this request's database connection, opening it if needed."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(error=None):
    """Close the connection at the end of the request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create the tasks table if it does not exist. Never deletes data."""
    db = get_db()
    db.executescript(SCHEMA)
    db.commit()


def init_app(app):
    """Hook the database into the Flask app and make sure the table exists."""
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()


# --- Task helpers -----------------------------------------------------------

def add_task(title, description):
    db = get_db()
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cursor = db.execute(
        "INSERT INTO tasks (title, description, completed, created_at) "
        "VALUES (?, ?, 0, ?)",
        (title, description, created_at),
    )
    db.commit()
    return cursor.lastrowid


def get_task(task_id):
    """Return one task row, or None if the ID does not exist."""
    return get_db().execute(
        "SELECT * FROM tasks WHERE id = ?", (task_id,)
    ).fetchone()


def list_tasks(status="all"):
    """Return tasks, newest first. status is 'all', 'pending' or 'completed'."""
    query = "SELECT * FROM tasks"
    params = ()
    if status == "pending":
        query += " WHERE completed = ?"
        params = (0,)
    elif status == "completed":
        query += " WHERE completed = ?"
        params = (1,)
    query += " ORDER BY id DESC"
    return get_db().execute(query, params).fetchall()


def update_task(task_id, title, description):
    """Update title and description. Returns True if the task existed."""
    db = get_db()
    cursor = db.execute(
        "UPDATE tasks SET title = ?, description = ? WHERE id = ?",
        (title, description, task_id),
    )
    db.commit()
    return cursor.rowcount == 1


def set_completed(task_id, completed):
    """Mark a task completed (True) or pending (False)."""
    db = get_db()
    cursor = db.execute(
        "UPDATE tasks SET completed = ? WHERE id = ?",
        (1 if completed else 0, task_id),
    )
    db.commit()
    return cursor.rowcount == 1


def delete_task(task_id):
    """Delete a task. Returns True if the task existed."""
    db = get_db()
    cursor = db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    return cursor.rowcount == 1

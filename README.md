# Simple To-Do List

A small, server-rendered to-do list built with **Python, Flask, SQLite, HTML, CSS and Jinja2**.
It uses ordinary HTML forms and page reloads. There is no API, no frontend framework and no
JavaScript apart from one browser confirmation dialog when deleting a task.

## Features

- Add a task with a title and an optional description
- View all tasks, with completed tasks styled differently
- Edit a task, with a Cancel button that discards changes
- Delete a task after a browser confirmation
- Mark a task complete, or move it back to pending
- Filter by **All**, **Pending** or **Completed** (the filter is kept after an action)
- Tasks are stored in SQLite and survive restarts
- Input validation, friendly error messages, a 404 page and CSRF protection
- Responsive layout for desktop and mobile browsers

## Requirements

- Python 3 (Flask 3 needs 3.9+; this project was only tested on Python 3.15)
- `pip`

## Installation

Run these from the `todo-list` folder.

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running the application

```bash
flask --app app run
```

Then open <http://127.0.0.1:5000> in your browser. Press `Ctrl+C` to stop the server.

Alternatives:

- `python app.py` starts the same server.
- For auto-reload while editing code, run `flask --app app run --debug`.

The database file `tasks.db` is created automatically in the project folder the first time the
app starts. Existing data is never cleared on startup. To start fresh, stop the app and delete
`tasks.db`.

### Configuration (optional)

| Environment variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Signs the session and CSRF tokens. **Set your own value if the app is ever used by other people.** | an insecure development value |
| `TODO_DB_PATH` | Where to keep the SQLite file | `tasks.db` in the project folder |

## Using the app

1. Type a **Title** (required, up to 100 characters) and an optional **Description** (up to 1000
   characters), then press **Add Task**.
2. Use **Mark Complete** / **Mark Pending** to change a task's status.
3. Use **Edit** to change the title or description, then **Save Changes** (or **Cancel**).
4. Use **Delete** and confirm the browser prompt to remove a task permanently.
5. Use the **All / Pending / Completed** buttons above the list to filter.

Leading and trailing spaces are removed from titles and descriptions. A title that is empty or
only spaces is rejected with a message, and nothing is saved.

## Running the tests

```bash
python -m pytest
```

The tests use Flask's test client and a **temporary SQLite file** for every test, so your real
`tasks.db` is never touched. CSRF protection stays switched on during the tests.

## Project structure

```
todo-list/
├── app.py              Flask app factory, routes and input validation
├── database.py         SQLite connection, table setup and query helpers
├── requirements.txt    Python dependencies
├── templates/          base.html, index.html, edit_task.html, 404.html
├── static/css/style.css
└── tests/              conftest.py (fixtures) and test_tasks.py
```

## Design decisions and assumptions

The requirements left a few details open. These are the choices made:

- **Delete confirmation** uses an inline `confirm()` call, the only JavaScript in the app. Without
  JavaScript the delete button works but skips the confirmation.
- **Delete and complete are POST-only** and protected by CSRF tokens (Flask-WTF), so a link or
  a search-engine crawler can never change data.
- **Length limits:** titles 100 characters, descriptions 1000.
- **Invalid submissions** re-display the form with the error next to the field and an HTTP 400
  status. Nothing is written to the database.
- **Missing tasks** (unknown, huge or non-numeric IDs) return a friendly 404 page.
- **Unknown filter values** such as `?filter=banana` behave like **All**.
- **Order:** newest task first. **Timestamps** (`created_at`) are stored as UTC ISO-8601 text.
- Every SQL statement uses `?` placeholders. User input is never joined into SQL text, and
  Jinja2 auto-escapes task text in the pages.

## Known limitations

- Single-user only: there are no accounts, and anyone who can reach the server sees all tasks.
- If the CSRF token is missing or expired (for example a page left open for over an hour), the
  server shows Flask's plain "Bad Request" page. Reload the page and try again.
- Pending/completed status is shown as text and colour. The delete confirmation cannot be
  exercised by the automated tests, which only verify that the confirmation is attached to the form.
- The built-in Flask server is for local use. Use a production server such as Waitress or
  Gunicorn, and set `SECRET_KEY`, before exposing the app to a network.

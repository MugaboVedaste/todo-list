import os

from flask import Flask, abort, flash, redirect, render_template, request, url_for
from flask_wtf.csrf import CSRFProtect

import database

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Task IDs must fit in SQLite's 64-bit integer; larger numbers simply do not match (404).
TASK_ID = "<int(max=9223372036854775807):task_id>"

TITLE_MAX = 100
DESCRIPTION_MAX = 1000

FILTERS = ("all", "pending", "completed")

csrf = CSRFProtect()


def current_filter():
    """Return the filter named in the URL or form, falling back to 'all'."""
    value = request.values.get("filter", "all")
    return value if value in FILTERS else "all"


def redirect_to_list():
    """Go back to the task list, keeping the filter the user was viewing."""
    selected = current_filter()
    return redirect(url_for("index", filter=None if selected == "all" else selected))


def read_task_form(form):
    """Return (title, description, errors) from submitted form data.

    Leading and trailing whitespace is removed. errors maps a field name to
    a message; it is empty when the input is valid.
    """
    title = form.get("title", "").strip()
    description = form.get("description", "").strip()
    errors = {}
    if not title:
        errors["title"] = "Please enter a title for the task."
    elif len(title) > TITLE_MAX:
        errors["title"] = f"The title must be {TITLE_MAX} characters or fewer."
    if len(description) > DESCRIPTION_MAX:
        errors["description"] = (
            f"The description must be {DESCRIPTION_MAX} characters or fewer."
        )
    return title, description, errors


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        DATABASE=os.environ.get("TODO_DB_PATH", os.path.join(BASE_DIR, "tasks.db")),
    )
    if test_config:
        app.config.update(test_config)

    csrf.init_app(app)
    database.init_app(app)

    @app.errorhandler(404)
    def not_found(error):
        return render_template("404.html"), 404

    @app.route("/")
    def index():
        selected = current_filter()
        tasks = database.list_tasks(selected)
        return render_template(
            "index.html", tasks=tasks, selected=selected, form={}, errors={}
        )

    @app.route("/tasks", methods=["POST"])
    def add_task():
        title, description, errors = read_task_form(request.form)
        if errors:
            selected = current_filter()
            tasks = database.list_tasks(selected)
            form = {"title": title, "description": description}
            return (
                render_template(
                    "index.html", tasks=tasks, selected=selected, form=form, errors=errors
                ),
                400,
            )
        database.add_task(title, description or None)
        flash("Task added.", "success")
        return redirect(url_for("index"))

    @app.route(f"/tasks/{TASK_ID}/edit", methods=["GET", "POST"])
    def edit_task(task_id):
        task = database.get_task(task_id)
        if task is None:
            abort(404)

        if request.method == "GET":
            form = {"title": task["title"], "description": task["description"] or ""}
            return render_template(
                "edit_task.html", task=task, selected=current_filter(), form=form, errors={}
            )

        title, description, errors = read_task_form(request.form)
        if errors:
            form = {"title": title, "description": description}
            return (
                render_template(
                    "edit_task.html",
                    task=task,
                    selected=current_filter(),
                    form=form,
                    errors=errors,
                ),
                400,
            )
        database.update_task(task_id, title, description or None)
        flash("Task updated.", "success")
        return redirect_to_list()

    @app.route(f"/tasks/{TASK_ID}/status", methods=["POST"])
    def set_task_status(task_id):
        """Mark a task completed (completed=1) or pending (completed=0)."""
        if database.get_task(task_id) is None:
            abort(404)
        value = request.form.get("completed")
        if value not in ("0", "1"):
            abort(400)
        database.set_completed(task_id, value == "1")
        flash("Task marked as completed." if value == "1" else "Task moved back to pending.", "success")
        return redirect_to_list()

    @app.route(f"/tasks/{TASK_ID}/delete", methods=["POST"])
    def delete_task(task_id):
        if not database.delete_task(task_id):
            abort(404)
        flash("Task deleted.", "success")
        return redirect_to_list()

    return app


if __name__ == "__main__":
    # Debug mode is off unless you opt in with FLASK_DEBUG=1.
    create_app().run(debug=os.environ.get("FLASK_DEBUG") == "1")

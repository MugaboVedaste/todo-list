import os
import sqlite3

import database
from app import DESCRIPTION_MAX, TITLE_MAX, create_app


def all_tasks(app):
    """Read tasks straight from SQLite, independent of the web pages."""
    with app.app_context():
        return [dict(row) for row in database.list_tasks()]


# --- Phase 2: database setup and persistence (FR-07) -------------------------

def test_database_file_and_table_are_created_automatically(db_path):
    assert not os.path.exists(db_path)
    create_app({"TESTING": True, "DATABASE": db_path})
    assert os.path.exists(db_path)

    conn = sqlite3.connect(db_path)
    columns = {row[1]: row for row in conn.execute("PRAGMA table_info(tasks)")}
    conn.close()
    assert set(columns) == {"id", "title", "description", "completed", "created_at"}
    assert columns["title"][3] == 1       # title is NOT NULL
    assert columns["completed"][3] == 1   # completed is NOT NULL
    assert columns["completed"][4] == "0"  # completed defaults to 0
    assert columns["created_at"][3] == 1  # created_at is NOT NULL


def test_tasks_survive_app_restart(db_path):
    first = create_app({"TESTING": True, "DATABASE": db_path})
    with first.app_context():
        task_id = database.add_task("Keep me", "after restart")
        database.set_completed(task_id, True)

    # "Restart": build a brand new app against the same database file.
    second = create_app({"TESTING": True, "DATABASE": db_path})
    with second.app_context():
        task = database.get_task(task_id)
        assert task["title"] == "Keep me"
        assert task["description"] == "after restart"
        assert task["completed"] == 1


def test_init_does_not_clear_existing_data(db_path):
    app = create_app({"TESTING": True, "DATABASE": db_path})
    with app.app_context():
        database.add_task("Stay", "")
        database.init_db()  # running setup again must not wipe anything
        assert len(database.list_tasks()) == 1


def test_sql_injection_text_is_stored_as_plain_text(db_path):
    app = create_app({"TESTING": True, "DATABASE": db_path})
    nasty = "x'); DROP TABLE tasks; --"
    with app.app_context():
        task_id = database.add_task(nasty, "")
        assert database.get_task(task_id)["title"] == nasty
        assert len(database.list_tasks()) == 1


# --- Phase 3: add and view tasks (FR-01, FR-02, FR-07, FR-08) ----------------

def test_empty_list_shows_friendly_message(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"You have no tasks yet" in response.data


def test_main_page_shows_app_name_and_add_form(client):
    html = client.get("/").get_data(as_text=True)
    assert "Simple To-Do List" in html
    assert '<label for="title">' in html
    assert '<label for="description">' in html


def test_add_task_with_title_and_description(browser, app):
    response = browser.post(
        "/tasks", {"title": "Buy milk", "description": "2 litres"}, follow_redirects=True
    )
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Buy milk" in html
    assert "2 litres" in html
    assert "Task added." in html
    assert "Pending" in html

    rows = all_tasks(app)
    assert len(rows) == 1
    assert rows[0]["title"] == "Buy milk"
    assert rows[0]["description"] == "2 litres"
    assert rows[0]["completed"] == 0
    assert rows[0]["created_at"]


def test_add_task_description_is_optional(browser, app):
    browser.post("/tasks", {"title": "No details"})
    rows = all_tasks(app)
    assert len(rows) == 1
    assert not rows[0]["description"]


def test_tasks_are_listed_newest_first(browser):
    browser.post("/tasks", {"title": "First task"})
    browser.post("/tasks", {"title": "Second task"})
    html = browser.get("/").get_data(as_text=True)
    assert html.index("Second task") < html.index("First task")


def test_empty_title_is_rejected(browser, app):
    response = browser.post("/tasks", {"title": "", "description": "keep me in the form"})
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert "Please enter a title" in html
    assert "keep me in the form" in html  # user's typing is not lost
    assert all_tasks(app) == []


def test_whitespace_only_title_is_rejected(browser, app):
    response = browser.post("/tasks", {"title": "   \t  "})
    assert response.status_code == 400
    assert "Please enter a title" in response.get_data(as_text=True)
    assert all_tasks(app) == []


def test_missing_title_field_is_rejected(browser, app):
    response = browser.post("/tasks", {"description": "no title field at all"})
    assert response.status_code == 400
    assert all_tasks(app) == []


def test_title_whitespace_is_trimmed(browser, app):
    browser.post("/tasks", {"title": "   Trim me  ", "description": "  details  "})
    row = all_tasks(app)[0]
    assert row["title"] == "Trim me"
    assert row["description"] == "details"


def test_too_long_title_and_description_are_rejected(browser, app):
    r1 = browser.post("/tasks", {"title": "x" * (TITLE_MAX + 1)})
    r2 = browser.post("/tasks", {"title": "ok", "description": "y" * (DESCRIPTION_MAX + 1)})
    assert r1.status_code == 400
    assert r2.status_code == 400
    assert all_tasks(app) == []


def test_title_at_maximum_length_is_accepted(browser, app):
    browser.post("/tasks", {"title": "x" * TITLE_MAX})
    assert len(all_tasks(app)) == 1


def test_html_in_title_is_escaped(browser):
    browser.post("/tasks", {"title": "<script>alert(1)</script>"})
    html = browser.get("/").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_post_without_csrf_token_is_rejected(client, app):
    response = client.post("/tasks", data={"title": "Sneaky"})
    assert response.status_code == 400
    assert all_tasks(app) == []


def test_post_with_wrong_csrf_token_is_rejected(client, app):
    response = client.post("/tasks", data={"title": "Sneaky", "csrf_token": "bogus"})
    assert response.status_code == 400
    assert all_tasks(app) == []


def test_added_task_survives_restart(browser, db_path):
    browser.post("/tasks", {"title": "Persistent task"})
    restarted = create_app({"TESTING": True, "DATABASE": db_path}).test_client()
    assert b"Persistent task" in restarted.get("/").data


# --- Phase 4: edit, delete, complete (FR-03, FR-04, FR-05) -------------------

def make_task(app, title="Sample task", description="Sample details", completed=False):
    """Insert a task directly into the test database and return its ID."""
    with app.app_context():
        task_id = database.add_task(title, description or None)
        if completed:
            database.set_completed(task_id, True)
        return task_id


def get_row(app, task_id):
    with app.app_context():
        row = database.get_task(task_id)
        return dict(row) if row else None


# FR-03 Edit

def test_edit_page_is_prefilled(client, app):
    task_id = make_task(app, "Original title", "Original details")
    html = client.get(f"/tasks/{task_id}/edit").get_data(as_text=True)
    assert 'value="Original title"' in html
    assert "Original details" in html
    assert "Save Changes" in html
    assert "Cancel" in html


def test_edit_saves_valid_changes(browser, app):
    task_id = make_task(app, "Old", "Old details")
    response = browser.post(
        f"/tasks/{task_id}/edit",
        {"title": "  New title ", "description": "New details"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "New title" in html
    assert "Task updated." in html
    row = get_row(app, task_id)
    assert row["title"] == "New title"
    assert row["description"] == "New details"


def test_edit_can_clear_description(browser, app):
    task_id = make_task(app, "Title", "Some details")
    browser.post(f"/tasks/{task_id}/edit", {"title": "Title", "description": ""})
    assert not get_row(app, task_id)["description"]


def test_edit_with_empty_title_keeps_existing_task(browser, app):
    task_id = make_task(app, "Keep this", "Keep details")
    response = browser.post(f"/tasks/{task_id}/edit", {"title": "   ", "description": "changed"})
    assert response.status_code == 400
    assert "Please enter a title" in response.get_data(as_text=True)
    row = get_row(app, task_id)
    assert row["title"] == "Keep this"
    assert row["description"] == "Keep details"


def test_edit_with_too_long_title_is_rejected(browser, app):
    task_id = make_task(app, "Keep this")
    response = browser.post(f"/tasks/{task_id}/edit", {"title": "x" * (TITLE_MAX + 1)})
    assert response.status_code == 400
    assert get_row(app, task_id)["title"] == "Keep this"


def test_cancel_link_returns_to_list_without_saving(client, app):
    task_id = make_task(app, "Unchanged")
    html = client.get(f"/tasks/{task_id}/edit").get_data(as_text=True)
    assert 'href="/"' in html  # Cancel is a plain link back to the list
    assert get_row(app, task_id)["title"] == "Unchanged"


def test_edit_does_not_change_completion_status(browser, app):
    task_id = make_task(app, "Done task", completed=True)
    browser.post(f"/tasks/{task_id}/edit", {"title": "Renamed"})
    assert get_row(app, task_id)["completed"] == 1


# FR-04 Delete

def test_delete_form_asks_for_confirmation(client, app):
    task_id = make_task(app)
    html = client.get("/").get_data(as_text=True)
    assert f'action="/tasks/{task_id}/delete"' in html
    assert "onsubmit=\"return confirm(" in html


def test_delete_removes_task(browser, app):
    keep = make_task(app, "Keep")
    gone = make_task(app, "Remove")
    response = browser.post(f"/tasks/{gone}/delete", follow_redirects=True)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Task deleted." in html
    assert "Remove" not in html.replace("Task deleted.", "")
    assert get_row(app, gone) is None
    assert get_row(app, keep) is not None


def test_delete_requires_post(client, app):
    task_id = make_task(app)
    assert client.get(f"/tasks/{task_id}/delete").status_code == 405
    assert get_row(app, task_id) is not None


# FR-05 Complete

def test_mark_pending_task_complete_then_pending(browser, app):
    task_id = make_task(app)
    browser.post(f"/tasks/{task_id}/status", {"completed": "1"})
    assert get_row(app, task_id)["completed"] == 1
    assert "Completed" in browser.get("/").get_data(as_text=True)

    browser.post(f"/tasks/{task_id}/status", {"completed": "0"})
    assert get_row(app, task_id)["completed"] == 0
    assert "Pending" in browser.get("/").get_data(as_text=True)


def test_completed_task_looks_different(browser, app):
    make_task(app, "Done one", completed=True)
    html = browser.get("/").get_data(as_text=True)
    assert "task-completed" in html
    assert "Mark Pending" in html


def test_pending_task_has_no_completed_style(browser, app):
    make_task(app, "Todo one")
    html = browser.get("/").get_data(as_text=True)
    assert "task-completed" not in html
    assert "Mark Complete" in html


def test_status_is_correct_after_restart(browser, app, db_path):
    task_id = make_task(app)
    browser.post(f"/tasks/{task_id}/status", {"completed": "1"})
    restarted = create_app({"TESTING": True, "DATABASE": db_path})
    assert get_row(restarted, task_id)["completed"] == 1


def test_invalid_status_value_is_rejected(browser, app):
    task_id = make_task(app)
    assert browser.post(f"/tasks/{task_id}/status", {"completed": "banana"}).status_code == 400
    assert browser.post(f"/tasks/{task_id}/status", {}).status_code == 400
    assert get_row(app, task_id)["completed"] == 0


def test_edit_delete_status_require_csrf_token(client, app):
    task_id = make_task(app, "Protected")
    assert client.post(f"/tasks/{task_id}/edit", data={"title": "Hacked"}).status_code == 400
    assert client.post(f"/tasks/{task_id}/status", data={"completed": "1"}).status_code == 400
    assert client.post(f"/tasks/{task_id}/delete").status_code == 400
    row = get_row(app, task_id)
    assert row["title"] == "Protected"
    assert row["completed"] == 0


# --- Phase 5: filters and error handling (FR-06, FR-09) ----------------------

def page(client, url):
    response = client.get(url)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_filter_all_shows_pending_and_completed(client, app):
    make_task(app, "Pending one")
    make_task(app, "Completed one", completed=True)
    for url in ("/", "/?filter=all"):
        html = page(client, url)
        assert "Pending one" in html
        assert "Completed one" in html


def test_filter_pending_shows_only_pending(client, app):
    make_task(app, "Pending one")
    make_task(app, "Completed one", completed=True)
    html = page(client, "/?filter=pending")
    assert "Pending one" in html
    assert "Completed one" not in html


def test_filter_completed_shows_only_completed(client, app):
    make_task(app, "Pending one")
    make_task(app, "Completed one", completed=True)
    html = page(client, "/?filter=completed")
    assert "Completed one" in html
    assert "Pending one" not in html


def test_filter_links_are_present_and_active_one_is_marked(client):
    html = page(client, "/?filter=pending")
    assert 'href="/?filter=all"' in html
    assert 'href="/?filter=pending"' in html
    assert 'href="/?filter=completed"' in html
    assert 'aria-current="page">Pending' in html


def test_filtering_does_not_change_data(client, app):
    make_task(app, "Pending one")
    make_task(app, "Completed one", completed=True)
    before = all_tasks(app)
    for name in ("pending", "completed", "all", "pending"):
        client.get(f"/?filter={name}")
    assert all_tasks(app) == before


def test_unknown_filter_falls_back_to_all(client, app):
    make_task(app, "Pending one")
    make_task(app, "Completed one", completed=True)
    html = page(client, "/?filter=banana")
    assert "Pending one" in html
    assert "Completed one" in html


def test_sql_injection_in_filter_is_harmless(client, app):
    make_task(app, "Still here")
    html = page(client, "/?filter=' OR 1=1; DROP TABLE tasks; --")
    assert "Still here" in html
    assert len(all_tasks(app)) == 1


def test_empty_filter_results_show_friendly_message(client, app):
    make_task(app, "Only pending")
    assert "No completed tasks yet" in page(client, "/?filter=completed")
    with app.app_context():
        database.delete_task(1)
    assert "No pending tasks" in page(client, "/?filter=pending")


def test_actions_keep_the_current_filter(browser, app):
    pending_id = make_task(app, "Pending one")
    done_id = make_task(app, "Done one", completed=True)

    r = browser.post(f"/tasks/{pending_id}/status", {"completed": "1", "filter": "pending"})
    assert r.headers["Location"].endswith("/?filter=pending")

    r = browser.post(f"/tasks/{done_id}/delete", {"filter": "completed"})
    assert r.headers["Location"].endswith("/?filter=completed")

    r = browser.post(f"/tasks/{pending_id}/edit?filter=completed", {"title": "Renamed"})
    assert r.headers["Location"].endswith("/?filter=completed")

    r = browser.post(f"/tasks/{pending_id}/status", {"completed": "0", "filter": "garbage"})
    assert r.headers["Location"].endswith("/")  # bad filter -> All, no query string


# FR-09 Missing tasks

def test_edit_unknown_task_returns_404_page(browser):
    for method in (browser.get, browser.post):
        response = method("/tasks/999/edit")
        assert response.status_code == 404
        assert "Page not found" in response.get_data(as_text=True)


def test_status_unknown_task_returns_404(browser):
    assert browser.post("/tasks/999/status", {"completed": "1"}).status_code == 404


def test_delete_unknown_task_returns_404(browser):
    assert browser.post("/tasks/999/delete").status_code == 404


def test_deleted_task_returns_404_afterwards(browser, app):
    task_id = make_task(app)
    browser.post(f"/tasks/{task_id}/delete")
    assert browser.get(f"/tasks/{task_id}/edit").status_code == 404
    assert browser.post(f"/tasks/{task_id}/delete").status_code == 404


def test_huge_and_nonnumeric_task_ids_return_404_not_500(browser):
    for bad_id in ("99999999999999999999999", "abc", "-1", "0"):
        assert browser.get(f"/tasks/{bad_id}/edit").status_code == 404
        assert browser.post(f"/tasks/{bad_id}/delete").status_code == 404
        assert browser.post(f"/tasks/{bad_id}/status", {"completed": "1"}).status_code == 404


def test_unknown_page_shows_friendly_404(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert "Back to my tasks" in response.get_data(as_text=True)


# --- Phase 6/7: interface rules (UI-01, UI-02, UI-03, NFR-05, NFR-06) --------

def test_pages_are_semantic_and_mobile_ready(client, app):
    task_id = make_task(app)
    for url in ("/", f"/tasks/{task_id}/edit", "/no-such-page"):
        html = client.get(url).get_data(as_text=True)
        assert "<!DOCTYPE html>" in html
        assert '<html lang="en">' in html
        assert 'name="viewport" content="width=device-width, initial-scale=1"' in html
        assert "<h1>" in html
        assert "<main" in html


def test_form_fields_have_labels_on_both_forms(client, app):
    task_id = make_task(app)
    for url in ("/", f"/tasks/{task_id}/edit"):
        html = client.get(url).get_data(as_text=True)
        assert '<label for="title">' in html and 'id="title"' in html
        assert '<label for="description">' in html and 'id="description"' in html


def test_validation_error_is_shown_next_to_the_field(browser):
    html = browser.post("/tasks", {"title": ""}).get_data(as_text=True)
    assert 'aria-describedby="title-error"' in html
    assert 'id="title-error"' in html


def test_every_form_that_changes_data_carries_a_csrf_token(client, app):
    task_id = make_task(app)
    index_html = client.get("/").get_data(as_text=True)
    edit_html = client.get(f"/tasks/{task_id}/edit").get_data(as_text=True)
    # add form + complete form + delete form on the list; one form on the edit page
    assert index_html.count('name="csrf_token"') == 3
    assert edit_html.count('name="csrf_token"') == 1


def test_stylesheet_is_served_and_is_responsive(client):
    response = client.get("/static/css/style.css")
    assert response.status_code == 200
    css = response.get_data(as_text=True)
    assert "@media" in css
    assert ".task-completed" in css
    response.close()


def test_task_page_works_without_javascript_except_for_confirm(client, app):
    make_task(app)
    html = client.get("/").get_data(as_text=True)
    assert "<script" not in html

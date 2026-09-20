def test_tasks_page_renders_sidebar_and_active_nav(client):
    response = client.get("/tasks")
    assert response.status_code == 200
    body = response.text
    assert 'class="app-shell"' in body
    assert 'class="app-sidebar"' in body
    assert "IDEA SPACE" in body
    assert 'nav-item nav-item--active' in body
    assert 'href="/tasks"' in body


def test_calendar_page_has_different_active_nav_than_tasks(client):
    tasks_body = client.get("/tasks").text
    calendar_body = client.get("/calendar").text
    # Each page's own nav link is the one marked active.
    tasks_active_idx = tasks_body.index('nav-item nav-item--active')
    assert 'href="/tasks"' in tasks_body[tasks_active_idx - 40 : tasks_active_idx + 60]
    calendar_active_idx = calendar_body.index('nav-item nav-item--active')
    assert 'href="/calendar"' in calendar_body[calendar_active_idx - 40 : calendar_active_idx + 60]

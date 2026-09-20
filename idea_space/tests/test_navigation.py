def test_main_nav_present_on_tasks_page(client):
    response = client.get("/tasks")
    assert response.status_code == 200
    assert b'class="primary-nav"' in response.content
    assert b'href="/requirements"' in response.content
    assert b'href="/matrix"' in response.content

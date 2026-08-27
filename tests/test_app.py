def test_dashboard_skeleton_renders(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"Home Lab Status" in response.data


def test_health_endpoint_returns_json(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json == {"data": {"status": "ok"}, "error": None}


def test_unknown_route_uses_custom_page(client):
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert b"Page not found" in response.data


def test_unknown_api_route_uses_json_error(client):
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.json == {"data": None, "error": "Not found"}

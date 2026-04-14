def test_health_endpoint(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "timestamp" in payload
    assert "environment" in payload
    assert "version" in payload
    assert "x-request-id" in response.headers

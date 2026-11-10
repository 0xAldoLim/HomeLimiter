def test_auth_and_host(client):
    assert client.get("/api/devices", headers={"Authorization": ""}).status_code == 401
    assert client.get("/api/status", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/api/status").json()["capabilities"]["simulated"] is True


def test_csrf(client):
    assert (
        client.post("/api/discover", json={}, headers={"Origin": "https://evil.example"}).status_code == 403
    )
    assert client.post("/api/discover", content="{}").status_code == 415
    assert client.post("/api/discover", json={}, headers={"Origin": "http://testserver"}).status_code == 200


def test_policy_lifecycle(client):
    refused = client.post("/api/policies", json={"device_id": "demo-2", "blocked": True})
    assert refused.status_code == 409
    result = client.post(
        "/api/policies", json={"device_id": "demo-2", "blocked": True, "confirm_device_id": "demo-2"}
    )
    assert result.status_code == 200 and result.json()["simulated"]
    identifier = result.json()["policy"]["id"]
    assert client.get("/api/devices/demo-2").json()["stats"]["available"] is False
    assert client.request("DELETE", f"/api/policies/{identifier}", json={}).status_code == 200
    assert client.get("/api/policies").json() == []


def test_error_and_secret_redaction(client):
    assert client.get("/api/devices/missing").status_code == 404
    assert client.post("/api/emergency", json={"confirm": False}).status_code == 409
    assert "token" not in client.get("/api/settings").text
    assert client.get("/").headers["content-security-policy"].startswith("default-src 'self'")

def auth_headers(client, email="test@example.com", password="test123"):
    r = client.post("/api/auth/register", json={"email": email, "name": "Test", "password": password})
    if r.status_code != 200:
        r = client.post("/api/auth/login", data={"username": email, "password": password})
        assert r.status_code == 200, r.text
    token = r.json().get("access_token")
    return {"Authorization": f"Bearer {token}"}

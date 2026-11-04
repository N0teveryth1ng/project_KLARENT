from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
r = client.get('/dashboard/')
print(r.status_code)
print(r.text[:500])

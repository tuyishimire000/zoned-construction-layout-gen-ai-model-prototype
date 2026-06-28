from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

desc = "I want a house with no parking one bathroom kitchen outside and everything else you suggest on 1000sqm"

try:
    response = client.post("/api/analyze", json={"description": desc})
    print("STATUS:", response.status_code)
    print("RESPONSE:", response.json())
except Exception as e:
    import traceback
    traceback.print_exc()



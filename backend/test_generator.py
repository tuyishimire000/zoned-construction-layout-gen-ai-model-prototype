from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

desc = "I have a 600 sqm plot. I want a house with 3 bedrooms, 1 living room, 1 kitchen, and 2 bathrooms, plus parking for 2 cars."

try:
    response = client.post("/api/analyze", json={"description": desc})
    print("STATUS:", response.status_code)
    print("RESPONSE:", response.json())
except Exception as e:
    import traceback
    traceback.print_exc()



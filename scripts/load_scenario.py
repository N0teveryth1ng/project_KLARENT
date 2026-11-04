import json
import sys
from app.database.session import SessionLocal
from app.models.scenario import Scenario

if len(sys.argv) < 2:
    print("Usage: python scripts/load_scenario.py <scenario.json>")
    sys.exit(1)

with open(sys.argv[1]) as f:
    data = json.load(f)

db = SessionLocal()
scenario = Scenario(
    name=data["name"],
    description=data.get("description"),
    configuration=data
)
db.add(scenario)
db.commit()
print(f"Loaded scenario: {scenario.id}")
db.close()

import os
from sqlalchemy import create_engine, text

env_vars = {}
with open('.env.vercel', 'r') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env_vars[k.strip()] = v.strip('"').strip("'")

db_url = env_vars.get('DATABASE_URL')
if not db_url:
    print("No DATABASE_URL found")
    exit(1)

if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

engine = create_engine(db_url, connect_args={"sslmode": "require"} if db_url.startswith("postgresql") else {})
with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE users ADD COLUMN full_name VARCHAR;"))
        conn.commit()
        print("Success adding full_name column!")
    except Exception as e:
        print(f"Error: {e}")

import os
import sys
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()

# We must ensure we connect to Postgres using pg8000
db_url = os.environ.get("DATABASE_URL")
if db_url and db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)
elif db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+pg8000://", 1)

print(f"Connecting to {db_url}")

# Setup SSL args exactly as in db.py
import ssl
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE
engine_args = {"connect_args": {"ssl_context": ssl_context}}

engine = create_engine(db_url, **engine_args)

from app.data.db import Base

print("Dropping all existing tables to clear history and reset schema...")
Base.metadata.drop_all(bind=engine)

print("Creating all tables with new Auth schema...")
Base.metadata.create_all(bind=engine)

print("Migration complete!")

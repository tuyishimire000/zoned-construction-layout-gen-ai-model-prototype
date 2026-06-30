import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

db_url = os.environ.get("DATABASE_URL")
if db_url:
    db_url = db_url.replace(":5432/", ":6543/")
if db_url and db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)

import ssl
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE
engine_args = {"connect_args": {"ssl_context": ssl_context}}

engine = create_engine(db_url, **engine_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from app.data.db import User
from app.api.auth import get_password_hash

def seed_users():
    db = SessionLocal()
    try:
        # Check if users exist
        user1 = db.query(User).filter(User.username == "architect_alice").first()
        if not user1:
            user1 = User(
                username="architect_alice",
                hashed_password=get_password_hash("password123")
            )
            db.add(user1)
            print("Seeded user: architect_alice (password: password123)")
        
        user2 = db.query(User).filter(User.username == "builder_bob").first()
        if not user2:
            user2 = User(
                username="builder_bob",
                hashed_password=get_password_hash("password123")
            )
            db.add(user2)
            print("Seeded user: builder_bob (password: password123)")
            
        db.commit()
        print("Database seeding completed.")
    except Exception as e:
        print(f"Error seeding database: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_users()

import sys
import os
import time

# Add backend to path so we can import our models
sys.path.insert(0, os.path.abspath('backend'))

from sqlalchemy import create_engine
from sqlalchemy.schema import CreateTable
from app.data.db import Base

# We MUST create a postgres engine specifically to dump postgres-compatible syntax
# (e.g., using proper JSON/JSONB types instead of SQLite text types)
engine = create_engine('postgresql://postgres:postgres@localhost:5432/postgres')

# Create the migrations directory if it doesn't exist
os.makedirs('supabase/migrations', exist_ok=True)

# Generate a timestamp for the migration file
timestamp = time.strftime('%Y%m%d%H%M%S')
filename = f"supabase/migrations/{timestamp}_initial_schema.sql"

with open(filename, 'w') as f:
    for table in Base.metadata.sorted_tables:
        create_stmt = CreateTable(table).compile(engine)
        # compile() returns a string that ends with a newline, but not necessarily a semicolon
        sql = str(create_stmt).strip()
        if not sql.endswith(';'):
            sql += ';'
        f.write(sql + '\n\n')

print(f"Successfully generated migration file: {filename}")

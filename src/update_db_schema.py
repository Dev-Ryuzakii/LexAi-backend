#!/usr/bin/env python3
"""
Script to update the database schema with new authentication fields
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from database import engine, Base
from sqlalchemy import text

def update_schema():
    """Update the database schema with new authentication fields"""
    try:
        # Add password_hash column to users table
        with engine.connect() as conn:
            # Check if the column exists
            result = conn.execute(text("PRAGMA table_info(users)"))
            columns = [row[1] for row in result]
            
            if 'password_hash' not in columns:
                print("Adding password_hash column to users table...")
                conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(128)"))
                print("password_hash column added successfully")
            else:
                print("password_hash column already exists")
            
            conn.commit()
        
        print("Database schema updated successfully")
        
    except Exception as e:
        print(f"Error updating database schema: {e}")

if __name__ == "__main__":
    update_schema()
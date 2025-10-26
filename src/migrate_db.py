#!/usr/bin/env python3
"""
Database migration script for AI-CBT API Platform.
This script initializes the database using Alembic migrations.
"""

import os
import sys
from alembic.config import Config
from alembic import command

def run_migrations():
    """Run database migrations"""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Go up one directory to the project root
    project_root = os.path.dirname(script_dir)
    
    # Path to alembic.ini
    alembic_ini_path = os.path.join(project_root, 'alembic.ini')
    
    # Check if alembic.ini exists
    if not os.path.exists(alembic_ini_path):
        print(f"Error: alembic.ini not found at {alembic_ini_path}")
        return False
    
    # Create Alembic config
    alembic_cfg = Config(alembic_ini_path)
    alembic_cfg.set_main_option("script_location", os.path.join(project_root, "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", "sqlite:///data/database.db")
    
    try:
        # Run migrations
        command.upgrade(alembic_cfg, "head")
        print("✅ Database migrations completed successfully")
        return True
    except Exception as e:
        # Check if it's a table already exists error, which is fine for existing databases
        error_str = str(e)
        if "already exists" in error_str:
            print("ℹ️  Database tables already exist, migration not needed")
            return True
        else:
            print(f"❌ Error running migrations: {e}")
            return False

def init_database():
    """Initialize the database with migrations"""
    print("🔄 Initializing database with migrations...")
    
    # Run migrations
    if run_migrations():
        print("✅ Database initialization completed")
        return True
    else:
        print("❌ Database initialization failed")
        return False

if __name__ == "__main__":
    success = init_database()
    sys.exit(0 if success else 1)
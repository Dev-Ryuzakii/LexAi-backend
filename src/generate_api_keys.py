#!/usr/bin/env python3
"""
API Key Generation Script for AI-CBT API Platform.
This script generates API keys for testing and production environments.
"""

import os
import sys
import secrets
import string
import argparse
from datetime import datetime

# Add the src directory to the path so we can import our models
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from database import DATABASE_URL, SessionLocal, User, APIKey

def generate_api_key(length=32):
    """Generate a secure random API key"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def create_user(session, email, plan_type="free"):
    """Create a new user or return existing user"""
    # Check if user already exists
    user = session.query(User).filter(User.email == email).first()
    if user:
        print(f"ℹ️  User {email} already exists (ID: {user.id})")
        return user
    
    # Create new user
    user = User(email=email, plan_type=plan_type)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user

def create_api_key(session, user_id, key_name, rate_limit=1000, monthly_quota=10000, is_active=True):
    """Create a new API key for a user"""
    api_key = generate_api_key()
    key = APIKey(
        key_name=key_name,
        api_key=api_key,
        user_id=user_id,
        rate_limit=rate_limit,
        monthly_quota=monthly_quota,
        is_active=is_active
    )
    session.add(key)
    session.commit()
    session.refresh(key)
    return key

def generate_test_keys():
    """Generate test API keys"""
    print("🔄 Generating test API keys...")
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Create a test user
        test_user = create_user(db, "test@example.com", "testing")
        print(f"✅ Test user: {test_user.email} (ID: {test_user.id})")
        
        # Create test API keys
        test_keys = [
            {
                "name": "Development Key",
                "key_name": "dev_key",
                "rate_limit": 1000,
                "monthly_quota": 10000
            },
            {
                "name": "Testing Key",
                "key_name": "test_key",
                "rate_limit": 500,
                "monthly_quota": 5000
            },
            {
                "name": "Staging Key",
                "key_name": "staging_key",
                "rate_limit": 2000,
                "monthly_quota": 20000
            }
        ]
        
        created_keys = []
        for key_info in test_keys:
            # Check if API key with this name already exists for this user
            existing_key = db.query(APIKey).filter(
                APIKey.user_id == test_user.id,
                APIKey.key_name == key_info["key_name"]
            ).first()
            
            if existing_key:
                print(f"ℹ️  {key_info['name']} already exists: {existing_key.api_key}")
                created_keys.append(existing_key)
                continue
            
            api_key = create_api_key(
                db,
                test_user.id,
                key_info["key_name"],
                key_info["rate_limit"],
                key_info["monthly_quota"]
            )
            created_keys.append(api_key)
            print(f"✅ Created {key_info['name']}: {api_key.api_key}")
        
        return created_keys
        
    except Exception as e:
        print(f"❌ Error generating test keys: {e}")
        return []
    finally:
        db.close()

def generate_production_keys():
    """Generate production API keys"""
    print("🔄 Generating production API keys...")
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Create a production user
        prod_user = create_user(db, "admin@ai-cbt-platform.com", "enterprise")
        print(f"✅ Production user: {prod_user.email} (ID: {prod_user.id})")
        
        # Create production API keys
        prod_keys = [
            {
                "name": "Production Admin Key",
                "key_name": "prod_admin_key",
                "rate_limit": 10000,
                "monthly_quota": 1000000
            },
            {
                "name": "Production Service Key",
                "key_name": "prod_service_key",
                "rate_limit": 5000,
                "monthly_quota": 500000
            }
        ]
        
        created_keys = []
        for key_info in prod_keys:
            # Check if API key with this name already exists for this user
            existing_key = db.query(APIKey).filter(
                APIKey.user_id == prod_user.id,
                APIKey.key_name == key_info["key_name"]
            ).first()
            
            if existing_key:
                print(f"ℹ️  {key_info['name']} already exists: {existing_key.api_key}")
                created_keys.append(existing_key)
                continue
            
            api_key = create_api_key(
                db,
                prod_user.id,
                key_info["key_name"],
                key_info["rate_limit"],
                key_info["monthly_quota"]
            )
            created_keys.append(api_key)
            print(f"✅ Created {key_info['name']}: {api_key.api_key}")
        
        return created_keys
        
    except Exception as e:
        print(f"❌ Error generating production keys: {e}")
        return []
    finally:
        db.close()

def list_existing_keys():
    """List all existing API keys"""
    print("📋 Listing existing API keys...")
    
    # Create database session
    db = SessionLocal()
    
    try:
        keys = db.query(APIKey).all()
        if not keys:
            print("ℹ️  No API keys found in the database")
            return
        
        print(f"{'ID':<5} {'Key Name':<20} {'API Key':<35} {'Rate Limit':<12} {'Monthly Quota':<15} {'Active':<8}")
        print("-" * 100)
        for key in keys:
            # Convert SQLAlchemy boolean to Python boolean
            active_status = "Yes" if bool(key.is_active) else "No"
            print(f"{key.id:<5} {key.key_name:<20} {key.api_key:<35} {key.rate_limit:<12} {key.monthly_quota:<15} {active_status:<8}")
            
    except Exception as e:
        print(f"❌ Error listing API keys: {e}")
    finally:
        db.close()

def main():
    """Main function to handle command line arguments"""
    parser = argparse.ArgumentParser(description="Generate API keys for AI-CBT API Platform")
    parser.add_argument("--test", action="store_true", help="Generate test API keys")
    parser.add_argument("--prod", action="store_true", help="Generate production API keys")
    parser.add_argument("--list", action="store_true", help="List existing API keys")
    parser.add_argument("--all", action="store_true", help="Generate both test and production API keys")
    
    args = parser.parse_args()
    
    # Ensure database tables exist
    from database import Base, engine
    Base.metadata.create_all(bind=engine)
    
    if args.list:
        list_existing_keys()
        return
    
    if args.test or args.all:
        generate_test_keys()
    
    if args.prod or args.all:
        generate_production_keys()
    
    if not any([args.test, args.prod, args.list, args.all]):
        # Default behavior: show help
        parser.print_help()

if __name__ == "__main__":
    main()
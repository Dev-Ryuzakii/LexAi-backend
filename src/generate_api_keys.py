#!/usr/bin/env python3
"""
Operator CLI for API keys. Keys are stored hashed, so the plaintext is printed once at creation.

    python src/generate_api_keys.py create --email user@example.com --name "CBT integration" [--plan test]
    python src/generate_api_keys.py list [--email user@example.com]
    python src/generate_api_keys.py revoke --id 3

The user must already exist (register through the API or the frontend).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api_service import PLAN_LIMITS, new_api_key  # noqa: E402
from database import APIKey, SessionLocal, User  # noqa: E402


def create(args):
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=args.email.lower()).first()
        if not user:
            sys.exit(f"No user with email {args.email}")
        caps = PLAN_LIMITS[args.plan]
        key, plaintext = new_api_key(db, user.id, args.name, args.plan, caps['rate_limit'], caps['monthly_quota'])
        db.commit()
        print(f"Created key {key.id} ({args.plan}) for {user.email}:\n\n  {plaintext}\n\nStore it now; it cannot be shown again.")
    finally:
        db.close()


def list_keys(args):
    db = SessionLocal()
    try:
        query = db.query(APIKey, User).join(User, APIKey.user_id == User.id)
        if args.email:
            query = query.filter(User.email == args.email.lower())
        print(f"{'ID':<5} {'Owner':<30} {'Name':<25} {'Prefix':<14} {'Plan':<11} {'Active'}")
        for key, user in query.order_by(APIKey.id):
            print(f"{key.id:<5} {user.email:<30} {key.key_name:<25} {key.key_prefix:<14} {key.plan_type or '-':<11} {'yes' if key.is_active else 'no'}")
    finally:
        db.close()


def revoke(args):
    db = SessionLocal()
    try:
        key = db.get(APIKey, args.id)
        if not key:
            sys.exit(f"No key with id {args.id}")
        key.is_active = False
        db.commit()
        print(f"Revoked key {args.id}")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Manage LexAi API keys")
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('create')
    p.add_argument('--email', required=True)
    p.add_argument('--name', required=True)
    p.add_argument('--plan', choices=tuple(PLAN_LIMITS), default='production')
    p.set_defaults(func=create)

    p = sub.add_parser('list')
    p.add_argument('--email')
    p.set_defaults(func=list_keys)

    p = sub.add_parser('revoke')
    p.add_argument('--id', type=int, required=True)
    p.set_defaults(func=revoke)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()

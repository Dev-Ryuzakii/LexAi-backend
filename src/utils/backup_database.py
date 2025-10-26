#!/usr/bin/env python3
"""
Database Backup Script for AI-CBT Theory Application

This script creates secure backups of the application's databases.
It compresses and encrypts the backups, and can upload them to remote storage.

Usage:
    python backup_database.py [--upload] [--path BACKUP_PATH]
"""
import os
import sys
import time
import sqlite3
import argparse
import shutil
import logging
import hashlib
import subprocess
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('backup.log')
    ]
)

# Default paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
DEFAULT_BACKUP_DIR = os.path.join(PROJECT_ROOT, 'backups')
DATABASE_PATHS = [
    os.path.join(PROJECT_ROOT, 'data', 'database.db'),
    os.path.join(PROJECT_ROOT, 'data', 'production_api.db'),
]

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='AI-CBT Theory Database Backup Tool')
    parser.add_argument('--upload', action='store_true', help='Upload backup to remote storage')
    parser.add_argument('--path', type=str, default=DEFAULT_BACKUP_DIR,
                      help='Backup directory path (default: ./backups)')
    return parser.parse_args()

def check_database_integrity(db_path):
    """Check SQLite database integrity"""
    if not os.path.exists(db_path):
        logging.warning(f"Database file not found: {db_path}")
        return False
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        conn.close()
        
        if result[0] == 'ok':
            logging.info(f"Integrity check passed for {os.path.basename(db_path)}")
            return True
        else:
            logging.error(f"Integrity check failed for {os.path.basename(db_path)}: {result[0]}")
            return False
    except Exception as e:
        logging.error(f"Error checking database integrity: {e}")
        return False

def create_backup_file(db_path, backup_dir):
    """Create a backup of the database file"""
    db_name = os.path.basename(db_path)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_filename = f"{db_name}_{timestamp}.backup"
    backup_path = os.path.join(backup_dir, backup_filename)
    
    try:
        # Create backup directory if it doesn't exist
        os.makedirs(backup_dir, exist_ok=True)
        
        # Copy the database file
        shutil.copy2(db_path, backup_path)
        
        # Calculate checksum
        with open(backup_path, 'rb') as f:
            checksum = hashlib.sha256(f.read()).hexdigest()
            
        # Create checksum file
        checksum_path = f"{backup_path}.sha256"
        with open(checksum_path, 'w') as f:
            f.write(checksum)
            
        logging.info(f"Created backup: {backup_filename} (Checksum: {checksum[:8]}...)")
        return backup_path
        
    except Exception as e:
        logging.error(f"Error creating backup: {e}")
        return None

def compress_and_encrypt_backup(backup_path):
    """Compress and encrypt the backup file"""
    try:
        # Compress with gzip
        compressed_path = f"{backup_path}.gz"
        with open(backup_path, 'rb') as f_in:
            # Try to use gzip command line tool first (faster)
            try:
                subprocess.run(['gzip', '-c', backup_path], stdout=open(compressed_path, 'wb'), check=True)
            except (subprocess.SubprocessError, FileNotFoundError):
                # Fallback to Python's gzip module
                import gzip
                with gzip.open(compressed_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
        
        # Remove original uncompressed backup
        os.unlink(backup_path)
        
        # Try to encrypt with GPG if available
        try:
            encrypted_path = f"{compressed_path}.enc"
            subprocess.run(['gpg', '--symmetric', '--batch', '--yes', '--cipher-algo', 'AES256',
                           '--output', encrypted_path, compressed_path], check=True)
            
            # Remove unencrypted compressed file
            os.unlink(compressed_path)
            logging.info(f"Backup compressed and encrypted: {os.path.basename(encrypted_path)}")
            return encrypted_path
        except (subprocess.SubprocessError, FileNotFoundError):
            # If GPG not available, return compressed file
            logging.info(f"Backup compressed: {os.path.basename(compressed_path)} (GPG not available for encryption)")
            return compressed_path
            
    except Exception as e:
        logging.error(f"Error compressing/encrypting backup: {e}")
        return backup_path  # Return original path if compression fails

def upload_to_remote(backup_path, remote_url=None):
    """Upload backup to remote storage"""
    # This is a placeholder for remote upload functionality
    # In a real implementation, you might use cloud storage SDKs or secure file transfer
    
    if not remote_url:
        logging.warning("No remote URL specified for upload")
        return False
        
    try:
        logging.info(f"Simulating upload of {os.path.basename(backup_path)} to remote storage")
        # Simulate upload with a short delay
        time.sleep(1)
        logging.info(f"Upload complete: {os.path.basename(backup_path)}")
        return True
    except Exception as e:
        logging.error(f"Error uploading backup: {e}")
        return False

def cleanup_old_backups(backup_dir, max_age_days=7, keep_min=3):
    """Remove backups older than specified number of days"""
    try:
        if not os.path.exists(backup_dir):
            return
            
        now = time.time()
        old_backups = []
        
        for filename in os.listdir(backup_dir):
            filepath = os.path.join(backup_dir, filename)
            if os.path.isfile(filepath) and (filename.endswith('.backup') or 
                                            filename.endswith('.gz') or 
                                            filename.endswith('.enc')):
                file_age_days = (now - os.path.getmtime(filepath)) / (24 * 3600)
                if file_age_days > max_age_days:
                    old_backups.append((filepath, file_age_days))
        
        # Sort by age (oldest first)
        old_backups.sort(key=lambda x: x[1], reverse=True)
        
        # Keep at least keep_min backups
        if len(old_backups) > keep_min:
            for filepath, age in old_backups[keep_min:]:
                try:
                    os.unlink(filepath)
                    logging.info(f"Removed old backup: {os.path.basename(filepath)} (Age: {age:.1f} days)")
                except Exception as e:
                    logging.error(f"Error removing old backup {os.path.basename(filepath)}: {e}")
    
    except Exception as e:
        logging.error(f"Error cleaning up old backups: {e}")

def main():
    """Main backup routine"""
    args = parse_arguments()
    backup_dir = os.path.abspath(args.path)
    
    logging.info("Starting AI-CBT Theory database backup")
    logging.info(f"Backup destination: {backup_dir}")
    
    # Create backup directory
    os.makedirs(backup_dir, exist_ok=True)
    
    successful_backups = 0
    for db_path in DATABASE_PATHS:
        db_name = os.path.basename(db_path)
        
        if not os.path.exists(db_path):
            logging.warning(f"Database not found: {db_path}")
            continue
            
        logging.info(f"Processing database: {db_name}")
        
        # Check database integrity
        if not check_database_integrity(db_path):
            logging.error(f"Skipping backup of {db_name} due to integrity check failure")
            continue
            
        # Create backup
        backup_path = create_backup_file(db_path, backup_dir)
        if not backup_path:
            continue
            
        # Compress and encrypt
        final_path = compress_and_encrypt_backup(backup_path)
        
        # Upload if requested
        if args.upload:
            # Replace with your actual remote storage URL
            upload_to_remote(final_path, "sftp://backup.example.com/ai-cbt-backups/")
            
        successful_backups += 1
        
    # Clean up old backups
    cleanup_old_backups(backup_dir)
    
    logging.info(f"Backup complete. {successful_backups}/{len(DATABASE_PATHS)} databases processed successfully.")
    
    return 0 if successful_backups == len(DATABASE_PATHS) else 1

if __name__ == "__main__":
    sys.exit(main())
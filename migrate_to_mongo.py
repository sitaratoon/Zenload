import sqlite3
from datetime import datetime
from pathlib import Path
import os
from dotenv import load_dotenv
from pymongo import MongoClient
from src.config import BASE_DIR
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def migrate_data():
    """Migrate data from SQLite to MongoDB"""
    # Connect to MongoDB
    mongo_uri = os.getenv('MONGODB_URI')
    if not mongo_uri:
        raise ValueError("MONGODB_URI environment variable is not set")
    
    client = MongoClient(mongo_uri)
    db = client.zenload
    
    # Create indexes
    db.user_settings.create_index("user_id", unique=True)
    db.group_settings.create_index("group_id", unique=True)
    db.group_settings.create_index("admin_id")
    
    # Path to SQLite database
    db_path = BASE_DIR / "zenload.db"
    if not db_path.exists():
        logger.error("SQLite database not found")
        return
    
    try:
        # Connect to SQLite
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Get column names for user_settings
            cursor.execute('PRAGMA table_info(user_settings)')
            user_columns = [col[1] for col in cursor.fetchall()]
            logger.info(f"Found user columns: {user_columns}")
            
            # Migrate user settings
            logger.info("Starting user settings migration...")
            cursor.execute("SELECT * FROM user_settings")
            users = cursor.fetchall()
            logger.info(f"Found {len(users)} users to migrate")
            
            for user in users:
                user_dict = dict(zip(user_columns, user))
                user_doc = {
                    "user_id": user_dict['user_id'],
                    "language": user_dict['language'],
                    "username": user_dict.get('username'),
                    "first_name": user_dict.get('first_name'),
                    "last_name": user_dict.get('last_name'),
                    "phone_number": user_dict.get('phone_number'),
                    "default_quality": user_dict.get('default_quality', 'ask'),
                    "is_premium": bool(user_dict.get('is_premium', False)),
                    "created_at": datetime.strptime(user_dict['created_at'], '%Y-%m-%d %H:%M:%S') if user_dict.get('created_at') else datetime.utcnow(),
                    "updated_at": datetime.strptime(user_dict['updated_at'], '%Y-%m-%d %H:%M:%S') if user_dict.get('updated_at') else datetime.utcnow()
                }
                
                db.user_settings.update_one(
                    {"user_id": user_doc["user_id"]},
                    {"$set": user_doc},
                    upsert=True
                )
                logger.info(f"Migrated user {user_doc['user_id']}")
            
            # Get column names for group_settings
            cursor.execute('PRAGMA table_info(group_settings)')
            group_columns = [col[1] for col in cursor.fetchall()]
            logger.info(f"Found group columns: {group_columns}")
            
            # Migrate group settings
            logger.info("Starting group settings migration...")
            cursor.execute("SELECT * FROM group_settings")
            groups = cursor.fetchall()
            logger.info(f"Found {len(groups)} groups to migrate")
            
            for group in groups:
                group_dict = dict(zip(group_columns, group))
                group_doc = {
                    "group_id": group_dict['group_id'],
                    "admin_id": group_dict['admin_id'],
                    "language": group_dict['language'],
                    "default_quality": group_dict.get('default_quality', 'ask'),
                    "created_at": datetime.strptime(group_dict['created_at'], '%Y-%m-%d %H:%M:%S') if group_dict.get('created_at') else datetime.utcnow(),
                    "updated_at": datetime.strptime(group_dict['updated_at'], '%Y-%m-%d %H:%M:%S') if group_dict.get('updated_at') else datetime.utcnow()
                }
                
                db.group_settings.update_one(
                    {"group_id": group_doc["group_id"]},
                    {"$set": group_doc},
                    upsert=True
                )
                logger.info(f"Migrated group {group_doc['group_id']}")
        
        logger.info("Successfully migrated all data from SQLite to MongoDB")
        
        # Print final statistics
        users_count = db.user_settings.count_documents({})
        groups_count = db.group_settings.count_documents({})
        logger.info(f"Final MongoDB Statistics:")
        logger.info(f"Total Users: {users_count}")
        logger.info(f"Total Groups: {groups_count}")
        
    except Exception as e:
        logger.error(f"Failed to migrate data: {e}")
        raise
    finally:
        client.close()

if __name__ == "__main__":
    migrate_data()


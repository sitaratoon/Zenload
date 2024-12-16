from typing import Optional
from datetime import datetime
from pymongo import MongoClient
from pymongo.database import Database
import os
from pathlib import Path
import sqlite3
import logging
from .config import BASE_DIR
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Initialize MongoDB connection
client = MongoClient(os.getenv('MONGODB_URI'))
db: Database = client.zenload

@dataclass
class UserSettings:
    user_id: int
    language: str = 'ru'
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    is_premium: bool = False
    default_quality: str = 'ask'
    created_at: datetime = None
    updated_at: datetime = None

@dataclass
class GroupSettings:
    group_id: int
    admin_id: int
    language: str = 'ru'
    default_quality: str = 'ask'
    created_at: datetime = None
    updated_at: datetime = None

class UserSettingsManager:
    def __init__(self):
        """Initialize settings manager with MongoDB connection"""
        self.db = db
        self._init_collections()

    def _init_collections(self):
        """Initialize MongoDB collections and indexes"""
        # Create indexes if they don't exist
        self.db.user_settings.create_index("user_id", unique=True)
        self.db.group_settings.create_index("group_id", unique=True)
        self.db.group_settings.create_index("admin_id")

    def get_settings(self, user_id: int, chat_id: Optional[int] = None, is_admin: bool = False) -> UserSettings:
        """
        Get settings based on context:
        - If chat_id is None, return user's personal settings
        - If chat_id is provided, return group settings if they exist, otherwise user's settings
        """
        try:
            # If this is a group chat
            if chat_id and chat_id < 0:  # Telegram group IDs are negative
                group_doc = self.db.group_settings.find_one({"group_id": chat_id})
                
                if group_doc:
                    return UserSettings(
                        user_id=user_id,
                        language=group_doc.get('language', 'ru'),
                        default_quality=group_doc.get('default_quality', 'ask')
                    )
            
            # Get or create user settings
            user_doc = self.db.user_settings.find_one({"user_id": user_id})

            if not user_doc:
                # Create default settings
                settings = UserSettings(user_id=user_id)
                self.db.user_settings.insert_one({
                    "user_id": user_id,
                    "language": settings.language,
                    "default_quality": settings.default_quality,
                    "username": None,
                    "first_name": None,
                    "last_name": None,
                    "phone_number": None,
                    "is_premium": False,
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                })
                return settings
            
            return UserSettings(
                user_id=user_id,
                language=user_doc.get('language', 'ru'),
                default_quality=user_doc.get('default_quality', 'ask'),
                username=user_doc.get('username'),
                first_name=user_doc.get('first_name'),
                last_name=user_doc.get('last_name'),
                phone_number=user_doc.get('phone_number'),
                is_premium=user_doc.get('is_premium', False),
                created_at=user_doc.get('created_at'),
                updated_at=user_doc.get('updated_at')
            )

        except Exception as e:
            logger.error(f"Failed to get settings for user {user_id}: {e}")
            return UserSettings(user_id=user_id)

    def update_settings(self, user_id: int, chat_id: Optional[int] = None, is_admin: bool = False, **kwargs) -> UserSettings:
        """Update settings based on context"""
        try:
            # If this is a group chat and user is admin
            if chat_id and chat_id < 0 and is_admin:
                valid_fields = {'language', 'default_quality'}
                update_fields = {k: v for k, v in kwargs.items() if k in valid_fields}
                
                if update_fields:
                    update_fields['updated_at'] = datetime.utcnow()
                    
                    self.db.group_settings.update_one(
                        {"group_id": chat_id},
                        {
                            "$set": update_fields,
                            "$setOnInsert": {
                                "group_id": chat_id,
                                "admin_id": user_id,
                                "created_at": datetime.utcnow()
                            }
                        },
                        upsert=True
                    )
                    
                    return self.get_settings(user_id, chat_id, is_admin)
            
            # Update user settings
            valid_fields = {'language', 'default_quality', 'username', 'first_name', 'last_name', 'phone_number', 'is_premium'}
            update_fields = {k: v for k, v in kwargs.items() if k in valid_fields}
            
            if update_fields:
                update_fields['updated_at'] = datetime.utcnow()
                
                self.db.user_settings.update_one(
                    {"user_id": user_id},
                    {
                        "$set": update_fields,
                        "$setOnInsert": {
                            "user_id": user_id,
                            "created_at": datetime.utcnow()
                        }
                    },
                    upsert=True
                )
            
            return self.get_settings(user_id)

        except Exception as e:
            logger.error(f"Failed to update settings for user {user_id}: {e}")
            return self.get_settings(user_id)

    def get_group_admin(self, group_id: int) -> Optional[int]:
        """Get the admin ID for a group if settings exist"""
        try:
            group_doc = self.db.group_settings.find_one({"group_id": group_id})
            return group_doc['admin_id'] if group_doc else None
        except Exception as e:
            logger.error(f"Failed to get admin for group {group_id}: {e}")
            return None

def migrate_from_sqlite():
    """Migrate data from SQLite to MongoDB if zenload.db exists"""
    db_path = BASE_DIR / "zenload.db"
    if not db_path.exists():
        return
    
    try:
        # Connect to SQLite
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Migrate user settings
            cursor.execute("SELECT * FROM user_settings")
            users = cursor.fetchall()
            
            for user in users:
                user_doc = {
                    "user_id": user[0],
                    "language": user[1],
                    "username": user[2],
                    "first_name": user[3],
                    "last_name": user[4],
                    "phone_number": user[5],
                    "default_quality": user[6],
                    "is_premium": bool(user[7]),
                    "created_at": datetime.strptime(user[8], '%Y-%m-%d %H:%M:%S') if user[8] else datetime.utcnow(),
                    "updated_at": datetime.strptime(user[9], '%Y-%m-%d %H:%M:%S') if user[9] else datetime.utcnow()
                }
                
                db.user_settings.update_one(
                    {"user_id": user_doc["user_id"]},
                    {"$set": user_doc},
                    upsert=True
                )
            
            # Migrate group settings
            cursor.execute("SELECT * FROM group_settings")
            groups = cursor.fetchall()
            
            for group in groups:
                group_doc = {
                    "group_id": group[0],
                    "admin_id": group[1],
                    "language": group[2],
                    "default_quality": group[3],
                    "created_at": datetime.strptime(group[4], '%Y-%m-%d %H:%M:%S') if group[4] else datetime.utcnow(),
                    "updated_at": datetime.strptime(group[5], '%Y-%m-%d %H:%M:%S') if group[5] else datetime.utcnow()
                }
                
                db.group_settings.update_one(
                    {"group_id": group_doc["group_id"]},
                    {"$set": group_doc},
                    upsert=True
                )
        
        logger.info("Successfully migrated data from SQLite to MongoDB")
        
    except Exception as e:
        logger.error(f"Failed to migrate data: {e}")
        raise


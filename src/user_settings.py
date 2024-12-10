import sqlite3
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class UserSettings:
    user_id: int
    language: str = 'ru'  # Default to Russian
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    is_premium: bool = False
    default_quality: str = 'ask'  # 'ask' or 'best'

@dataclass
class GroupSettings:
    group_id: int
    admin_id: int  # ID of the admin who configured the settings
    language: str = 'ru'
    default_quality: str = 'ask'

class UserSettingsManager:
    def __init__(self, db_path: Path):
        """Initialize settings manager with SQLite database"""
        self.db_path = db_path
        self._init_db()

    def _migrate_db(self, cursor):
        """Safely add new columns if they don't exist"""
        try:
            # Get current columns
            cursor.execute('PRAGMA table_info(user_settings)')
            existing_columns = {col[1] for col in cursor.fetchall()}
            
            # Define new columns to add
            new_columns = {
                'username': 'TEXT',
                'first_name': 'TEXT',
                'last_name': 'TEXT',
                'phone_number': 'TEXT',
                'is_premium': 'BOOLEAN NOT NULL DEFAULT 0'
            }
            
            # Add missing columns
            for column_name, column_type in new_columns.items():
                if column_name not in existing_columns:
                    cursor.execute(f'ALTER TABLE user_settings ADD COLUMN {column_name} {column_type}')
                    logger.info(f"Added new column: {column_name}")
            
        except Exception as e:
            logger.error(f"Failed to migrate database: {e}")
            raise

    def _init_db(self):
        """Initialize SQLite database and create tables if needed"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # User settings table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_settings (
                        user_id INTEGER PRIMARY KEY,
                        language TEXT NOT NULL DEFAULT 'ru',
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        phone_number TEXT,
                        default_quality TEXT NOT NULL DEFAULT 'ask',
                        is_premium BOOLEAN NOT NULL DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Group settings table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS group_settings (
                        group_id INTEGER PRIMARY KEY,
                        admin_id INTEGER NOT NULL,
                        language TEXT NOT NULL DEFAULT 'ru',
                        default_quality TEXT NOT NULL DEFAULT 'ask',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (admin_id) REFERENCES user_settings(user_id)
                    )
                """)

                self._migrate_db(cursor)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def get_settings(self, user_id: int, chat_id: Optional[int] = None, is_admin: bool = False) -> UserSettings:
        """
        Get settings based on context:
        - If chat_id is None, return user's personal settings
        - If chat_id is provided, return group settings if they exist, otherwise user's settings
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # If this is a group chat
                if chat_id and chat_id < 0:  # Telegram group IDs are negative
                    cursor.execute(
                        "SELECT language, default_quality FROM group_settings WHERE group_id = ?",
                        (chat_id,)
                    )
                    group_settings = cursor.fetchone()
                    
                    if group_settings:
                        return UserSettings(
                            user_id=user_id,
                            language=group_settings[0],
                            default_quality=group_settings[1]
                        )
                
                # Get or create user settings
                cursor.execute(
                    "SELECT language, default_quality, username, first_name, last_name, phone_number, is_premium FROM user_settings WHERE user_id = ?",
                    (user_id,)
                )
                result = cursor.fetchone()

                if not result:
                    # Create default settings
                    settings = UserSettings(user_id=user_id)
                    cursor.execute(
                        "INSERT INTO user_settings (user_id, language, default_quality, username, first_name, last_name, phone_number, is_premium) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (user_id, settings.language, settings.default_quality, None, None, None, None, False)
                    )
                    conn.commit()
                else:
                    settings = UserSettings(
                        user_id=user_id,
                        language=result[0],
                        default_quality=result[1],
                        username=result[2],
                        first_name=result[3],
                        last_name=result[4],
                        phone_number=result[5],
                        is_premium=bool(result[6])
                    )

                return settings
        except Exception as e:
            logger.error(f"Failed to get settings for user {user_id}: {e}")
            return UserSettings(user_id=user_id)  # Return defaults on error

    def update_settings(self, user_id: int, chat_id: Optional[int] = None, is_admin: bool = False, **kwargs) -> UserSettings:
        """Update settings based on context"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # If this is a group chat and user is admin
                if chat_id and chat_id < 0 and is_admin:
                    valid_fields = {'language', 'default_quality'}
                    update_fields = {k: v for k, v in kwargs.items() if k in valid_fields}
                    
                    if update_fields:
                        cursor.execute(
                            "SELECT 1 FROM group_settings WHERE group_id = ?",
                            (chat_id,)
                        )
                        exists = cursor.fetchone()
                        
                        if exists:
                            # Update existing group settings
                            query = "UPDATE group_settings SET " + \
                                   ", ".join(f"{k} = ?" for k in update_fields.keys()) + \
                                   ", updated_at = CURRENT_TIMESTAMP " + \
                                   "WHERE group_id = ?"
                            cursor.execute(query, (*update_fields.values(), chat_id))
                        else:
                            # Create new group settings
                            settings = GroupSettings(
                                group_id=chat_id,
                                admin_id=user_id,
                                **kwargs
                            )
                            cursor.execute(
                                """INSERT INTO group_settings 
                                   (group_id, admin_id, language, default_quality) 
                                   VALUES (?, ?, ?, ?)""",
                                (chat_id, user_id, settings.language, settings.default_quality)
                            )
                        
                        conn.commit()
                        return self.get_settings(user_id, chat_id, is_admin)
                
                # Update user settings
                valid_fields = {'language', 'default_quality', 'username', 'first_name', 'last_name', 'phone_number', 'is_premium'}
                update_fields = {k: v for k, v in kwargs.items() if k in valid_fields}
                
                if not update_fields:
                    return self.get_settings(user_id)

                query = "UPDATE user_settings SET " + \
                       ", ".join(f"{k} = ?" for k in update_fields.keys()) + \
                       ", updated_at = CURRENT_TIMESTAMP " + \
                       "WHERE user_id = ?"
                
                cursor.execute(query, (*update_fields.values(), user_id))
                
                if cursor.rowcount == 0:
                    # If no row was updated, insert new settings
                    settings = UserSettings(user_id=user_id, **kwargs)
                    cursor.execute(
                        "INSERT INTO user_settings (user_id, language, default_quality, username, first_name, last_name, phone_number, is_premium) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (user_id, settings.language, settings.default_quality, settings.username, settings.first_name, settings.last_name, settings.phone_number, settings.is_premium)
                    )
                
                conn.commit()
                return self.get_settings(user_id)
                
        except Exception as e:
            logger.error(f"Failed to update settings for user {user_id}: {e}")
            return self.get_settings(user_id)

    def get_group_admin(self, group_id: int) -> Optional[int]:
        """Get the admin ID for a group if settings exist"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT admin_id FROM group_settings WHERE group_id = ?",
                    (group_id,)
                )
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Failed to get admin for group {group_id}: {e}")
            return None





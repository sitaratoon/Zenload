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
    default_quality: str = 'ask'  # 'ask' or 'best'

class UserSettingsManager:
    def __init__(self, db_path: Path):
        """Initialize settings manager with SQLite database"""
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database and create tables if needed"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_settings (
                        user_id INTEGER PRIMARY KEY,
                        language TEXT NOT NULL DEFAULT 'ru',
                        default_quality TEXT NOT NULL DEFAULT 'ask',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def get_settings(self, user_id: int) -> UserSettings:
        """Get settings for user, create default if not exists"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT language, default_quality FROM user_settings WHERE user_id = ?",
                    (user_id,)
                )
                result = cursor.fetchone()

                if not result:
                    # Create default settings
                    settings = UserSettings(user_id=user_id)
                    cursor.execute(
                        "INSERT INTO user_settings (user_id, language, default_quality) VALUES (?, ?, ?)",
                        (user_id, settings.language, settings.default_quality)
                    )
                    conn.commit()
                else:
                    settings = UserSettings(
                        user_id=user_id,
                        language=result[0],
                        default_quality=result[1]
                    )

                return settings
        except Exception as e:
            logger.error(f"Failed to get settings for user {user_id}: {e}")
            return UserSettings(user_id=user_id)  # Return defaults on error

    def update_settings(self, user_id: int, **kwargs) -> UserSettings:
        """Update specific settings for user"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Build update query dynamically based on provided kwargs
                valid_fields = {'language', 'default_quality'}
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
                        "INSERT INTO user_settings (user_id, language, default_quality) VALUES (?, ?, ?)",
                        (user_id, settings.language, settings.default_quality)
                    )
                
                conn.commit()
                return self.get_settings(user_id)
                
        except Exception as e:
            logger.error(f"Failed to update settings for user {user_id}: {e}")
            return self.get_settings(user_id)

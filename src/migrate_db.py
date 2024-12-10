import sqlite3
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_database():
    """Add new user information columns to user_settings table"""
    db_path = Path(__file__).parent.parent / 'zenload.db'
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Add new columns one by one
            new_columns = [
                ('username', 'TEXT'),
                ('first_name', 'TEXT'),
                ('last_name', 'TEXT'),
                ('phone_number', 'TEXT'),
                ('is_premium', 'BOOLEAN NOT NULL DEFAULT 0')
            ]
            
            for column_name, column_type in new_columns:
                try:
                    cursor.execute(f'ALTER TABLE user_settings ADD COLUMN {column_name} {column_type}')
                    logger.info(f"Added column {column_name}")
                except sqlite3.OperationalError as e:
                    if 'duplicate column name' in str(e):
                        logger.info(f"Column {column_name} already exists")
                    else:
                        raise
            
            conn.commit()
            logger.info("Database migration completed successfully")
            
    except Exception as e:
        logger.error(f"Failed to migrate database: {e}")
        raise

if __name__ == "__main__":
    migrate_database()

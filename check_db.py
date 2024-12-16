from pymongo import MongoClient
import os
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

# Connect to MongoDB
client = MongoClient(os.getenv('MONGODB_URI'))
db = client.zenload

def print_separator():
    print("\n" + "="*50 + "\n")

def main():
    # Get collections stats
    users_count = db.user_settings.count_documents({})
    groups_count = db.group_settings.count_documents({})
    
    print("📊 Database Statistics:")
    print(f"Total Users: {users_count}")
    print(f"Total Groups: {groups_count}")
    
    print_separator()
    
    # User Statistics
    print("👤 User Details:")
    premium_users = db.user_settings.count_documents({"is_premium": True})
    print(f"Premium Users: {premium_users}")
    
    # Language distribution
    print("\nLanguage Distribution:")
    languages = db.user_settings.aggregate([
        {"$group": {"_id": "$language", "count": {"$sum": 1}}}
    ])
    for lang in languages:
        print(f"- {lang['_id']}: {lang['count']} users")
    
    print_separator()
    
    # Recent Activity
    print("🕒 Recent Activity:")
    recent_users = db.user_settings.find().sort("updated_at", -1).limit(5)
    print("\nRecently Active Users:")
    for user in recent_users:
        updated = user.get('updated_at', 'N/A')
        if isinstance(updated, datetime):
            updated = updated.strftime('%Y-%m-%d %H:%M:%S')
        print(f"User ID: {user['user_id']}, Last Updated: {updated}")

if __name__ == "__main__":
    try:
        main()
    finally:
        client.close()

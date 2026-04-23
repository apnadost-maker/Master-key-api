from pymongo import MongoClient
from datetime import datetime, timedelta
import pytz

class MongoDBHandler:
    def __init__(self, connection_string="mongodb+srv://niravpatel180503_db_user:vjWNaWhRk0gMSNyQ@cluster0.26bfgmf.mongodb.net/", db_name="niravpatel180503"):
        """
        Initialize MongoDB connection with MongoDB Atlas
        :param connection_string: MongoDB Atlas connection string
        :param db_name: Database name (niravpatel180503_db_user)
        """
        try:
            self.client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
            # Test the connection
            self.client.server_info()
            self.db = self.client[db_name]
            self.tokens = self.db.tokens
            self.keys = self.db.keys
            print("✅ Successfully connected to MongoDB Atlas")
        except Exception as e:
            print(f"❌ Failed to connect to MongoDB: {e}")
            raise
        
        # Create indexes for better query performance
        self.tokens.create_index("token", unique=True)
        self.tokens.create_index("expiry_time", expireAfterSeconds=0)  # TTL index for auto-deletion
        self.keys.create_index("key", unique=True)
        
        self.ist = pytz.timezone('Asia/Kolkata')
    
    # Token management
    def save_token(self, token, user_id, expiry_minutes=20):
        """Save a new token with expiry time"""
        expiry_time = datetime.now(self.ist) + timedelta(minutes=expiry_minutes)
        token_data = {
            "token": token,
            "user_id": user_id,
            "created_at": datetime.now(self.ist),
            "expiry_time": expiry_time
        }
        self.tokens.insert_one(token_data)
        return token_data
    
    def get_token(self, token):
        """Retrieve a token if it exists and is not expired"""
        return self.tokens.find_one({"token": token, "expiry_time": {"$gt": datetime.now(self.ist)}})
    
    def delete_token(self, token):
        """Delete a token"""
        return self.tokens.delete_one({"token": token})
    
    def cleanup_expired_tokens(self):
        """Clean up expired tokens (handled automatically by TTL index)"""
        return self.tokens.delete_many({"expiry_time": {"$lt": datetime.now(self.ist)}})
    
    # Key management
    def save_key(self, key_data):
        """Save a new key"""
        # Add created_at timestamp if not present
        if "created_at" not in key_data:
            key_data["created_at"] = datetime.now(self.ist)
        
        # Add expiry time if not present (default 2 days)
        if "expiry_days" not in key_data:
            key_data["expiry_days"] = 2
            
        if "expiry_time" not in key_data:
            key_data["expiry_time"] = datetime.now(self.ist) + timedelta(days=key_data["expiry_days"])
        
        return self.keys.insert_one(key_data)
    
    def get_key(self, key):
        """Retrieve a key by its value"""
        return self.keys.find_one({"key": key})
        
    def get_key_by_user_id(self, user_id):
        """Retrieve a key by user ID"""
        return self.keys.find_one({"user_id": user_id})
    
    def get_all_keys(self):
        """Retrieve all keys"""
        return list(self.keys.find({}))
    
    def update_key(self, key, update_data):
        """Update key data"""
        return self.keys.update_one({"key": key}, {"$set": update_data})
    
    def delete_key(self, key):
        """Delete a key"""
        return self.keys.delete_one({"key": key})
    
    def get_active_keys(self):
        """Get all active (non-expired) keys"""
        return list(self.keys.find({"expiry_time": {"$gt": datetime.now(self.ist)}}))
    
    def migrate_from_json(self, tokens_file="tokens.json", keys_file="keys.json"):
        """Migrate data from JSON files to MongoDB"""
        import json
        import os
        
        # Migrate tokens
        if os.path.exists(tokens_file):
            with open(tokens_file, 'r') as f:
                tokens_data = json.load(f)
                for token, data in tokens_data.items():
                    try:
                        self.save_token(
                            token=token,
                            user_id=data.get("user_id", ""),
                            expiry_minutes=20  # Default expiry
                        )
                    except Exception as e:
                        print(f"Error migrating token {token}: {e}")
        
        # Migrate keys
        if os.path.exists(keys_file):
            with open(keys_file, 'r') as f:
                keys_data = json.load(f)
                for key, data in keys_data.items():
                    try:
                        data["key"] = key  # Add key to the document
                        self.save_key(data)
                    except Exception as e:
                        print(f"Error migrating key {key}: {e}")

# Singleton instance
db_handler = MongoDBHandler()

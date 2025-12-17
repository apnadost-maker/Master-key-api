import os
import json
import time
import secrets
import requests
import base64
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, render_template_string, url_for
import pytz
from urllib.parse import urlencode
from pymongo import MongoClient
from bson import ObjectId

app = Flask(__name__)

TOKEN_EXPIRY_MINUTES = 20  
KEY_EXPIRY_DAYS = 1
SHORTENER_API_KEY = "365fb9d294e5a0288cb08be3e55f683d627fdc4a"

MONGODB_URI = "mongodb+srv://test:Bu&Hr!WFwdySyz8@cluster0.pofxanv.mongodb.net/?appName=Cluster0"
DATABASE_NAME = "key_database"
COLLECTION_NAME = "keys"
TOKEN_COLLECTION_NAME = "tokens"  

IST = pytz.timezone('Asia/Kolkata')


try:
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]
    keys_collection = db[COLLECTION_NAME]
    tokens_collection = db[TOKEN_COLLECTION_NAME]  # Token collection
    
    client.admin.command('ping')
    print("Successfully connected to MongoDB")
    mongo_connected = True
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    mongo_connected = False
    keys_collection = None
    tokens_collection = None

def get_current_ist_time():
    return datetime.now(IST)

def cleanup_expired_tokens():
    """Clean up expired tokens from MongoDB"""
    if not mongo_connected or tokens_collection is None:
        return
    
    try:
        current_time = get_current_ist_time()
        result = tokens_collection.delete_many({
            "expiry_time": {"$lt": current_time.isoformat()}
        })
        if result.deleted_count > 0:
            print(f"Cleaned up {result.deleted_count} expired tokens")
    except Exception as e:
        print(f"Error cleaning up expired tokens: {e}")

def get_mongodb_keys():
    """Get all keys from MongoDB"""
    if not mongo_connected or keys_collection is None:
        return {}
    
    try:
        keys_data = {}
        cursor = keys_collection.find({})
        for doc in cursor:
            keys_data[doc['user_id']] = {
                "key": doc['key'],
                "expiry_time": doc['expiry_time']
            }
        return keys_data
    except Exception as e:
        print(f"Error reading from MongoDB: {e}")
        return {}

def save_to_mongodb(user_id, key_data):
    """Save or update key in MongoDB"""
    if not mongo_connected or keys_collection is None:
        return False
    
    try:
        
        existing_user = keys_collection.find_one({"user_id": user_id})
        
        if existing_user:
            
            result = keys_collection.update_one(
                {"user_id": user_id},
                {"$set": {
                    "key": key_data["key"],
                    "expiry_time": key_data["expiry_time"]
                }}
            )
            return result.modified_count > 0
        else:
            
            key_data["user_id"] = user_id
            result = keys_collection.insert_one(key_data)
            return result.inserted_id is not None
    except Exception as e:
        print(f"Error saving to MongoDB: {e}")
        return False

def get_mongodb_tokens():
    """Get all tokens from MongoDB"""
    if not mongo_connected or tokens_collection is None:
        return {}
    
    try:
        
        cleanup_expired_tokens()
        
        tokens_data = {}
        cursor = tokens_collection.find({})
        for doc in cursor:
            tokens_data[doc['user_id']] = {
                "token": doc['token'],
                "expiry_time": doc['expiry_time']
            }
        return tokens_data
    except Exception as e:
        print(f"Error reading tokens from MongoDB: {e}")
        return {}

def save_token_to_mongodb(user_id, token_data):
    """Save or update token in MongoDB"""
    if not mongo_connected or tokens_collection is None:
        return False
    
    try:
        
        cleanup_expired_tokens()
        
        existing_user = tokens_collection.find_one({"user_id": user_id})
        
        if existing_user:
            
            result = tokens_collection.update_one(
                {"user_id": user_id},
                {"$set": {
                    "token": token_data["token"],
                    "expiry_time": token_data["expiry_time"]
                }}
            )
            return result.modified_count > 0
        else:
            
            token_data["user_id"] = user_id
            result = tokens_collection.insert_one(token_data)
            return result.inserted_id is not None
    except Exception as e:
        print(f"Error saving token to MongoDB: {e}")
        return False

def delete_token_from_mongodb(user_id):
    """Delete token from MongoDB"""
    if not mongo_connected or tokens_collection is None:
        return False
    
    try:
        result = tokens_collection.delete_one({"user_id": user_id})
        return result.deleted_count > 0
    except Exception as e:
        print(f"Error deleting token from MongoDB: {e}")
        return False

def save_all_to_mongodb(keys_data):
    """Save all keys to MongoDB (for bulk operations)"""
    if not mongo_connected or keys_collection is None:
        return False
    
    try:
        
        keys_collection.delete_many({})
        
        documents = []
        for user_id, key_info in keys_data.items():
            documents.append({
                "user_id": user_id,
                "key": key_info["key"],
                "expiry_time": key_info["expiry_time"]
            })
        
        if documents:
            result = keys_collection.insert_many(documents)
            return len(result.inserted_ids) == len(documents)
        return True
    except Exception as e:
        print(f"Error saving all to MongoDB: {e}")
        return False

def generate_token():
    return secrets.token_hex(16)

def generate_key():
    return secrets.token_hex(12)  

def shorten_url(long_url):
    try:
        
        random_suffix = secrets.token_hex(3)[:6]
        alias = f"vertex{random_suffix}"

        shortener_url = (
            f"https://arolinks.com/api?api={SHORTENER_API_KEY}"
            f"&url={requests.utils.quote(long_url)}"
            f"&alias={alias}"
        )

        response = requests.get(shortener_url)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        print(f"Error shortening URL: {e}")
        return None

@app.route('/api/login', methods=['GET'])
def login():
    user_id = request.args.get('id')
    if not user_id:
        return jsonify({"status": "error", "message": "ID is required"}), 400

    token = generate_token()
    expiry_time = get_current_ist_time() + timedelta(minutes=TOKEN_EXPIRY_MINUTES)
    
    token_data = {
        "token": token,
        "expiry_time": expiry_time.isoformat()
    }

    if not save_token_to_mongodb(user_id, token_data):
        return jsonify({"status": "error", "message": "Failed to generate token"}), 500

    verify_url = f"{request.url_root}api/verify?token={token}&id={user_id}"

    short_url_data = shorten_url(verify_url)
    if not short_url_data:
        return jsonify({"status": "error", "message": "Failed to shorten URL"}), 500

    response_data = {
        "status": "success",
        "shortenedUrl": short_url_data.get("shortenedUrl"),
        "video_url": "https://t.me/how_to_genrat/3"
    }

    return jsonify(response_data)

@app.route('/api/verify', methods=['GET'])
def verify():
    
    query_string = request.query_string.decode()

    if '&id=' in query_string:
        token = request.args.get('token')
        user_id = request.args.get('id')
    
    elif '&amp;id=' in query_string:
        parts = query_string.split('&amp;id=')
        if len(parts) == 2:
            token = parts[0].replace('token=', '')
            user_id = parts[1]
        else:
            return "Invalid request", 400
    else:
        return "Invalid request", 400

    if not token or not user_id:
        return "Invalid request", 400

    tokens_data = get_mongodb_tokens()
    token_data = tokens_data.get(user_id)
    
    if not token_data or token_data["token"] != token:
        return "Invalid or expired token", 400

    token_expiry = datetime.fromisoformat(token_data["expiry_time"])
    current_time = get_current_ist_time()

    if current_time > token_expiry:
        
        return "Token expired", 400

    keys_data = get_mongodb_keys()
    if user_id in keys_data:
        key_data = keys_data[user_id]
        expiry_time = datetime.fromisoformat(key_data["expiry_time"])

        
        if current_time <= expiry_time:
            
            return render_template_string('''
             <!DOCTYPE html>
<html>
<head>
    <title>Your Authentication Key</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #4361ee;
            --primary-dark: #3a56d4;
            --text: #2b2d42;
            --bg: #f5f7ff;
            --card-bg: #ffffff;
            --input-bg: #f8f9fa;
            --border-color: #e9ecef;
            --text-secondary: #6c757d;
            --success: #4cc9f0;
            --border-radius: 12px;
            --box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
            --transition: all 0.3s ease;
        }
        
        [data-theme="dark"] {
            --primary: #5a7aff;
            --primary-dark: #4a6bf5;
            --text: #f8f9fa;
            --bg: #1a1a2e;
            --card-bg: #16213e;
            --input-bg: #0f3460;
            --border-color: #2a3b5f;
            --text-secondary: #a8b2d1;
            --box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Inter', sans-serif;
            background-color: var(--bg);
            color: var(--text);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 20px;
            line-height: 1.6;
            transition: var(--transition);
        }
        
        .key-container {
            background: var(--card-bg);
            border-radius: var(--border-radius);
            box-shadow: var(--box-shadow);
            width: 100%;
            max-width: 500px;
            padding: 40px;
            text-align: center;
            position: relative;
            overflow: hidden;
            transition: var(--transition);
        }
        
        .branding {
            margin-bottom: 20px;
            text-align: center;
        }
        
        .branding h2 {
            color: var(--primary);
            font-size: 1.8rem;
            font-weight: 700;
            margin: 0;
            letter-spacing: -0.5px;
            background: linear-gradient(90deg, #4361ee, #4cc9f0);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            text-fill-color: transparent;
        }
        
        .branding .tagline {
            color: var(--text-secondary);
            font-size: 0.9rem;
            margin-top: 4px;
            font-weight: 400;
        }
        
        .key-container::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 4px;
            background: linear-gradient(90deg, #4361ee, #4cc9f0);
        }
        
        .key-icon {
            font-size: 48px;
            color: var(--primary);
            margin: 10px 0 20px;
            animation: float 3s ease-in-out infinite;
        }
        
        h1 {
            font-size: 24px;
            font-weight: 600;
            margin-bottom: 15px;
            color: var(--text);
        }
        
        .key-description {
            color: var(--text-secondary);
            margin-bottom: 30px;
            font-size: 15px;
        }
        
        .key-input-group {
            position: relative;
            margin-bottom: 25px;
        }
        
        .key-input {
            width: 100%;
            padding: 15px 20px;
            font-size: 16px;
            border: 2px solid var(--border-color);
            border-radius: var(--border-radius);
            background: var(--input-bg);
            font-family: 'Courier New', monospace;
            font-weight: 600;
            color: var(--text);
            letter-spacing: 1px;
            transition: var(--transition);
        }
        
        .key-input:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        .copy-btn {
            background-color: var(--primary);
            color: white;
            border: none;
            padding: 14px 28px;
            font-size: 16px;
            font-weight: 500;
            border-radius: var(--border-radius);
            cursor: pointer;
            transition: var(--transition);
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }
        
        .copy-btn:hover {
            background-color: var(--primary-dark);
            transform: translateY(-2px);
        }
        
        .copy-btn:active {
            transform: translateY(0);
        }
        
        .key-meta {
            margin-top: 25px;
            font-size: 13px;
            color: var(--text-secondary);
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 15px;
            flex-wrap: wrap;
        }
        
        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            background: #4bb543;
            color: white;
            padding: 15px 25px;
            border-radius: var(--border-radius);
            box-shadow: var(--box-shadow);
            transform: translateX(150%);
            transition: transform 0.3s ease;
            z-index: 1000;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .notification.show {
            transform: translateX(0);
        }
        
        .theme-toggle {
            position: absolute;
            top: 20px;
            right: 20px;
            background: none;
            border: none;
            color: var(--text);
            font-size: 1.5rem;
            cursor: pointer;
            transition: var(--transition);
            z-index: 10;
        }
        
        .theme-toggle:focus {
            outline: none;
            transform: scale(1.1);
        }
        
        .key-meta span {
            display: flex;
            align-items: center;
            gap: 5px;
        }
        
        @media (max-width: 600px) {
            .key-container {
                padding: 30px 20px;
                margin: 20px;
            }
            
            h1 {
                font-size: 20px;
                margin-top: 10px;
            }
            
            .key-meta {
                flex-direction: column;
                gap: 8px;
                text-align: center;
                width: 100%;
            }
            
            .key-icon {
                font-size: 40px;
                margin: 5px 0 15px;
            }
            
            .branding h2 {
                font-size: 1.5rem;
            }
            
            .branding .tagline {
                font-size: 0.8rem;
            }
            
            .key-description {
                font-size: 14px;
                margin-bottom: 20px;
            }
            
            .copy-btn {
                padding: 12px 24px;
                font-size: 15px;
            }
        }
        
        @keyframes float {
            0% { transform: translateY(0px); }
            50% { transform: translateY(-8px); }
            100% { transform: translateY(0px); }
        }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body>
    <button class="theme-toggle" id="themeToggle" aria-label="Toggle dark mode">
        <i class="fas fa-moon"></i>
    </button>
    
    <div class="key-container">
        <div class="branding">
            <h2>Welcome to ExamSaathi</h2>
            <div class="tagline">Your Learning Partner</div>
        </div>
        <div class="key-icon">
            <i class="fas fa-key"></i>
        </div>
        <h1>Your Authentication Key</h1>
        <p class="key-description">This key provides secure access to your account. Keep it confidential.</p>
        
        <div class="key-input-group">
            <input type="text" id="keyBox" class="key-input" value="{{ key }}" readonly>
        </div>
        
        <button class="copy-btn" onclick="copyKey()">
            <i class="far fa-copy"></i> Copy Key
        </button>
        
        <div class="key-meta">
            <span><i class="far fa-clock"></i> Valid for 24 Hours </span>
            <span><i class="fas fa-shield-alt"></i> Secure connection</span>
        </div>
    </div>
    
    <div class="notification" id="notification">
        <i class="fas fa-check-circle"></i>
        <span>Key copied to clipboard!</span>
    </div>
    
    <script>
        function copyKey() {
            var copyText = document.getElementById('keyBox');
            copyText.select();
            copyText.setSelectionRange(0, 99999);
            document.execCommand('copy');
            
            var notification = document.getElementById('notification');
            notification.classList.add('show');
            
            setTimeout(function() {
                notification.classList.remove('show');
            }, 3000);
        }
        
        document.getElementById('keyBox').addEventListener('click', function() {
            this.select();
        });
    </script>
    
    <script>
        // Theme Toggle Functionality
        const themeToggle = document.getElementById('themeToggle');
        const themeIcon = themeToggle.querySelector('i');
        const prefersDarkScheme = window.matchMedia('(prefers-color-scheme: dark)');
        
        // Check for saved theme preference or use system preference
        const currentTheme = localStorage.getItem('theme');
        
        if (currentTheme === 'dark' || (!currentTheme && prefersDarkScheme.matches)) {
            document.documentElement.setAttribute('data-theme', 'dark');
            themeIcon.classList.remove('fa-moon');
            themeIcon.classList.add('fa-sun');
        }
        
        // Toggle theme on button click
        themeToggle.addEventListener('click', () => {
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            
            if (isDark) {
                document.documentElement.removeAttribute('data-theme');
                themeIcon.classList.remove('fa-sun');
                themeIcon.classList.add('fa-moon');
                localStorage.setItem('theme', 'light');
            } else {
                document.documentElement.setAttribute('data-theme', 'dark');
                themeIcon.classList.remove('fa-moon');
                themeIcon.classList.add('fa-sun');
                localStorage.setItem('theme', 'dark');
            }
        });
        
        // Listen for system theme changes
        prefersDarkScheme.addEventListener('change', (e) => {
            if (!localStorage.getItem('theme')) {
                if (e.matches) {
                    document.documentElement.setAttribute('data-theme', 'dark');
                    themeIcon.classList.remove('fa-moon');
                    themeIcon.classList.add('fa-sun');
                } else {
                    document.documentElement.removeAttribute('data-theme');
                    themeIcon.classList.remove('fa-sun');
                    themeIcon.classList.add('fa-moon');
                }
            }
        });
    </script>
</body>
</html>
            ''', key=keys_data[user_id]["key"])

    key = generate_key()
    expiry_time = current_time + timedelta(days=KEY_EXPIRY_DAYS)

    key_data = {
        "key": key,
        "expiry_time": expiry_time.isoformat()
    }

    if not save_to_mongodb(user_id, key_data):
        return "Failed to save key", 500

    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Your Authentication Key</title>
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
                <style>
        :root {
            --primary: #4361ee;
            --primary-dark: #3a56d4;
            --text: #2b2d42;
            --light: #f8f9fa;
            --success: #4cc9f0;
            --border-radius: 12px;
            --box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Inter', sans-serif;
            background-color: #f5f7ff;
            color: var(--text);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 20px;
            line-height: 1.6;
        }
        
        .key-container {
            background: white;
            border-radius: var(--border-radius);
            box-shadow: var(--box-shadow);
            width: 100%;
            max-width: 500px;
            padding: 40px;
            text-align: center;
            position: relative;
            overflow: hidden;
        }
        
        .key-container::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 6px;
            background: linear-gradient(90deg, #4361ee, #4cc9f0);
        }
        
        .key-icon {
            font-size: 48px;
            color: var(--primary);
            margin-bottom: 20px;
            animation: float 3s ease-in-out infinite;
        }
        
        h1 {
            font-size: 24px;
            font-weight: 600;
            margin-bottom: 15px;
            color: var(--text);
        }
        
        .key-description {
            color: #6c757d;
            margin-bottom: 30px;
            font-size: 15px;
        }
        
        .key-input-group {
            position: relative;
            margin-bottom: 25px;
        }
        
        .key-input {
            width: 100%;
            padding: 15px 20px;
            font-size: 16px;
            border: 2px solid #e9ecef;
            border-radius: var(--border-radius);
            background: var(--light);
            font-family: 'Courier New', monospace;
            font-weight: 600;
            color: var(--text);
            letter-spacing: 1px;
            transition: all 0.3s ease;
        }
        
        .key-input:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.2);
        }
        
        .copy-btn {
            background-color: var(--primary);
            color: white;
            border: none;
            padding: 14px 28px;
            font-size: 16px;
            font-weight: 500;
            border-radius: var(--border-radius);
            cursor: pointer;
            transition: all 0.3s ease;
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }
        
        .copy-btn:hover {
            background-color: var(--primary-dark);
            transform: translateY(-2px);
        }
        
        .copy-btn:active {
            transform: translateY(0);
        }
        
        .key-meta {
            margin-top: 25px;
            font-size: 13px;
            color: #adb5bd;
            display: flex;
            justify-content: center;
            gap: 15px;
        }
        
        @keyframes float {
            0% { transform: translateY(0px); }
            50% { transform: translateY(-8px); }
            100% { transform: translateY(0px); }
        }
        
        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            background: #4bb543;
            color: white;
            padding: 15px 25px;
            border-radius: var(--border-radius);
            box-shadow: var(--box-shadow);
            transform: translateX(150%);
            transition: transform 0.3s ease;
            z-index: 1000;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .notification.show {
            transform: translateX(0);
        }
        
        @media (max-width: 600px) {
            .key-container {
                padding: 30px 20px;
            }
            
            h1 {
                font-size: 20px;
            }
        }
    </style>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
        </head>
        <body>
            <div class="key-container">
                <div class="key-icon">
                    <i class="fas fa-key"></i>
                </div>
                <h1>Your Authentication Key</h1>
                <p class="key-description">This key provides secure access to your account. Keep it confidential.</p>
                
                <div class="key-input-group">
                    <input type="text" id="keyBox" class="key-input" value="{{ key }}" readonly>
                </div>
                
                <button class="copy-btn" onclick="copyKey()">
                    <i class="far fa-copy"></i> Copy Key
                </button>
                
                <div class="key-meta">
                    <span><i class="far fa-clock"></i> Valid for 3 days</span>
                    <span><i class="fas fa-shield-alt"></i> Secure connection</span>
                </div>
            </div>
            
            <div class="notification" id="notification">
                <i class="fas fa-check-circle"></i>
                <span>Key copied to clipboard!</span>
            </div>
            
            <script>
                function copyKey() {
                    var copyText = document.getElementById('keyBox');
                    copyText.select();
                    copyText.setSelectionRange(0, 99999);
                    document.execCommand('copy');
                    
                    var notification = document.getElementById('notification');
                    notification.classList.add('show');
                    
                    setTimeout(function() {
                        notification.classList.remove('show');
                    }, 3000);
                }
                
                document.getElementById('keyBox').addEventListener('click', function() {
                    this.select();
                });
            </script>
        </body>
        </html>
    ''', key=key)

@app.route('/api/check', methods=['GET'])
def check():
    user_id = request.args.get('id')
    key = request.args.get('key')

    if not user_id or not key:
        return jsonify({"status":"Unauthorized"}), 400

    keys_data = get_mongodb_keys()
    user_data = keys_data.get(user_id)

    if user_data and user_data["key"] == key:
        
        expiry_time = datetime.fromisoformat(user_data["expiry_time"])
        current_time = get_current_ist_time()

        if current_time <= expiry_time:
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "Unauthorized"}), 401
    else:
        return jsonify({"status": "Unauthorized"}), 401

@app.route('/api/admin', methods=['GET'])
def admin():
    admin_key = request.args.get('adminkey')
    user_id = request.args.get('id')
    key = request.args.get('key')

    if admin_key != "SDV_BOTX_ADMIN_ID_SDVRWA@1234abcXYZ":
        return jsonify({"status": "error", "message": "Invalid admin key"}), 403

    if not user_id or not key:
        return jsonify({"status": "error", "message": "ID and key are required"}), 400

    expiry_time = get_current_ist_time() + timedelta(days=KEY_EXPIRY_DAYS)

    key_data = {
        "key": key,
        "expiry_time": expiry_time.isoformat()
    }

    if save_to_mongodb(user_id, key_data):
        return jsonify({"status": "success", "message": "Key added/updated"})
    else:
        return jsonify({"status": "error", "message": "Failed to save key"}), 500

@app.route('/api/view-keys', methods=['GET'])
def view_keys():
    admin_key = request.args.get('adminkey')
    
    if admin_key != "SDV_BOTX_ADMIN_ID_SDVRWA@1234abcXYZ":
        return jsonify({"status": "error", "message": "Invalid admin key"}), 403
    
    keys_data = get_mongodb_keys()
    return jsonify({"status": "success", "keys": keys_data})

@app.route('/api/view-tokens', methods=['GET'])
def view_tokens():
    admin_key = request.args.get('adminkey')
    
    if admin_key != "SDV_BOTX_ADMIN_ID_SDVRWA@1234abcXYZ":
        return jsonify({"status": "error", "message": "Invalid admin key"}), 403
    
    tokens_data = get_mongodb_tokens()
    return jsonify({"status": "success", "tokens": tokens_data})

@app.route('/api/cleanup-tokens', methods=['GET'])
def cleanup_tokens_endpoint():
    admin_key = request.args.get('adminkey')
    
    if admin_key != "SDV_BOTX_ADMIN_ID_SDVRWA@123abcXYZ":
        return jsonify({"status": "error", "message": "Invalid admin key"}), 403
    
    try:
        cleanup_expired_tokens()
        return jsonify({"status": "success", "message": "Expired tokens cleaned up"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error cleaning tokens: {e}"}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "success", 
        "message": "API is running",
        "mongodb_connected": mongo_connected
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

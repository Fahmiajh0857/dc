import os
import requests
import json
import random
import time
from datetime import datetime
from dotenv import load_dotenv
import threading

# === Load environment variables ===
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_IDS = os.getenv("CHANNEL_IDS", "").split(",")
BASE_URL = "https://discord.com/api/v9/channels"
HEADERS = {"Authorization": TOKEN, "Content-Type": "application/json"}
REACTION_EMOJI = ["🔥", "💀", "👀", "🙃", "😂", "🤔"]

# === Fetch Messages ===
def fetch_messages(channel_id):
    response = requests.get(f"{BASE_URL}/{channel_id}/messages", headers=HEADERS, params={"limit": 10})
    return response.json() if response.status_code == 200 else []

# === Generate Short Response ===
def get_response(input_text):
    """Generate a short and trendy response."""
    responses = [
        "Bruh 💀", "Sheeesh 🔥", "For real 🤔", "Nah fr", 
        "Lmao 😂", "Ayo?", "Chill 🙃", "Deadass?", 
        "Yikes", "Smh", "Wym?", "Say less"
    ]
    return random.choice(responses)

# === Send and Delete Message ===
def send_message(channel_id, content):
    data = {"content": content}
    response = requests.post(f"{BASE_URL}/{channel_id}/messages", headers=HEADERS, json=data)
    if response.status_code == 200:
        message_id = response.json()["id"]
        threading.Timer(random.randint(20, 45), delete_message, args=(channel_id, message_id)).start()

def delete_message(channel_id, message_id):
    requests.delete(f"{BASE_URL}/{channel_id}/messages/{message_id}", headers=HEADERS)

# === Main Bot Logic ===
def main():
    while True:
        for channel_id in CHANNEL_IDS:
            try:
                messages = fetch_messages(channel_id)
                if not messages:
                    continue

                for message in messages:
                    if random.random() > 0.7:  # Randomly choose to respond
                        response = get_response(message.get("content", ""))
                        send_message(channel_id, response)
                        time.sleep(random.randint(3, 10))  # Add slight delay
            except Exception as e:
                print(f"Error in channel {channel_id}: {e}")

        time.sleep(5)

if __name__ == "__main__":
    main()

import os
import requests
import json
import random
import time
from datetime import datetime, timedelta, timezone
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import threading
from dateutil import parser

# === Load environment variables ===
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_IDS = os.getenv("CHANNEL_IDS", "").split(",")
BASE_URL = "https://discord.com/api/v9/channels"
HEADERS = {
    "Authorization": TOKEN,
    "Content-Type": "application/json"
}
IGNORED_USER_IDS = os.getenv("IGNORED_USER_IDS", "").split(",")
BLOCKED_WORDS = ["stumble guys game", "stumble guys"]
REACTION_EMOJI = ["👍", "🔥", "❤️", "🤙", "✅", "🙌"]
REACTION_LOG = {channel_id: set() for channel_id in CHANNEL_IDS}

# === Load pre-trained embedding model ===
model = SentenceTransformer('all-MiniLM-L6-v2')

# === Memory Management ===
class Memory:
    def __init__(self):
        self.short_term = {channel_id: [] for channel_id in CHANNEL_IDS}
        self.long_term = {channel_id: [] for channel_id in CHANNEL_IDS}

    def update_short_term(self, channel_id, message):
        self.short_term[channel_id].append(message)
        if len(self.short_term[channel_id]) > 20:
            self.short_term[channel_id].pop(0)

    def add_long_term(self, channel_id, key_fact):
        self.long_term[channel_id].append(key_fact)

memory = Memory()

# === 1. Fetch Previous Messages ===
def fetch_previous_messages(channel_id, minutes=30, save=True):
    """Fetch messages from the last `minutes` in a channel and optionally save them."""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=minutes)

    params = {"limit": 100}
    response = requests.get(f"{BASE_URL}/{channel_id}/messages", headers=HEADERS, params=params)
    if response.status_code == 200:
        try:
            messages = response.json()
            filtered_messages = []

            print(f"Fetching messages from {start_time} to {end_time}")

            for message in messages:
                content = message.get("content", "")
                author_id = message["author"]["id"]

                try:
                    timestamp = parser.isoparse(message["timestamp"])
                except Exception as e:
                    print(f"Error parsing timestamp: {e}")
                    continue

                if (
                    len(content) > 200 or
                    content.isupper() or
                    author_id in IGNORED_USER_IDS or
                    any(blocked_word in content.lower() for blocked_word in BLOCKED_WORDS)
                ):
                    continue

                if start_time <= timestamp <= end_time:
                    filtered_messages.append({
                        "content": content,
                        "author": message["author"]["username"],
                        "author_id": author_id,
                        "timestamp": message["timestamp"],
                        "id": message["id"],
                        "replied_to": message.get("message_reference", {}).get("message_id")
                    })

            if save:
                file_path = f"chat_history_{channel_id}.json"
                with open(file_path, "w", encoding="utf-8") as file:
                    json.dump(filtered_messages, file, indent=4, ensure_ascii=False)
                print(f"Chats from the last {minutes} minutes saved to '{file_path}'.")

            return filtered_messages
        except Exception as e:
            print(f"Error processing messages: {e}")
    else:
        print(f"Error fetching messages for channel {channel_id}: {response.status_code}, {response.text}")
    return []

# === 2. Train Model ===
def train_model(channel_id):
    """Train model embeddings on chat history."""
    file_path = f"chat_history_{channel_id}.json"
    if not os.path.exists(file_path):
        print(f"Chat history file not found for channel {channel_id}. Creating a new one.")
        # Fetch the last 30 minutes of messages and create the file if not exists
        fetch_previous_messages(channel_id, minutes=30, save=True)
        return [], [], []  # Return empty lists if no previous messages available

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            chat_history = json.load(file)

        texts = [message["content"] for message in chat_history if message["content"].strip()]
        if not texts:
            print(f"Warning: No valid messages found in chat history for channel {channel_id}.")
            return None, None, [], []

        embeddings = model.encode(texts)
        return embeddings, texts, chat_history
    except FileNotFoundError:
        print(f"Chat history file not found for channel {channel_id}.")
    except json.JSONDecodeError:
        print(f"Error decoding JSON for chat history file: {file_path}.")
    return None, None, [], []

# === 3. Generate Response ===
def modify_message(message):
    """Modify a message with random stylistic changes."""
    words = message.split()
    if len(words) > 3:
        words.insert(random.randint(1, len(words) - 1), random.choice([
            "like", "you know", "tbh", "literally", "for real", "no cap", "fr", "kinda", "lowkey"
        ]))
    if len(words) > 5:
        words.pop(random.randint(1, len(words) - 2))
    if random.random() > 0.5:
        words.append(random.choice(["lol", "haha", "right?", "ikr", "smh"]))
    return " ".join(words)

def get_response(input_text, embeddings, texts):
    """Generate a response based on input text similarity."""
    input_embedding = model.encode([input_text])
    similarity = cosine_similarity(input_embedding, embeddings).flatten()

    if max(similarity) > 0.5:
        best_match_idx = similarity.argmax()
        return modify_message(texts[best_match_idx])
    return random.choice(["Tell me more!", "Interesting!", "I’d love to hear more about that!"])

# === 4. Send and Delete Message ===
def delete_message(channel_id, message_id):
    """Delete a message after a specified delay."""
    url = f"{BASE_URL}/{channel_id}/messages/{message_id}"
    response = requests.delete(url, headers=HEADERS)

    if response.status_code == 204:
        print(f"Message {message_id} in channel {channel_id} deleted successfully.")
    else:
        print(f"Error deleting message: {response.status_code}, {response.text}")

def send_message(channel_id, content, is_reply=False, reply_message_id=None):
    """Send a message to a channel, optionally as a reply."""
    data = {"content": content}
    if is_reply and reply_message_id:
        data["message_reference"] = {"message_id": reply_message_id}

    while True:
        response = requests.post(f"{BASE_URL}/{channel_id}/messages", headers=HEADERS, json=data)
        if response.status_code == 200:
            message_id = response.json()["id"]
            print(f"Message sent to channel {channel_id} successfully.")
            threading.Timer(55, delete_message, args=(channel_id, message_id)).start()
            break
        elif response.status_code == 429:
            retry_after = response.json().get("retry_after", 1)
            print(f"Rate limit hit. Retrying after {retry_after} seconds...")
            time.sleep(retry_after)
        else:
            print(f"Error sending message: {response.status_code}, {response.text}")
            break

# === 5. Main Bot Logic ===
def main():
    """Main logic for monitoring and responding in Discord channels."""
    last_message_times = {channel_id: datetime.now() - timedelta(minutes=1) for channel_id in CHANNEL_IDS}
    idle_states = {channel_id: False for channel_id in CHANNEL_IDS}

    while True:
        for channel_id in CHANNEL_IDS:
            try:
                embeddings, texts, chat_history = train_model(channel_id)
                if embeddings is None or texts is None:
                    continue  # Skip if training model failed

                recent_messages = fetch_previous_messages(channel_id, minutes=5, save=False)

                if recent_messages:
                    idle_states[channel_id] = False
                    for message in recent_messages:
                        if message["id"] in [msg["id"] for msg in chat_history]:
                            continue

                        chat_history.insert(0, message)

                        if "?" in message["content"]:
                            current_time = datetime.now()
                            if (current_time - last_message_times[channel_id]).total_seconds() >= 60:
                                response = get_response(message["content"], embeddings, texts)
                                send_message(channel_id, response, is_reply=True, reply_message_id=message["id"])
                                REACTION_LOG[channel_id].add(message["id"])
                                last_message_times[channel_id] = current_time

                elif not idle_states[channel_id]:
                    current_time = datetime.now()
                    if (current_time - last_message_times[channel_id]).total_seconds() >= random.randint(120, 300):
                        general_message = random.choice([
                            "Hey! How are you?", "Hello! Have a nice day!", "What's up?",
                            "Anyone here?", "How's it going?", "Hey guys!", "Any cool updates?"
                        ])
                        send_message(channel_id, general_message)
                        last_message_times[channel_id] = current_time
                        idle_states[channel_id] = True

                with open(f"chat_history_{channel_id}.json", "w", encoding="utf-8") as file:
                    json.dump(chat_history[:500], file, indent=4, ensure_ascii=False)

            except Exception as e:
                print(f"Error in channel {channel_id}: {e}")

        time.sleep(5)

if __name__ == "__main__":
    main()

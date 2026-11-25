import os
import logging
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]
PUBLIC_URL = os.environ["PUBLIC_URL"].rstrip("/")
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
WEBHOOK_PATH = f"/telegram/{WEBHOOK_SECRET}"


def telegram(method, data=None):
    response = requests.post(
        f"{API}/{method}",
        json=data or {},
        timeout=20
    )

    try:
        result = response.json()
    except ValueError:
        raise RuntimeError(
            f"Telegram returned HTTP {response.status_code}: "
            f"{response.text[:500]}"
        )

    if not response.ok or not result.get("ok"):
        raise RuntimeError(
            f"Telegram API error ({response.status_code}): "
            f"{result.get('description', response.text[:500])}"
        )

    return result.get("result")

def send_message(chat_id, message):
    telegram("sendMessage", {
        "chat_id": chat_id,
        "text": message
    })


@app.get("/")
def home():
    return "Auto Join Request Bot is running!"


@app.post(WEBHOOK_PATH)
def webhook():
    if request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token"
    ) != WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 403

    update = request.get_json(silent=True) or {}

    # Automatically approve a join request
    join_request = update.get("chat_join_request")

    if join_request:
        chat_id = join_request["chat"]["id"]
        user_id = join_request["from"]["id"]

        try:
            telegram("approveChatJoinRequest", {
                "chat_id": chat_id,
                "user_id": user_id
            })
            logging.info(
                "Approved user %s in chat %s",
                user_id, chat_id
            )
        except Exception:
            logging.exception("Could not approve join request")
            return jsonify({"error": "Approval failed"}), 500

    # Respond to /start in private chat
    message = update.get("message", {})
    chat = message.get("chat", {})

    if chat.get("type") == "private":
        text = message.get("text", "")

        if text.startswith("/start"):
            send_message(
                chat["id"],
                "Welcome! I automatically approve Telegram "
                "join requests in groups and channels where "
                "I am an administrator.\n\n"
                "To use me:\n"
                "1. Add me to your group or channel.\n"
                "2. Make me an administrator.\n"
                "3. Enable the Invite Users permission.\n"
                "4. Turn on join requests for your invite link.\n\n"
                "Use /help for instructions."
            )

        elif text.startswith("/help"):
            send_message(
                chat["id"],
                "Add this bot as an administrator and grant "
                "Invite Users permission. Enable join requests "
                "on your invite link. Requests will then be "
                "automatically approved."
            )

    return jsonify({"ok": True})


# Register the Telegram webhook when the app starts
def setup_webhook():
    telegram("setWebhook", {
        "url": PUBLIC_URL + WEBHOOK_PATH,
        "secret_token": WEBHOOK_SECRET,
        "allowed_updates": ["message", "chat_join_request"]
    })


setup_webhook()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )

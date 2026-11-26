import os
import logging
import requests
from flask import Flask, request, jsonify
from upstash_redis import Redis

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]
PUBLIC_URL = os.environ["PUBLIC_URL"].rstrip("/")
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
WEBHOOK_PATH = f"/telegram/{WEBHOOK_SECRET}"

redis = Redis.from_env()


def telegram(method, data=None):
    response = requests.post(
        f"{API}/{method}",
        json=data or {},
        timeout=20
    )

    result = response.json()

    if not response.ok or not result.get("ok"):
        raise RuntimeError(
            result.get("description", "Telegram API error")
        )

    return result.get("result")


def send_message(chat_id, message):
    telegram("sendMessage", {
        "chat_id": chat_id,
        "text": message
    })


@app.get("/")
def home():
    return "ReqFlowAcceptBot is running!"


@app.post(WEBHOOK_PATH)
def webhook():

    if request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token"
    ) != WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 403

    update = request.get_json(silent=True) or {}

    # Handle join requests
    join_request = update.get("chat_join_request")

    if join_request:

        chat_id = join_request["chat"]["id"]
        user_id = join_request["from"]["id"]
        user_chat_id = join_request.get("user_chat_id")

        channel_name = join_request["chat"].get(
            "title", "our channel/group"
        )

        redis.incr("total_requests")

        # STEP 1: Attempt DM before approval
        if user_chat_id:

            try:
                send_message(
    user_chat_id,
    f"I have successfully approved your request "
    f"to join {channel_name}. 🎉\n\n"
    "Welcome! Thank you for joining.\n\n"
    "📢 Join our WhatsApp Channel for more updates:\n"
    "👉 https://whatsapp.com/channel/0029VahpPcv1Hsq6t1DOMO1O"
)

                logging.info(
                    "Approval DM sent to user %s", user_id
                )

            except Exception:
                logging.exception(
                    "Approval DM failed for user %s", user_id
                )

        else:
            logging.warning(
                "No user_chat_id available for user %s", user_id
            )

        # STEP 2: Approve join request
        try:

            telegram("approveChatJoinRequest", {
                "chat_id": chat_id,
                "user_id": user_id
            })

            redis.incr("total_approved")

            logging.info(
                "Successfully approved user %s", user_id
            )

        except Exception as e:

            error = str(e)

            if "USER_ALREADY_PARTICIPANT" in error:

                logging.info(
                    "User %s is already a participant", user_id
                )

                return jsonify({
                    "ok": True,
                    "already_member": True
                }), 200

            redis.incr("total_errors")

            logging.exception("Approval failed")

            return jsonify({
                "error": "Approval failed"
            }), 500

    # Handle private messages and commands
    message = update.get("message", {})
    chat = message.get("chat", {})

    if chat.get("type") == "private":

        user_id = chat["id"]
        text = message.get("text", "").strip()

        if text.startswith("/start"):

            redis.sadd("bot_users", str(user_id))

            send_message(
                user_id,
                "Welcome to ReqFlowAcceptBot! 🤖\n\n"
                "I automatically approve Telegram join requests.\n\n"
                "1. Add me as an administrator.\n"
                "2. Enable Invite Users permission.\n"
                "3. Enable join requests on your invite link.\n\n"
                "Use /help for instructions."
            )

        elif text.startswith("/help"):

            send_message(
                user_id,
                "Add me as an administrator and enable "
                "Invite Users permission. Turn on join requests "
                "for your invite link."
            )

        elif user_id == ADMIN_ID and text == "/stats":

            users = redis.scard("bot_users")
            requests_count = redis.get("total_requests") or 0
            approved = redis.get("total_approved") or 0
            errors = redis.get("total_errors") or 0

            send_message(
                user_id,
                "📊 ReqFlowAcceptBot Stats\n\n"
                f"👥 Bot users: {users}\n"
                f"📩 Join requests: {requests_count}\n"
                f"✅ Approved: {approved}\n"
                f"❌ Errors: {errors}"
            )

        elif user_id == ADMIN_ID and text.startswith("/broadcast"):

            broadcast_text = text.partition(" ")[2].strip()

            if not broadcast_text:

                send_message(
                    user_id,
                    "Use this format:\n/broadcast Your message"
                )

            else:

                users = redis.smembers("bot_users")

                sent = 0
                failed = 0

                for recipient in users:

                    try:
                        send_message(
                            int(recipient),
                            broadcast_text
                        )
                        sent += 1

                    except Exception:
                        failed += 1

                        logging.exception(
                            "Broadcast failed for user %s",
                            recipient
                        )

                send_message(
                    user_id,
                    f"📢 Broadcast finished!\n\n"
                    f"✅ Sent: {sent}\n"
                    f"❌ Failed: {failed}"
                )

    return jsonify({"ok": True})


def setup_webhook():

    telegram("setWebhook", {
        "url": PUBLIC_URL + WEBHOOK_PATH,
        "secret_token": WEBHOOK_SECRET,
        "allowed_updates": [
            "message",
            "chat_join_request"
        ]
    })


setup_webhook()


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )

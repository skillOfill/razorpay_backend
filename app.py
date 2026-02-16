"""
License server: Razorpay webhook (generate key + email) and validation API for Streamlit app.
Deploy this to Railway, Render, or any host with a public URL; set that URL in Streamlit app as LICENSE_SERVER_URL.
"""
import os
import secrets
import logging
from flask import Flask, request, jsonify

from dotenv import load_dotenv
load_dotenv()

from db import add_key, is_valid_key, get_key_by_order, email_has_license
from mailer import send_license_email

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "").strip()
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")


def generate_license_key() -> str:
    return "SQLH-" + secrets.token_hex(4).upper() + "-" + secrets.token_hex(2).upper()


def verify_razorpay_signature(body: bytes, signature: str) -> bool:
    if not WEBHOOK_SECRET or not signature:
        return False
    try:
        import razorpay
        client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
        client.utility.verify_webhook_signature(body, signature, WEBHOOK_SECRET)
        return True
    except Exception as e:
        logger.warning("Webhook signature verification failed: %s", e)
        return False


@app.route("/webhook/razorpay", methods=["POST"])
def razorpay_webhook():
    """Razorpay calls this on payment.captured. Verify signature, generate key, store, email."""
    raw_body = request.get_data()
    signature = request.headers.get("X-Razorpay-Signature", "")

    if not verify_razorpay_signature(raw_body, signature):
        return jsonify({"ok": False, "error": "Invalid signature"}), 400

    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        return jsonify({"ok": False, "error": "Invalid JSON"}), 400

    event = data.get("event")
    if event != "payment.captured":
        return jsonify({"ok": True, "message": "Event ignored"}), 200

    payload = data.get("payload", {})
    payment = payload.get("payment", {})
    entity = payment.get("entity", payment)
    email = (entity.get("email") or "").strip()
    order_id = entity.get("order_id") or ""
    payment_id = entity.get("id") or ""

    if not email:
        logger.warning("payment.captured missing email: %s", data)
        return jsonify({"ok": False, "error": "Missing email"}), 400

    license_key = generate_license_key()
    add_key(license_key=license_key, email=email, order_id=order_id, payment_id=payment_id)

    sent = send_license_email(to_email=email, license_key=license_key)
    logger.info("License created for %s key=%s email_sent=%s", email, license_key[:12] + "...", sent)

    return jsonify({"ok": True, "license_key": license_key, "email_sent": sent}), 200


@app.route("/api/validate", methods=["GET"])
def validate_key():
    """Streamlit app calls this to check if a license key is valid."""
    key = (request.args.get("key") or "").strip()
    if not key:
        return jsonify({"valid": False}), 400
    return jsonify({"valid": is_valid_key(key)}), 200


@app.route("/api/validate-by-email", methods=["GET"])
def validate_by_email():
    """Streamlit app calls this for auto-unlock: has this email (e.g. Google) paid?"""
    email = (request.args.get("email") or "").strip()
    if not email:
        return jsonify({"valid": False}), 400
    return jsonify({"valid": email_has_license(email)}), 200


@app.route("/api/create-payment-link", methods=["POST"])
def create_payment_link():
    """Create a Razorpay payment link with customer email (for Google Login → Payment flow)."""
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        return jsonify({"error": "Razorpay not configured"}), 503
    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400
    email = (data.get("email") or "").strip()
    if not email or "@" not in email:
        return jsonify({"error": "Valid email required"}), 400

    amount = int(os.environ.get("PAYMENT_AMOUNT_PAISE", "49900"))  # ₹499
    currency = os.environ.get("PAYMENT_CURRENCY", "INR")
    description = os.environ.get("PAYMENT_DESCRIPTION", "SQL Humanizer Pro — Unlimited translations")

    try:
        import razorpay
        client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
        payload = {
            "amount": amount,
            "currency": currency,
            "description": description,
            "customer": {"email": email},
            "notify": {"sms": False, "email": True},
        }
        result = client.payment_link.create(payload)
        short_url = (result or {}).get("short_url") or ""
        if not short_url:
            return jsonify({"error": "No payment URL returned"}), 502
        return jsonify({"url": short_url}), 200
    except Exception as e:
        logger.exception("Create payment link failed: %s", e)
        return jsonify({"error": str(e)}), 500


@app.route("/thank-you", methods=["GET"])
def thank_you():
    """Optional: redirect customers here after payment; show key if order_id provided."""
    order_id = (request.args.get("order_id") or "").strip()
    key = get_key_by_order(order_id) if order_id else None
    if key:
        return f"""
        <!DOCTYPE html>
        <html><head><meta charset="utf-8"><title>Thank you</title></head>
        <body style="font-family:sans-serif; max-width:480px; margin:2rem auto; padding:1rem;">
        <h1>Thank you for your purchase</h1>
        <p>Your SQL Humanizer license key is:</p>
        <p style="font-size:1.2em; font-family:monospace; background:#f1f5f9; padding:0.75rem; border-radius:8px;"><strong>{key}</strong></p>
        <p>Enter it in the app sidebar to unlock Pro.</p>
        </body></html>
        """
    return """
    <!DOCTYPE html>
    <html><head><meta charset="utf-8"><title>Thank you</title></head>
    <body style="font-family:sans-serif; max-width:480px; margin:2rem auto; padding:1rem;">
    <h1>Thank you</h1>
    <p>Your payment was successful. We've sent your license key to your email address.</p>
    <p>Check your inbox (and spam folder).</p>
    </body></html>
    """


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "0") == "1")

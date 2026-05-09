import os
import hmac
import hashlib
import logging

logger = logging.getLogger(__name__)


def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """
    Verify Razorpay payment signature after frontend checkout completes.

    Razorpay computes: HMAC-SHA256("{order_id}|{payment_id}", key=RAZORPAY_KEY_SECRET)
    We replicate this server-side and compare with constant-time digest to
    prevent timing attacks.

    Returns True if the signature is valid, False otherwise.
    Never raises — logs errors and returns False on any failure.
    """
    key_secret = os.environ.get('RAZORPAY_KEY_SECRET', '')
    if not key_secret:
        logger.error("RAZORPAY_KEY_SECRET is not set — cannot verify payment signature")
        return False

    msg = f"{order_id}|{payment_id}"
    try:
        expected = hmac.new(
            key_secret.encode('utf-8'),
            msg.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        # constant-time comparison — prevents timing-based secret extraction
        return hmac.compare_digest(expected, signature)
    except Exception as e:
        logger.error(f"Payment signature verification failed unexpectedly: {e}")
        return False


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    """
    Verify Razorpay webhook signature from X-Razorpay-Signature header.

    Razorpay computes: HMAC-SHA256(raw_request_body, key=RAZORPAY_WEBHOOK_SECRET)
    `body` must be the raw bytes from request.get_data() — do NOT parse JSON first.

    Returns True if the signature is valid, False otherwise.
    Never raises — logs errors and returns False on any failure.
    """
    webhook_secret = os.environ.get('RAZORPAY_WEBHOOK_SECRET', '')
    if not webhook_secret:
        logger.error("RAZORPAY_WEBHOOK_SECRET is not set — cannot verify webhook signature")
        return False

    try:
        expected = hmac.new(
            webhook_secret.encode('utf-8'),
            body,
            hashlib.sha256
        ).hexdigest()
        # constant-time comparison — prevents timing-based secret extraction
        return hmac.compare_digest(expected, signature)
    except Exception as e:
        logger.error(f"Webhook signature verification failed unexpectedly: {e}")
        return False


def get_razorpay_client():
    """
    Returns an initialized Razorpay client using credentials from environment.

    Raises RuntimeError if RAZORPAY_KEY_ID or RAZORPAY_KEY_SECRET are not set,
    so callers can catch and return a 500 rather than exposing a misconfigured state.

    Key values are intentionally never logged.
    """
    import razorpay

    key_id = os.environ.get('RAZORPAY_KEY_ID')
    key_secret = os.environ.get('RAZORPAY_KEY_SECRET')

    if not key_id or not key_secret:
        raise RuntimeError(
            "Razorpay API keys not configured. "
            "Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in environment."
        )

    return razorpay.Client(auth=(key_id, key_secret))

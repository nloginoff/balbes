"""MAX inbound webhook signature helper."""

import hashlib
import hmac

from shared.max_inbound import verify_max_webhook_signature


def test_verify_max_signature_ok() -> None:
    secret = "test-secret"
    body = b'{"hello":"world"}'
    sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    assert verify_max_webhook_signature(body, sig, secret) is True


def test_verify_max_signature_wrong() -> None:
    assert verify_max_webhook_signature(b"a", "deadbeef", "secret") is False

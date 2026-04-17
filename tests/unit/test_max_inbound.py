"""MAX inbound webhook signature helper."""

import hashlib
import hmac

from shared.max_inbound import (
    verify_max_webhook_auth,
    verify_max_webhook_secret_header,
    verify_max_webhook_signature,
)


def test_verify_max_secret_header_ok() -> None:
    assert verify_max_webhook_secret_header("my-shared-secret", "my-shared-secret") is True
    assert verify_max_webhook_secret_header("wrong", "my-shared-secret") is False


def test_verify_max_webhook_auth_official_header() -> None:
    secret = "prod-webhook-secret-1"
    body = b'{"update_type":"message_created"}'
    assert (
        verify_max_webhook_auth(
            body=body,
            x_max_bot_api_secret=secret,
            x_signature=None,
            secret=secret,
        )
        is True
    )
    assert (
        verify_max_webhook_auth(
            body=body,
            x_max_bot_api_secret="wrong",
            x_signature=None,
            secret=secret,
        )
        is False
    )


def test_verify_max_signature_ok() -> None:
    secret = "test-secret"
    body = b'{"hello":"world"}'
    sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    assert verify_max_webhook_signature(body, sig, secret) is True


def test_verify_max_signature_wrong() -> None:
    assert verify_max_webhook_signature(b"a", "deadbeef", "secret") is False


def test_verify_max_webhook_auth_legacy_hmac() -> None:
    secret = "test-secret"
    body = b'{"hello":"world"}'
    sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    assert (
        verify_max_webhook_auth(
            body=body,
            x_max_bot_api_secret=None,
            x_signature=sig,
            secret=secret,
        )
        is True
    )


def test_verify_max_webhook_auth_empty_secret_means_ok() -> None:
    assert (
        verify_max_webhook_auth(
            body=b"{}",
            x_max_bot_api_secret=None,
            x_signature=None,
            secret="",
        )
        is True
    )

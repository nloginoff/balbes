"""MAX webhook reply target extraction (real-world payloads vs bot id in recipient)."""

from shared.max_webhook import extract_max_reply_targets


def test_real_payload_prefers_negative_chat_id() -> None:
    msg = {
        "recipient": {"chat_id": -100000000, "chat_type": "dialog", "user_id": 12345},
        "sender": {
            "user_id": 54321,
            "is_bot": False,
            "name": "Human",
        },
    }
    cid, uid = extract_max_reply_targets(msg)
    assert cid == -100000000
    assert uid is None


def test_dm_without_chat_id_uses_human_sender_not_bot_recipient() -> None:
    """recipient.user_id is the bot; sender.user_id is the human — reply must go to human."""
    msg = {
        "recipient": {"user_id": 999888},  # bot
        "sender": {"user_id": 54321, "is_bot": False},
    }
    cid, uid = extract_max_reply_targets(msg)
    assert cid is None
    assert uid == 54321


def test_nested_recipient_chat_chat_id() -> None:
    msg = {
        "recipient": {"chat": {"chat_id": -42}},
        "sender": {"user_id": 1, "is_bot": True},
    }
    cid, uid = extract_max_reply_targets(msg)
    assert cid == -42
    assert uid is None


def test_callback_bot_message_uses_recipient_human_id() -> None:
    """Bot sent the message; recipient.user_id is the human peer (real callback payload)."""
    msg = {
        "recipient": {"chat_id": -100000000, "user_id": 54321},
        "sender": {"user_id": 12345, "is_bot": True, "name": "Bot"},
    }
    cid, uid = extract_max_reply_targets(msg)
    assert cid == -100000000
    assert uid is None


def test_bot_sender_no_recipient_returns_none() -> None:
    msg = {"sender": {"user_id": 1, "is_bot": True}}
    assert extract_max_reply_targets(msg) == (None, None)

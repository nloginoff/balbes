"""MAX webhook parsing helpers."""

from shared.max_webhook import extract_message_callback, parse_slash_command


def test_parse_slash_basic() -> None:
    assert parse_slash_command("/chats") == ("chats", "")
    assert parse_slash_command("/model arg") == ("model", "arg")
    assert parse_slash_command("/start@SomeBot") == ("start", "")


def test_parse_slash_not_command() -> None:
    assert parse_slash_command("hello /chats") is None
    assert parse_slash_command("") is None


def test_extract_message_callback() -> None:
    data = {
        "update_type": "message_callback",
        "callback": {
            "callback_id": "cb1",
            "payload": "MENU|chats",
            "user": {"user_id": 42},
        },
        "message": {"recipient": {"chat_id": -1}},
    }
    out = extract_message_callback(data)
    assert out is not None
    assert out["callback_id"] == "cb1"
    assert out["payload"] == "MENU|chats"
    assert out["user_id"] == 42


def test_extract_message_callback_wrong_type() -> None:
    assert extract_message_callback({"update_type": "message_created"}) is None

from __future__ import annotations

import auth_store


def test_user_device_and_message_persistence(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(auth_store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(auth_store, "DB_PATH", tmp_path / "app.db")

    auth_store.init_db()
    ok, _message, user = auth_store.create_user("alice", "secret123")
    assert ok
    assert user is not None

    ok, _message, authed = auth_store.authenticate_user("alice", "secret123")
    assert ok
    assert authed is not None
    assert authed["username"] == "alice"

    device_id = auth_store.ensure_device("device-token", int(authed["id"]))
    conversation_id = auth_store.get_or_create_conversation(int(authed["id"]), device_id)
    auth_store.append_message(conversation_id, {"role": "user", "content": "栈是什么"})
    auth_store.append_message(
        conversation_id,
        {
            "role": "assistant",
            "content": "栈是后进先出的线性表。",
            "code_blocks": ["```c\nint top = -1;\n```"],
            "code_check": "通过",
        },
    )

    messages = auth_store.load_messages(conversation_id)
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["code_blocks"]
    assert messages[1]["code_check"] == "通过"

    auth_store.clear_messages(conversation_id)
    assert auth_store.load_messages(conversation_id) == []

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "app.db"


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL UNIQUE,
                user_id INTEGER,
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                device_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                code_blocks_json TEXT NOT NULL DEFAULT '[]',
                show_code INTEGER NOT NULL DEFAULT 0,
                code_check TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS learning_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                device_id INTEGER,
                conversation_id INTEGER,
                tag TEXT NOT NULL,
                source_type TEXT NOT NULL,
                prompt TEXT NOT NULL,
                correct INTEGER NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
            """
        )
        ensure_message_column(conn, "rag_keywords_json", "TEXT NOT NULL DEFAULT '[]'")
        ensure_message_column(conn, "quiz_json", "TEXT NOT NULL DEFAULT '[]'")
        ensure_message_column(conn, "step_links_json", "TEXT NOT NULL DEFAULT '[]'")
        ensure_message_column(conn, "demo_request_json", "TEXT NOT NULL DEFAULT '{}'")


def ensure_message_column(conn: sqlite3.Connection, name: str, definition: str) -> None:
    columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(messages)").fetchall()
    }
    if name not in columns:
        conn.execute(f"ALTER TABLE messages ADD COLUMN {name} {definition}")


def _json_list(value: Any) -> list[Any]:
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 120_000)
    return digest.hex(), salt


def create_user(username: str, password: str) -> tuple[bool, str, dict[str, Any] | None]:
    username = username.strip()
    if len(username) < 3:
        return False, "用户名至少 3 个字符。", None
    if len(password) < 6:
        return False, "密码至少 6 个字符。", None

    password_hash, salt = hash_password(password)
    try:
        with connect() as conn:
            cursor = conn.execute(
                "INSERT INTO users (username, password_hash, salt, created_at) VALUES (?, ?, ?, ?)",
                (username, password_hash, salt, utc_now()),
            )
            user_id = int(cursor.lastrowid)
    except sqlite3.IntegrityError:
        return False, "用户名已存在。", None
    return True, "注册成功。", {"id": user_id, "username": username}


def authenticate_user(username: str, password: str) -> tuple[bool, str, dict[str, Any] | None]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()
    if row is None:
        return False, "用户名或密码错误。", None

    password_hash, _salt = hash_password(password, str(row["salt"]))
    if not secrets.compare_digest(password_hash, str(row["password_hash"])):
        return False, "用户名或密码错误。", None
    return True, "登录成功。", {"id": int(row["id"]), "username": str(row["username"])}


def verify_user(username: str, password: str) -> tuple[bool, int | str]:
    ok, message, user = authenticate_user(username, password)
    if ok and user:
        return True, int(user["id"])
    return False, message


def ensure_device(token: str, user_id: int | None = None) -> int:
    now = utc_now()
    with connect() as conn:
        row = conn.execute("SELECT id FROM devices WHERE token = ?", (token,)).fetchone()
        if row:
            device_id = int(row["id"])
            conn.execute(
                "UPDATE devices SET last_seen_at = ?, user_id = COALESCE(?, user_id) WHERE id = ?",
                (now, user_id, device_id),
            )
            return device_id

        cursor = conn.execute(
            "INSERT INTO devices (token, user_id, created_at, last_seen_at) VALUES (?, ?, ?, ?)",
            (token, user_id, now, now),
        )
        return int(cursor.lastrowid)


def bind_device_to_user(device_id: int, user_id: int) -> None:
    with connect() as conn:
        conn.execute("UPDATE devices SET user_id = ?, last_seen_at = ? WHERE id = ?", (user_id, utc_now(), device_id))


def get_or_create_conversation(user_id: int | None, device_id: int) -> int:
    with connect() as conn:
        if user_id is not None:
            row = conn.execute(
                "SELECT id FROM conversations WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM conversations WHERE user_id IS NULL AND device_id = ? ORDER BY updated_at DESC LIMIT 1",
                (device_id,),
            ).fetchone()
        if row:
            return int(row["id"])

        now = utc_now()
        cursor = conn.execute(
            "INSERT INTO conversations (user_id, device_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, device_id, "默认对话", now, now),
        )
        return int(cursor.lastrowid)


def load_messages(conversation_id: int, limit: int = 200) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT role, content, code_blocks_json, show_code, code_check, rag_keywords_json, quiz_json, step_links_json, demo_request_json
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (conversation_id, limit),
        ).fetchall()

    messages: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        code_blocks = _json_list(row["code_blocks_json"])
        message: dict[str, Any] = {
            "id": index,
            "role": str(row["role"]),
            "content": str(row["content"]),
        }
        if code_blocks:
            message["code_blocks"] = code_blocks
        if int(row["show_code"]):
            message["show_code"] = True
        if row["code_check"]:
            message["code_check"] = str(row["code_check"])
        rag_keywords = _json_list(row["rag_keywords_json"])
        if rag_keywords:
            message["rag_keywords"] = rag_keywords
        quiz = _json_list(row["quiz_json"])
        if quiz:
            message["quiz"] = quiz
        step_links = _json_list(row["step_links_json"])
        if step_links:
            message["step_links"] = step_links
        try:
            demo_request = json.loads(str(row["demo_request_json"]))
        except json.JSONDecodeError:
            demo_request = {}
        if isinstance(demo_request, dict) and demo_request:
            message["demo_request"] = demo_request
        messages.append(message)
    return messages


def append_message(conversation_id: int, message: dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO messages (conversation_id, role, content, code_blocks_json, show_code, code_check, rag_keywords_json, quiz_json, step_links_json, demo_request_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                str(message.get("role", "assistant")),
                str(message.get("content", "")),
                json.dumps(message.get("code_blocks") or [], ensure_ascii=False),
                1 if message.get("show_code") else 0,
                str(message.get("code_check") or ""),
                json.dumps(message.get("rag_keywords") or [], ensure_ascii=False),
                json.dumps(message.get("quiz") or [], ensure_ascii=False),
                json.dumps(message.get("step_links") or [], ensure_ascii=False),
                json.dumps(message.get("demo_request") or {}, ensure_ascii=False),
                utc_now(),
            ),
        )
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (utc_now(), conversation_id))


def clear_messages(conversation_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (utc_now(), conversation_id))


def add_learning_event(
    *,
    user_id: int | None,
    device_id: int | None,
    conversation_id: int | None,
    tag: str,
    source_type: str,
    prompt: str,
    correct: bool,
    note: str = "",
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO learning_events
                (user_id, device_id, conversation_id, tag, source_type, prompt, correct, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                device_id,
                conversation_id,
                tag,
                source_type,
                prompt,
                1 if correct else 0,
                note,
                utc_now(),
            ),
        )


def load_weak_points(user_id: int | None, device_id: int | None, limit: int = 8) -> list[dict[str, Any]]:
    where = "user_id = ?" if user_id is not None else "device_id = ?"
    key = user_id if user_id is not None else device_id
    if key is None:
        return []
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                tag,
                COUNT(*) AS attempts,
                SUM(CASE WHEN correct = 0 THEN 1 ELSE 0 END) AS misses,
                MAX(created_at) AS last_seen_at
            FROM learning_events
            WHERE {where}
            GROUP BY tag
            HAVING misses > 0
            ORDER BY misses DESC, last_seen_at DESC
            LIMIT ?
            """,
            (key, limit),
        ).fetchall()
    return [
        {
            "tag": str(row["tag"]),
            "attempts": int(row["attempts"]),
            "misses": int(row["misses"]),
            "last_seen_at": str(row["last_seen_at"]),
        }
        for row in rows
    ]

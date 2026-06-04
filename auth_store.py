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
            """
        )


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
            SELECT role, content, code_blocks_json, show_code, code_check
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (conversation_id, limit),
        ).fetchall()

    messages: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        try:
            code_blocks = json.loads(str(row["code_blocks_json"]))
        except json.JSONDecodeError:
            code_blocks = []
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
        messages.append(message)
    return messages


def append_message(conversation_id: int, message: dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO messages (conversation_id, role, content, code_blocks_json, show_code, code_check, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                str(message.get("role", "assistant")),
                str(message.get("content", "")),
                json.dumps(message.get("code_blocks") or [], ensure_ascii=False),
                1 if message.get("show_code") else 0,
                str(message.get("code_check") or ""),
                utc_now(),
            ),
        )
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (utc_now(), conversation_id))


def clear_messages(conversation_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (utc_now(), conversation_id))

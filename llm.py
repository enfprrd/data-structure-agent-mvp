from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests


BASE_DIR = Path(__file__).resolve().parent
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"


class DeepSeekError(RuntimeError):
    pass


def load_dotenv(path: Path | None = None) -> None:
    """Load simple KEY=VALUE pairs from .env without adding a dependency."""
    env_path = path or BASE_DIR / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get_api_key_from_streamlit_secrets() -> str | None:
    try:
        import streamlit as st

        value = st.secrets.get("DEEPSEEK_API_KEY")
    except Exception:
        return None

    return str(value) if value else None


class DeepSeekClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        timeout: int = 60,
    ) -> None:
        load_dotenv()
        self.api_key = (
            api_key
            or os.getenv("DEEPSEEK_API_KEY")
            or get_api_key_from_streamlit_secrets()
        )
        self.model = model
        self.timeout = timeout

        if not self.api_key:
            raise DeepSeekError(
                "未检测到 DEEPSEEK_API_KEY。请在项目根目录创建 .env 文件，"
                "写入 DEEPSEEK_API_KEY=你的 API Key，或配置系统环境变量。"
            )

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 2500,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                DEEPSEEK_API_URL,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise DeepSeekError(f"网络请求失败：{exc}") from exc

        if response.status_code >= 400:
            raise DeepSeekError(f"HTTP {response.status_code}: {response.text[:1000]}")

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise DeepSeekError(f"API 返回格式异常：{data}") from exc

        if not isinstance(content, str) or not content.strip():
            raise DeepSeekError(f"API 返回内容为空：{data}")

        return content

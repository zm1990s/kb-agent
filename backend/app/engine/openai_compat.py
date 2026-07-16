"""OpenAICompatEngine —— 调用 OpenAI 兼容 API（/v1/chat/completions）。

支持 Ollama、vLLM、OpenAI、Azure OpenAI 等任何实现了该接口的服务。
注意：不支持 files 参数（文档归类须用 ClaudeCliEngine）。
"""

import json
import logging
from collections.abc import AsyncGenerator
from pathlib import Path

import httpx

from app.engine.base import EngineError, EngineResult

logger = logging.getLogger(__name__)


class OpenAICompatEngineError(EngineError):
    """OpenAI 兼容引擎调用失败。"""


class OpenAICompatEngine:
    """调用 OpenAI 兼容 /v1/chat/completions 接口。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "none",
        model: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._extra_headers = extra_headers or {}

    async def complete(
        self,
        prompt: str,
        *,
        files: list[Path] | None = None,
        system: str | None = None,
    ) -> EngineResult:
        if files:
            raise NotImplementedError(
                "OpenAICompatEngine 不支持文件读取，文档处理请使用 ClaudeCliEngine"
            )

        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict = {"model": self._model, "messages": messages, "enable_thinking": False}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self._extra_headers,
        }

        try:
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                return EngineResult(text=text)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "OpenAI 兼容引擎 HTTP 错误 | status=%d | url=%s | body=%s",
                exc.response.status_code,
                exc.request.url,
                exc.response.text[:500],
            )
            raise OpenAICompatEngineError(
                f"API 返回 HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise OpenAICompatEngineError("请求超时（300s）") from exc
        except httpx.RequestError as exc:
            raise OpenAICompatEngineError(f"网络请求失败: {exc}") from exc
        except (KeyError, IndexError) as exc:
            raise OpenAICompatEngineError(f"响应格式解析失败: {exc}") from exc

    async def complete_streaming(
        self, prompt: str, *, system: str | None = None
    ) -> AsyncGenerator[str, None]:
        """流式调用：逐 token yield 文字增量。"""
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "enable_thinking": False,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self._extra_headers,
        }

        try:
            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: ") or line == "data: [DONE]":
                            continue
                        try:
                            chunk = json.loads(line[6:])
                            delta = chunk["choices"][0]["delta"].get("content") or ""
                            if delta:
                                yield delta
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except httpx.HTTPStatusError as exc:
            logger.error(
                "OpenAI 兼容引擎流式 HTTP 错误 | status=%d | body=%s",
                exc.response.status_code,
                exc.response.text[:500],
            )
            raise OpenAICompatEngineError(
                f"API 返回 HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise OpenAICompatEngineError("流式请求超时（300s）") from exc
        except httpx.RequestError as exc:
            raise OpenAICompatEngineError(f"网络请求失败: {exc}") from exc

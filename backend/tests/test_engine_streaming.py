"""ClaudeCliEngine.complete_streaming — mock subprocess 验证。

不真正调用 CLI；用 AsyncMock 模拟 NDJSON stdout 输出，
验证 ThinkingChunk / TextChunk 的正确产出。
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.engine.base import TextChunk, ThinkingChunk
from app.engine.claude_cli import ClaudeCliEngine


def _make_stream_event(delta_type: str, **kwargs) -> bytes:
    """构造一行 stream-json 格式的流式事件。"""
    obj = {
        "type": "stream_event",
        "event": {"delta": {"type": delta_type, **kwargs}},
    }
    return (json.dumps(obj) + "\n").encode()


def _make_result_line(is_error: bool = False) -> bytes:
    obj = {"type": "result", "is_error": is_error}
    return (json.dumps(obj) + "\n").encode()


def _make_mock_proc(lines: list[bytes]):
    """返回一个 mock asyncio 子进程，stdout.readline 按 lines 逐行返回。"""
    proc = MagicMock()
    proc.returncode = 0
    proc.kill = MagicMock()
    proc.wait = AsyncMock()

    # readline 用完后返回 b""（EOF）
    readline_side_effects = lines + [b""]
    proc.stdout = AsyncMock()
    proc.stdout.readline = AsyncMock(side_effect=readline_side_effects)
    proc.stderr = AsyncMock()
    proc.stderr.read = AsyncMock(return_value=b"")
    return proc


@pytest.mark.asyncio
async def test_complete_streaming_text_only():
    """纯文本 delta（无 thinking）只产出 TextChunk。"""
    lines = [
        _make_stream_event("text_delta", text="Hello"),
        _make_stream_event("text_delta", text=", world"),
        _make_result_line(),
    ]
    mock_proc = _make_mock_proc(lines)

    engine = ClaudeCliEngine()
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        chunks = []
        async for chunk in engine.complete_streaming("hi"):
            chunks.append(chunk)

    assert all(isinstance(c, TextChunk) for c in chunks)
    assert "".join(c.text for c in chunks) == "Hello, world"


@pytest.mark.asyncio
async def test_complete_streaming_thinking_and_text():
    """同时有 thinking_delta 和 text_delta 时正确分流。"""
    lines = [
        _make_stream_event("thinking_delta", thinking="let me think..."),
        _make_stream_event("thinking_delta", thinking=" more thoughts"),
        _make_stream_event("text_delta", text="Answer here"),
        _make_result_line(),
    ]
    mock_proc = _make_mock_proc(lines)

    engine = ClaudeCliEngine()
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        chunks = []
        async for chunk in engine.complete_streaming("question"):
            chunks.append(chunk)

    thinking_chunks = [c for c in chunks if isinstance(c, ThinkingChunk)]
    text_chunks = [c for c in chunks if isinstance(c, TextChunk)]

    assert "".join(c.text for c in thinking_chunks) == "let me think... more thoughts"
    assert "".join(c.text for c in text_chunks) == "Answer here"


@pytest.mark.asyncio
async def test_complete_streaming_ignores_signature_delta():
    """signature_delta 事件静默忽略，不产出任何 chunk。"""
    lines = [
        _make_stream_event("signature_delta", signature="abc123"),
        _make_stream_event("text_delta", text="ok"),
        _make_result_line(),
    ]
    mock_proc = _make_mock_proc(lines)

    engine = ClaudeCliEngine()
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        chunks = []
        async for chunk in engine.complete_streaming("q"):
            chunks.append(chunk)

    assert len(chunks) == 1
    assert isinstance(chunks[0], TextChunk)


@pytest.mark.asyncio
async def test_complete_streaming_skips_non_stream_events():
    """非 stream_event 行（hook、system 等）静默跳过。"""
    other_lines = [
        (json.dumps({"type": "system", "subtype": "init"}) + "\n").encode(),
        (json.dumps({"type": "assistant", "message": {}}) + "\n").encode(),
        _make_stream_event("text_delta", text="hi"),
        _make_result_line(),
    ]
    mock_proc = _make_mock_proc(other_lines)

    engine = ClaudeCliEngine()
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        chunks = []
        async for chunk in engine.complete_streaming("q"):
            chunks.append(chunk)

    assert len(chunks) == 1 and chunks[0].text == "hi"


@pytest.mark.asyncio
async def test_complete_not_affected_by_streaming():
    """complete() 非流式接口不受 complete_streaming 改动影响。"""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.kill = MagicMock()
    mock_proc.wait = AsyncMock()
    mock_proc.stdout = AsyncMock()
    mock_proc.stdout.read = AsyncMock(side_effect=[b"the answer", b""])
    mock_proc.stderr = AsyncMock()
    mock_proc.stderr.read = AsyncMock(return_value=b"")

    engine = ClaudeCliEngine()
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await engine.complete("test prompt")

    assert "the answer" in result.text


@pytest.mark.asyncio
async def test_complete_streaming_argv_includes_stream_flags():
    """verify streaming argv contains the required flags."""
    engine = ClaudeCliEngine()
    argv = engine._build_argv("hi", None)
    # base argv does NOT have stream flags
    assert "--output-format" not in argv
    assert "--include-partial-messages" not in argv

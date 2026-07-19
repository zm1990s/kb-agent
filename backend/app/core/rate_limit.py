"""进程内 IP 级速率限制（滑动窗口，无外部依赖）。

用于认证端点防暴力破解：login / register / forgot-password / verify-email-pin。
注意：多进程部署时各进程独立计数；生产环境如需跨进程统一限制，应换用 Redis 实现。
"""

import asyncio
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

_windows: dict[str, deque[float]] = defaultdict(deque)
_lock = asyncio.Lock()


async def check_rate(request: Request, *, limit: int, window_sec: int) -> None:
    """检查当前 IP 在 window_sec 秒内的请求次数，超过 limit 则返回 429。"""
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    async with _lock:
        dq = _windows[ip]
        while dq and now - dq[0] > window_sec:
            dq.popleft()
        if len(dq) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="请求过于频繁，请稍后重试",
            )
        dq.append(now)

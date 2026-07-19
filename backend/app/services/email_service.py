"""SMTP 邮件发送服务。SMTP_HOST 未配置时静默跳过，不影响主流程。"""

import html
import logging
import re
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings_service import (
    get_smtp_from,
    get_smtp_host,
    get_smtp_password,
    get_smtp_port,
    get_smtp_tls,
    get_smtp_user,
)

logger = logging.getLogger(__name__)


def _smtp_tls_kwargs(port: int, smtp_tls: bool) -> dict:
    """返回 aiosmtplib.send() 所需的 TLS 参数。
    端口 465 → 隐式 TLS（use_tls=True），其余端口 → STARTTLS（start_tls=smtp_tls）。
    """
    if port == 465:
        return {"use_tls": True}
    return {"start_tls": smtp_tls}

_STYLE = (
    "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
    "font-size:14px;line-height:1.6;color:#1f2937"
)


def _md_to_html(md: str) -> str:
    """将摘要 Markdown 转为内联样式 HTML（仅处理标题/加粗/列表/换行）。"""
    lines = md.splitlines()
    out: list[str] = []
    in_ul = False

    def close_ul() -> None:
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    def inline(text: str) -> str:
        text = html.escape(text)
        # **bold**
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        # *italic*
        text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
        return text

    for line in lines:
        # H3
        if line.startswith("### "):
            close_ul()
            out.append(
                f"<h3 style='margin:16px 0 4px;font-size:15px;color:#111827'>"
                f"{inline(line[4:])}</h3>"
            )
        # H2
        elif line.startswith("## "):
            close_ul()
            out.append(
                f"<h2 style='margin:20px 0 6px;font-size:16px;color:#111827'>"
                f"{inline(line[3:])}</h2>"
            )
        # H1
        elif line.startswith("# "):
            close_ul()
            out.append(
                f"<h1 style='margin:24px 0 8px;font-size:18px;color:#111827'>"
                f"{inline(line[2:])}</h1>"
            )
        # 水平线
        elif re.match(r"^-{3,}$", line.strip()):
            close_ul()
            out.append("<hr style='border:none;border-top:1px solid #e5e7eb;margin:16px 0'>")
        # 列表项
        elif re.match(r"^[-*]\s+", line):
            if not in_ul:
                out.append(
                    "<ul style='margin:8px 0;padding-left:20px;list-style:disc'>"
                )
                in_ul = True
            out.append(f"<li style='margin:3px 0'>{inline(line[2:].strip())}</li>")
        # 空行
        elif not line.strip():
            close_ul()
            out.append("<br>")
        # 普通段落
        else:
            close_ul()
            out.append(f"<p style='margin:6px 0'>{inline(line)}</p>")

    close_ul()
    return "\n".join(out)


def _build_html(reports: list[dict]) -> str:
    parts = [
        f"<html><body style='max-width:640px;margin:0 auto;padding:24px;{_STYLE}'>",
        "<h2 style='color:#1d4ed8;margin-bottom:4px'>知识库新动态</h2>",
        "<hr style='border:none;border-top:1px solid #e5e7eb;margin-bottom:20px'>",
    ]
    for r in reports:
        period = f"{r['period_start'][:10]} ~ {r['period_end'][:10]}"
        ws_name = html.escape(r["workspace_name"])
        parts.append(
            f"<h3 style='margin-top:24px;margin-bottom:6px;font-size:16px'>"
            f"{ws_name}"
            f"<span style='font-size:12px;color:#6b7280;margin-left:8px;font-weight:normal'>"
            f"{period}</span></h3>"
        )
        if r.get("summary"):
            summary_html = _md_to_html(r["summary"])
            parts.append(
                f"<div style='background:#f8fafc;border-left:3px solid #3b82f6;"
                f"padding:12px 16px;margin:8px 0;border-radius:0 4px 4px 0'>"
                f"{summary_html}</div>"
            )
        if r.get("documents"):
            parts.append(
                "<div style='margin-top:12px'>"
                "<p style='font-size:13px;color:#6b7280;margin-bottom:6px'>本期新增文档：</p>"
                "<ul style='margin:0;padding-left:20px;list-style:disc'>"
            )
            for doc in r["documents"]:
                title = html.escape(doc.get("title", ""))
                cat = html.escape(doc.get("category", ""))
                cat_span = (
                    f"&nbsp;<span style='color:#9ca3af;font-size:12px'>{cat}</span>"
                    if cat else ""
                )
                parts.append(
                    f"<li style='margin:4px 0'>{title}{cat_span}</li>"
                )
            parts.append("</ul>")
            parts.append(
                "<p style='font-size:12px;color:#6b7280;margin-top:8px'>"
                "如需下载原文，请登录平台「新动态」页面查看。</p>"
                "</div>"
            )

    parts.append(
        "<p style='font-size:12px;color:#9ca3af;"
        "margin-top:32px;border-top:1px solid #e5e7eb;padding-top:12px'>"
        "此邮件由 KB-Agent 自动发送。如需退订，请前往「新动态」页面修改订阅设置。"
        "</p></body></html>"
    )
    return "".join(parts)


def _build_plaintext(reports: list[dict]) -> str:
    lines = ["知识库新动态\n"]
    for r in reports:
        lines.append(f"== {r['workspace_name']} ==")
        if r.get("summary"):
            lines.append(r["summary"])
        for doc in r.get("documents", []):
            lines.append(f"  - {doc['title']} ({doc.get('category', '')})")
        lines.append("  如需下载原文，请登录平台「新动态」页面查看。")
        lines.append("")
    lines.append("此邮件由 KB-Agent 自动发送。如需退订，请前往「新动态」页面修改订阅设置。")
    return "\n".join(lines)


async def send_verification_pin(session: AsyncSession, to_email: str, pin: str) -> None:
    """发送邮箱验证 PIN 邮件（6 位数字，10 分钟有效）。SMTP_HOST 未配置时记录警告并跳过。"""
    smtp_host = await get_smtp_host(session)
    if not smtp_host:
        logger.warning("email_service: SMTP_HOST 未配置，跳过发送验证 PIN to=%s", to_email)
        return

    smtp_port = await get_smtp_port(session)
    smtp_user = await get_smtp_user(session)
    smtp_password = await get_smtp_password(session)
    smtp_from = await get_smtp_from(session)
    smtp_tls = await get_smtp_tls(session)

    plain = (
        f"您的邮箱验证码为：{pin}\n\n"
        "验证码 10 分钟内有效，请勿转发给他人。\n\n"
        "如非本人操作，请忽略此邮件。"
    )
    html_body = (
        f"<html><body style='max-width:480px;margin:0 auto;padding:24px;{_STYLE}'>"
        "<h2 style='color:#1d4ed8;margin-bottom:4px'>邮箱验证</h2>"
        "<hr style='border:none;border-top:1px solid #e5e7eb;margin-bottom:20px'>"
        "<p>感谢注册！请使用以下验证码完成邮箱验证（<strong>10 分钟内有效</strong>）：</p>"
        "<p style='font-size:36px;font-weight:700;letter-spacing:0.3em;"
        "color:#1d4ed8;margin:24px 0;text-align:center'>"
        f"{html.escape(pin)}</p>"
        "<p style='font-size:12px;color:#6b7280'>请勿将验证码转发给任何人。</p>"
        "<p style='font-size:12px;color:#9ca3af;margin-top:32px;border-top:1px solid #e5e7eb;"
        "padding-top:12px'>如非本人操作，请忽略此邮件，您的账号仍然安全。</p>"
        "</body></html>"
    )

    try:
        import aiosmtplib

        msg = MIMEMultipart("alternative")
        msg["Subject"] = Header("您的邮箱验证码", "utf-8").encode()
        raw_from = smtp_from or smtp_user or ""
        name, addr = parseaddr(raw_from)
        msg["From"] = formataddr((str(Header(name, "utf-8")) if name else "", addr))
        msg["To"] = to_email
        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_user or None,
            password=smtp_password or None,
            **_smtp_tls_kwargs(smtp_port, smtp_tls),
        )
        logger.info("email_service: 已发送验证 PIN 邮件 to=%s", to_email)
    except Exception:
        logger.exception("email_service: 验证 PIN 邮件发送失败 to=%s", to_email)


async def send_whatsnew_digest(session: AsyncSession, to_email: str, reports: list[dict]) -> None:
    """发送新动态摘要邮件。SMTP_HOST 未配置时静默返回。"""
    smtp_host = await get_smtp_host(session)
    if not smtp_host:
        logger.warning("email_service: SMTP_HOST 未配置，跳过发送 to=%s", to_email)
        return
    if not reports:
        logger.info("email_service: 无报告可发，跳过 to=%s", to_email)
        return

    smtp_port = await get_smtp_port(session)
    smtp_user = await get_smtp_user(session)
    smtp_password = await get_smtp_password(session)
    smtp_from = await get_smtp_from(session)
    smtp_tls = await get_smtp_tls(session)

    try:
        import aiosmtplib

        msg = MIMEMultipart("alternative")
        msg["Subject"] = Header("知识库新动态", "utf-8").encode()
        # RFC 2047-encode the display name so non-ASCII chars pass QQ's validator
        raw_from = smtp_from or smtp_user or ""
        name, addr = parseaddr(raw_from)
        msg["From"] = formataddr((str(Header(name, "utf-8")) if name else "", addr))
        msg["To"] = to_email
        msg.attach(MIMEText(_build_plaintext(reports), "plain", "utf-8"))
        msg.attach(MIMEText(_build_html(reports), "html", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_user or None,
            password=smtp_password or None,
            **_smtp_tls_kwargs(smtp_port, smtp_tls),
        )
        logger.info("email_service: 已发送新动态邮件 to=%s", to_email)
    except Exception:
        logger.exception("email_service: 发送失败 to=%s", to_email)


async def send_reset_code_email(session: AsyncSession, to_email: str, code: str) -> None:
    """发送密码重置验证码邮件。SMTP_HOST 未配置时记录警告并跳过。"""
    smtp_host = await get_smtp_host(session)
    if not smtp_host:
        logger.warning("email_service: SMTP_HOST 未配置，跳过发送重置码邮件 to=%s", to_email)
        return

    smtp_port = await get_smtp_port(session)
    smtp_user = await get_smtp_user(session)
    smtp_password = await get_smtp_password(session)
    smtp_from = await get_smtp_from(session)
    smtp_tls = await get_smtp_tls(session)

    plain = (
        f"您的密码重置验证码为：{code}\n\n"
        "验证码 10 分钟内有效，请勿转发给他人。\n\n"
        "如非本人操作，请忽略此邮件，您的账号仍然安全。"
    )
    html_body = (
        f"<html><body style='max-width:480px;margin:0 auto;padding:24px;{_STYLE}'>"
        "<h2 style='color:#1d4ed8;margin-bottom:4px'>密码重置验证码</h2>"
        "<hr style='border:none;border-top:1px solid #e5e7eb;margin-bottom:20px'>"
        "<p>请使用以下验证码重置您的密码（<strong>10 分钟内有效</strong>）：</p>"
        "<p style='font-size:32px;font-weight:700;letter-spacing:0.2em;"
        "color:#1d4ed8;margin:24px 0;text-align:center'>"
        f"{html.escape(code)}</p>"
        "<p style='font-size:12px;color:#6b7280'>请勿将验证码转发给任何人。</p>"
        "<p style='font-size:12px;color:#9ca3af;margin-top:32px;border-top:1px solid #e5e7eb;"
        "padding-top:12px'>如非本人操作，请忽略此邮件，您的账号仍然安全。</p>"
        "</body></html>"
    )

    try:
        import aiosmtplib

        msg = MIMEMultipart("alternative")
        msg["Subject"] = Header("您的密码重置验证码", "utf-8").encode()
        raw_from = smtp_from or smtp_user or ""
        name, addr = parseaddr(raw_from)
        msg["From"] = formataddr((str(Header(name, "utf-8")) if name else "", addr))
        msg["To"] = to_email
        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_user or None,
            password=smtp_password or None,
            **_smtp_tls_kwargs(smtp_port, smtp_tls),
        )
        logger.info("email_service: 已发送重置码邮件 to=%s", to_email)
    except Exception:
        logger.exception("email_service: 重置码邮件发送失败 to=%s", to_email)

import asyncio
import email
import email.header
import email.message
import email.utils
import imaplib
import os
import re
from dataclasses import dataclass
from functools import partial

from accounts import get_account


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    parts = email.header.decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _get_text_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        text_parts = []
        html_parts = []
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    text_parts.append(payload.decode(charset, errors="replace"))
            elif ct == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    html_parts.append(payload.decode(charset, errors="replace"))
        if text_parts:
            return "\n".join(text_parts)
        if html_parts:
            return _strip_html("\n".join(html_parts))
        return ""
    else:
        payload = msg.get_payload(decode=True)
        if not payload:
            return ""
        charset = msg.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace")
        if msg.get_content_type() == "text/html":
            return _strip_html(text)
        return text


def _get_html_body(msg: email.message.Message) -> str:
    """Return the raw text/html body of a message, or '' if none present."""
    if msg.is_multipart():
        html_parts = []
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    html_parts.append(payload.decode(charset, errors="replace"))
        return "\n".join(html_parts)
    if msg.get_content_type() == "text/html":
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


def _strip_html(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _quote_folder(folder: str) -> str:
    if " " in folder and not folder.startswith('"'):
        return f'"{folder}"'
    return folder


def _connect(account: str = "a") -> imaplib.IMAP4_SSL:
    acc = get_account(account)
    ctx = acc.ssl_context()
    if ctx is not None:
        # Passwordless client-certificate login (SASL EXTERNAL).
        conn = imaplib.IMAP4_SSL(acc.imap_host, acc.imap_port, ssl_context=ctx)
        conn.authenticate("EXTERNAL", lambda _: b"")
    else:
        conn = imaplib.IMAP4_SSL(acc.imap_host, acc.imap_port)
        conn.login(acc.email_user, acc.email_password)
    return conn


async def _run(func, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))


async def list_folders(account: str = "a") -> list[str]:
    def _do():
        conn = _connect(account)
        try:
            status, data = conn.list()
            folders = []
            for item in data:
                if isinstance(item, bytes):
                    try:
                        name = item.split(b'" ')[-1].strip(b'"').decode()
                    except Exception:
                        match = re.search(rb'"([^"]*)"$|(\S+)$', item)
                        if match:
                            name = (match.group(1) or match.group(2)).decode("utf-8", errors="replace")
                        else:
                            continue
                    folders.append(name)
            return folders
        finally:
            conn.logout()
    return await _run(_do)


async def list_emails(folder: str = "INBOX", page: int = 1, page_size: int = 20, account: str = "a") -> dict:
    def _do():
        conn = _connect(account)
        try:
            conn.select(_quote_folder(folder), readonly=True)
            status, data = conn.uid("search", None, "ALL")
            if status != "OK":
                return {"emails": [], "total": 0, "page": page}
            uids = data[0].split() if data[0] else []
            uids.reverse()  # newest first
            total = len(uids)
            start = (page - 1) * page_size
            end = start + page_size
            page_uids = uids[start:end]
            if not page_uids:
                return {"emails": [], "total": total, "page": page, "page_size": page_size}
            uid_str = b",".join(page_uids)
            status, data = conn.uid("fetch", uid_str, "(ENVELOPE FLAGS)")
            emails = []
            for item in data:
                if not isinstance(item, tuple):
                    continue
                raw = item[1]
                uid_match = re.search(rb"UID (\d+)", item[0] if isinstance(item[0], bytes) else raw)
                uid = uid_match.group(1).decode() if uid_match else "?"
                env_match = re.search(rb"ENVELOPE \((.+)\)", raw, re.DOTALL) if isinstance(raw, bytes) else None
                # Parse basic info from raw response
                subject = ""
                from_addr = ""
                date = ""
                flags = ""
                # Try to get flags
                flags_match = re.search(rb"FLAGS \(([^)]*)\)", item[0] if isinstance(item[0], bytes) else b"")
                if flags_match:
                    flags = flags_match.group(1).decode(errors="replace")
                # Fetch individual envelope for reliability
                st2, d2 = conn.uid("fetch", page_uids[len(emails)] if len(emails) < len(page_uids) else page_uids[-1], "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
                if st2 == "OK" and d2 and isinstance(d2[0], tuple):
                    hdr = email.message_from_bytes(d2[0][1])
                    subject = _decode_header(hdr.get("Subject", ""))
                    from_addr = _decode_header(hdr.get("From", ""))
                    date = hdr.get("Date", "")
                emails.append({
                    "uid": uid,
                    "subject": subject,
                    "from": from_addr,
                    "date": date,
                    "flags": flags,
                })
            return {"emails": emails, "total": total, "page": page, "page_size": page_size}
        finally:
            conn.logout()
    return await _run(_do)


async def read_email(folder: str, uid: int, account: str = "a") -> dict:
    def _do():
        conn = _connect(account)
        try:
            conn.select(_quote_folder(folder))
            status, data = conn.uid("fetch", str(uid), "(RFC822)")
            if status != "OK" or not data or not isinstance(data[0], tuple):
                return {"error": "Email not found"}
            raw = data[0][1]
            msg = email.message_from_bytes(raw)
            body = _get_text_body(msg)
            if len(body) > 50000:
                body = body[:50000] + "\n\n... [truncated, original length: {}]".format(len(body))
            body_html = _get_html_body(msg)
            if len(body_html) > 200000:
                body_html = body_html[:200000] + "\n<!-- ... [truncated, original length: {}] -->".format(len(body_html))
            attachments = []
            for part in msg.walk():
                fn = part.get_filename()
                if fn:
                    attachments.append(_decode_header(fn))
            return {
                "uid": uid,
                "subject": _decode_header(msg.get("Subject")),
                "from": _decode_header(msg.get("From")),
                "to": _decode_header(msg.get("To")),
                "cc": _decode_header(msg.get("Cc")),
                "date": msg.get("Date", ""),
                "message_id": msg.get("Message-ID", ""),
                "in_reply_to": msg.get("In-Reply-To", ""),
                "body": body,
                "body_html": body_html,
                "attachments": attachments,
            }
        finally:
            conn.logout()
    return await _run(_do)


async def search_emails(folder: str = "INBOX", query: str = "", criteria: str = "ALL", account: str = "a") -> list[dict]:
    def _do():
        conn = _connect(account)
        try:
            conn.select(_quote_folder(folder), readonly=True)
            if query and criteria.upper() == "ALL":
                search_criteria = f'(OR (SUBJECT "{query}") (FROM "{query}"))'
            elif query:
                search_criteria = f'({criteria} "{query}")'
            else:
                search_criteria = "(ALL)"
            status, data = conn.uid("search", None, search_criteria)
            if status != "OK" or not data[0]:
                return []
            uids = data[0].split()
            uids.reverse()
            uids = uids[:50]  # limit results
            results = []
            for u in uids:
                st, d = conn.uid("fetch", u, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
                if st == "OK" and d and isinstance(d[0], tuple):
                    hdr = email.message_from_bytes(d[0][1])
                    results.append({
                        "uid": u.decode(),
                        "subject": _decode_header(hdr.get("Subject", "")),
                        "from": _decode_header(hdr.get("From", "")),
                        "date": hdr.get("Date", ""),
                    })
            return results
        finally:
            conn.logout()
    return await _run(_do)


async def move_email(folder: str, uid: int, destination: str, account: str = "a") -> str:
    def _do():
        conn = _connect(account)
        try:
            conn.select(_quote_folder(folder))
            status, _ = conn.uid("copy", str(uid), destination)
            if status != "OK":
                return f"Failed to copy to {destination}"
            conn.uid("store", str(uid), "+FLAGS", "(\\Deleted)")
            conn.expunge()
            return f"Moved UID {uid} from {folder} to {destination}"
        finally:
            conn.logout()
    return await _run(_do)


async def delete_email(folder: str, uid: int, account: str = "a") -> str:
    return await move_email(folder, uid, "Trash", account)


async def create_folder(folder_name: str, account: str = "a") -> str:
    def _do():
        conn = _connect(account)
        try:
            status, _ = conn.create(folder_name)
            return f"Created folder: {folder_name}" if status == "OK" else f"Failed to create: {folder_name}"
        finally:
            conn.logout()
    return await _run(_do)


async def rename_folder(old_name: str, new_name: str, account: str = "a") -> str:
    def _do():
        conn = _connect(account)
        try:
            status, _ = conn.rename(old_name, new_name)
            return f"Renamed {old_name} -> {new_name}" if status == "OK" else f"Failed to rename"
        finally:
            conn.logout()
    return await _run(_do)


async def delete_folder(folder_name: str, account: str = "a") -> str:
    if folder_name.upper() == "INBOX":
        return "Refusing to delete INBOX"
    def _do():
        conn = _connect(account)
        try:
            status, _ = conn.delete(folder_name)
            return f"Deleted folder: {folder_name}" if status == "OK" else f"Failed to delete: {folder_name}"
        finally:
            conn.logout()
    return await _run(_do)


async def get_email_for_reply(folder: str, uid: int, account: str = "a") -> dict:
    """Get email data needed for constructing a reply."""
    return await read_email(folder, uid, account)


async def set_flags(folder: str, uid: int, flags: str, action: str = "add", account: str = "a") -> str:
    """Add or remove IMAP flags. action: 'add' or 'remove'."""
    def _do():
        conn = _connect(account)
        try:
            conn.select(_quote_folder(folder))
            op = "+FLAGS" if action == "add" else "-FLAGS"
            status, _ = conn.uid("store", str(uid), op, f"({flags})")
            if status != "OK":
                return f"Failed to {action} flags {flags} on UID {uid}"
            return f"Flags {flags} {'added to' if action == 'add' else 'removed from'} UID {uid}"
        finally:
            conn.logout()
    return await _run(_do)


async def get_unread_count(folder: str = "INBOX", account: str = "a") -> dict:
    def _do():
        conn = _connect(account)
        try:
            conn.select(_quote_folder(folder), readonly=True)
            status, data = conn.uid("search", None, "UNSEEN")
            if status != "OK" or not data[0]:
                return {"folder": folder, "unread": 0}
            uids = data[0].split()
            return {"folder": folder, "unread": len(uids)}
        finally:
            conn.logout()
    return await _run(_do)


async def batch_move_emails(folder: str, uids: list[int], destination: str, account: str = "a") -> str:
    def _do():
        conn = _connect(account)
        try:
            conn.select(_quote_folder(folder))
            moved = 0
            for uid in uids:
                status, _ = conn.uid("copy", str(uid), destination)
                if status == "OK":
                    conn.uid("store", str(uid), "+FLAGS", "(\\Deleted)")
                    moved += 1
            conn.expunge()
            return f"Moved {moved}/{len(uids)} emails from {folder} to {destination}"
        finally:
            conn.logout()
    return await _run(_do)


async def batch_delete_emails(folder: str, uids: list[int], account: str = "a") -> str:
    return await batch_move_emails(folder, uids, "Trash", account)


async def download_attachment(folder: str, uid: int, filename: str, save_dir: str, account: str = "a") -> str:
    """Extract an attachment from an email and save it to disk."""
    def _do():
        conn = _connect(account)
        try:
            conn.select(_quote_folder(folder), readonly=True)
            status, data = conn.uid("fetch", str(uid), "(RFC822)")
            if status != "OK" or not data or not isinstance(data[0], tuple):
                return "Email not found"
            msg = email.message_from_bytes(data[0][1])
            for part in msg.walk():
                fn = part.get_filename()
                if fn and _decode_header(fn) == filename:
                    payload = part.get_payload(decode=True)
                    if payload is None:
                        return f"Attachment '{filename}' has no content"
                    os.makedirs(save_dir, exist_ok=True)
                    dest = os.path.join(save_dir, filename)
                    with open(dest, "wb") as f:
                        f.write(payload)
                    return f"Saved attachment to {dest} ({len(payload)} bytes)"
            return f"Attachment '{filename}' not found in email UID {uid}"
        finally:
            conn.logout()
    return await _run(_do)


async def get_email_for_forward(folder: str, uid: int, account: str = "a") -> dict:
    """Get full email data including raw attachment parts for forwarding."""
    def _do():
        conn = _connect(account)
        try:
            conn.select(_quote_folder(folder), readonly=True)
            status, data = conn.uid("fetch", str(uid), "(RFC822)")
            if status != "OK" or not data or not isinstance(data[0], tuple):
                return {"error": "Email not found"}
            raw = data[0][1]
            msg = email.message_from_bytes(raw)
            body = _get_text_body(msg)
            body_html = _get_html_body(msg)
            attachments_data = []
            for part in msg.walk():
                fn = part.get_filename()
                if fn:
                    payload = part.get_payload(decode=True)
                    if payload:
                        attachments_data.append({
                            "filename": _decode_header(fn),
                            "content_type": part.get_content_type(),
                            "data": payload,
                        })
            return {
                "uid": uid,
                "subject": _decode_header(msg.get("Subject")),
                "from": _decode_header(msg.get("From")),
                "to": _decode_header(msg.get("To")),
                "cc": _decode_header(msg.get("Cc")),
                "date": msg.get("Date", ""),
                "message_id": msg.get("Message-ID", ""),
                "body": body,
                "body_html": body_html,
                "attachments_data": attachments_data,
            }
        finally:
            conn.logout()
    return await _run(_do)

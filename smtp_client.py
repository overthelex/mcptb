import os
import imaplib
import mimetypes
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formataddr, formatdate, make_msgid

import aiosmtplib

from accounts import get_account


def _save_to_sent(msg, account: str = "a"):
    """Save sent message to IMAP Sent folder directly."""
    import time
    acc = get_account(account)
    try:
        conn = imaplib.IMAP4_SSL(acc.imap_host, acc.imap_port)
        conn.login(acc.email_user, acc.email_password)
        # Try common Sent folder names
        sent_folder = None
        for name in ["Sent", "Sent Messages", "INBOX.Sent", "Sent Items"]:
            status, _ = conn.select(f'"{name}"')
            if status == "OK":
                sent_folder = name
                break
        if not sent_folder:
            # Fallback: list folders and find one with \Sent flag
            status, folders = conn.list()
            if status == "OK":
                for f in folders:
                    decoded = f.decode() if isinstance(f, bytes) else f
                    if "\\Sent" in decoded:
                        # Extract folder name from IMAP LIST response
                        parts = decoded.split(' "/" ')
                        if len(parts) == 2:
                            sent_folder = parts[1].strip().strip('"')
                            break
        if sent_folder:
            conn.select(f'"{sent_folder}"')
            conn.append(
                f'"{sent_folder}"',
                "\\Seen",
                imaplib.Time2Internaldate(time.time()),
                msg.as_bytes(),
            )
        conn.logout()
    except Exception as e:
        # Fallback: save to queue file
        try:
            queue_dir = "/tmp/sent_queue"
            os.makedirs(queue_dir, exist_ok=True)
            filename = f"{queue_dir}/{int(time.time() * 1000)}.eml"
            with open(filename, "wb") as f:
                f.write(msg.as_bytes())
        except Exception:
            pass
        with open("/tmp/sent_queue_error.log", "a") as f:
            f.write(f"{e}\n")


def _attach_files(msg: MIMEMultipart, file_paths: list[str]) -> list[str]:
    """Attach files to a MIME message. Returns list of attached filenames."""
    attached = []
    for path in file_paths:
        path = path.strip()
        if not path:
            continue
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Attachment not found: {path}")
        filename = os.path.basename(path)
        ctype, _ = mimetypes.guess_type(path)
        if ctype is None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        with open(path, "rb") as f:
            part = MIMEBase(maintype, subtype)
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)
        attached.append(filename)
    return attached


async def send_email(
    to: str | list[str],
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    attachments: list[str] | None = None,
    account: str = "a",
) -> str:
    acc = get_account(account)
    msg = MIMEMultipart()
    msg["From"] = formataddr((acc.email_fullname, acc.email_user))
    if isinstance(to, list):
        msg["To"] = ", ".join(to)
    else:
        msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=acc.email_user.split("@")[-1])
    if cc:
        msg["Cc"] = cc
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if attachments:
        _attach_files(msg, attachments)

    all_recipients = []
    to_list = to if isinstance(to, list) else [t.strip() for t in to.split(",")]
    all_recipients.extend(to_list)
    if cc:
        all_recipients.extend([c.strip() for c in cc.split(",")])
    if bcc:
        all_recipients.extend([b.strip() for b in bcc.split(",")])

    await aiosmtplib.send(
        msg,
        hostname=acc.smtp_host,
        port=acc.smtp_port,
        username=acc.email_user,
        password=acc.email_password,
        use_tls=True,
        recipients=all_recipients,
    )
    _save_to_sent(msg, account)
    return f"Email sent to {msg['To']} (from {acc.email_user})"


async def reply_to_email(
    original: dict,
    body: str,
    reply_all: bool = False,
    attachments: list[str] | None = None,
    account: str = "a",
) -> str:
    acc = get_account(account)
    subject = original.get("subject", "")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    msg = MIMEMultipart()
    msg["From"] = formataddr((acc.email_fullname, acc.email_user))

    # Reply to the sender
    reply_to = original.get("from", "")
    msg["To"] = reply_to
    recipients = [reply_to]

    if reply_all:
        cc_parts = []
        for field in ["to", "cc"]:
            val = original.get(field, "")
            if val:
                addrs = [a.strip() for a in val.split(",")]
                for a in addrs:
                    if acc.email_user.lower() not in a.lower() and a not in cc_parts:
                        cc_parts.append(a)
        if cc_parts:
            msg["Cc"] = ", ".join(cc_parts)
            recipients.extend(cc_parts)

    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=acc.email_user.split("@")[-1])

    if original.get("message_id"):
        msg["In-Reply-To"] = original["message_id"]
        msg["References"] = original.get("in_reply_to", "") + " " + original["message_id"]

    msg.attach(MIMEText(body, "plain", "utf-8"))
    if attachments:
        _attach_files(msg, attachments)

    await aiosmtplib.send(
        msg,
        hostname=acc.smtp_host,
        port=acc.smtp_port,
        username=acc.email_user,
        password=acc.email_password,
        use_tls=True,
        recipients=recipients,
    )
    _save_to_sent(msg, account)
    return f"Reply sent to {msg['To']} (from {acc.email_user})"


async def forward_email(
    original: dict,
    to: str,
    body: str = "",
    attachments: list[str] | None = None,
    account: str = "a",
) -> str:
    acc = get_account(account)
    subject = original.get("subject", "")
    if not subject.lower().startswith("fwd:"):
        subject = f"Fwd: {subject}"

    msg = MIMEMultipart()
    msg["From"] = formataddr((acc.email_fullname, acc.email_user))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=acc.email_user.split("@")[-1])

    if original.get("message_id"):
        msg["References"] = original["message_id"]

    # Build forwarded body
    fwd_header = (
        f"\n\n---------- Forwarded message ----------\n"
        f"From: {original.get('from', '')}\n"
        f"Date: {original.get('date', '')}\n"
        f"Subject: {original.get('subject', '')}\n"
        f"To: {original.get('to', '')}\n\n"
    )
    full_body = body + fwd_header + original.get("body", "")
    msg.attach(MIMEText(full_body, "plain", "utf-8"))

    # Attach original email's attachments
    for att in original.get("attachments_data", []):
        maintype, subtype = att["content_type"].split("/", 1)
        part = MIMEBase(maintype, subtype)
        part.set_payload(att["data"])
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=att["filename"])
        msg.attach(part)

    # Attach extra files from disk
    if attachments:
        _attach_files(msg, attachments)

    recipients = [r.strip() for r in to.split(",")]

    await aiosmtplib.send(
        msg,
        hostname=acc.smtp_host,
        port=acc.smtp_port,
        username=acc.email_user,
        password=acc.email_password,
        use_tls=True,
        recipients=recipients,
    )
    _save_to_sent(msg, account)
    return f"Forwarded to {to} (from {acc.email_user})"

import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr, formatdate, make_msgid

import aiosmtplib

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
EMAIL_USER = os.environ.get("EMAIL_USER", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_FULLNAME = os.environ.get("EMAIL_FULLNAME", "")


async def send_email(
    to: str | list[str],
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
) -> str:
    msg = MIMEMultipart()
    msg["From"] = formataddr((EMAIL_FULLNAME, EMAIL_USER))
    if isinstance(to, list):
        msg["To"] = ", ".join(to)
    else:
        msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=EMAIL_USER.split("@")[-1])
    if cc:
        msg["Cc"] = cc
    msg.attach(MIMEText(body, "plain", "utf-8"))

    all_recipients = []
    to_list = to if isinstance(to, list) else [t.strip() for t in to.split(",")]
    all_recipients.extend(to_list)
    if cc:
        all_recipients.extend([c.strip() for c in cc.split(",")])
    if bcc:
        all_recipients.extend([b.strip() for b in bcc.split(",")])

    await aiosmtplib.send(
        msg,
        hostname=SMTP_HOST,
        port=SMTP_PORT,
        username=EMAIL_USER,
        password=EMAIL_PASSWORD,
        use_tls=True,
        recipients=all_recipients,
    )
    return f"Email sent to {msg['To']}"


async def reply_to_email(
    original: dict,
    body: str,
    reply_all: bool = False,
) -> str:
    subject = original.get("subject", "")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    msg = MIMEMultipart()
    msg["From"] = formataddr((EMAIL_FULLNAME, EMAIL_USER))

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
                    if EMAIL_USER.lower() not in a.lower() and a not in cc_parts:
                        cc_parts.append(a)
        if cc_parts:
            msg["Cc"] = ", ".join(cc_parts)
            recipients.extend(cc_parts)

    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=EMAIL_USER.split("@")[-1])

    if original.get("message_id"):
        msg["In-Reply-To"] = original["message_id"]
        msg["References"] = original.get("in_reply_to", "") + " " + original["message_id"]

    msg.attach(MIMEText(body, "plain", "utf-8"))

    await aiosmtplib.send(
        msg,
        hostname=SMTP_HOST,
        port=SMTP_PORT,
        username=EMAIL_USER,
        password=EMAIL_PASSWORD,
        use_tls=True,
        recipients=recipients,
    )
    return f"Reply sent to {msg['To']}"

import os
from dataclasses import dataclass


@dataclass
class Account:
    email_user: str
    email_password: str
    email_fullname: str
    imap_host: str
    imap_port: int
    smtp_host: str
    smtp_port: int


# Default account (no prefix)
_default = Account(
    email_user=os.environ.get("EMAIL_USER", ""),
    email_password=os.environ.get("EMAIL_PASSWORD", ""),
    email_fullname=os.environ.get("EMAIL_FULLNAME", ""),
    imap_host=os.environ.get("IMAP_HOST", ""),
    imap_port=int(os.environ.get("IMAP_PORT", "993")),
    smtp_host=os.environ.get("SMTP_HOST", ""),
    smtp_port=int(os.environ.get("SMTP_PORT", "465")),
)

# Account B
_account_b = Account(
    email_user=os.environ.get("B_EMAIL_USER", ""),
    email_password=os.environ.get("B_EMAIL_PASSWORD", ""),
    email_fullname=os.environ.get("B_EMAIL_FULLNAME", ""),
    imap_host=os.environ.get("B_IMAP_HOST", os.environ.get("IMAP_HOST", "")),
    imap_port=int(os.environ.get("B_IMAP_PORT", os.environ.get("IMAP_PORT", "993"))),
    smtp_host=os.environ.get("B_SMTP_HOST", os.environ.get("SMTP_HOST", "")),
    smtp_port=int(os.environ.get("B_SMTP_PORT", os.environ.get("SMTP_PORT", "465"))),
)

_accounts = {
    "a": _default,
    "b": _account_b,
}


def get_account(account: str = "a") -> Account:
    acc = _accounts.get(account.lower(), _default)
    if not acc.email_user:
        raise ValueError(f"Account '{account}' is not configured")
    return acc


def list_accounts() -> list[dict]:
    result = []
    for key, acc in _accounts.items():
        if acc.email_user:
            result.append({"id": key, "email": acc.email_user, "name": acc.email_fullname})
    return result

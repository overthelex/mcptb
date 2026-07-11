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
    # Passwordless client-certificate auth (SASL EXTERNAL on IMAP,
    # permit_tls_clientcerts on SMTP). When client_cert is set the cert is
    # used and no password is sent.
    client_cert: str = ""
    client_key: str = ""

    def ssl_context(self):
        """SSLContext presenting the client cert, or None for password auth."""
        if not self.client_cert:
            return None
        import ssl

        ctx = ssl.create_default_context()
        ctx.load_cert_chain(self.client_cert, self.client_key or self.client_cert)
        return ctx


# Default account (no prefix)
_default = Account(
    email_user=os.environ.get("EMAIL_USER", ""),
    email_password=os.environ.get("EMAIL_PASSWORD", ""),
    email_fullname=os.environ.get("EMAIL_FULLNAME", ""),
    imap_host=os.environ.get("IMAP_HOST", ""),
    imap_port=int(os.environ.get("IMAP_PORT", "993")),
    smtp_host=os.environ.get("SMTP_HOST", ""),
    smtp_port=int(os.environ.get("SMTP_PORT", "465")),
    client_cert=os.environ.get("CLIENT_CERT", ""),
    client_key=os.environ.get("CLIENT_KEY", ""),
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
    client_cert=os.environ.get("B_CLIENT_CERT", ""),
    client_key=os.environ.get("B_CLIENT_KEY", ""),
)

# Account C
_account_c = Account(
    email_user=os.environ.get("C_EMAIL_USER", ""),
    email_password=os.environ.get("C_EMAIL_PASSWORD", ""),
    email_fullname=os.environ.get("C_EMAIL_FULLNAME", ""),
    imap_host=os.environ.get("C_IMAP_HOST", os.environ.get("IMAP_HOST", "")),
    imap_port=int(os.environ.get("C_IMAP_PORT", os.environ.get("IMAP_PORT", "993"))),
    smtp_host=os.environ.get("C_SMTP_HOST", os.environ.get("SMTP_HOST", "")),
    smtp_port=int(os.environ.get("C_SMTP_PORT", os.environ.get("SMTP_PORT", "465"))),
    client_cert=os.environ.get("C_CLIENT_CERT", ""),
    client_key=os.environ.get("C_CLIENT_KEY", ""),
)

_accounts = {
    "a": _default,
    "b": _account_b,
    "c": _account_c,
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

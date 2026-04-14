import asyncio
import base64
import re
import socket
import ssl
import threading
from functools import partial

from accounts import get_account


# --- ManageSieve protocol client (blocking, run in executor) ---

class SieveClient:
    """Minimal ManageSieve (RFC 5804) client — blocking I/O."""

    def __init__(self, host: str, port: int = 4190):
        self.host = host
        self.port = port
        self.sock = None
        self.file = None

    def connect(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=10)
        self.file = self.sock.makefile("rb")
        greeting = self._read_response()
        if not greeting["ok"]:
            raise ConnectionError(f"ManageSieve greeting failed: {greeting['data']}")
        return greeting

    def starttls(self):
        self._send("STARTTLS")
        resp = self._read_response()
        if not resp["ok"]:
            raise ConnectionError(f"STARTTLS failed: {resp['data']}")
        ctx = ssl.create_default_context()
        self.sock = ctx.wrap_socket(self.sock, server_hostname=self.host)
        self.file = self.sock.makefile("rb")
        # re-read capabilities after TLS
        caps = self._read_response()
        return caps

    def authenticate(self, username: str, password: str):
        auth_str = f"\x00{username}\x00{password}"
        encoded = base64.b64encode(auth_str.encode("utf-8")).decode("ascii")
        self._send(f'AUTHENTICATE "PLAIN" "{encoded}"')
        resp = self._read_response()
        if not resp["ok"]:
            raise ConnectionError(f"Authentication failed: {resp['data']}")
        return resp

    def listscripts(self) -> list[dict]:
        self._send("LISTSCRIPTS")
        resp = self._read_response()
        if not resp["ok"]:
            raise Exception(f"LISTSCRIPTS failed: {resp['data']}")
        scripts = []
        for line in resp["lines"]:
            m = re.match(r'"([^"]+)"(\s+ACTIVE)?', line)
            if m:
                scripts.append({"name": m.group(1), "active": bool(m.group(2))})
        return scripts

    def getscript(self, name: str) -> str:
        self._send(f'GETSCRIPT "{name}"')
        resp = self._read_response()
        if not resp["ok"]:
            raise Exception(f"GETSCRIPT failed: {resp['data']}")
        return resp["script"]

    def putscript(self, name: str, content: str):
        encoded = content.encode("utf-8")
        self.sock.sendall(f'PUTSCRIPT "{name}" {{{len(encoded)}+}}\r\n'.encode("utf-8"))
        self.sock.sendall(encoded)
        self.sock.sendall(b"\r\n")
        resp = self._read_response()
        if not resp["ok"]:
            raise Exception(f"PUTSCRIPT failed: {resp['data']}")
        return resp

    def setactive(self, name: str):
        self._send(f'SETACTIVE "{name}"')
        resp = self._read_response()
        if not resp["ok"]:
            raise Exception(f"SETACTIVE failed: {resp['data']}")
        return resp

    def deletescript(self, name: str):
        self._send(f'DELETESCRIPT "{name}"')
        resp = self._read_response()
        if not resp["ok"]:
            raise Exception(f"DELETESCRIPT failed: {resp['data']}")
        return resp

    def logout(self):
        try:
            self._send("LOGOUT")
            self.sock.close()
        except Exception:
            pass

    def _send(self, cmd: str):
        self.sock.sendall(f"{cmd}\r\n".encode("utf-8"))

    def _read_response(self) -> dict:
        lines = []
        script = ""
        while True:
            raw = self.file.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if line.startswith("OK"):
                return {"ok": True, "data": line, "lines": lines, "script": script}
            elif line.startswith("NO"):
                return {"ok": False, "data": line, "lines": lines, "script": script}
            elif line.startswith("BYE"):
                return {"ok": False, "data": line, "lines": lines, "script": script}
            elif line.startswith("{"):
                m = re.match(r"\{(\d+)\+?\}", line)
                if m:
                    size = int(m.group(1))
                    data = self.file.read(size)
                    script = data.decode("utf-8", errors="replace")
                    self.file.readline()  # trailing \r\n
                else:
                    lines.append(line)
            else:
                lines.append(line)


# --- High-level async functions (blocking ops in executor) ---

async def _run(func, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(func, *args, **kwargs))


def _connect(account: str = "a") -> SieveClient:
    acc = get_account(account)
    client = SieveClient(acc.imap_host, 4190)
    client.connect()
    try:
        client.starttls()
    except Exception:
        pass
    client.authenticate(acc.email_user, acc.email_password)
    return client


async def list_scripts(account: str = "a") -> list[dict]:
    def _do():
        client = _connect(account)
        try:
            return client.listscripts()
        finally:
            client.logout()
    return await _run(_do)


async def get_script(name: str, account: str = "a") -> str:
    def _do():
        client = _connect(account)
        try:
            return client.getscript(name)
        finally:
            client.logout()
    return await _run(_do)


async def put_script(name: str, content: str, account: str = "a") -> str:
    def _do():
        client = _connect(account)
        try:
            client.putscript(name, content)
            return f"Script '{name}' uploaded successfully"
        finally:
            client.logout()
    return await _run(_do)


async def activate_script(name: str, account: str = "a") -> str:
    def _do():
        client = _connect(account)
        try:
            client.setactive(name)
            return f"Script '{name}' activated"
        finally:
            client.logout()
    return await _run(_do)


async def deactivate_scripts(account: str = "a") -> str:
    def _do():
        client = _connect(account)
        try:
            client.setactive("")
            return "All scripts deactivated"
        finally:
            client.logout()
    return await _run(_do)


async def delete_script(name: str, account: str = "a") -> str:
    def _do():
        client = _connect(account)
        try:
            client.deletescript(name)
            return f"Script '{name}' deleted"
        finally:
            client.logout()
    return await _run(_do)


# --- Filter helper: builds Sieve script from simple conditions ---

def build_sieve_script(rules: list[dict]) -> str:
    """Build a Sieve script from a list of rules.

    Each rule is a dict:
    {
        "name": "rule name (comment)",
        "conditions": [
            {"field": "from"|"to"|"subject"|"body"|"header", "contains": "value",
             "header_name": "X-Header" (only if field=="header")}
        ],
        "match": "all"|"any",  # all conditions must match, or any
        "actions": [
            {"type": "fileinto", "folder": "FolderName"},
            {"type": "flag", "flags": "\\Seen"},
            {"type": "redirect", "address": "user@example.com"},
            {"type": "discard"},
            {"type": "keep"},
            {"type": "stop"}
        ]
    }
    """
    requires = set()
    rule_blocks = []

    for rule in rules:
        conditions = rule.get("conditions", [])
        actions = rule.get("actions", [])
        match_type = rule.get("match", "all")
        name = rule.get("name", "")

        # Build conditions
        cond_parts = []
        for cond in conditions:
            field = cond["field"].lower()
            value = cond["contains"]
            escaped = value.replace('\\', '\\\\').replace('"', '\\"')
            if field == "from":
                cond_parts.append(f'header :contains "From" "{escaped}"')
            elif field == "to":
                cond_parts.append(f'header :contains "To" "{escaped}"')
            elif field == "subject":
                cond_parts.append(f'header :contains "Subject" "{escaped}"')
            elif field == "body":
                requires.add("body")
                cond_parts.append(f'body :contains "{escaped}"')
            elif field == "header":
                header_name = cond.get("header_name", "X-Header")
                cond_parts.append(f'header :contains "{header_name}" "{escaped}"')

        # Build condition expression
        if len(cond_parts) == 0:
            condition_str = "true"
        elif len(cond_parts) == 1:
            condition_str = cond_parts[0]
        elif match_type == "any":
            condition_str = "anyof (" + ", ".join(cond_parts) + ")"
        else:
            condition_str = "allof (" + ", ".join(cond_parts) + ")"

        # Build actions
        action_lines = []
        for action in actions:
            atype = action["type"].lower()
            if atype == "fileinto":
                requires.add("fileinto")
                folder = action["folder"].replace('\\', '\\\\').replace('"', '\\"')
                action_lines.append(f'    fileinto "{folder}";')
            elif atype == "flag":
                requires.add("imap4flags")
                flags = action.get("flags", "\\\\Seen")
                action_lines.append(f'    setflag "{flags}";')
            elif atype == "addflag":
                requires.add("imap4flags")
                flags = action.get("flags", "\\\\Flagged")
                action_lines.append(f'    addflag "{flags}";')
            elif atype == "redirect":
                addr = action["address"]
                action_lines.append(f'    redirect "{addr}";')
            elif atype == "discard":
                action_lines.append("    discard;")
            elif atype == "keep":
                action_lines.append("    keep;")
            elif atype == "stop":
                action_lines.append("    stop;")
            elif atype == "reject":
                requires.add("reject")
                reason = action.get("reason", "Rejected")
                action_lines.append(f'    reject "{reason}";')
            elif atype == "vacation":
                requires.add("vacation")
                subj = action.get("subject", "Auto-reply")
                body = action.get("body", "I am currently unavailable.")
                action_lines.append(f'    vacation :subject "{subj}" "{body}";')

        comment = f"  # {name}\n" if name else ""
        actions_block = "\n".join(action_lines)
        rule_blocks.append(f"{comment}  if {condition_str} {{\n{actions_block}\n  }}")

    # Build full script
    header_parts = []
    for req in sorted(requires):
        header_parts.append(f'require "{req}";')
    header = "\n".join(header_parts)
    body = "\n\n".join(rule_blocks)

    script = ""
    if header:
        script += header + "\n\n"
    script += body + "\n"
    return script


async def create_filter(
    script_name: str,
    rules: list[dict],
    activate: bool = True,
    account: str = "a",
) -> str:
    """Create a Sieve filter script from rules and optionally activate it."""
    content = build_sieve_script(rules)
    def _do():
        client = _connect(account)
        try:
            client.putscript(script_name, content)
            if activate:
                client.setactive(script_name)
            status = "uploaded and activated" if activate else "uploaded"
            return f"Filter '{script_name}' {status}.\n\nGenerated Sieve script:\n{content}"
        finally:
            client.logout()
    return await _run(_do)

import json
from mcp.server.fastmcp import FastMCP

import imap_client
import smtp_client
import contacts

mcp = FastMCP("Thunderbird Email")


# --- Folder tools ---

@mcp.tool()
async def list_folders() -> str:
    """List all mail folders."""
    folders = await imap_client.list_folders()
    return json.dumps(folders, ensure_ascii=False, indent=2)


@mcp.tool()
async def create_folder(folder_name: str) -> str:
    """Create a new mail folder."""
    return await imap_client.create_folder(folder_name)


@mcp.tool()
async def rename_folder(old_name: str, new_name: str) -> str:
    """Rename a mail folder."""
    return await imap_client.rename_folder(old_name, new_name)


@mcp.tool()
async def delete_folder(folder_name: str) -> str:
    """Delete a mail folder (cannot delete INBOX)."""
    return await imap_client.delete_folder(folder_name)


# --- Email read tools ---

@mcp.tool()
async def list_emails(folder: str = "INBOX", page: int = 1, page_size: int = 20) -> str:
    """List emails in a folder with pagination. Returns subject, from, date, uid, flags."""
    result = await imap_client.list_emails(folder, page, page_size)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def read_email(folder: str, uid: int) -> str:
    """Read a full email by UID. Returns subject, from, to, cc, date, body, attachments."""
    result = await imap_client.read_email(folder, uid)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def search_emails(query: str, folder: str = "INBOX", criteria: str = "ALL") -> str:
    """Search emails. Criteria can be: ALL (searches subject+from), SUBJECT, FROM, BODY, TO."""
    results = await imap_client.search_emails(folder, query, criteria)
    return json.dumps(results, ensure_ascii=False, indent=2)


# --- Email actions ---

@mcp.tool()
async def move_email(folder: str, uid: int, destination_folder: str) -> str:
    """Move an email to another folder."""
    return await imap_client.move_email(folder, uid, destination_folder)


@mcp.tool()
async def delete_email(folder: str, uid: int) -> str:
    """Delete an email (moves to Trash)."""
    return await imap_client.delete_email(folder, uid)


# --- Send tools ---

@mcp.tool()
async def send_email(to: str, subject: str, body: str, cc: str = "", bcc: str = "") -> str:
    """Send a new email. 'to' can be comma-separated for multiple recipients."""
    return await smtp_client.send_email(to, subject, body, cc, bcc)


@mcp.tool()
async def reply_to_email(folder: str, uid: int, body: str, reply_all: bool = False) -> str:
    """Reply to an email by UID. Set reply_all=true to reply to all recipients."""
    original = await imap_client.get_email_for_reply(folder, uid)
    if "error" in original:
        return original["error"]
    return await smtp_client.reply_to_email(original, body, reply_all)


# --- Contacts ---

@mcp.tool()
async def list_contacts(search: str = "") -> str:
    """List contacts from Thunderbird address book. Optional search filter."""
    results = await contacts.list_contacts(search)
    return json.dumps(results, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")

import json
from mcp.server.fastmcp import FastMCP

import imap_client
import smtp_client
import contacts
import sieve_client
import accounts as acc_module

mcp = FastMCP("Thunderbird Email")


# --- Account tools ---

@mcp.tool()
async def list_mail_accounts() -> str:
    """List all configured email accounts. Returns account id, email, and display name."""
    return json.dumps(acc_module.list_accounts(), ensure_ascii=False, indent=2)


# --- Folder tools ---

@mcp.tool()
async def list_folders(account: str = "a") -> str:
    """List all mail folders. Use account='b' for panoptic.com.ua."""
    folders = await imap_client.list_folders(account)
    return json.dumps(folders, ensure_ascii=False, indent=2)


@mcp.tool()
async def create_folder(folder_name: str, account: str = "a") -> str:
    """Create a new mail folder."""
    return await imap_client.create_folder(folder_name, account)


@mcp.tool()
async def rename_folder(old_name: str, new_name: str, account: str = "a") -> str:
    """Rename a mail folder."""
    return await imap_client.rename_folder(old_name, new_name, account)


@mcp.tool()
async def delete_folder(folder_name: str, account: str = "a") -> str:
    """Delete a mail folder (cannot delete INBOX)."""
    return await imap_client.delete_folder(folder_name, account)


# --- Email read tools ---

@mcp.tool()
async def list_emails(folder: str = "INBOX", page: int = 1, page_size: int = 20, account: str = "a") -> str:
    """List emails in a folder with pagination. Returns subject, from, date, uid, flags. Use account='b' for panoptic.com.ua."""
    result = await imap_client.list_emails(folder, page, page_size, account)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def read_email(folder: str, uid: int, account: str = "a") -> str:
    """Read a full email by UID. Returns subject, from, to, cc, date, body (plaintext), body_html (raw HTML if present), attachments."""
    result = await imap_client.read_email(folder, uid, account)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def search_emails(query: str, folder: str = "INBOX", criteria: str = "ALL", account: str = "a") -> str:
    """Search emails. Criteria can be: ALL (searches subject+from), SUBJECT, FROM, BODY, TO."""
    results = await imap_client.search_emails(folder, query, criteria, account)
    return json.dumps(results, ensure_ascii=False, indent=2)


# --- Email actions ---

@mcp.tool()
async def move_email(folder: str, uid: int, destination_folder: str, account: str = "a") -> str:
    """Move an email to another folder."""
    return await imap_client.move_email(folder, uid, destination_folder, account)


@mcp.tool()
async def delete_email(folder: str, uid: int, account: str = "a") -> str:
    """Delete an email (moves to Trash)."""
    return await imap_client.delete_email(folder, uid, account)


# --- Send tools ---

@mcp.tool()
async def send_email(to: str, subject: str, body: str, cc: str = "", bcc: str = "", attachments: list[str] | None = None, account: str = "a", html: bool = False) -> str:
    """Send a new email. 'to' can be comma-separated for multiple recipients. 'attachments' is a list of absolute file paths. Set html=true to send 'body' as HTML (a plaintext fallback is generated automatically). Use account='b' to send from panoptic.com.ua."""
    return await smtp_client.send_email(to, subject, body, cc, bcc, attachments, account, html)


@mcp.tool()
async def reply_to_email(folder: str, uid: int, body: str, reply_all: bool = False, attachments: list[str] | None = None, account: str = "a", html: bool = False) -> str:
    """Reply to an email by UID. Set reply_all=true to reply to all recipients. 'attachments' is a list of absolute file paths. Set html=true to send 'body' as HTML."""
    original = await imap_client.get_email_for_reply(folder, uid, account)
    if "error" in original:
        return original["error"]
    return await smtp_client.reply_to_email(original, body, reply_all, attachments, account, html)


@mcp.tool()
async def forward_email(folder: str, uid: int, to: str, body: str = "", attachments: list[str] | None = None, account: str = "a", html: bool = False) -> str:
    """Forward an email by UID to another recipient. Original attachments are included. Extra 'attachments' is a list of file paths. Set html=true to forward as HTML (uses the original message's HTML part when present)."""
    original = await imap_client.get_email_for_forward(folder, uid, account)
    if "error" in original:
        return original["error"]
    return await smtp_client.forward_email(original, to, body, attachments, account, html)


# --- Email flags ---

@mcp.tool()
async def mark_as_read(folder: str, uid: int, account: str = "a") -> str:
    """Mark an email as read."""
    return await imap_client.set_flags(folder, uid, "\\Seen", "add", account)


@mcp.tool()
async def mark_as_unread(folder: str, uid: int, account: str = "a") -> str:
    """Mark an email as unread."""
    return await imap_client.set_flags(folder, uid, "\\Seen", "remove", account)


@mcp.tool()
async def flag_email(folder: str, uid: int, account: str = "a") -> str:
    """Star/flag an email."""
    return await imap_client.set_flags(folder, uid, "\\Flagged", "add", account)


@mcp.tool()
async def unflag_email(folder: str, uid: int, account: str = "a") -> str:
    """Remove star/flag from an email."""
    return await imap_client.set_flags(folder, uid, "\\Flagged", "remove", account)


# --- Attachments ---

@mcp.tool()
async def download_attachment(folder: str, uid: int, filename: str, save_dir: str = "/tmp", account: str = "a") -> str:
    """Download an attachment from an email by UID. Specify the attachment filename and target directory."""
    return await imap_client.download_attachment(folder, uid, filename, save_dir, account)


# --- Stats ---

@mcp.tool()
async def get_unread_count(folder: str = "INBOX", account: str = "a") -> str:
    """Get the number of unread emails in a folder."""
    result = await imap_client.get_unread_count(folder, account)
    return json.dumps(result, ensure_ascii=False)


# --- Batch operations ---

@mcp.tool()
async def batch_move_emails(folder: str, uids: list[int], destination_folder: str, account: str = "a") -> str:
    """Move multiple emails by UIDs to another folder."""
    return await imap_client.batch_move_emails(folder, uids, destination_folder, account)


@mcp.tool()
async def batch_delete_emails(folder: str, uids: list[int], account: str = "a") -> str:
    """Delete multiple emails by UIDs (moves to Trash)."""
    return await imap_client.batch_delete_emails(folder, uids, account)


# --- Contacts ---

@mcp.tool()
async def list_contacts(search: str = "") -> str:
    """List contacts from Thunderbird address book. Optional search filter."""
    results = await contacts.list_contacts(search)
    return json.dumps(results, ensure_ascii=False, indent=2)


@mcp.tool()
async def add_contact(display_name: str, email: str, first_name: str = "", last_name: str = "", phone: str = "", notes: str = "") -> str:
    """Add a new contact to the Thunderbird address book."""
    props = {"DisplayName": display_name, "PrimaryEmail": email}
    if first_name:
        props["FirstName"] = first_name
    if last_name:
        props["LastName"] = last_name
    if phone:
        props["CellularNumber"] = phone
    if notes:
        props["Notes"] = notes
    return await contacts.add_contact(props)


@mcp.tool()
async def update_contact(email_address: str, display_name: str = "", first_name: str = "", last_name: str = "", phone: str = "", notes: str = "") -> str:
    """Update an existing contact by email address."""
    props = {}
    if display_name:
        props["DisplayName"] = display_name
    if first_name:
        props["FirstName"] = first_name
    if last_name:
        props["LastName"] = last_name
    if phone:
        props["CellularNumber"] = phone
    if notes:
        props["Notes"] = notes
    if not props:
        return "No fields to update"
    return await contacts.update_contact(email_address, props)


@mcp.tool()
async def delete_contact(email_address: str) -> str:
    """Delete a contact by email address."""
    return await contacts.delete_contact(email_address)


# --- Sieve filters ---

@mcp.tool()
async def list_sieve_scripts(account: str = "a") -> str:
    """List all Sieve filter scripts on the server. Shows name and active status."""
    scripts = await sieve_client.list_scripts(account)
    return json.dumps(scripts, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_sieve_script(name: str, account: str = "a") -> str:
    """Get the content of a Sieve filter script by name."""
    content = await sieve_client.get_script(name, account)
    return content


@mcp.tool()
async def put_sieve_script(name: str, content: str, account: str = "a") -> str:
    """Upload a raw Sieve script. Use this for advanced Sieve scripts."""
    return await sieve_client.put_script(name, content, account)


@mcp.tool()
async def activate_sieve_script(name: str, account: str = "a") -> str:
    """Activate a Sieve script. Only one script can be active at a time."""
    return await sieve_client.activate_script(name, account)


@mcp.tool()
async def deactivate_sieve_scripts(account: str = "a") -> str:
    """Deactivate all Sieve scripts (no filtering)."""
    return await sieve_client.deactivate_scripts(account)


@mcp.tool()
async def delete_sieve_script(name: str, account: str = "a") -> str:
    """Delete a Sieve filter script. Cannot delete the active script — deactivate first."""
    return await sieve_client.delete_script(name, account)


@mcp.tool()
async def create_filter(
    script_name: str,
    rules: list[dict],
    activate: bool = True,
    account: str = "a",
) -> str:
    """Create an email filter from simple rules and upload as Sieve script.

    Each rule in the list is a dict with:
    - name: optional comment/description
    - conditions: list of {field, contains} where field is from/to/subject/body/header
    - match: "all" or "any" (default: all)
    - actions: list of actions:
        - {type: "fileinto", folder: "FolderName"} — move to folder
        - {type: "flag", flags: "\\\\Seen"} — set flags
        - {type: "addflag", flags: "\\\\Flagged"} — add flag
        - {type: "redirect", address: "user@example.com"} — forward
        - {type: "discard"} — delete
        - {type: "keep"} — keep in inbox
        - {type: "reject", reason: "..."} — reject with message
        - {type: "vacation", subject: "...", body: "..."} — auto-reply
        - {type: "stop"} — stop processing

    Example: create_filter("my-filter", [
        {"name": "Newsletters to folder", "conditions": [{"field": "from", "contains": "newsletter"}],
         "actions": [{"type": "fileinto", "folder": "Newsletters"}, {"type": "stop"}]}
    ])
    """
    return await sieve_client.create_filter(script_name, rules, activate, account)


if __name__ == "__main__":
    mcp.run(transport="stdio")

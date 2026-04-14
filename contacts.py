import os

import aiosqlite

ABOOK_PATH = os.environ.get("ABOOK_PATH", "/data/abook.sqlite")

PROPERTIES = [
    "DisplayName", "PrimaryEmail", "SecondEmail",
    "FirstName", "LastName",
    "WorkPhone", "HomePhone", "CellularNumber",
    "Notes",
]


async def list_contacts(search: str = "") -> list[dict]:
    if not os.path.exists(ABOOK_PATH):
        return []

    async with aiosqlite.connect(f"file:{ABOOK_PATH}?mode=ro", uri=True) as db:
        placeholders = ",".join(["?"] * len(PROPERTIES))
        if search:
            query = f"""
                SELECT card, name, value FROM properties
                WHERE name IN ({placeholders})
                AND card IN (
                    SELECT DISTINCT card FROM properties
                    WHERE (name='DisplayName' OR name='PrimaryEmail' OR name='FirstName' OR name='LastName')
                    AND value LIKE ?
                )
            """
            params = PROPERTIES + [f"%{search}%"]
        else:
            query = f"SELECT card, name, value FROM properties WHERE name IN ({placeholders})"
            params = PROPERTIES

        contacts_map: dict[str, dict] = {}
        async with db.execute(query, params) as cursor:
            async for card, name, value in cursor:
                if card not in contacts_map:
                    contacts_map[card] = {}
                contacts_map[card][name] = value

    return list(contacts_map.values())


async def add_contact(properties: dict) -> str:
    """Add a new contact. properties: dict with keys like DisplayName, PrimaryEmail, etc."""
    if not os.path.exists(ABOOK_PATH):
        return "Address book not found"

    async with aiosqlite.connect(ABOOK_PATH) as db:
        # Get next card id
        async with db.execute("SELECT COALESCE(MAX(CAST(card AS INTEGER)), 0) + 1 FROM properties") as cur:
            row = await cur.fetchone()
            card_id = str(row[0])

        for name, value in properties.items():
            if name in PROPERTIES and value:
                await db.execute(
                    "INSERT INTO properties (card, name, value) VALUES (?, ?, ?)",
                    (card_id, name, value),
                )
        await db.commit()
    return f"Contact added (card {card_id})"


async def update_contact(email_address: str, properties: dict) -> str:
    """Update a contact found by PrimaryEmail. properties: dict of fields to update."""
    if not os.path.exists(ABOOK_PATH):
        return "Address book not found"

    async with aiosqlite.connect(ABOOK_PATH) as db:
        # Find card by email
        async with db.execute(
            "SELECT card FROM properties WHERE name='PrimaryEmail' AND value=?",
            (email_address,),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return f"Contact with email '{email_address}' not found"
            card_id = row[0]

        for name, value in properties.items():
            if name not in PROPERTIES:
                continue
            # Try update, if no rows affected — insert
            async with db.execute(
                "UPDATE properties SET value=? WHERE card=? AND name=?",
                (value, card_id, name),
            ) as cur:
                if cur.rowcount == 0:
                    await db.execute(
                        "INSERT INTO properties (card, name, value) VALUES (?, ?, ?)",
                        (card_id, name, value),
                    )
        await db.commit()
    return f"Contact '{email_address}' updated"


async def delete_contact(email_address: str) -> str:
    """Delete a contact by PrimaryEmail."""
    if not os.path.exists(ABOOK_PATH):
        return "Address book not found"

    async with aiosqlite.connect(ABOOK_PATH) as db:
        async with db.execute(
            "SELECT card FROM properties WHERE name='PrimaryEmail' AND value=?",
            (email_address,),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return f"Contact with email '{email_address}' not found"
            card_id = row[0]

        await db.execute("DELETE FROM properties WHERE card=?", (card_id,))
        await db.commit()
    return f"Contact '{email_address}' deleted"

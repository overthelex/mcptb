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

# queuectl/settings.py
from queuectl.database import get_db_connection

def update_setting(key, value):
    """Updates or inserts a configuration setting."""
    with get_db_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            (key, str(value))
        )
        conn.commit()
    return True

def get_setting(key, default=None):
    """Retrieves a configuration setting."""
    with get_db_connection() as conn:
        row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
        if row:
            try:
                return int(row['value'])
            except ValueError:
                return row['value']
        return default
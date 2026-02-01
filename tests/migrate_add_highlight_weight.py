"""Add highlight_weight column to the highlight table if missing."""
import os
import sqlite3


def migrate():
    db_url = os.getenv("FREEWISE_DB_URL", "sqlite:///./db/freewise.db")
    db_path = db_url.replace("sqlite:///", "")

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        print("No migration needed - database will be created on next startup.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(highlight)")
    columns = {row[1] for row in cursor.fetchall()}

    if "highlight_weight" not in columns:
        cursor.execute("ALTER TABLE highlight ADD COLUMN highlight_weight REAL DEFAULT 1.0")
        print("Added highlight_weight column")

    conn.commit()
    conn.close()
    print("✅ Migration completed successfully")


if __name__ == "__main__":
    migrate()

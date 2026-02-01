"""Add cover image columns to the book table if missing."""
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

    cursor.execute("PRAGMA table_info(book)")
    columns = {row[1] for row in cursor.fetchall()}

    if "cover_image_url" not in columns:
        cursor.execute("ALTER TABLE book ADD COLUMN cover_image_url TEXT")
        print("Added cover_image_url column")

    if "cover_image_source" not in columns:
        cursor.execute("ALTER TABLE book ADD COLUMN cover_image_source TEXT")
        print("Added cover_image_source column")

    conn.commit()
    conn.close()
    print("✅ Migration completed successfully")

if __name__ == "__main__":
    migrate()

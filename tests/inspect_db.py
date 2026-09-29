import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "db" / "chatbot.db"
con = sqlite3.connect(DB)
for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    cols = [c[1] for c in con.execute(f"PRAGMA table_info({name})")]
    count = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
    print(f"\n=== {name} ({count} dòng) ===")
    print("Cột:", ", ".join(cols))
    for row in con.execute(f"SELECT * FROM {name} ORDER BY 1 DESC LIMIT 5"):
        print("  ", row)
con.close()
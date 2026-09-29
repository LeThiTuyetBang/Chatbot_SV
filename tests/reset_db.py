import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "chatbot.db"
CLEAN = ROOT / "db" / "chatbot_clean.db"

if len(sys.argv) != 2 or sys.argv[1] not in ("save", "restore"):
    print("Dùng: python tests/reset_db.py save   (lưu bản sạch)")
    print("  hoặc python tests/reset_db.py restore (khôi phục về bản sạch)")
    sys.exit(1)

if sys.argv[1] == "save":
    shutil.copy2(DB, CLEAN)
    print("Đã lưu bản sạch:", CLEAN)
else:
    if not CLEAN.exists():
        print("Chưa có bản sạch. Hãy chạy 'save' trước.")
        sys.exit(1)
    shutil.copy2(CLEAN, DB)
    print("Đã khôi phục database về bản sạch.")
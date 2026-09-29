"""
Xóa TOÀN BỘ đơn xin nghỉ + lịch sử + minh chứng, giữ nguyên bảng Users
(tài khoản sinh viên/giáo vụ). Dùng để đưa DB về trạng thái sạch trước khi
lưu lại bằng reset_db.py save.

Cách dùng:
    1. Tắt rasa run, rasa run actions, webapp.py trước.
    2. venv\\Scripts\\python.exe tests\\clean_test_data.py            (xem trước)
    3. venv\\Scripts\\python.exe tests\\clean_test_data.py --yes      (xóa thật)
"""

#python tests/reset_db.py restore
#python tests/run_e2e.py


import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "db" / "chatbot.db"


def main():
    confirm = "--yes" in sys.argv

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    counts = {}
    for table in ("Evidences", "RequestStatusHistory", "AbsenceRequests"):
        counts[table] = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    print("Số dòng hiện tại:")
    for table, n in counts.items():
        print(f"  {table}: {n}")

    if not confirm:
        print("\n[XEM TRƯỚC] Chưa xóa gì. Chạy lại với --yes để xóa thật.")
        con.close()
        return

    # Xóa bảng con trước (tham chiếu request_id), bảng chính sau
    cur.execute("DELETE FROM Evidences")
    cur.execute("DELETE FROM RequestStatusHistory")
    cur.execute("DELETE FROM AbsenceRequests")

    # Reset lại số thứ tự id về 1 (để lần sau đơn mới là #1 cho dễ theo dõi)
    cur.execute(
        "DELETE FROM sqlite_sequence WHERE name IN "
        "('AbsenceRequests', 'RequestStatusHistory', 'Evidences')"
    )

    con.commit()
    con.close()
    print("\nĐã xóa xong. Users được giữ nguyên.")


if __name__ == "__main__":
    main()
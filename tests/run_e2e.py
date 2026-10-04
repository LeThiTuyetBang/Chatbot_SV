"""
Script chạy tự động bộ kịch bản End-to-End qua Flask API + Rasa.
Cách chạy:
    1. Khởi động 3 tiến trình (Action Server, Rasa, Flask) trước.
    2. python tests/run_e2e.py
"""

import os
import sys
import json
import time
import sqlite3
from pathlib import Path

import requests
import yaml

# Cho phép import trực tiếp db/store.py (dùng để chuẩn bị dữ liệu test,
# ví dụ giáo vụ duyệt đơn, mà không cần gọi qua API HTTP).
sys.path.insert(0, str(Path(__file__).parent.parent))
from db import store  # noqa: E402

# ================== CẤU HÌNH ==================
BASE_URL = "http://127.0.0.1:5000"          # Flask
SCENARIOS_DIR = Path(__file__).parent / "e2e_scenarios"
DB_PATH = Path(__file__).parent.parent / "db" / "chatbot.db"

# Lấy từ biến môi trường, có fallback cho local test
STUDENT_USER = os.getenv("E2E_STUDENT_USER", "066305014844")
STUDENT_PASS = os.getenv("E2E_STUDENT_PASS", "UTH@2026")   # chỉ dùng khi chạy test local
STAFF_USER   = os.getenv("E2E_STAFF_USER", "gv_tien")
STAFF_PASS   = os.getenv("E2E_STAFF_PASS", "UTH@2026")

# Timeout mỗi request (giây)
TIMEOUT = 30
# ==============================================


def load_scenarios():
    """Đọc tất cả file YAML trong thư mục e2e_scenarios, sắp xếp theo tên."""
    files = sorted(SCENARIOS_DIR.glob("*.yaml"))
    scenarios = []
    for f in files:
        with open(f, encoding="utf-8") as fp:
            data = yaml.safe_load(fp)
        if data is None:
            print(f"  [WARN] Bỏ qua file rỗng: {f.name}")
            continue
        if not isinstance(data, dict):
            print(f"  [WARN] Bỏ qua file không đúng định dạng dict: {f.name}")
            continue
        data["_file"] = f.name
        scenarios.append(data)
    return scenarios


def login(session: requests.Session, username: str, password: str) -> bool:
    """Đăng nhập, trả về True nếu thành công."""
    r = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": username, "password": password},
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        print(f"  [LOGIN FAIL] {username}: status={r.status_code} body={r.text}")
        return False
    data = r.json()
    if not data.get("ok"):
        print(f"  [LOGIN FAIL] {username}: {data.get('message')}")
        return False
    return True


def restart_chat(session: requests.Session):
    """Gửi lệnh reset hội thoại Rasa cho user hiện tại."""
    try:
        session.post(f"{BASE_URL}/api/chat/restart", timeout=TIMEOUT)
    except Exception as e:
        print(f"  [WARN] restart chat: {e}")


def cancel_all_pending_of_student(username: str = STUDENT_USER) -> int:
    """
    Hủy TẤT CẢ đơn PENDING của sinh viên test.
    Tránh lỗi 'chồng lấn khoảng ngày' khi các kịch bản dùng ngày tương đối
    (mai / ngày kia) hoặc cùng môn học.
    Trả về số đơn đã hủy.
    """
    try:
        student = store.get_user_by_credentials(STUDENT_USER, STUDENT_PASS)
        if not student:
            return 0
        student_id = student["id"]
        cancelled = 0
        while True:
            result = store.cancel_latest_pending_request(
                student_id=student_id,
                changed_by=student_id,
                note="[E2E] Tự động hủy trước kịch bản mới để tránh chồng lấn ngày",
            )
            if result is None:
                break
            cancelled += 1
            if cancelled > 50:  # safety
                break
        if cancelled:
            print(f"  [CLEAN] Đã hủy {cancelled} đơn PENDING của {username}")
        return cancelled
    except Exception as e:
        print(f"  [CLEAN WARN] {e}")
        return 0


def send_message(session: requests.Session, text: str) -> list[str]:
    """
    Gửi 1 câu chat, trả về list các câu bot trả lời (text).
    """
    r = session.post(
        f"{BASE_URL}/api/chat",
        json={"message": text},
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        return [f"[HTTP {r.status_code}] {r.text}"]
    data = r.json()
    if not data.get("ok"):
        return [f"[API ERROR] {data.get('message')}"]
    responses = data.get("data") or []
    texts = []
    for item in responses:
        if isinstance(item, dict) and item.get("text"):
            texts.append(item["text"])
        elif isinstance(item, str):
            texts.append(item)
    return texts if texts else ["(bot không trả lời gì)"]


def check_contains(bot_texts: list[str], expected_contains: list[str]) -> bool:
    """True nếu mọi chuỗi trong expected_contains đều xuất hiện trong bot_texts."""
    joined = " ".join(bot_texts)
    for needle in expected_contains:
        if needle.lower() not in joined.lower():
            return False
    return True


def get_latest_student_request_status(student_username: str = STUDENT_USER) -> str | None:
    """Đọc status đơn mới nhất của sinh viên từ SQLite (nếu có)."""
    if not DB_PATH.exists():
        return None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ar.status
            FROM AbsenceRequests ar
            JOIN Users u ON u.id = ar.student_id
            WHERE u.username = ?
            ORDER BY ar.id DESC
            LIMIT 1
            """,
            (student_username,),
        )
        row = cur.fetchone()
        conn.close()
        return row["status"] if row else None
    except Exception as e:
        print(f"  [DB WARN] {e}")
        return None

def _submit_one_pending_via_chat(session: requests.Session) -> None:
    """Nộp 1 đơn PENDING qua chat (ngày tuyệt đối xa, tránh chồng với setup #22)."""
    restart_chat(session)
    time.sleep(0.3)
    # Dùng khoảng ngày khác hẳn 20-22/10 để không đụng đơn APPROVED của #22
    send_message(
        session,
        "em xin nghỉ môn Kiểm thử phần mềm lớp CN2302C từ 25/11/2026 đến 27/11/2026 vì ốm, không có minh chứng",
    )
    send_message(session, "có")


def setup_pending_request(session: requests.Session):
    """Chuẩn bị 1 đơn PENDING cho các kịch bản hủy đơn (#21, #23, #35)."""
    _submit_one_pending_via_chat(session)
    student = store.get_user_by_credentials(STUDENT_USER, STUDENT_PASS)
    if not student:
        raise RuntimeError("Setup PENDING: không tìm thấy tài khoản sinh viên test")
    pending = store.list_requests_by_student(student["id"], limit=1)
    if not pending or pending[0]["status"] != store.STATUS_PENDING:
        raise RuntimeError("Setup PENDING: không tạo được đơn PENDING")


def setup_approved_request(session: requests.Session):
    """Chuẩn bị đơn PENDING rồi duyệt thành APPROVED (cho #22)."""
    _submit_one_pending_via_chat(session)

    student = store.get_user_by_credentials(STUDENT_USER, STUDENT_PASS)
    if not student:
        raise RuntimeError("Không tìm thấy tài khoản sinh viên test để setup #22")

    pending = store.list_requests_by_student(student["id"], limit=1)
    if not pending or pending[0]["status"] != store.STATUS_PENDING:
        raise RuntimeError("Setup #22: không tạo được đơn PENDING để duyệt")

    staff = store.get_user_by_credentials(STAFF_USER, STAFF_PASS)
    if not staff:
        raise RuntimeError("Không tìm thấy tài khoản giáo vụ test để setup #22")

    store.update_request_status(
        request_id=pending[0]["id"],
        new_status=store.STATUS_APPROVED,
        changed_by=staff["id"],
        note="Setup tự động cho kịch bản #22",
    )


SETUP_FUNCTIONS = {
    "approve_latest_request_for_student": setup_approved_request,
    "create_pending_request": setup_pending_request,
}


def run_chat_scenario(scenario: dict) -> dict:
    """
    Chạy 1 kịch bản có turns (hội thoại).
    Trả về dict kết quả: {id, name, pass, turn_count, errors}
    """
    sid = scenario.get("id", "?")
    name = scenario.get("name", "")
    turns = scenario.get("turns") or []
    final_check = scenario.get("final_check") or {}

    result = {
        "id": sid,
        "name": name,
        "file": scenario.get("_file"),
        "pass": True,
        "turn_count": 0,
        "errors": [],
    }

    if not turns:
        # Kịch bản API-only → bỏ qua ở phiên bản 1
        result["pass"] = None  # skipped
        result["errors"].append("Không có turns (kịch bản API) → bỏ qua phiên bản 1")
        return result

    session = requests.Session()
    if not login(session, STUDENT_USER, STUDENT_PASS):
        result["pass"] = False
        result["errors"].append("Không đăng nhập được tài khoản sinh viên")
        return result
    # Dọn sạch đơn PENDING trước mỗi kịch bản (tránh chồng lấn ngày)
    cancel_all_pending_of_student()

    setup = scenario.get("setup") or {}
    setup_fn = SETUP_FUNCTIONS.get(setup.get("type")) if isinstance(setup, dict) else None
    if setup_fn:
        try:
            setup_fn(session)
        except Exception as e:
            result["pass"] = False
            result["errors"].append(f"Setup lỗi: {e}")
            return result

    restart_chat(session)
    time.sleep(0.3)  # chờ Rasa reset

    for i, turn in enumerate(turns, start=1):
        user_text = turn.get("user", "").strip()
        expected = turn.get("expected_bot") or []
        # expected có thể là list dict {"contains": [...]} hoặc list chuỗi
        contains_list = []
        for exp in expected:
            if isinstance(exp, dict) and "contains" in exp:
                contains_list.extend(exp["contains"])
            elif isinstance(exp, str):
                contains_list.append(exp)

        bot_texts = send_message(session, user_text)
        result["turn_count"] += 1

        print(f"    Turn {i}: USER → {user_text[:60]}{'...' if len(user_text) > 60 else ''}")
        print(f"           BOT  → {bot_texts[0][:80] if bot_texts else '(rỗng)'}...")

        if contains_list and not check_contains(bot_texts, contains_list):
            result["pass"] = False
            result["errors"].append(
                f"Turn {i}: không tìm thấy {contains_list} trong câu trả lời bot: {bot_texts}"
            )

    # Kiểm tra DB nếu kịch bản yêu cầu
    expected_status = final_check.get("db_status")
    if expected_status:
        actual_status = get_latest_student_request_status()
        if actual_status != expected_status:
            result["pass"] = False
            result["errors"].append(
                f"DB status mong đợi '{expected_status}' nhưng thực tế là '{actual_status}'"
            )

    return result


def main():
    print("=" * 60)
    print("CHẠY BỘ KỊCH BẢN END-TO-END (phiên bản 1 – chỉ chat)")
    print("=" * 60)

    if not SCENARIOS_DIR.exists():
        print(f"[ERROR] Không tìm thấy thư mục: {SCENARIOS_DIR}")
        sys.exit(1)

    scenarios = load_scenarios()
    print(f"Tìm thấy {len(scenarios)} file kịch bản.\n")

    results = []
    for sc in scenarios:
        print(f"▶ [{sc.get('id')}] {sc.get('name')} ({sc.get('_file')})")
        res = run_chat_scenario(sc)
        results.append(res)

        if res["pass"] is None:
            print("  → SKIP (API-only)\n")
        elif res["pass"]:
            print(f"  → PASS  (turns={res['turn_count']})\n")
        else:
            print(f"  → FAIL  (turns={res['turn_count']})")
            for e in res["errors"]:
                print(f"     • {e}")
            print()

    # ========== TỔNG HỢP ==========
    executed = [r for r in results if r["pass"] is not None]
    passed = [r for r in executed if r["pass"]]
    failed = [r for r in executed if not r["pass"]]
    skipped = [r for r in results if r["pass"] is None]

    total = len(executed)
    tcr = (len(passed) / total * 100) if total else 0.0
    avg_turns = (
        sum(r["turn_count"] for r in passed) / len(passed) if passed else 0.0
    )

    print("=" * 60)
    print("TỔNG HỢP KẾT QUẢ")
    print("=" * 60)
    print(f"Tổng file YAML        : {len(results)}")
    print(f"Đã chạy (có turns)    : {total}")
    print(f"Pass                  : {len(passed)}")
    print(f"Fail                  : {len(failed)}")
    print(f"Skip (API-only)       : {len(skipped)}")
    print(f"TCR                   : {tcr:.2f}%   (= {len(passed)}/{total})")
    print(f"Average Turn Count    : {avg_turns:.2f}")
    print()

    if failed:
        print("Các kịch bản FAIL:")
        for r in failed:
            print(f"  - [{r['id']}] {r['name']}")
            for e in r["errors"]:
                print(f"      {e}")

    # Ghi file kết quả JSON để đưa vào phụ lục sau này
    out_path = Path(__file__).parent / "e2e_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "total_executed": total,
                "passed": len(passed),
                "failed": len(failed),
                "skipped": len(skipped),
                "tcr": tcr,
                "average_turn_count": avg_turns,
                "details": results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\nĐã ghi kết quả chi tiết → {out_path}")


if __name__ == "__main__":
    main()
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
import random
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()
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
STUDENT_PASS = os.getenv("E2E_STUDENT_PASS") or os.getenv("DEFAULT_PASSWORD")
STAFF_USER   = os.getenv("E2E_STAFF_USER", "gv_tien")
STAFF_PASS   = os.getenv("E2E_STAFF_PASS") or os.getenv("DEFAULT_PASSWORD")

if not STUDENT_PASS or not STAFF_PASS:
    raise RuntimeError(
        "Thiếu E2E_STUDENT_PASS / E2E_STAFF_PASS hoặc DEFAULT_PASSWORD. "
        "Hãy set biến môi trường trước khi chạy test."
    )

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


def check_contains(bot_texts: list[str], expected_contains: list[str]) -> tuple[bool, list[str]]:
    """
    True nếu mọi chuỗi trong expected_contains đều xuất hiện trong bot_texts.
    Trả thêm danh sách từ khóa bị thiếu để log rõ lỗi.
    """
    joined = " ".join(bot_texts).lower()
    missing = [n for n in expected_contains if n.lower() not in joined]
    return len(missing) == 0, missing


def get_latest_student_request(student_username: str = STUDENT_USER) -> dict | None:
    """
    Trả về thông tin đơn mới nhất của sinh viên + số lượng minh chứng.
    Dùng để kiểm tra final_check: db_status, has_evidence...
    """
    if not DB_PATH.exists():
        return None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ar.id, ar.status, ar.course_code, ar.start_date, ar.end_date,
                   (SELECT COUNT(*) FROM Evidences e WHERE e.request_id = ar.id) AS evidence_count
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
        return dict(row) if row else None
    except Exception as e:
        print(f"  [DB WARN] {e}")
        return None


def get_latest_student_request_status(student_username: str = STUDENT_USER) -> str | None:
    """Giữ lại để tương thích (nếu chỗ khác còn gọi)."""
    latest = get_latest_student_request(student_username)
    return latest["status"] if latest else None

def create_pending_request_via_api(session: requests.Session) -> int:
    """
    Tạo 1 đơn PENDING qua API Form.
    Ngày luôn trong khoảng [today+3, today+60] → không quá khứ, không vượt 90 ngày.
    """
    today = date.today()
    # 3..60 ngày tới: an toàn với max_future_days=90 và tránh trùng "mai"
    offset = random.randint(3, 60)
    base = today + timedelta(days=offset)
    start = base.isoformat()
    end = (base + timedelta(days=2)).isoformat()

    body = {
        "course_code": f"Mon setup E2E {random.randint(100, 999)}",
        "class_code": "CN2302C",
        "start_date": start,
        "end_date": end,
        "reason": "Om – setup tu dong cho E2E",
        "evidence_url": "",
    }
    r = session.post(
        f"{BASE_URL}/api/student/requests",
        json=body,
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        raise RuntimeError(
            f"Setup PENDING qua API thất bại: status={r.status_code} body={r.text[:300]}"
        )
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Setup PENDING qua API thất bại: {data.get('message')}")

    req_id = (data.get("data") or {}).get("id")
    if not req_id:
        student = store.get_user_by_credentials(STUDENT_USER, STUDENT_PASS)
        pending = store.list_requests_by_student(student["id"], limit=1)
        if not pending or pending[0]["status"] != store.STATUS_PENDING:
            raise RuntimeError("Setup PENDING: không lấy được request_id sau khi tạo")
        req_id = pending[0]["id"]
    return int(req_id)

def setup_pending_request(session: requests.Session):
    """Chuẩn bị 1 đơn PENDING cho các kịch bản hủy đơn (#21, #23, #35) và API (#24, #25, #27)."""
    # Đảm bảo đã login SV
    if not session.cookies:
        if not login(session, STUDENT_USER, STUDENT_PASS):
            raise RuntimeError("Setup PENDING: không login được sinh viên")
    
    cancel_all_pending_of_student()   # dọn sạch trước
    req_id = create_pending_request_via_api(session)
     
    # Verify
    req = store.get_request_by_id(req_id)
    if not req or req["status"] != store.STATUS_PENDING:
        raise RuntimeError(f"Setup PENDING: đơn #{req_id} không ở trạng thái PENDING")
    return req_id


def setup_approved_request(session: requests.Session):
    """Chuẩn bị đơn PENDING rồi duyệt thành APPROVED (cho #22)."""
    req_id = setup_pending_request(session)

    staff = store.get_user_by_credentials(STAFF_USER, STAFF_PASS)
    if not staff:
        raise RuntimeError("Không tìm thấy tài khoản giáo vụ test để setup #22")

    store.update_request_status(
        request_id=req_id,
        new_status=store.STATUS_APPROVED,
        changed_by=staff["id"],
        note="Setup tự động cho kịch bản #22",
    )

SETUP_FUNCTIONS = {
    "approve_latest_request_for_student": setup_approved_request,
    "create_pending_request": setup_pending_request,
}
def run_api_scenario(scenario: dict) -> dict:
    """
    Chạy kịch bản API-only (form / admin / phân quyền / đăng nhập sai).
    Kiểm tra status code, message, role, DB status, history.
    """
    sid = str(scenario.get("id", "?"))
    name = scenario.get("name", "")
    result = {
        "id": sid,
        "name": name,
        "file": scenario.get("_file"),
        "pass": True,
        "turn_count": 0,
        "errors": [],
    }

    api_steps = scenario.get("api_steps") or []
    if not api_steps:
        result["pass"] = None
        result["errors"].append("Kịch bản API nhưng không có api_steps → bỏ qua")
        return result

    session = requests.Session()
    request_id = None

    # Setup đơn PENDING cho các kịch bản cần {id}: duyệt / từ chối / xem chi tiết
    if sid in ("24", "25", "27"):
        setup_sess = requests.Session()
        if not login(setup_sess, STUDENT_USER, STUDENT_PASS):
            result["pass"] = False
            result["errors"].append("Không login được SV để setup đơn PENDING")
            return result
        cancel_all_pending_of_student()
        try:
            setup_pending_request(setup_sess)
            student = store.get_user_by_credentials(STUDENT_USER, STUDENT_PASS)
            pending = store.list_requests_by_student(student["id"], limit=1)
            if pending:
                request_id = pending[0]["id"]
            else:
                result["pass"] = False
                result["errors"].append("Setup PENDING: không lấy được request_id")
                return result
        except Exception as e:
            result["pass"] = False
            result["errors"].append(f"Setup PENDING lỗi: {e}")
            return result

        # #27: YAML không có login → tự login STAFF trước khi chạy steps
        if sid == "27":
            if not login(session, STAFF_USER, STAFF_PASS):
                result["pass"] = False
                result["errors"].append("Không login được STAFF cho kịch bản #27")
                return result

    for i, step in enumerate(api_steps, start=1):
        method = (step.get("method") or "GET").upper()
        endpoint = step.get("endpoint", "")
        body = step.get("body")
        expected_status = step.get("expected_status", 200)
        expected_message = step.get("expected_message")
        expected_data = step.get("expected_data") or {}
        expected_db_status = step.get("expected_db_status")
        expected_fields = step.get("expected_fields") or []

        if "{id}" in endpoint:
            if request_id is None:
                result["pass"] = False
                result["errors"].append(f"Step {i}: endpoint cần {{id}} nhưng chưa có request_id")
                continue
            endpoint = endpoint.replace("{id}", str(request_id))

        url = f"{BASE_URL}{endpoint}"
        try:
            if method == "GET":
                r = session.get(url, timeout=TIMEOUT)
            elif method == "POST":
                r = session.post(url, json=body, timeout=TIMEOUT)
            elif method == "PUT":
                r = session.put(url, json=body, timeout=TIMEOUT)
            else:
                result["pass"] = False
                result["errors"].append(f"Step {i}: method {method} chưa hỗ trợ")
                continue
        except Exception as e:
            result["pass"] = False
            result["errors"].append(f"Step {i}: request lỗi – {e}")
            continue

        # 1. Status code
        if r.status_code != expected_status:
            result["pass"] = False
            result["errors"].append(
                f"Step {i} {method} {endpoint}: status mong đợi {expected_status}, "
                f"nhận {r.status_code} – {r.text[:200]}"
            )
            continue

        data = {}
        try:
            data = r.json()
        except Exception:
            pass

        # 2. Message (substring)
        if expected_message:
            actual_msg = str(data.get("message", ""))
            if expected_message.lower() not in actual_msg.lower():
                result["pass"] = False
                result["errors"].append(
                    f"Step {i}: message mong đợi chứa '{expected_message}', nhận '{actual_msg}'"
                )

        # 3. expected_data (role, …) — data nằm trong payload["data"]
        if expected_data:
            actual_data = data.get("data") if isinstance(data.get("data"), dict) else data
            for key, val in expected_data.items():
                if actual_data.get(key) != val:
                    result["pass"] = False
                    result["errors"].append(
                        f"Step {i}: data.{key} mong đợi '{val}', nhận '{actual_data.get(key)}'"
                    )

        # 4. expected_fields
        if expected_fields:
            actual_data = data.get("data") if isinstance(data.get("data"), dict) else data
            for field in expected_fields:
                if field not in actual_data:
                    result["pass"] = False
                    result["errors"].append(f"Step {i}: thiếu field '{field}' trong response")

        # 5. Bắt request_id từ response tạo đơn (#06)
        if method == "POST" and endpoint.rstrip("/").endswith("/api/student/requests"):
            created = data.get("data") if isinstance(data.get("data"), dict) else {}
            if created.get("id"):
                request_id = created["id"]

        # 6. DB status ngay sau bước
        if expected_db_status and request_id:
            req = store.get_request_by_id(request_id)
            actual = req["status"] if req else None
            if actual != expected_db_status:
                result["pass"] = False
                result["errors"].append(
                    f"Step {i}: DB status mong đợi '{expected_db_status}', thực tế '{actual}'"
                )

        print(f"    API Step {i}: {method} {endpoint} → {r.status_code}")

    # Final check DB
    final_check = scenario.get("final_check") or {}
    if final_check.get("db_status") and request_id:
        req = store.get_request_by_id(request_id)
        actual = req["status"] if req else None
        if actual != final_check["db_status"]:
            result["pass"] = False
            result["errors"].append(
                f"final_check db_status mong đợi '{final_check['db_status']}', thực tế '{actual}'"
            )
    elif final_check.get("db_status") and not request_id:
        # #06: nếu không bắt được id, fallback đơn mới nhất của SV
        latest = get_latest_student_request()
        actual = latest["status"] if latest else None
        if actual != final_check["db_status"]:
            result["pass"] = False
            result["errors"].append(
                f"final_check db_status mong đợi '{final_check['db_status']}', "
                f"thực tế '{actual}' (fallback latest)"
            )

    if final_check.get("has_history") and request_id:
        history = store.get_request_history(request_id)
        if not history:
            result["pass"] = False
            result["errors"].append("final_check has_history=True nhưng không có lịch sử")

    if final_check.get("has_evidence") is not None and request_id:
        ev = store.get_evidences_by_request(request_id)
        actual_ev = len(ev) > 0
        expected_ev = bool(final_check["has_evidence"])
        if actual_ev != expected_ev:
            result["pass"] = False
            result["errors"].append(
                f"has_evidence mong đợi {expected_ev} nhưng thực tế {actual_ev}"
            )

    return result

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
        # Kịch bản API-only → chạy thật bằng run_api_scenario
        return run_api_scenario(scenario)

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

        if contains_list:
            ok, missing = check_contains(bot_texts, contains_list)
            if not ok:
                result["pass"] = False
                result["errors"].append(
                    f"Turn {i}: thiếu từ khóa {missing} trong câu bot: {bot_texts}"
                )

    # === Kiểm tra final_check đầy đủ ===
    if final_check:
        latest = get_latest_student_request()

        # 1. db_status
        expected_status = final_check.get("db_status")
        if expected_status:
            actual_status = latest["status"] if latest else None
            if actual_status != expected_status:
                result["pass"] = False
                result["errors"].append(
                    f"DB status mong đợi '{expected_status}' nhưng thực tế '{actual_status}'"
                )

        # 2. has_evidence
        if "has_evidence" in final_check:
            expected_ev = bool(final_check["has_evidence"])
            actual_ev = bool(latest and latest.get("evidence_count", 0) > 0)
            if actual_ev != expected_ev:
                result["pass"] = False
                result["errors"].append(
                    f"has_evidence mong đợi {expected_ev} nhưng thực tế {actual_ev}"
                )

        # 3. expected_turn_count
        expected_turns = final_check.get("expected_turn_count")
        if expected_turns is not None and result["turn_count"] != expected_turns:
            result["pass"] = False
            result["errors"].append(
                f"Số turn mong đợi {expected_turns} nhưng thực tế {result['turn_count']}"
            )

    return result


def main():
    print("=" * 60)
    print("CHẠY BỘ KỊCH BẢN END-TO-END (chat + API)")
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

        # Phân loại: có turns = chat; không turns = API
        is_api = not (sc.get("turns") or [])

        if res["pass"] is None:
            print("  → SKIP\n")
        elif res["pass"]:
            kind = "API" if is_api else "chat"
            print(f"  → PASS ({kind}, turns={res['turn_count']})\n")
        else:
            kind = "API" if is_api else "chat"
            print(f"  → FAIL ({kind}, turns={res['turn_count']})")
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

    # Đếm riêng chat / API (để báo cáo CD4 / TCR rõ ràng)
    api_ids = {"06", "6", "24", "25", "26", "27", "30"}
    passed_api = [r for r in passed if str(r.get("id")) in api_ids]
    passed_chat = [r for r in passed if str(r.get("id")) not in api_ids]
    failed_api = [r for r in failed if str(r.get("id")) in api_ids]
    failed_chat = [r for r in failed if str(r.get("id")) not in api_ids]

    print("=" * 60)
    print("TỔNG HỢP KẾT QUẢ")
    print("=" * 60)
    print(f"Tổng file YAML        : {len(results)}")
    print(f"Đã chạy (executed)    : {total}")
    print(f"  - Pass              : {len(passed)}  (chat={len(passed_chat)}, API={len(passed_api)})")
    print(f"  - Fail              : {len(failed)}  (chat={len(failed_chat)}, API={len(failed_api)})")
    print(f"Skip                  : {len(skipped)}")
    print(f"TCR                   : {tcr:.2f}%   (= {len(passed)}/{total})")
    print(f"Average Turn Count    : {avg_turns:.2f}  (chỉ tính kịch bản chat pass)")
    print()

    if failed:
        print("Các kịch bản FAIL:")
        for r in failed:
            print(f"  - [{r['id']}] {r['name']}")
            for e in r["errors"]:
                print(f"      {e}")

    # Ghi file kết quả JSON (thêm chat/api counts cho báo cáo)
    out_path = Path(__file__).parent / "e2e_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "total_executed": total,
                "passed": len(passed),
                "failed": len(failed),
                "skipped": len(skipped),
                "passed_chat": len(passed_chat),
                "passed_api": len(passed_api),
                "failed_chat": len(failed_chat),
                "failed_api": len(failed_api),
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


if __name__ == "__main__":
    main()
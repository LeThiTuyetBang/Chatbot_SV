import hashlib
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, date
from typing import Any, Dict, Iterable, List, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "chatbot.db")

STATUS_PENDING = "PENDING"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"
STATUS_CANCELLED = "CANCELLED"

STATUS_LABELS = {
    STATUS_PENDING: "Chờ duyệt",
    STATUS_APPROVED: "Đã duyệt",
    STATUS_REJECTED: "Từ chối",
    STATUS_CANCELLED: "Đã Huỷ",
}

ALLOWED_TRANSITIONS = {
    STATUS_PENDING: {STATUS_APPROVED, STATUS_REJECTED, STATUS_CANCELLED},
}


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def parse_date_obj(date_str: str) -> Optional[date]:
    if not date_str:
        return None
    s = str(date_str).strip()
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        pass
    try:
        return datetime.strptime(s, "%d/%m/%Y").date()
    except ValueError:
        pass
    return None


def validate_date_range(start_date_str: str, end_date_str: str) -> None:
    d_start = parse_date_obj(start_date_str)
    d_end = parse_date_obj(end_date_str)
    if d_start and d_end and d_start > d_end:
        raise ValueError("Ngày kết thúc không được trước ngày bắt đầu.")


@contextmanager
def connect_db() -> Iterable[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return dict(row)


def _fetch_one(cursor: sqlite3.Cursor, query: str, params: tuple[Any, ...]) -> Optional[Dict[str, Any]]:
    cursor.execute(query, params)
    return row_to_dict(cursor.fetchone())


def resolve_user_id(cursor: sqlite3.Cursor, metadata: Dict[str, Any]) -> int:
    identifier = metadata.get("student_id") or metadata.get("username") or metadata.get("mssv")
    if identifier is None:
        return 1

    if isinstance(identifier, int):
        cursor.execute("SELECT id FROM Users WHERE id = ?", (identifier,))
        row = cursor.fetchone()
        return int(row["id"]) if row else 1

    identifier_text = str(identifier).strip()
    cursor.execute("SELECT id FROM Users WHERE username = ?", (identifier_text,))
    row = cursor.fetchone()
    if row:
        return int(row["id"])

    if identifier_text.isdigit():
        cursor.execute("SELECT id FROM Users WHERE id = ?", (int(identifier_text),))
        row = cursor.fetchone()
        if row:
            return int(row["id"])

    return 1


def resolve_user_id_from_metadata(metadata: Dict[str, Any]) -> int:
    identifier = metadata.get("student_id") or metadata.get("username") or metadata.get("mssv")
    if identifier is None:
        return 1

    with connect_db() as conn:
        cursor = conn.cursor()
        if isinstance(identifier, int):
            cursor.execute("SELECT id FROM Users WHERE id = ?", (identifier,))
            row = cursor.fetchone()
            return int(row["id"]) if row else 1

        identifier_text = str(identifier).strip()
        cursor.execute("SELECT id FROM Users WHERE username = ?", (identifier_text,))
        row = cursor.fetchone()
        if row:
            return int(row["id"])

        if identifier_text.isdigit():
            cursor.execute("SELECT id FROM Users WHERE id = ?", (int(identifier_text),))
            row = cursor.fetchone()
            if row:
                return int(row["id"])

    return 1


def get_user_by_credentials(username: str, password: str) -> Optional[Dict[str, Any]]:
    password_hash = hash_password(password)
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, username, full_name, role, class_code
            FROM Users
            WHERE username = ? AND password_hash = ?
            """,
            (username, password_hash),
        )
        return row_to_dict(cursor.fetchone())


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, username, full_name, role, class_code
            FROM Users
            WHERE id = ?
            """,
            (user_id,),
        )
        return row_to_dict(cursor.fetchone())


def create_absence_request(
    student_id: int,
    course_code: str,
    class_code: str,
    start_date: str,
    end_date: str,
    reason: str,
    created_by: Optional[int] = None,
    source: str = "form",  # "form" | "chatbot"
) -> int:
    validate_date_range(start_date, end_date)
    actor_id = created_by or student_id
    with connect_db() as conn:
        cursor = conn.cursor()
        user_info = _fetch_one(cursor, "SELECT full_name FROM Users WHERE id = ?", (actor_id,))
        actor_name = user_info["full_name"] if user_info else f"Sinh viên #{actor_id}"

        cursor.execute(
            """
            INSERT INTO AbsenceRequests (
                student_id, course_code, class_code, start_date, end_date, reason, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (student_id, course_code, class_code, start_date, end_date, reason, STATUS_PENDING),
        )
        request_id = cursor.lastrowid

        # Ghi chú lịch sử rõ nguồn tạo đơn
        if source == "chatbot":
            history_note = f"{actor_name} đã tạo đơn xin nghỉ học qua Chatbot"
        else:
            history_note = f"{actor_name} đã tạo đơn xin nghỉ học qua Form web"

        cursor.execute(
            """
            INSERT INTO RequestStatusHistory (request_id, old_status, new_status, changed_by, note)
            VALUES (?, NULL, ?, ?, ?)
            """,
            (request_id, STATUS_PENDING, actor_id, history_note),
        )
        return int(request_id)


def add_evidence(request_id: int, file_name: str, file_url: str) -> int:
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO Evidences (request_id, file_name, file_url)
            VALUES (?, ?, ?)
            """,
            (request_id, file_name, file_url),
        )
        return int(cursor.lastrowid)


def get_evidences_by_request(request_id: int) -> List[Dict[str, Any]]:
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, request_id, file_name, file_url, uploaded_at
            FROM Evidences
            WHERE request_id = ?
            ORDER BY uploaded_at ASC, id ASC
            """,
            (request_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_request_by_id(request_id: int) -> Optional[Dict[str, Any]]:
    with connect_db() as conn:
        cursor = conn.cursor()
        req = _fetch_one(
            cursor,
            """
            SELECT ar.id, ar.student_id, u.username AS student_username, u.full_name AS student_name,
                   u.class_code AS student_class_code,
                   ar.course_code, ar.class_code, ar.start_date, ar.end_date, ar.reason, ar.status,
                   ar.created_at
            FROM AbsenceRequests ar
            LEFT JOIN Users u ON u.id = ar.student_id
            WHERE ar.id = ?
            """,
            (request_id,),
        )
        if not req:
            return None

        cursor.execute(
            """
            SELECT rsh.note, rsh.changed_at, u.full_name AS handler_name
            FROM RequestStatusHistory rsh
            LEFT JOIN Users u ON u.id = rsh.changed_by
            WHERE rsh.request_id = ? AND rsh.new_status IN ('APPROVED', 'REJECTED', 'CANCELLED')
            ORDER BY rsh.changed_at DESC, rsh.id DESC
            LIMIT 1
            """,
            (request_id,),
        )
        last_action = cursor.fetchone()
        if last_action:
            req["handler_name"] = last_action["handler_name"]
            req["handled_at"] = last_action["changed_at"]
            req["last_note"] = last_action["note"]
        else:
            req["handler_name"] = None
            req["handled_at"] = None
            req["last_note"] = None

        return req


def list_requests(status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    query = """
        SELECT ar.id, ar.student_id, u.username AS student_username, u.full_name AS student_name,
               ar.course_code, ar.class_code, ar.start_date, ar.end_date, ar.reason, ar.status,
               ar.created_at
        FROM AbsenceRequests ar
        LEFT JOIN Users u ON u.id = ar.student_id
    """
    params: List[Any] = []
    if status:
        query += " WHERE ar.status = ?"
        params.append(status)
    query += " ORDER BY ar.created_at DESC, ar.id DESC LIMIT ?"
    params.append(limit)

    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        return [dict(row) for row in cursor.fetchall()]


def list_requests_by_student(student_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, course_code, class_code, start_date, end_date, reason, status, created_at
            FROM AbsenceRequests
            WHERE student_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (student_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]


def update_request_status(
    request_id: int,
    new_status: str,
    changed_by: int,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    if new_status not in STATUS_LABELS:
        raise ValueError(f"Trạng thái không hợp lệ: {new_status}")

    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, status FROM AbsenceRequests WHERE id = ?", (request_id,))
        current_row = cursor.fetchone()
        if current_row is None:
            raise ValueError(f"Không tìm thấy đơn #{request_id}")

        current_status = current_row["status"]
        if current_status == new_status:
            return get_request_by_id(request_id) or {}

        allowed = ALLOWED_TRANSITIONS.get(current_status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Không thể chuyển trạng thái đơn từ [{STATUS_LABELS.get(current_status, current_status)}] "
                f"sang [{STATUS_LABELS.get(new_status, new_status)}]"
            )

        cursor.execute(
            "UPDATE AbsenceRequests SET status = ? WHERE id = ? AND status = ?",
            (new_status, request_id, current_status),
        )
        if cursor.rowcount == 0:
            raise ValueError("Đơn này đã được xử lý trước đó bởi người khác.")

        user_info = _fetch_one(cursor, "SELECT full_name FROM Users WHERE id = ?", (changed_by,))
        user_name = user_info["full_name"] if user_info else f"Người dùng #{changed_by}"

        default_note = f"{user_name} đã cập nhật trạng thái đơn thành {STATUS_LABELS.get(new_status, new_status)}"
        if new_status == STATUS_APPROVED:
            default_note = f"{user_name} đã duyệt đơn"
        elif new_status == STATUS_REJECTED:
            default_note = f"{user_name} đã từ chối đơn"
        elif new_status == STATUS_CANCELLED:
            default_note = f"{user_name} đã huỷ đơn"

        cursor.execute(
            """
            INSERT INTO RequestStatusHistory (request_id, old_status, new_status, changed_by, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (request_id, current_status, new_status, changed_by, note or default_note),
        )
        return get_request_by_id(request_id) or {}


def update_staff_decision(
    request_id: int,
    new_status: str,
    changed_by: int,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    if new_status not in (STATUS_APPROVED, STATUS_REJECTED):
        raise ValueError("Giáo vụ chỉ được phép chuyển trạng thái đơn thành Đã duyệt hoặc Từ chối.")

    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, status FROM AbsenceRequests WHERE id = ?", (request_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Không tìm thấy đơn #{request_id}")

        current_status = row["status"]
        if current_status not in (STATUS_APPROVED, STATUS_REJECTED):
            raise ValueError("Chỉ có thể chỉnh sửa kết quả duyệt/từ chối của những đơn đã được xử lý trước đó.")

        if current_status == new_status:
            return get_request_by_id(request_id) or {}

        cursor.execute(
            "UPDATE AbsenceRequests SET status = ? WHERE id = ?",
            (new_status, request_id),
        )

        user_info = _fetch_one(cursor, "SELECT full_name FROM Users WHERE id = ?", (changed_by,))
        user_name = user_info["full_name"] if user_info else f"Giáo vụ #{changed_by}"

        old_label = STATUS_LABELS.get(current_status, current_status)
        new_label = STATUS_LABELS.get(new_status, new_status)
        history_note = note or f"{user_name} đã điều chỉnh kết quả đơn từ [{old_label}] sang [{new_label}]"

        cursor.execute(
            """
            INSERT INTO RequestStatusHistory (request_id, old_status, new_status, changed_by, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (request_id, current_status, new_status, changed_by, history_note),
        )
        return get_request_by_id(request_id) or {}


def cancel_latest_pending_request(student_id: int, changed_by: int, note: Optional[str] = None) -> Optional[Dict[str, Any]]:
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id
            FROM AbsenceRequests
            WHERE student_id = ? AND status = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (student_id, STATUS_PENDING),
        )
        row = cursor.fetchone()
        if row is None:
            return None

    return update_request_status(
        int(row["id"]),
        STATUS_CANCELLED,
        changed_by,
        note or "Sinh viên đã huỷ đơn gần nhất",
    )


def get_request_history(request_id: int) -> List[Dict[str, Any]]:
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT rsh.id, rsh.request_id, rsh.old_status, rsh.new_status, rsh.changed_by, rsh.note, rsh.changed_at,
                   u.full_name AS changer_name, u.role AS changer_role, u.username AS changer_username
            FROM RequestStatusHistory rsh
            LEFT JOIN Users u ON u.id = rsh.changed_by
            WHERE rsh.request_id = ?
            ORDER BY rsh.changed_at ASC, rsh.id ASC
            """,
            (request_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_status_counts() -> Dict[str, int]:
    counts = {status: 0 for status in STATUS_LABELS}
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, COUNT(*) AS total FROM AbsenceRequests GROUP BY status")
        for row in cursor.fetchall():
            counts[row["status"]] = row["total"]
    return counts


def label_status(status: str) -> str:
    return STATUS_LABELS.get(status, status)

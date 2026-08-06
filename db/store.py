import hashlib
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
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


def create_absence_request(
    student_id: int,
    course_code: str,
    class_code: str,
    start_date: str,
    end_date: str,
    reason: str,
    created_by: Optional[int] = None,
) -> int:
    actor_id = created_by or student_id
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO AbsenceRequests (
                student_id, course_code, class_code, start_date, end_date, reason, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (student_id, course_code, class_code, start_date, end_date, reason, STATUS_PENDING),
        )
        request_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT INTO RequestStatusHistory (request_id, old_status, new_status, changed_by, note)
            VALUES (?, NULL, ?, ?, ?)
            """,
            (request_id, STATUS_PENDING, actor_id, "Sinh viên nộp đơn xin nghỉ học qua chatbot"),
        )
        return int(request_id)


def get_request_by_id(request_id: int) -> Optional[Dict[str, Any]]:
    with connect_db() as conn:
        cursor = conn.cursor()
        return _fetch_one(
            cursor,
            """
            SELECT ar.id, ar.student_id, u.username AS student_username, u.full_name AS student_name,
                   ar.course_code, ar.class_code, ar.start_date, ar.end_date, ar.reason, ar.status,
                   ar.created_at
            FROM AbsenceRequests ar
            LEFT JOIN Users u ON u.id = ar.student_id
            WHERE ar.id = ?
            """,
            (request_id,),
        )


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


def list_requests_by_student(student_id: int, limit: int = 10) -> List[Dict[str, Any]]:
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
            raise ValueError(f"Không thể chuyển từ {current_status} sang {new_status}")

        cursor.execute(
            "UPDATE AbsenceRequests SET status = ? WHERE id = ?",
            (new_status, request_id),
        )
        cursor.execute(
            """
            INSERT INTO RequestStatusHistory (request_id, old_status, new_status, changed_by, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (request_id, current_status, new_status, changed_by, note or f"Chuyển trạng thái sang {new_status}"),
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
        note or "Sinh viên yêu cầu huỷ đơn qua chatbot hoặc giao diện quản lý",
    )


def get_request_history(request_id: int) -> List[Dict[str, Any]]:
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, request_id, old_status, new_status, changed_by, note, changed_at
            FROM RequestStatusHistory
            WHERE request_id = ?
            ORDER BY changed_at ASC, id ASC
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


def format_request_summary(request: Dict[str, Any]) -> str:
    return (
        f"#{request['id']}: {request['course_code']} | lớp {request['class_code']} | "
        f"{request['start_date']} đến {request['end_date']} | {label_status(request['status'])}"
    )

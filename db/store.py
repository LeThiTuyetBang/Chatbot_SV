import hashlib
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, date, timedelta
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

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


from werkzeug.security import generate_password_hash, check_password_hash

def hash_password(password: str) -> str:
    """Băm mật khẩu bằng thuật toán an toàn (pbkdf2:sha256 + salt)."""
    return generate_password_hash(password)

def check_password(password_hash: str, password: str) -> bool:
    """Kiểm tra mật khẩu."""
    return check_password_hash(password_hash, password)


def parse_date_obj(date_str: str) -> Optional[date]:
    if not date_str:
        return None
    s = str(date_str).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def normalize_date(date_str: str) -> str:
    """Chuẩn hóa về YYYY-MM-DD. Ném ValueError nếu không parse được."""
    d = parse_date_obj(date_str)
    if d is None:
        raise ValueError(
            f"Ngày không hợp lệ hoặc sai định dạng: '{date_str}'. "
            "Ví dụ đúng: 2026-09-25 hoặc 25/09/2026"
        )
    return d.isoformat()


def validate_evidence_url(url: str) -> str:
    """
    Chỉ chấp nhận http/https thuần túy, loại bỏ các scheme nguy hiểm như javascript:.
    Ném ValueError nếu không hợp lệ hoặc quá dài.
    """
    if not url or not url.strip():
        return ""   # Cho phép để trống (không có minh chứng)

    url = url.strip()
    if len(url) > 500:
        raise ValueError("Link minh chứng quá dài (tối đa 500 ký tự).")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            "Link minh chứng chỉ được phép dùng http hoặc https. "
            f"Scheme '{parsed.scheme or 'không có'}' không được chấp nhận."
        )
    if not parsed.netloc:
        raise ValueError("Link minh chứng không hợp lệ.")
        
    # Chặn bổ sung các trường hợp chèn mã độc qua scheme
    lowered_url = url.lower()
    if "javascript:" in lowered_url or "data:" in lowered_url or "vbscript:" in lowered_url:
        raise ValueError("Link minh chứng chứa định dạng không được phép.")

    return url


def validate_date_range(
    start_date_str: str,
    end_date_str: str,
    allow_past_days: int = 0,      # 0 = không cho phép ngày quá khứ
    max_future_days: int = 90,     # tối đa 90 ngày trong tương lai
    max_duration_days: int = 30,   # khoảng nghỉ tối đa 30 ngày
) -> tuple[str, str]:
    """
    Validate + chuẩn hóa cả hai ngày.
    - Ném ValueError nếu một trong hai ngày không parse được.
    - Ném ValueError nếu start > end.
    - Ném ValueError nếu ngày bắt đầu nằm trong quá khứ (mặc định).
    - Ném ValueError nếu khoảng nghỉ quá dài hoặc quá xa trong tương lai.
    Trả về (normalized_start, normalized_end) dạng YYYY-MM-DD.
    """
    start_norm = normalize_date(start_date_str)
    end_norm = normalize_date(end_date_str)

    d_start = date.fromisoformat(start_norm)
    d_end = date.fromisoformat(end_norm)
    today = date.today()

    # 1. start không được sau end
    if d_start > d_end:
        raise ValueError("Ngày kết thúc không được trước ngày bắt đầu.")

    # 2. Chặn ngày quá khứ
    earliest_allowed = today - timedelta(days=allow_past_days)
    if d_start < earliest_allowed:
        if allow_past_days == 0:
            raise ValueError(
                f"Không được xin nghỉ ngày trong quá khứ (ngày bắt đầu {start_norm}). "
                "Vui lòng chọn từ hôm nay trở đi."
            )
        else:
            raise ValueError(
                f"Ngày bắt đầu không được quá {allow_past_days} ngày trước hôm nay."
            )

    # 3. Giới hạn khoảng nghỉ quá dài
    if (d_end - d_start).days > max_duration_days:
        raise ValueError(
            f"Khoảng thời gian xin nghỉ không được vượt quá {max_duration_days} ngày."
        )

    # 4. Không cho xin quá xa trong tương lai
    if d_start > today + timedelta(days=max_future_days):
        raise ValueError(
            f"Ngày bắt đầu không được quá xa trong tương lai (tối đa {max_future_days} ngày)."
        )

    return start_norm, end_norm

def has_overlapping_request(
    student_id: int,
    course_code: str,
    start_date: str,
    end_date: str,
    exclude_request_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Kiểm tra xem sinh viên đã có đơn PENDING hoặc APPROVED
    chồng lấn khoảng ngày với cùng môn học chưa.
    Trả về dict đơn bị chồng nếu có, None nếu không.
    """
    with connect_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT id, course_code, start_date, end_date, status, reason
            FROM AbsenceRequests
            WHERE student_id = ?
              AND LOWER(course_code) = LOWER(?)
              AND status IN ('PENDING', 'APPROVED')
              AND NOT (end_date < ? OR start_date > ?)
        """
        params: list = [student_id, course_code, start_date, end_date]

        if exclude_request_id is not None:
            query += " AND id != ?"
            params.append(exclude_request_id)

        cursor.execute(query, tuple(params))
        row = cursor.fetchone()
        return row_to_dict(row) if row else None


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

import yaml 

_SUBJECTS_CACHE: Optional[List[str]] = None
_SUBJECTS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "subjects.yml")


def get_known_subjects(include_from_db: bool = True) -> List[str]:
    """
    Đọc danh sách môn từ data/subjects.yml.
    Nếu include_from_db=True: gộp thêm course_code từng xuất hiện trong AbsenceRequests
    (để không phải sửa code khi đã có đơn với môn mới).
    """
    global _SUBJECTS_CACHE
    if _SUBJECTS_CACHE is not None:
        return list(_SUBJECTS_CACHE)

    names: List[str] = []

    # 1) Từ file cấu hình
    path = os.path.abspath(_SUBJECTS_PATH)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            raw = data.get("subjects") or []
            for item in raw:
                s = str(item).strip()
                if s and s not in names:
                    names.append(s)
        except Exception:
            pass  # file lỗi → vẫn có thể lấy từ DB

    # 2) Từ DB (các môn đã từng nộp đơn)
    if include_from_db:
        try:
            with connect_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT DISTINCT course_code
                    FROM AbsenceRequests
                    WHERE course_code IS NOT NULL AND TRIM(course_code) != ''
                    ORDER BY course_code
                    """
                )
                for row in cursor.fetchall():
                    s = (row["course_code"] or "").strip()
                    if s and not any(s.lower() == x.lower() for x in names):
                        names.append(s)
        except Exception:
            pass

    # Fallback tối thiểu nếu cả YAML + DB trống
    if not names:
        names = [
            "Lập trình Python",
            "Cơ sở dữ liệu",
            "CSDL",
            "Mạng máy tính",
            "Kiểm thử phần mềm",
        ]

    _SUBJECTS_CACHE = names
    return list(names)


def clear_known_subjects_cache() -> None:
    """Gọi sau khi sửa subjects.yml (hoặc trong test)."""
    global _SUBJECTS_CACHE
    _SUBJECTS_CACHE = None

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


def resolve_user_id_from_metadata(metadata: Dict[str, Any]) -> Optional[int]:
    """
    Trả về user_id nếu tìm thấy, None nếu thiếu metadata hoặc không tồn tại.
    Không bao giờ fallback về user_id = 1.
    """
    if not metadata:
        return None

    identifier = metadata.get("student_id") or metadata.get("username") or metadata.get("mssv")
    if identifier is None:
        return None

    with connect_db() as conn:
        cursor = conn.cursor()

        if isinstance(identifier, int):
            cursor.execute("SELECT id FROM Users WHERE id = ?", (identifier,))
            row = cursor.fetchone()
            return int(row["id"]) if row else None

        identifier_text = str(identifier).strip()
        if not identifier_text:
            return None

        cursor.execute("SELECT id FROM Users WHERE username = ?", (identifier_text,))
        row = cursor.fetchone()
        if row:
            return int(row["id"])

        if identifier_text.isdigit():
            cursor.execute("SELECT id FROM Users WHERE id = ?", (int(identifier_text),))
            row = cursor.fetchone()
            if row:
                return int(row["id"])

    return None


def get_user_by_credentials(username: str, password: str) -> Optional[Dict[str, Any]]:
    with connect_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, username, password_hash, full_name, role, class_code
            FROM Users
            WHERE username = ?
            """,
            (username,),
        )
        row = cursor.fetchone()
        if row and check_password(row["password_hash"], password):
            user = dict(row)
            del user["password_hash"]   # không trả password_hash ra ngoài
            return user
        return None


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
    # 1. Validate ngày (đã chặn quá khứ + khoảng quá dài)
    start_date, end_date = validate_date_range(start_date, end_date)

    # 2. Kiểm tra đơn trùng / chồng lấn
    overlap = has_overlapping_request(
        student_id=student_id,
        course_code=course_code,
        start_date=start_date,
        end_date=end_date,
    )
    if overlap:
        status_label = STATUS_LABELS.get(overlap["status"], overlap["status"])
        raise ValueError(
            f"Bạn đã có đơn #{overlap['id']} ({status_label}) "
            f"cho môn {course_code} từ {overlap['start_date']} đến {overlap['end_date']}. "
            "Không được nộp đơn chồng lấn khoảng ngày."
        )

    actor_id = created_by or student_id
    with connect_db() as conn:
        # ... phần còn lại giữ nguyên hoàn toàn
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
    file_url = validate_evidence_url(file_url)   # ← thêm dòng này
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
    """
    Giáo vụ chỉ được duyệt / từ chối đơn đang ở trạng thái PENDING.
    Không cho phép đổi trạng thái cuối (APPROVED / REJECTED / CANCELLED).
    """
    if new_status not in (STATUS_APPROVED, STATUS_REJECTED):
        raise ValueError("Giáo vụ chỉ được phép chuyển trạng thái đơn thành Đã duyệt hoặc Từ chối.")

    # Dùng chung logic với update_request_status → tôn trọng ALLOWED_TRANSITIONS
    return update_request_status(
        request_id=request_id,
        new_status=new_status,
        changed_by=changed_by,
        note=note,
    )


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

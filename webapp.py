import json
import os
import queue
import threading
from functools import wraps
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from flask import Flask, Response, jsonify, render_template, request, session

from db.store import (
    STATUS_APPROVED,
    STATUS_CANCELLED,
    STATUS_LABELS,
    STATUS_PENDING,
    STATUS_REJECTED,
    add_evidence,
    cancel_latest_pending_request,
    create_absence_request,
    update_staff_decision,
    get_evidences_by_request,
    get_request_by_id,
    get_request_history,
    get_status_counts,
    get_user_by_credentials,
    get_user_by_id,
    list_requests,
    list_requests_by_student,
    resolve_user_id_from_metadata,
    update_request_status,
    validate_date_range,
)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.environ.get("SECRET_KEY", "chatbot_sv_secure_key_2026_antigravity")

RASA_REST_URL = os.environ.get("RASA_REST_URL", "http://localhost:5005/webhooks/rest/webhook")

# Thread-safe event bus for SSE Realtime
sse_listeners = []
sse_lock = threading.Lock()


def broadcast_event(event_type: str, data: dict):
    """Broadcasting events to all SSE subscribers"""
    msg = f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
    with sse_lock:
        dead = []
        for q in sse_listeners:
            try:
                q.put_nowait(msg)
            except queue.Full:
                dead.append(q)
        for q in dead:
            if q in sse_listeners:
                sse_listeners.remove(q)


def _json_response(data=None, message: str = "", ok: bool = True, status_code: int = 200):
    payload = {"ok": ok}
    if message:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status_code


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            return _json_response(
                message="Vui lòng đăng nhập trước khi sử dụng hệ thống.",
                ok=False,
                status_code=401,
            )
        return f(*args, **kwargs)

    return decorated_function


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get("user_id"):
                return _json_response(
                    message="Vui lòng đăng nhập trước khi sử dụng hệ thống.",
                    ok=False,
                    status_code=401,
                )
            user_role = session.get("role")
            if user_role not in roles:
                return _json_response(
                    message="Bạn không có quyền thực hiện thao tác này.",
                    ok=False,
                    status_code=403,
                )
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def _rasa_send_message(sender: str, message_text: str, metadata: dict) -> list[dict]:
    body = json.dumps({"sender": sender, "message": message_text, "metadata": metadata}).encode("utf-8")
    request_obj = Request(
        RASA_REST_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request_obj, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except (URLError, HTTPError) as error:
        raise RuntimeError(f"Không kết nối được Rasa REST API: {error}") from error


@app.get("/")
def index():
    return render_template(
        "index.html",
        status_labels=STATUS_LABELS,
        status_counts=get_status_counts(),
        active_view="student",
    )


@app.get("/admin")
def admin_view():
    return render_template(
        "index.html",
        status_labels=STATUS_LABELS,
        status_counts=get_status_counts(),
        active_view="admin",
    )


@app.get("/api/events")
def sse_events():
    def stream():
        q = queue.Queue(maxsize=50)
        with sse_lock:
            sse_listeners.append(q)
        yield "event: ping\ndata: {}\n\n"
        try:
            while True:
                try:
                    msg = q.get(timeout=20)
                    yield msg
                except queue.Empty:
                    yield ": keep-alive\n\n"
        finally:
            with sse_lock:
                if q in sse_listeners:
                    sse_listeners.remove(q)

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/auth/login")
def login():
    payload = request.get_json(force=True, silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    if not username or not password:
        return _json_response(message="Thiếu tên đăng nhập hoặc mật khẩu.", ok=False, status_code=400)

    user = get_user_by_credentials(username, password)
    if not user:
        return _json_response(message="Sai tên đăng nhập hoặc mật khẩu.", ok=False, status_code=401)

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]
    session["full_name"] = user["full_name"]
    session["class_code"] = user.get("class_code")

    return _json_response(data=user, message=f"Đăng nhập thành công với vai trò {user['role']}.")


@app.get("/favicon.ico")
def favicon():
    return "", 204


@app.get("/api/auth/me")
def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return _json_response(data=None, message="Chưa đăng nhập.", ok=False, status_code=200)
    user = get_user_by_id(user_id)
    if not user:
        session.clear()
        return _json_response(data=None, message="Tài khoản không còn tồn tại.", ok=False, status_code=200)
    return _json_response(data=user, message="Thông tin phiên đăng nhập hiện tại.")


@app.post("/api/auth/logout")
def logout():
    session.clear()
    return _json_response(message="Đã đăng xuất thành công.")


@app.post("/api/student/requests")
@role_required("STUDENT")
def student_create_request():
    payload = request.get_json(force=True, silent=True) or {}
    student_id = session["user_id"]
    course_code = (payload.get("course_code") or "").strip()
    class_code = (payload.get("class_code") or session.get("class_code") or "").strip()
    start_date = (payload.get("start_date") or "").strip()
    end_date = (payload.get("end_date") or "").strip()
    reason = (payload.get("reason") or "").strip()
    evidence_url = (payload.get("evidence_url") or "").strip()

    if not course_code or not start_date or not end_date or not reason:
        return _json_response(
            message="Vui lòng điền đầy đủ môn học, lớp, ngày bắt đầu, ngày kết thúc và lý do.",
            ok=False,
            status_code=400,
        )

    try:
        validate_date_range(start_date, end_date)
    except ValueError as ve:
        return _json_response(message=str(ve), ok=False, status_code=400)

    try:
        req_id = create_absence_request(
            student_id=student_id,
            course_code=course_code,
            class_code=class_code or "DTH2151",
            start_date=start_date,
            end_date=end_date,
            reason=reason,
            created_by=student_id,
        )
        if evidence_url:
            add_evidence(request_id=req_id, file_name="minh_chung", file_url=evidence_url)

        request_data = get_request_by_id(req_id)
        broadcast_event("request_created", {"request_id": req_id, "student_id": student_id})
        return _json_response(data=request_data, message="Gửi đơn thành công.")
    except Exception as e:
        return _json_response(message=f"Gửi đơn thất bại: {str(e)}", ok=False, status_code=400)


@app.get("/api/student/requests")
@role_required("STUDENT")
def student_requests():
    student_id = session["user_id"]
    return _json_response(
        data={
            "requests": list_requests_by_student(student_id=student_id, limit=50),
            "status_counts": get_status_counts(),
        },
        message="Danh sách đơn của sinh viên.",
    )


@app.post("/api/student/requests/<int:request_id>/cancel")
@role_required("STUDENT")
def student_cancel_request(request_id: int):
    student_id = session["user_id"]
    req = get_request_by_id(request_id)
    if not req:
        return _json_response(message="Không tìm thấy đơn.", ok=False, status_code=404)
    if req["student_id"] != student_id:
        return _json_response(message="Bạn không có quyền huỷ đơn của sinh viên khác.", ok=False, status_code=403)
    if req["status"] != STATUS_PENDING:
        return _json_response(message="Chỉ được huỷ đơn khi đơn đang ở trạng thái Chờ duyệt.", ok=False, status_code=400)

    try:
        updated = update_request_status(
            request_id=request_id,
            new_status=STATUS_CANCELLED,
            changed_by=student_id,
            note="Sinh viên đã huỷ đơn xin nghỉ",
        )
        broadcast_event("request_updated", {"request_id": request_id, "status": STATUS_CANCELLED})
        return _json_response(data=updated, message="Đã huỷ đơn thành công.")
    except Exception as error:
        return _json_response(message=str(error), ok=False, status_code=400)


@app.post("/api/student/cancel-latest")
@role_required("STUDENT")
def student_cancel_latest():
    student_id = session["user_id"]
    try:
        updated = cancel_latest_pending_request(
            student_id=student_id,
            changed_by=student_id,
            note="Sinh viên yêu cầu huỷ đơn gần nhất",
        )
    except Exception as error:
        return _json_response(message=str(error), ok=False, status_code=400)

    if not updated:
        return _json_response(message="Không có đơn Chờ duyệt nào để huỷ.", ok=False, status_code=404)

    broadcast_event("request_updated", {"request_id": updated["id"], "status": STATUS_CANCELLED})
    return _json_response(data=updated, message="Đã huỷ đơn thành công.")


@app.post("/api/student/reset-draft")
@login_required
def student_reset_draft():
    return _json_response(message="Đã huỷ quá trình viết đơn và xoá draft thành công.")


@app.get("/api/admin/requests")
@role_required("STAFF")
def admin_requests():
    status = request.args.get("status")
    status_filter = status.strip() if status and status.strip() else None
    requests_data = list_requests(status=status_filter, limit=100)
    return _json_response(
        data={
            "requests": requests_data,
            "status_counts": get_status_counts(),
        },
        message="Danh sách quản lý đơn.",
    )


@app.get("/api/admin/requests/<int:request_id>")
@login_required
def request_detail(request_id: int):
    request_data = get_request_by_id(request_id)
    if not request_data:
        return _json_response(message="Không tìm thấy đơn.", ok=False, status_code=404)

    user_role = session.get("role")
    user_id = session.get("user_id")
    if user_role == "STUDENT" and request_data["student_id"] != user_id:
        return _json_response(message="Bạn không có quyền xem đơn này.", ok=False, status_code=403)

    request_data["history"] = get_request_history(request_id)
    request_data["evidences"] = get_evidences_by_request(request_id)
    request_data["status_label"] = STATUS_LABELS.get(request_data["status"], request_data["status"])
    return _json_response(data=request_data, message="Chi tiết đơn.")


@app.post("/api/admin/requests/<int:request_id>/approve")
@role_required("STAFF")
def approve_request(request_id: int):
    admin_id = session["user_id"]
    try:
        updated = update_request_status(
            request_id=request_id,
            new_status=STATUS_APPROVED,
            changed_by=admin_id,
            note="Giáo vụ đã duyệt đơn xin nghỉ học",
        )
        broadcast_event("request_updated", {"request_id": request_id, "status": STATUS_APPROVED})
        return _json_response(data=updated, message="Duyệt đơn thành công.")
    except Exception as error:
        status_code = 409 if "xử lý trước đó" in str(error) else 400
        return _json_response(message=str(error), ok=False, status_code=status_code)


@app.post("/api/admin/requests/<int:request_id>/reject")
@role_required("STAFF")
def reject_request(request_id: int):
    payload = request.get_json(force=True, silent=True) or {}
    admin_id = session["user_id"]
    reject_reason = (payload.get("note") or payload.get("reason") or "").strip()
    note_text = f"Giáo vụ đã từ chối đơn. Lý do: {reject_reason}" if reject_reason else "Giáo vụ đã từ chối đơn"

    try:
        updated = update_request_status(
            request_id=request_id,
            new_status=STATUS_REJECTED,
            changed_by=admin_id,
            note=note_text,
        )
        broadcast_event("request_updated", {"request_id": request_id, "status": STATUS_REJECTED})
        return _json_response(data=updated, message="Đã từ chối đơn.")
    except Exception as error:
        status_code = 409 if "xử lý trước đó" in str(error) else 400
        return _json_response(message=str(error), ok=False, status_code=status_code)


@app.put("/api/admin/requests/<int:request_id>")
@role_required("STAFF")
def edit_request(request_id: int):
    payload = request.get_json(force=True, silent=True) or {}
    admin_id = session["user_id"]
    new_status = (payload.get("new_status") or "").strip()
    note = (payload.get("note") or "").strip()

    if new_status not in (STATUS_APPROVED, STATUS_REJECTED):
        return _json_response(message="Trạng thái chuyển đổi không hợp lệ. Chỉ được chuyển sang Đã duyệt hoặc Từ chối.", ok=False, status_code=400)

    try:
        updated = update_staff_decision(
            request_id=request_id,
            new_status=new_status,
            changed_by=admin_id,
            note=note,
        )
        broadcast_event("request_updated", {"request_id": request_id, "status": updated["status"]})
        return _json_response(data=updated, message=f"Đã điều chỉnh trạng thái đơn thành [{STATUS_LABELS[new_status]}].")
    except Exception as error:
        return _json_response(message=str(error), ok=False, status_code=400)


@app.post("/api/chat")
@login_required
def chat():
    payload = request.get_json(force=True, silent=True) or {}
    sender = session.get("username", "student")
    message_text = (payload.get("message") or "").strip()
    metadata = {
        "student_id": session.get("user_id"),
        "username": session.get("username"),
        "class_code": session.get("class_code"),
    }
    if not message_text:
        return _json_response(message="Tin nhắn không được để trống.", ok=False, status_code=400)

    try:
        responses = _rasa_send_message(sender, message_text, metadata)
    except RuntimeError as error:
        return _json_response(message=str(error), ok=False, status_code=502)

    return _json_response(data=responses, message="Đã gửi đến chatbot.")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)

import json
import os
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from flask import Flask, jsonify, render_template, request

from db.store import (
    STATUS_APPROVED,
    STATUS_CANCELLED,
    STATUS_LABELS,
    STATUS_PENDING,
    STATUS_REJECTED,
    cancel_latest_pending_request,
    get_request_history,
    get_request_by_id,
    get_status_counts,
    get_user_by_credentials,
    list_requests,
    list_requests_by_student,
    resolve_user_id_from_metadata,
    update_request_status,
)

app = Flask(__name__, template_folder="templates", static_folder="static")

RASA_REST_URL = os.environ.get("RASA_REST_URL", "http://localhost:5005/webhooks/rest/webhook")
DEFAULT_STUDENT_ID = 1
DEFAULT_ADMIN_ID = 2


def _json_response(data=None, message: str = "", ok: bool = True, status_code: int = 200):
    payload = {"ok": ok}
    if message:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status_code


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


@app.post("/api/auth/login")
def login():
    payload = request.get_json(force=True, silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    if not username or not password:
        return _json_response(message="Thiếu username hoặc password.", ok=False, status_code=400)

    user = get_user_by_credentials(username, password)
    if not user:
        return _json_response(message="Sai username hoặc password.", ok=False, status_code=401)

    return _json_response(data=user, message="Đăng nhập mô phỏng thành công.")


@app.post("/api/chat")
def chat():
    payload = request.get_json(force=True, silent=True) or {}
    sender = (payload.get("sender") or "student").strip() or "student"
    message_text = (payload.get("message") or "").strip()
    metadata = payload.get("metadata") or {}
    if not message_text:
        return _json_response(message="Tin nhắn không được để trống.", ok=False, status_code=400)

    try:
        responses = _rasa_send_message(sender, message_text, metadata)
    except RuntimeError as error:
        return _json_response(message=str(error), ok=False, status_code=502)

    return _json_response(data=responses, message="Đã gửi đến chatbot.")


@app.get("/api/student/requests")
def student_requests():
    student_id = request.args.get("student_id", type=int) or DEFAULT_STUDENT_ID
    return _json_response(
        data={
            "requests": list_requests_by_student(student_id=student_id, limit=20),
            "status_counts": get_status_counts(),
        },
        message="Danh sách đơn của sinh viên.",
    )


@app.get("/api/admin/requests")
def admin_requests():
    status = request.args.get("status")
    requests_data = list_requests(status=status if status else None, limit=100)
    return _json_response(
        data={
            "requests": requests_data,
            "status_counts": get_status_counts(),
        },
        message="Danh sách quản lý đơn.",
    )


@app.get("/api/admin/requests/<int:request_id>")
def request_detail(request_id: int):
    request_data = get_request_by_id(request_id)
    if not request_data:
        return _json_response(message="Không tìm thấy đơn.", ok=False, status_code=404)
    request_data["history"] = get_request_history(request_id)
    request_data["status_label"] = STATUS_LABELS.get(request_data["status"], request_data["status"])
    return _json_response(data=request_data, message="Chi tiết đơn.")


@app.post("/api/admin/requests/<int:request_id>/approve")
def approve_request(request_id: int):
    payload = request.get_json(force=True, silent=True) or {}
    admin_id = payload.get("admin_id") or DEFAULT_ADMIN_ID
    try:
        updated = update_request_status(
            request_id=request_id,
            new_status=STATUS_APPROVED,
            changed_by=admin_id,
            note="Giáo vụ duyệt đơn qua giao diện quản lý",
        )
    except Exception as error:
        return _json_response(message=str(error), ok=False, status_code=400)
    return _json_response(data=updated, message="Đã duyệt đơn.")


@app.post("/api/admin/requests/<int:request_id>/reject")
def reject_request(request_id: int):
    payload = request.get_json(force=True, silent=True) or {}
    admin_id = payload.get("admin_id") or DEFAULT_ADMIN_ID
    try:
        updated = update_request_status(
            request_id=request_id,
            new_status=STATUS_REJECTED,
            changed_by=admin_id,
            note=payload.get("note") or "Giáo vụ từ chối đơn qua giao diện quản lý",
        )
    except Exception as error:
        return _json_response(message=str(error), ok=False, status_code=400)
    return _json_response(data=updated, message="Đã từ chối đơn.")



@app.post("/api/student/cancel-latest")
def student_cancel_latest():
    payload = request.get_json(force=True, silent=True) or {}
    metadata = payload.get("metadata") or {}
    student_id = resolve_user_id_from_metadata(metadata) if metadata else DEFAULT_STUDENT_ID
    try:
        updated = cancel_latest_pending_request(
            student_id=student_id,
            changed_by=student_id,
            note="Sinh viên huỷ đơn gần nhất qua giao diện chat",
        )
    except Exception as error:
        return _json_response(message=str(error), ok=False, status_code=400)
    if not updated:
        return _json_response(message="Không có đơn Chờ duyệt nào để huỷ.", ok=False, status_code=404)
    return _json_response(data=updated, message="Đã huỷ đơn gần nhất.")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)

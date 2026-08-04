import sqlite3
import os
import re
from datetime import date, timedelta
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

# Xác định đường dẫn tuyệt đối tới file chatbot.db trong thư mục db/
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'chatbot.db')


def _parse_date_text(raw_value: Text) -> Text:
    value = (raw_value or "").strip().lower()
    if not value:
        return ""

    today = date.today()
    relative_dates = {
        "hôm nay": today,
        "hom nay": today,
        "hôm qua": today - timedelta(days=1),
        "hom qua": today - timedelta(days=1),
        "ngày mai": today + timedelta(days=1),
        "ngay mai": today + timedelta(days=1),
        "mai": today + timedelta(days=1),
        "ngày kia": today + timedelta(days=2),
        "ngay kia": today + timedelta(days=2),
    }
    if value in relative_dates:
        return relative_dates[value].isoformat()

    normalized_match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", value)
    if normalized_match:
        day = int(normalized_match.group(1))
        month = int(normalized_match.group(2))
        year_text = normalized_match.group(3)
        year = int(year_text) if year_text else today.year
        if year < 100:
            year += 2000
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return ""

    weekday_match = re.search(r"\b(?:thứ\s*([2-7])|chủ nhật)(?:\s*(tuần\s*(này|sau|tới)))?\b", value)
    if weekday_match:
        if weekday_match.group(1):
            weekday = int(weekday_match.group(1)) - 2
        else:
            weekday = 6

        week_modifier = weekday_match.group(3) or ""
        days_ahead = (weekday - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        if week_modifier in {"sau", "tới"}:
            days_ahead += 7
        return (today + timedelta(days=days_ahead)).isoformat()

    return raw_value.strip()


def _date_display(raw_value: Text, normalized_value: Text) -> Text:
    if normalized_value and normalized_value != raw_value.strip():
        return f"{raw_value.strip()} -> {normalized_value}"
    return normalized_value or raw_value.strip()

class ActionSubmitAbsenceRequest(Action):
    def name(self) -> Text:
        return "action_submit_absence_request"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # 1. Lấy thông tin từ các Slot do Form thu thập được
        course_code = tracker.get_slot('ma_mon_hoc') or tracker.get_slot('ma_mon')
        class_code = tracker.get_slot('ma_lop')
        start_date = tracker.get_slot('normalized_start_date') or tracker.get_slot('start_date')
        end_date = tracker.get_slot('normalized_end_date') or tracker.get_slot('end_date')
        reason = tracker.get_slot('reason')

        # 2. Lấy định danh sinh viên (student_id) từ phiên đăng nhập (Metadata hoặc Session)
        # Theo đúng yêu cầu: MSSV lấy từ phiên đăng nhập, không thu qua hội thoại!
        metadata = tracker.latest_message.get('metadata', {})

        # Kiểm tra xem đã đủ thông tin cơ bản chưa
        if not course_code or not start_date or not reason:
            dispatcher.utter_message(text="Thiếu thông tin quan trọng (môn học, ngày nghỉ hoặc lý do), vui lòng cung cấp đầy đủ nhé!")
            return []

        try:
            # 3. Kết nối CSDL SQLite
            conn = sqlite3.connect(DB_PATH)
            conn.execute("PRAGMA foreign_keys = ON;")
            cursor = conn.cursor()

            # Nếu test trực tiếp qua Rasa Shell (chưa truyền metadata từ UI), ta gán tạm ID = 1 (Lê Thị Tuyết Băng)
            student_id = metadata.get('student_id')
            if not student_id:
                student_id = 1 

            # 4. Thực hiện INSERT đơn xin nghỉ vào bảng AbsenceRequests với trạng thái mặc định 'PENDING'
            cursor.execute('''
                INSERT INTO AbsenceRequests (student_id, course_code, class_code, start_date, end_date, reason, status)
                VALUES (?, ?, ?, ?, ?, ?, 'PENDING')
            ''', (student_id, course_code, class_code, start_date, end_date, reason))
            
            request_id = cursor.lastrowid # Lấy ID của đơn vừa tạo

            # 5. Ghi vết vào bảng RequestStatusHistory (Lịch sử trạng thái)
            cursor.execute('''
                INSERT INTO RequestStatusHistory (request_id, old_status, new_status, changed_by, note)
                VALUES (?, NULL, 'PENDING', ?, 'Sinh viên nộp đơn xin nghỉ học qua chatbot')
            ''', (request_id, student_id))

            conn.commit()
            conn.close()

            # 6. Phản hồi thành công về cho người dùng
            response_text = (
                f" Ghi nhận thành công đơn xin nghỉ môn **{course_code}** từ ngày **{start_date}** đến ngày **{end_date}**. "
                f"Trạng thái hiện tại: **Chờ duyệt (PENDING)**. Mã đơn của bạn là #{request_id}."
            )
            dispatcher.utter_message(text=response_text)

        except Exception as e:
            dispatcher.utter_message(text=f" Lỗi hệ thống khi lưu CSDL: {str(e)}")

        return [SlotSet("awaiting_request_confirmation", False)]


class ActionPreviewAbsenceRequest(Action):
    def name(self) -> Text:
        return "action_preview_absence_request"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        start_date_raw = tracker.get_slot('start_date') or ""
        end_date_raw = tracker.get_slot('end_date') or ""

        normalized_start_date = _parse_date_text(start_date_raw)
        normalized_end_date = _parse_date_text(end_date_raw)

        if not normalized_start_date or not normalized_end_date:
            dispatcher.utter_message(text="Mình chưa hiểu rõ ngày nghỉ. Bạn hãy nhập lại ngày theo dạng dd/mm/yyyy hoặc các cách như 'mai', 'ngày mai'.")
            return [
                SlotSet("normalized_start_date", None),
                SlotSet("normalized_end_date", None),
                SlotSet("awaiting_request_confirmation", False),
            ]

        preview_message = (
            f"Mình đã hiểu: từ { _date_display(start_date_raw, normalized_start_date) } đến { _date_display(end_date_raw, normalized_end_date) }. "
            f"Bạn xác nhận để mình lưu đơn nhé?"
        )
        dispatcher.utter_message(text=preview_message)

        return [
            SlotSet("normalized_start_date", normalized_start_date),
            SlotSet("normalized_end_date", normalized_end_date),
            SlotSet("awaiting_request_confirmation", True),
        ]


class ActionResetAbsenceForm(Action):
    def name(self) -> Text:
        return "action_reset_absence_form"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(text="Được rồi, mình sẽ nhập lại thông tin từ đầu nhé.")
        return [
            SlotSet("ma_mon_hoc", None),
            SlotSet("ma_lop", None),
            SlotSet("start_date", None),
            SlotSet("end_date", None),
            SlotSet("reason", None),
            SlotSet("normalized_start_date", None),
            SlotSet("normalized_end_date", None),
            SlotSet("awaiting_request_confirmation", False),
        ]
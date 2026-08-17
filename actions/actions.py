import re
from datetime import date, timedelta
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, ActiveLoop 

from db.store import (
    STATUS_APPROVED,
    STATUS_CANCELLED,
    STATUS_LABELS,
    STATUS_PENDING,
    STATUS_REJECTED,
    cancel_latest_pending_request,
    create_absence_request,
    list_requests_by_student,
    resolve_user_id_from_metadata,
)


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

class ActionStartAbsenceForm(Action):
    def name(self) -> Text:
        return "action_start_absence_form"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(
            text=(
                "Để xin nghỉ học hợp lệ, bạn cần gửi đơn xin phép cho giảng viên kèm minh chứng "
                "(giấy khám bệnh, xác nhận của gia đình...). "
                "Bạn vui lòng cung cấp Mã lớp và Môn học để hệ thống ghi nhận nhé."
            )
        )
        return [
            SlotSet("ma_mon_hoc", None),
            SlotSet("ma_mon", None),
            SlotSet("ma_lop", None),
            SlotSet("start_date", None),
            SlotSet("end_date", None),
            SlotSet("reason", None),
            SlotSet("normalized_start_date", None),
            SlotSet("normalized_end_date", None),
            SlotSet("awaiting_request_confirmation", False),
        ]



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
        evidence_url = tracker.get_slot("evidence_url")

        metadata = tracker.latest_message.get('metadata', {})

        # Chỉ cho phép lưu khi người dùng đã xác nhận preview
        if not tracker.get_slot("awaiting_request_confirmation"):
            dispatcher.utter_message(text="Chưa có đơn nào đang chờ xác nhận. Bạn hãy nộp đơn và xác nhận trước nhé.")
            return []

        # Kiểm tra xem đã đủ thông tin cơ bản chưa
        if not course_code or not start_date or not reason:
            dispatcher.utter_message(text="Thiếu thông tin quan trọng (môn học, ngày nghỉ hoặc lý do), vui lòng cung cấp đầy đủ nhé!")
            return []

        try:
            # Định danh mô phỏng: ưu tiên metadata, nếu không có thì lấy tài khoản mẫu đầu tiên.
            student_id = resolve_user_id_from_metadata(metadata) if metadata else 1
            request_id = create_absence_request(
                student_id=student_id,
                course_code=course_code,
                class_code=class_code or "",
                start_date=start_date,
                end_date=end_date or start_date,
                reason=reason,
                created_by=student_id,
            )
            # ========== 
            if evidence_url and str(evidence_url).strip().lower() not in {"không", "khong", "no", ""}:
                from db.store import add_evidence
                add_evidence(
                    request_id=request_id,
                    file_name="minh_chung",
                    file_url=str(evidence_url).strip(),
                )
            dispatcher.utter_message(
                text=(
                    f"Ghi nhận thành công đơn xin nghỉ môn {course_code} "
                    f"từ ngày {start_date} đến ngày {end_date or start_date}. "
                    f"Trạng thái hiện tại: Chờ duyệt (PENDING). Mã đơn của bạn là #{request_id}."
                )
            )
            # Reset slot sau khi lưu thành công
            return [
                SlotSet("awaiting_request_confirmation", False),
                SlotSet("ma_mon_hoc", None),
                SlotSet("ma_mon", None),
                SlotSet("ma_lop", None),
                SlotSet("start_date", None),
                SlotSet("end_date", None),
                SlotSet("reason", None),
                SlotSet("normalized_start_date", None),
                SlotSet("normalized_end_date", None),
                SlotSet("evidence_url", None),
            ]
        except Exception as e:
            dispatcher.utter_message(text=f"Lỗi hệ thống khi lưu CSDL: {str(e)}")
            return [
                SlotSet("awaiting_request_confirmation", False),
            ]




class ActionPreviewAbsenceRequest(Action):
    def name(self) -> Text:
        return "action_preview_absence_request"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        course_code = tracker.get_slot("ma_mon_hoc") or tracker.get_slot("ma_mon") or ""
        class_code = tracker.get_slot("ma_lop") or ""
        reason = tracker.get_slot("reason") or ""
        start_date_raw = tracker.get_slot("start_date") or ""
        end_date_raw = tracker.get_slot("end_date") or ""
        evidence_url = tracker.get_slot("evidence_url") or ""

        normalized_start = _parse_date_text(start_date_raw)
        normalized_end = _parse_date_text(end_date_raw)

        # --- Validation ---
        if not course_code or not class_code or not reason:
            dispatcher.utter_message(
                text="Thiếu thông tin (môn học / lớp / lý do). Mình sẽ hỏi lại từ đầu nhé."
            )
            return [
                SlotSet("awaiting_request_confirmation", False),
                SlotSet("normalized_start_date", None),
                SlotSet("normalized_end_date", None),
            ]

        if not normalized_start or not normalized_end:
            dispatcher.utter_message(
                text=(
                    "Mình chưa hiểu rõ ngày nghỉ. "
                    "Bạn nhập lại theo dạng dd/mm/yyyy hoặc 'mai', 'ngày mai', 'thứ 2 tuần sau' nhé."
                )
            )
            return [
                SlotSet("start_date", None),
                SlotSet("end_date", None),
                SlotSet("normalized_start_date", None),
                SlotSet("normalized_end_date", None),
                SlotSet("awaiting_request_confirmation", False),
                ActiveLoop("absence_form"),
            ]

        # start <= end
        try:
            from datetime import date as date_cls
            d1 = date_cls.fromisoformat(normalized_start)
            d2 = date_cls.fromisoformat(normalized_end)
            if d1 > d2:
                dispatcher.utter_message(
                    text="Ngày bắt đầu không được sau ngày kết thúc. Bạn nhập lại khoảng ngày nghỉ nhé."
                )
                return [
                    SlotSet("start_date", None),
                    SlotSet("end_date", None),
                    SlotSet("normalized_start_date", None),
                    SlotSet("normalized_end_date", None),
                    SlotSet("awaiting_request_confirmation", False),
                    ActiveLoop("absence_form"), 
                ]
        except ValueError:
            dispatcher.utter_message(text="Định dạng ngày không hợp lệ. Bạn nhập lại nhé.")
            return [
                SlotSet("start_date", None),
                SlotSet("end_date", None),
                SlotSet("normalized_start_date", None),
                SlotSet("normalized_end_date", None),
                SlotSet("awaiting_request_confirmation", False),
                ActiveLoop("absence_form"),
            ]

        # --- Preview đầy đủ ---
        start_show = _date_display(start_date_raw, normalized_start)
        end_show = _date_display(end_date_raw, normalized_end)

        preview = (
            f"Mình đã hiểu đơn của bạn như sau:\n"
            f"- Môn: {course_code}\n"
            f"- Lớp: {class_code}\n"
            f"- Từ: {start_show}\n"
            f"- Đến: {end_show}\n"
            f"- Lý do: {reason}\n\n"
            f"- Minh chứng: {evidence_url if evidence_url and evidence_url.strip().lower() not in {'không', 'khong', 'no', ''} else 'Không có'}\n\n"
            f"Bạn xác nhận để mình lưu đơn nhé? (có / không)"
        )
        dispatcher.utter_message(text=preview)

        return [
            SlotSet("normalized_start_date", normalized_start),
            SlotSet("normalized_end_date", normalized_end),
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


class ActionCheckAbsenceStatus(Action):
    def name(self) -> Text:
        return "action_check_absence_status"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        metadata = tracker.latest_message.get("metadata", {})
        student_id = resolve_user_id_from_metadata(metadata) if metadata else 1

        try:
            requests = list_requests_by_student(student_id=student_id, limit=5)
            if not requests:
                dispatcher.utter_message(text="Bạn chưa có đơn xin nghỉ nào trong hệ thống.")
                return []

            lines = ["Danh sách các đơn nghỉ gần nhất của bạn:"]
            for request in requests:
                lines.append(
                    f"- #{request['id']}: {request['course_code']} | lớp {request['class_code']} | "
                    f"{request['start_date']} đến {request['end_date']} | {STATUS_LABELS.get(request['status'], request['status'])}"
                )
            dispatcher.utter_message(text="\n".join(lines))
        except Exception as e:
            dispatcher.utter_message(text=f"Không thể tra cứu trạng thái đơn: {str(e)}")

        return []


class ActionCancelAbsence(Action):
    def name(self) -> Text:
        return "action_cancel_absence"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        metadata = tracker.latest_message.get("metadata", {})
        student_id = resolve_user_id_from_metadata(metadata) if metadata else 1

        try:
            request = cancel_latest_pending_request(
                student_id=student_id,
                changed_by=student_id,
                note="Sinh viên yêu cầu hủy đơn qua chatbot",
            )
            if not request:
                dispatcher.utter_message(text="Hiện không có đơn Chờ duyệt nào để hủy.")
                return []

            dispatcher.utter_message(
                text=f"Đã hủy đơn #{request['id']} và cập nhật trạng thái thành {STATUS_LABELS[STATUS_CANCELLED]}."
            )
        except Exception as e:
            dispatcher.utter_message(text=f"Không thể hủy đơn: {str(e)}")

        return []
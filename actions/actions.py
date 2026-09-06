import re
from datetime import date, timedelta
from typing import Any, Text, Dict, List, Tuple, Optional
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, ActiveLoop 
from rasa_sdk.forms import FormValidationAction
from rasa_sdk.types import DomainDict

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
        "ngày mốt": today + timedelta(days=2),   
        "ngay mot": today + timedelta(days=2),  
        "mốt": today + timedelta(days=2), 
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


def _get_student_id(tracker: Tracker) -> int:
    metadata = tracker.latest_message.get("metadata") or {}
    student_id = resolve_user_id_from_metadata(metadata) if metadata else None
    if not student_id or student_id == 1:
        sender_id = tracker.sender_id
        if sender_id:
            student_id = resolve_user_id_from_metadata({"username": sender_id})
    return student_id or 1


KNOWN_SUBJECTS = [
    "Lập trình Python", "Cơ sở dữ liệu", "CSDL", "Mạng máy tính",
    "Cấu trúc dữ liệu và giải thuật", "CTDL", "Software Testing",
    "Kiểm thử phần mềm", "Trí tuệ nhân tạo", "AI", "Hệ quản trị CSDL",
    "Thực tập tốt nghiệp", "An toàn thông tin", "Phát triển ứng dụng web"
]


def _is_class_code(val: str) -> bool:
    """Kiểm tra một chuỗi có mang cấu trúc của mã lớp hay không (ví dụ: CN2302C, DTH2151, DH21IT01, 010112610016)."""
    if not val:
        return False
    s = str(val).strip().upper()
    if " " in s:
        return False
    if re.match(r"^[A-Z]{2,5}\d{2,6}[A-Z0-9_-]{0,4}$", s):
        return True
    if re.match(r"^\d{10,12}$", s):
        return True
    return False


def _extract_date_range_from_text(
    text: str,
    entities: List[Dict[Text, Any]],
    prefer_slot: Optional[str] = None   # "start_date" | "end_date" | None
) -> Tuple[Optional[Text], Optional[Text]]:
    text_lower = (text or "").strip().lower()

    # 1. Bắt mẫu "từ A đến B"
    range_match = re.search(
        r"(?:từ|tu)\s+([0-9]{1,2}[/-][0-9]{1,2}(?:[/-][0-9]{2,4})?|hôm nay|hôm qua|ngày mai|mai|ngày kia|thứ\s*[2-7]|chủ nhật)\s+(?:đến|den|-)\s+([0-9]{1,2}[/-][0-9]{1,2}(?:[/-][0-9]{2,4})?|hôm nay|hôm qua|ngày mai|mai|ngày kia|thứ\s*[2-7]|chủ nhật)",
        text_lower
    )
    if range_match:
        return range_match.group(1).strip(), range_match.group(2).strip()

    # 2. Tìm tất cả biểu thức ngày
    date_pattern = r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b|\b(?:hôm nay|hôm qua|ngày mai|mai|ngày kia|ngày mốt|mốt)\b|\b(?:thứ\s*[2-7]|chủ nhật)(?:\s*(?:tuần\s*(?:này|sau|tới)))?\b"
    found_dates = re.findall(date_pattern, text_lower)

    if len(found_dates) >= 2:
        return found_dates[0], found_dates[1]

    # 3. Entity start/end khác nhau
    start_e = [e.get("value") for e in entities if e.get("entity") == "start_date"]
    end_e = [e.get("value") for e in entities if e.get("entity") == "end_date"]
    if start_e and end_e and start_e[0] != end_e[0]:
        return start_e[0], end_e[0]

    # 4. Nếu chỉ tìm được 1 ngày trong câu
    if len(found_dates) == 1:
        date_val = found_dates[0]

        # Từ khóa rõ ràng về ngày kết thúc
        if any(kw in text_lower for kw in ["kết thúc", "ket thuc", "ngày kết thúc", "đến ngày", "den ngay", "đến hết"]):
            return None, date_val
        if re.search(r"(?:đến|den)\s+" + re.escape(date_val), text_lower):
            return None, date_val

        # Từ khóa rõ ràng về ngày bắt đầu
        if any(kw in text_lower for kw in ["bắt đầu", "bat dau", "ngày bắt đầu", "từ ngày", "tu ngay"]):
            return date_val, None
        if re.search(r"(?:từ|tu)\s+" + re.escape(date_val), text_lower):
            return date_val, None

        # Ưu tiên theo prefer_slot (nếu có)
        if prefer_slot == "end_date":
            return None, date_val
        if prefer_slot == "start_date":
            return date_val, None

        # === QUAN TRỌNG: Mặc định chỉ trả về ngày bắt đầu, KHÔNG tự set end = start ===
        return date_val, None

    if start_e:
        return start_e[0], None
    if end_e:
        return None, end_e[0]

    return None, None


class ValidateAbsenceForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_absence_form"

    def extract_ma_mon_hoc(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> Dict[Text, Any]:
        requested_slot = tracker.get_slot("requested_slot")
        current = tracker.get_slot("ma_mon_hoc")

        # Nếu current bị gán nhầm giá trị của một mã lớp (VD: DTH2151, CN2302C) thì hủy bỏ
        if current and _is_class_code(current) and not any(current.lower() == sub.lower() for sub in KNOWN_SUBJECTS):
            current = None

        text = tracker.latest_message.get("text", "")
        entities = tracker.latest_message.get("entities", [])
        text_lower = text.lower().strip()

        # 1. Bắt theo mẫu rõ ràng "môn <Tên môn / Mã môn>" hoặc "học phần <...>"
        subject_match = re.search(
            r"(?:môn|mon|học phần|hoc phan)\s+([A-Za-z0-9_\s\+À-ỹ]+?)(?=\s+(?:lớp|lop|từ|tu|ngày|ngay|vì|vi|do|lý do|ly do|minh chứng|minh chung)|$)",
            text,
            re.IGNORECASE
        )
        if subject_match:
            candidate = subject_match.group(1).strip()
            if candidate and len(candidate) >= 2:
                return {"ma_mon_hoc": candidate}

        # 2. Tìm tên môn trong danh sách các môn phổ biến (kể cả CSDL, CTDL, AI)
        for sub in KNOWN_SUBJECTS:
            if re.search(r"\b" + re.escape(sub.lower()) + r"\b", text_lower):
                return {"ma_mon_hoc": sub}

        # 3. Entity ma_mon_hoc trực tiếp từ NLU (loại trừ nếu entity đó thực chất là mã lớp)
        for e in entities:
            if e.get("entity") == "ma_mon_hoc" and e.get("value"):
                val = e.get("value").strip()
                if not _is_class_code(val) or any(val.lower() == sub.lower() for sub in KNOWN_SUBJECTS):
                    return {"ma_mon_hoc": val}

        # 4. Entity ma_mon: CHỈ chấp nhận nếu có từ "môn" phía trước hoặc không phải định dạng mã lớp
        for e in entities:
            if e.get("entity") == "ma_mon" and e.get("value"):
                val = e.get("value").strip()
                if re.search(r"(?:môn|mon)\s+" + re.escape(val), text, re.IGNORECASE):
                    return {"ma_mon_hoc": val}
                if not _is_class_code(val):
                    return {"ma_mon_hoc": val}

        # 5. Nếu đang trong form hỏi riêng slot ma_mon_hoc và user nhập câu trả lời
        if requested_slot == "ma_mon_hoc" and text:
            if tracker.latest_message.get("intent", {}).get("name") not in ["deny", "cancel_absence"]:
                clean = re.sub(r"^(?:môn|mon|học phần)\s*", "", text.strip(), flags=re.IGNORECASE).strip()
                # TUYỆT ĐỐI KHÔNG GÁN NẾU USER NHẬP VÀO MỘT MÃ LỚP!
                if clean and not _is_class_code(clean):
                    return {"ma_mon_hoc": clean}
                elif _is_class_code(clean):
                    return {"ma_mon_hoc": None}

        if current and requested_slot != "ma_mon_hoc":
            return {"ma_mon_hoc": current}

        return {}

    def extract_ma_lop(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> Dict[Text, Any]:
        requested_slot = tracker.get_slot("requested_slot")
        current = tracker.get_slot("ma_lop")

        text = tracker.latest_message.get("text", "")
        entities = tracker.latest_message.get("entities", [])
        metadata = tracker.latest_message.get("metadata") or {}

        # 1. Bắt theo mẫu "lớp <mã lớp>"
        class_match = re.search(r"(?:lớp|lop)\s+([A-Za-z0-9_-]+)", text, re.IGNORECASE)
        if class_match:
            return {"ma_lop": class_match.group(1).strip().upper()}

        # 2. Entity ma_lop từ NLU
        for e in entities:
            if e.get("entity") == "ma_lop" and e.get("value"):
                return {"ma_lop": e.get("value").strip().upper()}

        # 3. Nếu người dùng chỉ nhập một mã lớp (VD: "CN2302C", "DTH2151")
        clean_text = text.strip()
        if _is_class_code(clean_text) and not re.search(r"(?:môn|mon)\s+" + re.escape(clean_text), text, re.IGNORECASE):
            return {"ma_lop": clean_text.upper()}

        # 4. Regex mã lớp dạng chữ-số trong câu (loại trừ nếu đi ngay sau 'môn')
        potential_codes = re.findall(r"\b[A-Za-z]{2,5}\d{2,6}[A-Za-z0-9_-]*\b", text)
        for code in potential_codes:
            if not re.search(r"(?:môn|mon)\s+" + re.escape(code), text, re.IGNORECASE):
                if _is_class_code(code):
                    return {"ma_lop": code.upper()}

        # 5. Nếu đang trong form hỏi riêng slot ma_lop
        if requested_slot == "ma_lop" and text:
            if tracker.latest_message.get("intent", {}).get("name") not in ["deny", "cancel_absence"]:
                clean = re.sub(r"^(?:lớp|lop)\s*", "", text.strip(), flags=re.IGNORECASE).strip().upper()
                if clean:
                    return {"ma_lop": clean}

        # 6. Fallback từ session metadata (nếu sinh viên đã đăng nhập và có mã lớp sẵn)
        #if metadata.get("class_code") and not current:
          #  return {"ma_lop": str(metadata.get("class_code")).strip().upper()}

        if current and requested_slot != "ma_lop":
            return {"ma_lop": current}

        return {}

    def extract_start_date(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> Dict[Text, Any]:
        requested_slot = tracker.get_slot("requested_slot")
        current_start = tracker.get_slot("start_date")
        text = tracker.latest_message.get("text", "")
        entities = tracker.latest_message.get("entities", [])

        # Nếu đang hỏi ngày kết thúc thì KHÔNG được đụng đến start_date
        if requested_slot == "end_date":
            if current_start:
                return {"start_date": current_start}
            return {}

        new_start, _ = _extract_date_range_from_text(text, entities, prefer_slot="start_date")
        if new_start:
            return {"start_date": new_start, "normalized_start_date": _parse_date_text(new_start)}

        if current_start and requested_slot != "start_date":
            return {"start_date": current_start}

        if requested_slot == "start_date" and text:
            if tracker.latest_message.get("intent", {}).get("name") not in ["deny", "cancel_absence"]:
                # Làm sạch text trước khi parse
                clean_text = re.sub(r"^(?:ngày bắt đầu|ngay bat dau|từ|tu)\s*", "", text.strip(), flags=re.IGNORECASE).strip()
                date_val = _parse_date_text(clean_text)
                if date_val:
                    return {"start_date": clean_text, "normalized_start_date": date_val}

        return {}

    def extract_end_date(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> Dict[Text, Any]:
        requested_slot = tracker.get_slot("requested_slot")
        current_end = tracker.get_slot("end_date")
        text = tracker.latest_message.get("text", "")
        entities = tracker.latest_message.get("entities", [])

        # Nếu đang hỏi ngày bắt đầu thì KHÔNG được đụng đến end_date
        if requested_slot == "start_date":
            if current_end:
                return {"end_date": current_end}
            return {}
        
    # Chỉ dùng prefer_slot="end_date" khi ĐANG HỎI end_date
        prefer = "end_date" if requested_slot == "end_date" else None

        _, new_end = _extract_date_range_from_text(text, entities, prefer_slot="end_date")
        if new_end:
            return {"end_date": new_end, "normalized_end_date": _parse_date_text(new_end)}

        if current_end and requested_slot != "end_date":
            return {"end_date": current_end}

        if requested_slot == "end_date" and text:
            if tracker.latest_message.get("intent", {}).get("name") not in ["deny", "cancel_absence"]:
                # Làm sạch text (bỏ "ngày kết thúc", "đến"...)
                clean_text = re.sub(
                    r"^(?:ngày kết thúc|ngay ket thuc|đến|den|kết thúc|ket thuc)\s*",
                    "",
                    text.strip(),
                    flags=re.IGNORECASE
                ).strip()
                date_val = _parse_date_text(clean_text)
                if date_val:
                    return {"end_date": clean_text, "normalized_end_date": date_val}

        return {}

    def extract_reason(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> Dict[Text, Any]:
        requested_slot = tracker.get_slot("requested_slot")
        current_reason = tracker.get_slot("reason")
        if current_reason and requested_slot != "reason":
            return {"reason": current_reason}

        text = tracker.latest_message.get("text", "")
        entities = tracker.latest_message.get("entities", [])
        text_clean = text.strip()

        # 1. Bắt theo mẫu "vì / do / lý do là / lý do: ..." kết hợp loại bỏ minh chứng/link ở đuôi
        reason_match = re.search(
            r"(?:vì|vi|do|lý do là|lý do:|ly do la|ly do)\s+(.+?)(?=(?:,\s*|\s+)(?:không|khong|chưa|chua|ko)?\s*(?:có|co)?\s*(?:minh chứng|minh chung|giấy|giay|hồ sơ|ho so)|minh chứng|minh chung|link|url|https?://|$|\.)",
            text_clean,
            re.IGNORECASE
        )
        if reason_match:
            val = reason_match.group(1).strip()
            val = re.sub(r"^(?:là|la|:\s*)\s*", "", val).strip()
            val = re.sub(r"[,\.]+$", "", val).strip()
            if val and len(val) >= 2 and val.lower() not in ["không", "khong", "ko"]:
                return {"reason": val}

        # 2. Bắt mẫu "em bị <bệnh> nên xin nghỉ..."
        illness_match = re.search(
            r"(?:em\s+)?(?:bị|bi)\s+([A-Za-z0-9_\sÀ-ỹ]+?)(?=\s+(?:nên|nen|xin|muốn|muon|để|de|không đi|khong di)|$)",
            text_clean,
            re.IGNORECASE
        )
        if illness_match:
            val = "bị " + illness_match.group(1).strip()
            val = re.sub(r"[,\.]+$", "", val).strip()
            if len(val) >= 4:
                return {"reason": val}

        # 3. Entity reason từ NLU (bỏ qua giá trị 'không', 'ko' do NLU gắn nhầm)
        for e in entities:
            if e.get("entity") == "reason":
                val = str(e.get("value") or "").strip()
                if val.lower() not in ["không", "khong", "ko", "hủy", "huy"] and len(val) >= 2:
                    return {"reason": val}

        # 4. Khi đang hỏi trực tiếp slot reason
        if requested_slot == "reason" and text:
            if tracker.latest_message.get("intent", {}).get("name") not in ["deny", "cancel_absence"]:
                clean_reason = text.strip()
                clean_reason = re.sub(r"^(?:lý do|ly do|vì|vi|do)\s*(?:là|la|:\s*)?\s*", "", clean_reason, flags=re.IGNORECASE).strip()
                if clean_reason:
                    return {"reason": clean_reason}

        return {}

    def extract_evidence_url(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> Dict[Text, Any]:
        requested_slot = tracker.get_slot("requested_slot")
        current_url = tracker.get_slot("evidence_url")
        if current_url and requested_slot != "evidence_url":
            return {"evidence_url": current_url}

        text = tracker.latest_message.get("text", "")
        text_lower = text.lower().strip()
        entities = tracker.latest_message.get("entities", [])

        # 1. Trích xuất đường link
        url_match = re.search(r"https?://[^\s]+|drive\.google\.com[^\s]+|imgur\.com[^\s]+", text)
        if url_match:
            return {"evidence_url": url_match.group(0).strip()}

        # 2. Bắt các từ khóa xác nhận không có minh chứng
        neg_keywords = [
            "không có minh chứng", "khong co minh chung", "không minh chứng", "khong minh chung",
            "chưa có minh chứng", "chua co minh chung", "ko có minh chứng", "ko minh chung",
            "không có giấy", "chưa có giấy", "ko có giấy", "không có", "khong co", "ko co",
            "chưa có", "chua co", "không", "khong", "no"
        ]
        if any(kw in text_lower for kw in neg_keywords):
            return {"evidence_url": "không"}

        # 3. Entity evidence_url từ NLU
        for e in entities:
            if e.get("entity") == "evidence_url" and e.get("value"):
                return {"evidence_url": e.get("value").strip()}

        # 4. Khi đang trong form hỏi riêng slot evidence_url
        if requested_slot == "evidence_url" and text:
            return {"evidence_url": text.strip()}

        return {}

    def validate_ma_mon_hoc(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        val = (slot_value or "").strip()
        # Nếu slot_value bị gán nhầm là một mã lớp và không có trong danh sách môn
        if _is_class_code(val) and not any(val.lower() == sub.lower() for sub in KNOWN_SUBJECTS):
            return {"ma_mon_hoc": None, "ma_lop": val.upper()}
        return {"ma_mon_hoc": val}

    def validate_start_date(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        start_raw = slot_value or ""
        normalized_start = _parse_date_text(start_raw)
        if not normalized_start:
            dispatcher.utter_message(
                text="Mình chưa hiểu ngày bắt đầu. Bạn nhập lại dạng dd/mm/yyyy hoặc 'mai', 'thứ 2 tuần sau' nhé."
            )
            return {"start_date": None, "normalized_start_date": None}
        return {
            "start_date": start_raw,
            "normalized_start_date": normalized_start,
        }

    def validate_end_date(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        start_raw = tracker.get_slot("start_date") or ""
        end_raw = (slot_value or "").strip()
        normalized_start = _parse_date_text(start_raw)
        normalized_end = _parse_date_text(end_raw)

        if not normalized_end or not re.match(r"^\d{4}-\d{2}-\d{2}$", normalized_end):
            dispatcher.utter_message(
                text="Mình chưa hiểu ngày kết thúc. Bạn nhập lại dạng dd/mm/yyyy hoặc 'mai', 'thứ 2 tuần sau' nhé."
            )
            return {"end_date": None, "normalized_end_date": None}

        if start_raw:
            if not normalized_start or not re.match(r"^\d{4}-\d{2}-\d{2}$", normalized_start):
                dispatcher.utter_message(
                    text="Ngày bắt đầu chưa hợp lệ. Bạn nhập lại ngày bắt đầu nhé."
                )
                return {
                    "start_date": None,
                    "normalized_start_date": None,
                    "end_date": None,
                    "normalized_end_date": None,
                }
            try:
                d1 = date.fromisoformat(normalized_start)
                d2 = date.fromisoformat(normalized_end)
                if d1 > d2:
                    dispatcher.utter_message(
                        text=(
                            f"Ngày kết thúc ({end_raw}) không được trước ngày bắt đầu ({start_raw}). "
                            "Bạn nhập lại ngày kết thúc nhé."
                        )
                    )
                    return {"end_date": None, "normalized_end_date": None}
            except Exception:
                pass

        return {
            "end_date": end_raw,
            "normalized_end_date": normalized_end,
        }


class ActionStartAbsenceForm(Action):
    def name(self) -> Text:
        return "action_start_absence_form"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        return [
            SlotSet("awaiting_request_confirmation", False),
        ]


class ActionSubmitAbsenceRequest(Action):
    def name(self) -> Text:
        return "action_submit_absence_request"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        try:
            course_code = tracker.get_slot('ma_mon_hoc') or tracker.get_slot('ma_mon')
            class_code = tracker.get_slot('ma_lop')
            start_date = tracker.get_slot('normalized_start_date') or tracker.get_slot('start_date')
            end_date = tracker.get_slot('normalized_end_date') or tracker.get_slot('end_date')
            reason = tracker.get_slot('reason')
            evidence_url = tracker.get_slot("evidence_url")

            if not tracker.get_slot("awaiting_request_confirmation"):
                dispatcher.utter_message(text="Hiện không có đơn nào đang chờ xác nhận. Bạn muốn xin nghỉ học thì cho mình biết môn học và lớp nhé!")
                return []

            if not course_code or not start_date or not reason:
                dispatcher.utter_message(text="Thiếu thông tin quan trọng (môn học, ngày nghỉ hoặc lý do), vui lòng cung cấp đầy đủ nhé!")
                return []

            student_id = _get_student_id(tracker)
            request_id = create_absence_request(
                student_id=student_id,
                course_code=course_code,
                class_code=class_code or "",
                start_date=start_date,
                end_date=end_date or start_date,
                reason=reason,
                created_by=student_id,
                source="chatbot",
            )
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
        try:
            course_code = tracker.get_slot("ma_mon_hoc") or tracker.get_slot("ma_mon") or ""
            class_code = tracker.get_slot("ma_lop") or ""
            reason = tracker.get_slot("reason") or ""
            start_date_raw = tracker.get_slot("start_date") or ""
            end_date_raw = tracker.get_slot("end_date") or ""
            evidence_url = tracker.get_slot("evidence_url") or ""

            normalized_start = tracker.get_slot("normalized_start_date") or _parse_date_text(start_date_raw)
            normalized_end = tracker.get_slot("normalized_end_date") or _parse_date_text(end_date_raw)

            if not course_code or not class_code or not reason:
                dispatcher.utter_message(
                    text="Thiếu thông tin (môn học / lớp / lý do). Bạn vui lòng cung cấp đủ nhé."
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

            try:
                from datetime import date as date_cls
                d1 = date_cls.fromisoformat(str(normalized_start))
                d2 = date_cls.fromisoformat(str(normalized_end))
                if d1 > d2:
                    dispatcher.utter_message(
                        text="Ngày kết thúc không được trước ngày bắt đầu."
                    )
                    return [
                        SlotSet("start_date", None),
                        SlotSet("end_date", None),
                        SlotSet("normalized_start_date", None),
                        SlotSet("normalized_end_date", None),
                        SlotSet("awaiting_request_confirmation", False),
                        ActiveLoop("absence_form"), 
                    ]
            except Exception:
                pass

            start_show = _date_display(start_date_raw, normalized_start)
            end_show = _date_display(end_date_raw, normalized_end)

            preview = (
                f"Mình đã hiểu đơn của bạn như sau:\n"
                f"- Môn: {course_code}\n"
                f"- Lớp: {class_code}\n"
                f"- Từ: {start_show}\n"
                f"- Đến: {end_show}\n"
                f"- Lý do: {reason}\n"
                f"- Minh chứng: {evidence_url if evidence_url and str(evidence_url).strip().lower() not in {'không', 'khong', 'no', ''} else 'Không có'}\n\n"
                f"Bạn xác nhận để mình lưu đơn nhé? (có / không / gõ thông tin cần sửa lại)"
            )
            dispatcher.utter_message(text=preview)

            return [
                SlotSet("normalized_start_date", normalized_start),
                SlotSet("normalized_end_date", normalized_end),
                SlotSet("awaiting_request_confirmation", True),
            ]
        except Exception as e:
            dispatcher.utter_message(
                text=f"Có lỗi xảy ra khi tạo bản xem trước: {str(e)}. Bạn vui lòng nhập lại thông tin nhé."
            )
            return [
                SlotSet("awaiting_request_confirmation", False),
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
            SlotSet("ma_mon", None),
            SlotSet("ma_lop", None),
            SlotSet("start_date", None),
            SlotSet("end_date", None),
            SlotSet("reason", None),
            SlotSet("normalized_start_date", None),
            SlotSet("normalized_end_date", None),
            SlotSet("evidence_url", None),
            SlotSet("awaiting_request_confirmation", False),
        ]


class ActionHandleAbsenceCorrection(Action):
    def name(self) -> Text:
        return "action_handle_absence_correction"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        try:
            text = tracker.latest_message.get("text", "").strip().lower()
            intent_name = tracker.latest_message.get("intent", {}).get("name")
            entities = tracker.latest_message.get("entities", [])

            # Kiểm tra xem có entity hoặc từ khóa thông tin mới đi kèm không (môn, lớp, ngày, lý do, link)
            has_update_entity = any(
                e.get("entity") in ["start_date", "end_date", "time", "ma_mon_hoc", "ma_mon", "ma_lop", "reason", "evidence_url"] 
                for e in entities
            )
            has_update_keyword = any(kw in text for kw in ["ngày", "môn", "lớp", "lý do", "ly do", "minh chứng", "http", "drive"])

            # Nếu user trả lời "không", "hủy", "không đồng ý", "thôi" mà KHÔNG CÓ thông tin sửa đi kèm -> HỦY ĐƠN & RESET FORM
            if (intent_name in ["deny", "cancel_absence"] or any(kw == text or text.startswith(kw) for kw in ["không", "khong", "hủy", "huy", "thôi", "từ chối", "làm lại"])) and not (has_update_entity or has_update_keyword):
                dispatcher.utter_message(
                    text="Đã hủy đơn xin nghỉ học và không lưu thông tin. Bạn có thể nhập thông tin mới nếu muốn tạo lại đơn nhé!"
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
                    SlotSet("evidence_url", None),
                    SlotSet("awaiting_request_confirmation", False),
                ]

            slot_events = []
            updated_fields = []

            # 1. Cập nhật môn học
            mon_updated = None
            if any(kw in text for kw in ["môn", "mon", "học phần", "hoc phan"]):
                m_mon = re.search(r"(?:môn|mon|học phần|hoc phan)\s*(?:là|la|thành|thanh|:)?\s*([A-Za-z0-9_\s\+À-ỹ]+?)(?=\s+(?:lớp|lop|từ|tu|ngày|ngay|vì|vi|do|lý do|ly do|minh chứng|minh chung)|$)", text, re.IGNORECASE)
                if m_mon and m_mon.group(1).strip():
                    mon_updated = m_mon.group(1).strip()
            if not mon_updated:
                for sub in KNOWN_SUBJECTS:
                    if re.search(r"\b" + re.escape(sub.lower()) + r"\b", text):
                        mon_updated = sub
                        break
            if not mon_updated:
                for e in entities:
                    if e.get("entity") == "ma_mon_hoc":
                        mon_updated = e.get("value")
                        break
            if mon_updated and not (_is_class_code(mon_updated) and not any(mon_updated.lower() == s.lower() for s in KNOWN_SUBJECTS)):
                slot_events.append(SlotSet("ma_mon_hoc", mon_updated))
                updated_fields.append(f"Môn học: {mon_updated}")

            # 2. Cập nhật lớp
            lop_updated = None
            if any(kw in text for kw in ["lớp", "lop"]):
                m_lop = re.search(r"(?:lớp|lop)\s*(?:là|la|thành|thanh|:)?\s*([A-Za-z0-9_-]+)", text, re.IGNORECASE)
                if m_lop:
                    lop_updated = m_lop.group(1).strip().upper()
            if not lop_updated:
                for e in entities:
                    if e.get("entity") == "ma_lop":
                        lop_updated = e.get("value").strip().upper()
                        break
            if not lop_updated:
                potential_codes = re.findall(r"\b[A-Za-z]{2,5}\d{2,6}[A-Za-z0-9_-]*\b", text)
                for code in potential_codes:
                    if not re.search(r"(?:môn|mon)\s+" + re.escape(code), text, re.IGNORECASE):
                        if _is_class_code(code):
                            lop_updated = code.upper()
                            break
            if lop_updated:
                slot_events.append(SlotSet("ma_lop", lop_updated))
                updated_fields.append(f"Lớp: {lop_updated}")

            # 3. Cập nhật lý do
            reason_entities = [e for e in entities if e.get("entity") == "reason"]
            if reason_entities and reason_entities[0].get("value", "").lower() not in ["không", "khong", "ko"]:
                val = reason_entities[0].get("value")
                slot_events.append(SlotSet("reason", val))
                updated_fields.append(f"Lý do: {val}")
            elif "lý do" in text or "ly do" in text:
                reason_match = re.search(r"(?:lý do|ly do)(?:\s+là|\s+là:|\s*:)?\s*(.+)", text, re.IGNORECASE)
                if reason_match:
                    val = reason_match.group(1).strip()
                    if not re.search(r"\b\d{1,2}[/-]\d{1,2}\b", val):
                        slot_events.append(SlotSet("reason", val))
                        updated_fields.append(f"Lý do: {val}")

            # 4. Cập nhật minh chứng
            evidence_entities = [e for e in entities if e.get("entity") == "evidence_url"]
            if evidence_entities:
                val = evidence_entities[0].get("value")
                slot_events.append(SlotSet("evidence_url", val))
                updated_fields.append(f"Minh chứng: {val}")
            elif "http" in text or "drive.google.com" in text or "imgur.com" in text:
                url_match = re.search(r"https?://[^\s]+|drive\.google\.com[^\s]+|imgur\.com[^\s]+", text)
                if url_match:
                    val = url_match.group(0)
                    slot_events.append(SlotSet("evidence_url", val))
                    updated_fields.append(f"Minh chứng: {val}")

            # 5. Cập nhật ngày tháng (phân biệt rõ sửa ngày bắt đầu vs ngày kết thúc vs cả hai)
            is_start_only = any(kw in text for kw in ["bắt đầu", "bat dau", "start", "từ ngày", "tu ngay"]) and not any(kw in text for kw in ["kết thúc", "ket thuc", "đến ngày", "den ngay", "đến hết", "hết ngày"])
            is_end_only = any(kw in text for kw in ["kết thúc", "ket thuc", "end", "đến ngày", "den ngay", "đến hết", "hết ngày"]) and not any(kw in text for kw in ["bắt đầu", "bat dau", "từ ngày", "tu ngay"])

                      
            # ===== XỬ LÝ NGÀY - PHIÊN BẢN SỬA LỖI =====
            prefer = None
            text_lower = text.lower()

            if any(kw in text_lower for kw in ["bắt đầu", "bat dau", "ngày bắt đầu", "đổi ngày bắt đầu", "sửa ngày bắt đầu"]):
                prefer = "start_date"
            elif any(kw in text_lower for kw in ["kết thúc", "ket thuc", "ngày kết thúc", "đổi ngày kết thúc", "sửa ngày kết thúc"]):
                prefer = "end_date"

            new_start, new_end = _extract_date_range_from_text(text, entities, prefer_slot=prefer)

            # --- Helper: kiểm tra ngày parse được có hợp lệ (ISO format) hay không ---
            def _is_valid_parsed_date(raw_val):
                """Trả về normalized ISO string nếu hợp lệ, ngược lại trả về None."""
                if not raw_val:
                    return None
                norm = _parse_date_text(raw_val)
                if not norm:
                    return None
                # _parse_date_text trả về raw_value.strip() nếu không parse được
                # → phải kiểm tra kết quả có đúng định dạng ISO (YYYY-MM-DD) không
                try:
                    from datetime import date as date_cls
                    date_cls.fromisoformat(str(norm))
                    return norm
                except (ValueError, TypeError):
                    return None

            # Lấy giá trị cũ từ tracker để bảo vệ slot không bị sửa
            old_start_date = tracker.get_slot("start_date")
            old_end_date = tracker.get_slot("end_date")
            old_norm_start = tracker.get_slot("normalized_start_date")
            old_norm_end = tracker.get_slot("normalized_end_date")

            # Chỉ cập nhật đúng slot người dùng muốn sửa, giữ nguyên slot còn lại
            if prefer == "start_date":
                # Chỉ sửa start_date, TUYỆT ĐỐI giữ nguyên end_date cũ
                if new_start:
                    norm = _is_valid_parsed_date(new_start)
                    if norm:
                        slot_events.append(SlotSet("start_date", new_start))
                        slot_events.append(SlotSet("normalized_start_date", norm))
                        updated_fields.append(f"Ngày bắt đầu: {_date_display(new_start, norm)}")
                # Luôn ghi đè lại end_date bằng giá trị cũ để chống Rasa auto-fill
                slot_events.append(SlotSet("end_date", old_end_date))
                slot_events.append(SlotSet("normalized_end_date", old_norm_end))

            elif prefer == "end_date":
                # Chỉ sửa end_date, TUYỆT ĐỐI giữ nguyên start_date cũ
                if new_end:
                    norm = _is_valid_parsed_date(new_end)
                    if norm:
                        slot_events.append(SlotSet("end_date", new_end))
                        slot_events.append(SlotSet("normalized_end_date", norm))
                        updated_fields.append(f"Ngày kết thúc: {_date_display(new_end, norm)}")
                # Luôn ghi đè lại start_date bằng giá trị cũ để chống Rasa auto-fill
                slot_events.append(SlotSet("start_date", old_start_date))
                slot_events.append(SlotSet("normalized_start_date", old_norm_start))

            else:
                # Trường hợp người dùng nói chung chung (không nói rõ bắt đầu hay kết thúc)
                if new_start:
                    norm = _is_valid_parsed_date(new_start)
                    if norm:
                        slot_events.append(SlotSet("start_date", new_start))
                        slot_events.append(SlotSet("normalized_start_date", norm))
                        updated_fields.append(f"Ngày bắt đầu: {_date_display(new_start, norm)}")
                if new_end:
                    norm = _is_valid_parsed_date(new_end)
                    if norm:
                        slot_events.append(SlotSet("end_date", new_end))
                        slot_events.append(SlotSet("normalized_end_date", norm))
                        updated_fields.append(f"Ngày kết thúc: {_date_display(new_end, norm)}")

            # ===== Phần tạo preview + kiểm tra ngày hợp lệ =====
            if updated_fields:
                curr_course = mon_updated if mon_updated else (tracker.get_slot("ma_mon_hoc") or tracker.get_slot("ma_mon"))
                curr_class = lop_updated if lop_updated else tracker.get_slot("ma_lop")

                if prefer == "start_date":
                    curr_start = new_start if new_start else old_start_date
                    curr_end = old_end_date
                elif prefer == "end_date":
                    curr_start = old_start_date
                    curr_end = new_end if new_end else old_end_date
                else:
                    curr_start = new_start if new_start else tracker.get_slot("start_date")
                    curr_end = new_end if new_end else tracker.get_slot("end_date")

                if reason_entities:
                    curr_reason = reason_entities[0].get("value")
                elif "lý do" in text or "ly do" in text:
                    reason_match = re.search(r"(?:lý do|ly do)(?:\s+là|\s+là:|\s*:)?\s*(.+)", text, re.IGNORECASE)
                    curr_reason = reason_match.group(1).strip() if (reason_match and not re.search(r"\b\d{1,2}[/-]\d{1,2}\b", reason_match.group(1))) else tracker.get_slot("reason")
                else:
                    curr_reason = tracker.get_slot("reason")

                curr_evidence = tracker.get_slot("evidence_url")

                norm_s = _parse_date_text(curr_start) if curr_start else ""
                norm_e = _parse_date_text(curr_end) if curr_end else ""

                start_show = _date_display(curr_start, norm_s)
                end_show = _date_display(curr_end, norm_e)

                # Kiểm tra ngày hợp lệ
                try:
                    from datetime import date as date_cls
                    d1 = date_cls.fromisoformat(str(norm_s)) if norm_s else None
                    d2 = date_cls.fromisoformat(str(norm_e)) if norm_e else None
                    if d1 and d2 and d1 > d2:
                        dispatcher.utter_message(
                            text=f"Ngày kết thúc ({end_show}) không được trước ngày bắt đầu ({start_show}). Bạn vui lòng chọn lại ngày kết thúc nhé."
                        )
                        return [SlotSet("awaiting_request_confirmation", True)]
                except Exception:
                    pass

                preview_msg = (
                    f"Đã cập nhật thông tin đơn của bạn:\n"
                    f"- Môn: {curr_course}\n"
                    f"- Lớp: {curr_class}\n"
                    f"- Từ: {start_show}\n"
                    f"- Đến: {end_show}\n"
                    f"- Lý do: {curr_reason}\n"
                    f"- Minh chứng: {curr_evidence if curr_evidence and str(curr_evidence).strip().lower() not in {'không', 'khong', 'no', ''} else 'Không có'}\n\n"
                    f"Bạn xác nhận để mình lưu đơn nhé? (có / không / gõ thông tin cần sửa lại)"
                )
                dispatcher.utter_message(text=preview_msg)
                slot_events.append(SlotSet("awaiting_request_confirmation", True))
                return slot_events

            dispatcher.utter_message(
                text=(
                    "Bạn muốn điều chỉnh thông tin nào? Bạn có thể gõ thông tin cần sửa, ví dụ:\n"
                    "- *'ngày từ 28/8/2026 đến 1/9/2026'*\n"
                    "- *'sửa ngày kết thúc thành 2/9'*\n"
                    "- *'sửa lý do: đi khám bệnh tại bệnh viện'*\n"
                    "- *'sửa lớp DH21IT02'*\n"
                    "Hoặc gõ *'không'* / *'hủy'* nếu muốn hủy đơn này."
                )
            )
            return [SlotSet("awaiting_request_confirmation", True)]
        except Exception as e:
            dispatcher.utter_message(
                text=f"Có lỗi xử lý thông tin: {str(e)}. Bạn thử gõ lại thông tin nhé."
            )
            return [SlotSet("awaiting_request_confirmation", True)]


class ActionCheckAbsenceStatus(Action):
    def name(self) -> Text:
        return "action_check_absence_status"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        try:
            student_id = _get_student_id(tracker)
            requests = list_requests_by_student(student_id=student_id, limit=10)
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
        try:
            student_id = _get_student_id(tracker)
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
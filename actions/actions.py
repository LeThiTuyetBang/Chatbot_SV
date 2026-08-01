import sqlite3
import os
from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

# Xác định đường dẫn tuyệt đối tới file chatbot.db trong thư mục db/
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'db', 'chatbot.db')

class ActionSubmitAbsenceRequest(Action):
    def name(self) -> Text:
        return "action_submit_absence_request"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        # 1. Lấy thông tin từ các Slot do Form thu thập được
        course_code = tracker.get_slot('ma_mon_hoc') or tracker.get_slot('ma_mon')
        class_code = tracker.get_slot('ma_lop')
        start_date = tracker.get_slot('start_date')
        end_date = tracker.get_slot('end_date')
        reason = tracker.get_slot('reason')

        # 2. Lấy định danh sinh viên (student_id) từ phiên đăng nhập (Metadata hoặc Session)
        # Theo đúng yêu cầu: MSSV lấy từ phiên đăng nhập, không thu qua hội thoại!
        metadata = tracker.latest_message.get('metadata', {})
        student_id = metadata.get('student_id')

        # Nếu test trực tiếp qua Rasa Shell (chưa truyền metadata từ UI), ta gán tạm ID = 1 (Lê Thị Tuyết Băng)
        if not student_id:
            student_id = 1 

        # Kiểm tra xem đã đủ thông tin cơ bản chưa
        if not course_code or not start_date or not reason:
            dispatcher.utter_message(text="Thiếu thông tin quan trọng (môn học, ngày nghỉ hoặc lý do), vui lòng cung cấp đầy đủ nhé!")
            return []

        try:
            # 3. Kết nối CSDL SQLite
            conn = sqlite3.connect(DB_PATH)
            conn.execute("PRAGMA foreign_keys = ON;")
            cursor = conn.cursor()

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
            dispatcher.utter_message(
                text=f" Ghi nhận thành công đơn xin nghỉ môn **{course_code}** từ ngày **{start_date}** đến ngày **{end_date}**. "
                     f"Trạng thái hiện tại: **Chờ duyệt (PENDING)**. Mã đơn của bạn là #{request_id}."
            )

        except Exception as e:
            dispatcher.utter_message(text=f" Lỗi hệ thống khi lưu CSDL: {str(e)}")

        return []
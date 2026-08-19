import unittest
import json
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from webapp import app
from db.init_db import init_database
from db.store import validate_date_range, create_absence_request, update_request_status, STATUS_APPROVED, STATUS_CANCELLED

class SystemTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database()

    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test_secret'
        self.client = app.test_client()

    def test_01_date_validation_helper(self):
        """Kiểm tra helper validate_date_range"""
        # Hợp lệ
        try:
            validate_date_range("2026-08-20", "2026-08-20")
            validate_date_range("2026-08-20", "2026-08-25")
        except ValueError:
            self.fail("validate_date_range raised ValueError for valid dates")

        # Không hợp lệ (Ngày bắt đầu > Ngày kết thúc)
        with self.assertRaises(ValueError) as cm:
            validate_date_range("2026-08-20", "2026-08-19")
        self.assertEqual(str(cm.exception), "Ngày kết thúc không được trước ngày bắt đầu.")

    def test_02_unauthenticated_access_denied(self):
        """Kiểm tra chưa đăng nhập bị chặn truy cập API"""
        # Cố truy cập API sinh viên khi chưa login
        res = self.client.get('/api/student/requests')
        self.assertEqual(res.status_code, 401)
        data = json.loads(res.data.decode('utf-8'))
        self.assertFalse(data['ok'])
        self.assertIn("đăng nhập", data['message'].lower())

        # Cố truy cập API giáo vụ khi chưa login
        res = self.client.get('/api/admin/requests')
        self.assertEqual(res.status_code, 401)

    def test_03_student_login_and_create_request_validation(self):
        """Kiểm tra sinh viên đăng nhập và tạo đơn với date validation"""
        # 1. Đăng nhập sinh viên
        login_res = self.client.post('/api/auth/login', data=json.dumps({
            'username': '066305014844',
            'password': '123456'
        }), content_type='application/json')
        self.assertEqual(login_res.status_code, 200)

        # 2. Tạo đơn với ngày không hợp lệ (Bắt đầu 20/08/2026 > Kết thúc 19/08/2026)
        invalid_req_res = self.client.post('/api/student/requests', data=json.dumps({
            'course_code': 'Kiểm thử phần mềm',
            'class_code': 'DTH2151',
            'start_date': '2026-08-20',
            'end_date': '2026-08-19',
            'reason': 'Bị sốt'
        }), content_type='application/json')
        self.assertEqual(invalid_req_res.status_code, 400)
        invalid_data = json.loads(invalid_req_res.data.decode('utf-8'))
        self.assertFalse(invalid_data['ok'])
        self.assertEqual(invalid_data['message'], "Ngày kết thúc không được trước ngày bắt đầu.")

        # 3. Tạo đơn với ngày hợp lệ
        valid_req_res = self.client.post('/api/student/requests', data=json.dumps({
            'course_code': 'Kiểm thử phần mềm',
            'class_code': 'DTH2151',
            'start_date': '2026-08-20',
            'end_date': '2026-08-22',
            'reason': 'Bị sốt đi khám bệnh'
        }), content_type='application/json')
        self.assertEqual(valid_req_res.status_code, 200)
        valid_data = json.loads(valid_req_res.data.decode('utf-8'))
        self.assertTrue(valid_data['ok'])
        self.assertIn('id', valid_data['data'])

    def test_04_role_authorization_student_cannot_access_admin(self):
        """Kiểm tra sinh viên không được gọi API của giáo vụ"""
        # Đăng nhập sinh viên
        self.client.post('/api/auth/login', data=json.dumps({
            'username': '066305014844',
            'password': '123456'
        }), content_type='application/json')

        # Thử gọi API danh sách giáo vụ
        res = self.client.get('/api/admin/requests')
        self.assertEqual(res.status_code, 403)
        data = json.loads(res.data.decode('utf-8'))
        self.assertFalse(data['ok'])

    def test_05_staff_login_and_approve(self):
        """Kiểm tra giáo vụ đăng nhập và duyệt đơn thành công"""
        # Đăng nhập giáo vụ
        login_res = self.client.post('/api/auth/login', data=json.dumps({
            'username': 'gv_tien',
            'password': '123456'
        }), content_type='application/json')
        self.assertEqual(login_res.status_code, 200)

        # Lấy danh sách đơn admin
        req_res = self.client.get('/api/admin/requests?status=PENDING')
        self.assertEqual(req_res.status_code, 200)
        req_data = json.loads(req_res.data.decode('utf-8'))
        requests = req_data['data']['requests']

        if requests:
            target_id = requests[0]['id']
            approve_res = self.client.post(f'/api/admin/requests/{target_id}/approve')
            self.assertEqual(approve_res.status_code, 200)

if __name__ == '__main__':
    unittest.main()

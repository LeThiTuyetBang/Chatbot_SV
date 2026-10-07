import json
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from webapp import app
from db.init_db import init_database
from db.store import validate_date_range

STUDENT_USER = os.getenv("E2E_STUDENT_USER", "066305014844")
STUDENT_PASS = os.getenv("E2E_STUDENT_PASS", os.getenv("DEFAULT_PASSWORD", "MatKhauMoiCuaBan@2026"))
STAFF_USER = os.getenv("E2E_STAFF_USER", "gv_tien")
STAFF_PASS = os.getenv("E2E_STAFF_PASS", os.getenv("DEFAULT_PASSWORD", "MatKhauMoiCuaBan@2026"))


def _future(days: int) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


class SystemTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Đảm bảo có user seed (dùng DB dự án; không tạo ngày cố định)
        init_database()

    def setUp(self):
        # SECRET_KEY bắt buộc khi import webapp trong một số cấu hình
        if not os.environ.get("SECRET_KEY"):
            os.environ["SECRET_KEY"] = "test_secret_key_for_unittest"
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "test_secret_key_for_unittest")
        self.client = app.test_client()

    def test_01_date_validation_helper(self):
        """validate_date_range với ngày tương đối."""
        s, e = _future(5), _future(7)
        try:
            validate_date_range(s, s)
            validate_date_range(s, e)
        except ValueError:
            self.fail("validate_date_range raised ValueError for valid future dates")

        with self.assertRaises(ValueError) as cm:
            validate_date_range(_future(7), _future(5))
        self.assertIn("không được trước", str(cm.exception))

        # Quá khứ phải bị chặn
        past = (date.today() - timedelta(days=3)).isoformat()
        with self.assertRaises(ValueError):
            validate_date_range(past, past)

    def test_02_unauthenticated_access_denied(self):
        res = self.client.get("/api/student/requests")
        self.assertEqual(res.status_code, 401)
        data = json.loads(res.data.decode("utf-8"))
        self.assertFalse(data["ok"])
        self.assertIn("đăng nhập", data["message"].lower())

        res = self.client.get("/api/admin/requests")
        self.assertEqual(res.status_code, 401)

    def test_03_student_login_and_create_request_validation(self):
        login_res = self.client.post(
            "/api/auth/login",
            data=json.dumps({"username": STUDENT_USER, "password": STUDENT_PASS}),
            content_type="application/json",
        )
        self.assertEqual(login_res.status_code, 200)

        # Ngày bắt đầu > kết thúc
        invalid_req_res = self.client.post(
            "/api/student/requests",
            data=json.dumps({
                "course_code": "Kiểm thử phần mềm",
                "class_code": "DTH2151",
                "start_date": _future(10),
                "end_date": _future(8),
                "reason": "Bị sốt",
            }),
            content_type="application/json",
        )
        self.assertEqual(invalid_req_res.status_code, 400)
        invalid_data = json.loads(invalid_req_res.data.decode("utf-8"))
        self.assertFalse(invalid_data["ok"])
        self.assertIn("không được trước", invalid_data["message"])

        # Ngày hợp lệ (môn + offset riêng để giảm chồng với E2E/DB cũ)
        valid_req_res = self.client.post(
            "/api/student/requests",
            data=json.dumps({
                "course_code": "UnitTest Mon System",
                "class_code": "DTH2151",
                "start_date": _future(40),
                "end_date": _future(42),
                "reason": "Bị sốt đi khám bệnh",
            }),
            content_type="application/json",
        )
        self.assertEqual(valid_req_res.status_code, 200, valid_req_res.data)
        valid_data = json.loads(valid_req_res.data.decode("utf-8"))
        self.assertTrue(valid_data["ok"])
        self.assertIn("id", valid_data["data"])

    def test_04_role_authorization_student_cannot_access_admin(self):
        self.client.post(
            "/api/auth/login",
            data=json.dumps({"username": STUDENT_USER, "password": STUDENT_PASS}),
            content_type="application/json",
        )
        res = self.client.get("/api/admin/requests")
        self.assertEqual(res.status_code, 403)
        data = json.loads(res.data.decode("utf-8"))
        self.assertFalse(data["ok"])

    def test_05_staff_login_and_approve(self):
        login_res = self.client.post(
            "/api/auth/login",
            data=json.dumps({"username": STAFF_USER, "password": STAFF_PASS}),
            content_type="application/json",
        )
        self.assertEqual(login_res.status_code, 200)

        req_res = self.client.get("/api/admin/requests?status=PENDING")
        self.assertEqual(req_res.status_code, 200)
        req_data = json.loads(req_res.data.decode("utf-8"))
        requests_list = req_data["data"]["requests"]

        if requests_list:
            target_id = requests_list[0]["id"]
            approve_res = self.client.post(f"/api/admin/requests/{target_id}/approve")
            self.assertEqual(approve_res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
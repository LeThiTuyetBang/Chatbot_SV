import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.store import (
    validate_date_range,
    validate_evidence_url,
    create_absence_request,
    get_user_by_credentials,
)
from actions.actions import _parse_date_text


def _future(days: int) -> str:
    """Ngày ISO (YYYY-MM-DD) cách hôm nay `days` ngày (luôn trong tương lai)."""
    return (date.today() + timedelta(days=days)).isoformat()


class TestDateParsing(unittest.TestCase):
    """Test hàm _parse_date_text – mock today để kết quả ổn định."""

    @patch("actions.actions.date")
    def test_relative_dates(self, mock_date):
        fixed_today = date(2026, 10, 2)
        mock_date.today.return_value = fixed_today
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

        self.assertEqual(_parse_date_text("mai"), "2026-10-03")
        self.assertEqual(_parse_date_text("ngày mai"), "2026-10-03")
        self.assertEqual(_parse_date_text("ngày kia"), "2026-10-04")
        self.assertEqual(_parse_date_text("mốt"), "2026-10-04")
        self.assertEqual(_parse_date_text("hôm nay"), "2026-10-02")

    def test_absolute_dates(self):
        # Parse tuyệt đối không phụ thuộc "có được xin nghỉ không"
        self.assertEqual(_parse_date_text("15/11/2026"), "2026-11-15")
        self.assertEqual(_parse_date_text("15-11-2026"), "2026-11-15")
        # dd/mm không năm → năm hiện tại
        d = date.today()
        expected = date(d.year, 11, 15).isoformat()
        self.assertEqual(_parse_date_text("15/11"), expected)


class TestValidateDateRange(unittest.TestCase):
    """Test validate_date_range với ngày tương đối so với hôm nay."""

    def test_valid_range(self):
        start_s, end_s = _future(10), _future(12)
        start, end = validate_date_range(start_s, end_s)
        self.assertEqual(start, start_s)
        self.assertEqual(end, end_s)

    def test_start_after_end(self):
        with self.assertRaises(ValueError) as cm:
            validate_date_range(_future(12), _future(10))
        self.assertIn("không được trước", str(cm.exception))

    def test_past_date(self):
        past = (date.today() - timedelta(days=5)).isoformat()
        past2 = (date.today() - timedelta(days=3)).isoformat()
        with self.assertRaises(ValueError) as cm:
            validate_date_range(past, past2)
        self.assertIn("quá khứ", str(cm.exception).lower())

    def test_invalid_format(self):
        with self.assertRaises(ValueError):
            validate_date_range("abc", _future(5))
        with self.assertRaises(ValueError):
            validate_date_range("2026-13-45", _future(5))

    def test_too_far_future(self):
        # max_future_days mặc định = 90
        far = (date.today() + timedelta(days=100)).isoformat()
        far2 = (date.today() + timedelta(days=102)).isoformat()
        with self.assertRaises(ValueError) as cm:
            validate_date_range(far, far2)
        self.assertIn("tương lai", str(cm.exception).lower())


class TestEvidenceUrl(unittest.TestCase):
    def test_valid_url(self):
        url = validate_evidence_url("https://drive.google.com/file/123")
        self.assertTrue(url.startswith("https://"))

    def test_empty_allowed(self):
        self.assertEqual(validate_evidence_url(""), "")
        self.assertEqual(validate_evidence_url("   "), "")

    def test_javascript_blocked(self):
        with self.assertRaises(ValueError):
            validate_evidence_url("javascript:alert(1)")

    def test_data_scheme_blocked(self):
        with self.assertRaises(ValueError):
            validate_evidence_url("data:text/html,<script>alert(1)</script>")


class TestSystemWithTempDB(unittest.TestCase):
    """DB tạm – không đụng chatbot.db; không phụ thuộc student_id=1 cứng theo nghĩa 'user bất kỳ'."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()

        import db.store as store
        import db.init_db as init_db_mod

        self._store = store
        self._init_db = init_db_mod
        self.original_store_path = store.DB_PATH
        self.original_init_path = init_db_mod.DB_PATH

        store.DB_PATH = self.temp_db.name
        init_db_mod.DB_PATH = self.temp_db.name

        init_db_mod.init_database()

        # Lấy student_id thật từ user seed (không hardcode = 1)
        student = store.get_user_by_credentials("066305014844", os.getenv("DEFAULT_PASSWORD", "MatKhauMoiCuaBan@2026"))
        self.assertIsNotNone(student, "Seed student không tồn tại trong DB test")
        self.student_id = student["id"]

    def tearDown(self):
        self._store.DB_PATH = self.original_store_path
        self._init_db.DB_PATH = self.original_init_path
        try:
            os.unlink(self.temp_db.name)
        except OSError:
            pass

    def test_create_and_overlap(self):
        start1, end1 = _future(20), _future(22)
        start2, end2 = _future(21), _future(23)  # chồng với [20, 22]

        req_id = create_absence_request(
            student_id=self.student_id,
            course_code="CSDL",
            class_code="DTH2151",
            start_date=start1,
            end_date=end1,
            reason="Ốm",
            source="test",
        )
        self.assertIsInstance(req_id, int)

        with self.assertRaises(ValueError) as cm:
            create_absence_request(
                student_id=self.student_id,
                course_code="CSDL",
                class_code="DTH2151",
                start_date=start2,
                end_date=end2,
                reason="Ốm nữa",
                source="test",
            )
        self.assertIn("chồng lấn", str(cm.exception).lower())


if __name__ == "__main__":
    unittest.main()
import os
import sys
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

# Thêm project root vào path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.store import (
    validate_date_range,
    validate_evidence_url,
    has_overlapping_request,
    create_absence_request,
    normalize_date,
)
from actions.actions import _parse_date_text


class TestDateParsing(unittest.TestCase):
    """Test hàm _parse_date_text"""

    @patch("actions.actions.date")
    def test_relative_dates(self, mock_date):
        mock_date.today.return_value = date(2026, 10, 2)
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)

        self.assertEqual(_parse_date_text("mai"), "2026-10-03")
        self.assertEqual(_parse_date_text("ngày mai"), "2026-10-03")
        self.assertEqual(_parse_date_text("ngày kia"), "2026-10-04")
        self.assertEqual(_parse_date_text("mốt"), "2026-10-04")
        self.assertEqual(_parse_date_text("hôm nay"), "2026-10-02")

    def test_absolute_dates(self):
        self.assertEqual(_parse_date_text("5/10/2026"), "2026-10-05")
        self.assertEqual(_parse_date_text("05-10-2026"), "2026-10-05")
        self.assertEqual(_parse_date_text("5/10"), "2026-10-05")  # năm hiện tại


class TestValidateDateRange(unittest.TestCase):
    """Test validate_date_range"""

    def test_valid_range(self):
        start, end = validate_date_range("2026-10-05", "2026-10-07")
        self.assertEqual(start, "2026-10-05")
        self.assertEqual(end, "2026-10-07")

    def test_start_after_end(self):
        with self.assertRaises(ValueError) as cm:
            validate_date_range("2026-10-10", "2026-10-05")
        self.assertIn("không được trước", str(cm.exception))

    def test_past_date(self):
        with self.assertRaises(ValueError) as cm:
            validate_date_range("2020-01-01", "2020-01-02")
        self.assertIn("quá khứ", str(cm.exception).lower())

    def test_invalid_format(self):
        with self.assertRaises(ValueError):
            validate_date_range("abc", "2026-10-05")
        with self.assertRaises(ValueError):
            validate_date_range("2026-13-45", "2026-10-05")


class TestEvidenceUrl(unittest.TestCase):
    """Test validate_evidence_url"""

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
    """Test dùng database tạm, không đụng chatbot.db thật"""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        os.environ["TEST_DB_PATH"] = self.temp_db.name

        # Override DB_PATH trong store
        import db.store as store
        self.original_db_path = store.DB_PATH
        store.DB_PATH = self.temp_db.name

        # Khởi tạo schema
        from db.init_db import init_database
        init_database()

    def tearDown(self):
        import db.store as store
        store.DB_PATH = self.original_db_path
        try:
            os.unlink(self.temp_db.name)
        except:
            pass

    def test_create_and_overlap(self):
        # Tạo user trước (vì init_db đã insert mẫu)
        req_id = create_absence_request(
            student_id=1,
            course_code="CSDL",
            class_code="DTH2151",
            start_date="2026-10-10",
            end_date="2026-10-12",
            reason="Ốm",
            source="test"
        )
        self.assertIsInstance(req_id, int)

        # Thử tạo đơn chồng lấn → phải báo lỗi
        with self.assertRaises(ValueError) as cm:
            create_absence_request(
                student_id=1,
                course_code="CSDL",
                class_code="DTH2151",
                start_date="2026-10-11",
                end_date="2026-10-13",
                reason="Ốm nữa",
                source="test"
            )
        self.assertIn("chồng lấn", str(cm.exception).lower())


if __name__ == "__main__":
    unittest.main()
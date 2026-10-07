import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from actions.actions import _is_cancel_correction_text


class TestCancelCorrectionText(unittest.TestCase):
    def test_exact_cancel(self):
        for t in ["không", "khong", "hủy", "thôi", "no", "hủy đơn"]:
            self.assertTrue(_is_cancel_correction_text(t, None), msg=t)
            self.assertTrue(_is_cancel_correction_text(t, "deny"), msg=t)

    def test_not_cancel_evidence(self):
        for t in [
            "không có minh chứng",
            "khong co minh chung",
            "không có link",
            "không cần giấy",
        ]:
            self.assertFalse(_is_cancel_correction_text(t, None), msg=t)
            self.assertFalse(_is_cancel_correction_text(t, "deny"), msg=t)

    def test_not_cancel_reason(self):
        self.assertFalse(
            _is_cancel_correction_text("lý do không khỏe", None)
        )

    def test_cancel_absence_intent(self):
        self.assertTrue(
            _is_cancel_correction_text("bất kỳ", "cancel_absence")
        )


if __name__ == "__main__":
    unittest.main()
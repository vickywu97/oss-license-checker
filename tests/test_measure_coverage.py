"""measure_real_coverage.classify_unknown_reason 的回归测试。

该函数负责在「落 unknown」时反推真实原因（无字段 / UNKNOWN /
SEE LICENSE 等），是 README 诚实叙事的数据来源。
"""
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from scripts.measure_real_coverage import classify_unknown_reason  # noqa: E402


class ClassifyUnknownReasonTest(unittest.TestCase):
    def test_no_license_field(self):
        self.assertIn("无 license 字段",
                      classify_unknown_reason({"name": "x", "version": "1.0.0"}))

    def test_license_unknown(self):
        self.assertIn("UNKNOWN",
                      classify_unknown_reason({"license": "UNKNOWN"}))

    def test_license_unlicensed(self):
        self.assertIn("UNLICENSED",
                      classify_unknown_reason({"license": "UNLICENSED"}))

    def test_license_see_license_in_license(self):
        self.assertIn("SEE LICENSE",
                      classify_unknown_reason(
                          {"license": "SEE LICENSE IN LICENSE"}))

    def test_ambiguous_bsd(self):
        # 纯 BSD 含糊写法归一化失败 → 标记含糊而非猜测版本
        self.assertIn("含糊写法",
                      classify_unknown_reason({"license": "BSD License"}))


if __name__ == "__main__":
    unittest.main()

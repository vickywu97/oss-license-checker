"""measure_real_coverage 的 unknown 原因分类回归测试。

npm / Python 两类的原因反推，是 README 诚实叙事的数据来源：
不掩盖 unknown 桶，而是说明每个 unknown 到底是为什么。
"""
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from scripts.measure_real_coverage import (  # noqa: E402
    classify_python_unknown_reason,
    classify_unknown_reason,
)


def _write_metadata(tmp, text, name="METADATA"):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


class PythonUnknownReasonTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_license_unknown(self):
        meta = _write_metadata(self.tmp, "Name: x\nVersion: 1\nLicense: UNKNOWN\n")
        self.assertIn("UNKNOWN", classify_python_unknown_reason(meta))

    def test_license_file_only(self):
        """flask / Werkzeug 的真实情形：只给 License-File 指针，无 SPDX 字段。"""
        meta = _write_metadata(self.tmp,
                               "Name: werkzeug\nVersion: 3.1.8\n"
                               "License-File: LICENSE.txt\n")
        self.assertIn("License-File", classify_python_unknown_reason(meta))

    def test_classifier_only(self):
        meta = _write_metadata(self.tmp,
                               "Name: y\nVersion: 1\n"
                               "Classifier: License :: OSI Approved :: BSD License\n")
        self.assertIn("Classifier", classify_python_unknown_reason(meta))

    def test_no_license_declaration(self):
        meta = _write_metadata(self.tmp, "Name: z\nVersion: 1\nSummary: hi\n")
        self.assertIn("无任何 license 声明", classify_python_unknown_reason(meta))


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

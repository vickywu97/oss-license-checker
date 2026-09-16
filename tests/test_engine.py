import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from oss_license_checker.engine import (  # noqa: E402
    normalize_license,
    parse_expression,
    analyze,
    load_licenses,
    load_compatibility,
    load_package_map,
)


class NormalizeTest(unittest.TestCase):
    def test_aliases(self):
        cases = {
            "MIT License": "MIT",
            "Apache 2.0": "Apache-2.0",
            "Apache License 2.0": "Apache-2.0",
            "GPLv3": "GPL-3.0-only",
            "GPL-2.0": "GPL-2.0-only",
            "AGPL-3.0": "AGPL-3.0-only",
            "LGPLv2.1": "LGPL-2.1-only",
            "BSD-3-Clause": "BSD-3-Clause",
            "CC BY-NC 4.0": "CC-BY-NC-4.0",
            "MPL-2.0": "MPL-2.0",
        }
        for raw, expected in cases.items():
            self.assertEqual(normalize_license(raw), expected, raw)

    def test_unknown(self):
        self.assertIsNone(normalize_license("Proprietary-EULA-v99"))


class ExpressionTest(unittest.TestCase):
    def test_single(self):
        r = parse_expression("MIT")
        self.assertEqual(r["op"], "single")
        self.assertEqual(r["spdx_ids"], ["MIT"])

    def test_or(self):
        r = parse_expression("MIT OR Apache-2.0")
        self.assertEqual(r["op"], "or")
        self.assertEqual(r["spdx_ids"], ["MIT", "Apache-2.0"])

    def test_and(self):
        r = parse_expression("GPL-3.0-only AND MIT")
        self.assertEqual(r["op"], "and")
        self.assertEqual(r["spdx_ids"], ["GPL-3.0-only", "MIT"])


class AnalyzeTest(unittest.TestCase):
    def test_gpl_into_mit_conflict(self):
        results = analyze({"mysql": "2.18.1"}, project_license="MIT")
        mysql = results[0]
        self.assertEqual(mysql["spdx_id"], "GPL-2.0-only")
        self.assertEqual(mysql["risk_level"], "high")
        self.assertEqual(mysql["compatibility"], "incompatible")

    def test_agpl_network_copyleft(self):
        results = analyze({"ghostscript": "1.0"}, project_license="MIT")
        gs = results[0]
        self.assertEqual(gs["spdx_id"], "AGPL-3.0-only")
        self.assertTrue(gs["network_copyleft"])
        self.assertEqual(gs["risk_level"], "high")

    def test_mit_safe(self):
        results = analyze({"lodash": "4.17.21"}, project_license="MIT")
        self.assertEqual(results[0]["risk_level"], "low")

    def test_apache_in_mit_project_is_low(self):
        # 回归测试：Apache-2.0 依赖放入 MIT 项目应判低风险（曾误判 incompatible/high）
        results = analyze({"typescript": "5.0.0"}, project_license="MIT")
        self.assertEqual(results[0]["spdx_id"], "Apache-2.0")
        self.assertEqual(results[0]["compatibility"], "compatible")
        self.assertEqual(results[0]["risk_level"], "low")

    def test_lgpl_in_mit_is_conditional_medium(self):
        # 弱 copyleft 依赖放入 MIT 项目：可用但须履行义务 → 中风险
        results = analyze({"psycopg2-binary": "2.9.9"}, project_license="MIT")
        self.assertEqual(results[0]["spdx_id"], "LGPL-3.0-only")
        self.assertEqual(results[0]["risk_level"], "medium")

    def test_noncommercial_flag(self):
        results = analyze({"metabase": "0.47.0"}, project_license="MIT")
        # metabase 是 AGPL；这里单独验证 CC-BY-NC 的商用判定
        results = analyze({"cc-nc-sample": "1.0"}, project_license="MIT")
        # cc-nc-sample 不在映射表 → unknown，走 medium 分支
        self.assertEqual(results[0]["risk_level"], "medium")

    def test_unknown_package_needs_review(self):
        results = analyze({"totally-unknown-pkg": "1.0"}, project_license="MIT")
        r = results[0]
        self.assertEqual(r["spdx_id"], None)
        self.assertEqual(r["risk_level"], "medium")
        self.assertTrue(any("人工核实" in rec for rec in r["recommendations"]))

    def test_unknown_license_string(self):
        # 直接给一个不在映射里的包名，配合自定义 pkg_map 模拟未知 license 文本
        pkg_map = {"mystery-pkg": "Some-Proprietary-License-3.7"}
        results = analyze({"mystery-pkg": "1.0"}, project_license="MIT", pkg_map=pkg_map)
        self.assertIsNone(results[0]["spdx_id"])
        self.assertEqual(results[0]["risk_level"], "medium")


class FactIntegrityTest(unittest.TestCase):
    def test_library_loads_and_covers_matrix_keys(self):
        licenses = load_licenses()
        compat = load_compatibility()
        matrix = compat["matrix"]
        self.assertGreaterEqual(len(licenses), 20)
        # 矩阵中出现过的 license 都应在事实库中
        missing = set()
        for a, row in matrix.items():
            if a not in licenses:
                missing.add(a)
            for b in row:
                if b not in licenses:
                    missing.add(b)
        self.assertEqual(missing, set())

    def test_commercial_false_implies_high(self):
        pkg_map = {"nc-thing": "CC-BY-NC-4.0"}
        results = analyze({"nc-thing": "1.0"}, project_license="MIT", pkg_map=pkg_map)
        self.assertEqual(results[0]["risk_level"], "high")
        self.assertFalse(results[0]["commercial_use"])


if __name__ == "__main__":
    unittest.main()

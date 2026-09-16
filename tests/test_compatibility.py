import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from oss_license_checker.engine import load_compatibility  # noqa: E402


class CompatibilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = load_compatibility()["matrix"]
        cls.default = load_compatibility()["default"]

    def rel(self, a, b):
        return self.matrix.get(a, {}).get(b, self.default)

    def test_permissive_into_copyleft_one_way(self):
        # MIT 代码可并入 GPL-3.0 项目，反向不可
        self.assertEqual(self.rel("MIT", "GPL-3.0-only"), "one-way")

    def test_apache_vs_gpl2_incompatible(self):
        self.assertEqual(self.rel("Apache-2.0", "GPL-2.0-only"), "incompatible")

    def test_apache_vs_gpl3_compatible(self):
        self.assertEqual(self.rel("Apache-2.0", "GPL-3.0-only"), "compatible")

    def test_gpl2_vs_gpl3_incompatible(self):
        self.assertEqual(self.rel("GPL-2.0-only", "GPL-3.0-only"), "incompatible")

    def test_agpl_not_downgradable(self):
        self.assertEqual(self.rel("AGPL-3.0-only", "GPL-3.0-only"), "incompatible")

    def test_mpl_into_gpl_compatible(self):
        self.assertEqual(self.rel("MPL-2.0", "GPL-3.0-only"), "compatible")

    def test_cddl_into_gpl_incompatible(self):
        self.assertEqual(self.rel("CDDL-1.0", "GPL-3.0-only"), "incompatible")

    def test_nc_incompatible_everywhere(self):
        self.assertEqual(self.rel("CC-BY-NC-4.0", "MIT"), "incompatible")
        self.assertEqual(self.rel("CC-BY-NC-4.0", "Apache-2.0"), "incompatible")

    def test_unlisted_pair_defaults_unknown(self):
        # 矩阵未显式覆盖的组合应落到 default=unknown，而非抛错或静默放行
        self.assertEqual(self.rel("HPND", "EPL-2.0"), "unknown")


if __name__ == "__main__":
    unittest.main()

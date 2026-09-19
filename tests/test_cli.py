import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from oss_license_checker import cli  # noqa: E402
from oss_license_checker.engine import scan  # noqa: E402
from oss_license_checker.report import render_cyclonedx  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestCycloneDX(unittest.TestCase):
    def test_cyclonedx_structure(self):
        results = scan([os.path.join(ROOT, "demo", "sample_package.json")])
        bom = json.loads(render_cyclonedx(results, "demo-project", "MIT"))
        self.assertEqual(bom["bomFormat"], "CycloneDX")
        self.assertEqual(bom["specVersion"], "1.5")
        self.assertEqual(bom["metadata"]["component"]["name"], "demo-project")
        self.assertEqual(len(bom["components"]), len(results))
        props = {p["name"]: p["value"] for p in bom["components"][0]["properties"]}
        self.assertIn("vickywu:risk_level", props)

    def test_cyclonedx_via_main(self):
        rc = cli.main([
            "--format", "cyclonedx",
            os.path.join(ROOT, "demo", "sample_package.json"),
        ])
        self.assertEqual(rc, 0)


class TestFailOn(unittest.TestCase):
    def _write(self, text):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                       delete=False, encoding="utf-8")
        f.write(text)
        f.close()
        return f.name

    def test_fail_on_high_triggers(self):
        path = self._write("mysql==1.0.0\n")  # GPL-2.0 -> high
        try:
            self.assertEqual(cli.main(["--fail-on", "high", path]), 1)
        finally:
            os.unlink(path)

    def test_fail_on_high_passes_clean(self):
        path = self._write("requests==2.31.0\nflask==3.0.0\n")  # permissive
        try:
            self.assertEqual(cli.main(["--fail-on", "high", path]), 0)
        finally:
            os.unlink(path)

    def test_default_no_fail(self):
        path = self._write("mysql==1.0.0\n")
        try:
            self.assertEqual(cli.main([path]), 0)
        finally:
            os.unlink(path)

    def test_fail_on_transitive_gpl_permissive_project(self):
        # MIT 项目 + 传递 GPL 依赖（ffmpeg-static）→ 视同 high，应 fail
        demo = os.path.join(ROOT, "demo", "with_gpl_transitive", "package.json")
        self.assertEqual(
            cli.main(["--transitive", "--fail-on", "high", demo]), 1)

    def test_fail_on_transitive_gpl_strong_project_passes(self):
        # 项目自身即为强传染（GPL-3.0-only），其 GPL 传递依赖属合规，
        # 不应误报 fail（宽松项目 + GPL 依赖才会 fail）
        demo = os.path.join(ROOT, "demo", "with_gpl_transitive", "package.json")
        self.assertEqual(
            cli.main(["--transitive", "--fail-on", "high",
                      "--project-license", "GPL-3.0-only", demo]), 0)


if __name__ == "__main__":
    unittest.main()

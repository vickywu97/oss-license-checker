"""engine / report 与依赖图的集成测试。

验证：传递依赖被纳入逐依赖判定、传染路径落到结果里、
无 lock 时优雅降级、报告渲染出「传递依赖传染分析」章节。
"""
import json
import os
import shutil
import tempfile
import unittest

from oss_license_checker.engine import scan_with_graph
from oss_license_checker.report import render_markdown


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _make_project(tmp, with_lock=True):
    _write_json(os.path.join(tmp, "package.json"),
                {"name": "demo", "dependencies": {"acme-video-tool": "^1.0.0"}})
    if with_lock:
        _write_json(os.path.join(tmp, "package-lock.json"), {
            "lockfileVersion": 3,
            "packages": {
                "": {"dependencies": {"acme-video-tool": "^1.0.0"}},
                "node_modules/acme-video-tool": {
                    "version": "1.0.0", "dependencies": {"gpl-pkg": "^1.0.0"}},
                "node_modules/gpl-pkg": {"version": "1.0.0"},
            },
        })
    # 供 license_resolver 读取本地元数据（模拟已安装依赖）
    _write_json(os.path.join(tmp, "node_modules", "acme-video-tool", "package.json"),
                {"name": "acme-video-tool", "version": "1.0.0", "license": "MIT"})
    _write_json(os.path.join(tmp, "node_modules", "gpl-pkg", "package.json"),
                {"name": "gpl-pkg", "version": "1.0.0",
                 "license": "GPL-3.0-or-later"})


class ScanWithGraphTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_transitive_dep_analyzed_and_flagged(self):
        _make_project(self.tmp)
        results, info = scan_with_graph(
            [os.path.join(self.tmp, "package.json")],
            project_license="MIT", project_name="demo",
        )
        by_name = {r["package"]: r for r in results}
        # 传递依赖也被纳入逐依赖判定
        self.assertIn("gpl-pkg", by_name)
        gpl = by_name["gpl-pkg"]
        self.assertTrue(gpl["is_transitive"])
        self.assertEqual(gpl["infection_path"],
                         ["demo", "acme-video-tool@1.0.0", "gpl-pkg@1.0.0"])
        self.assertEqual(gpl["risk_level"], "high")
        self.assertTrue(any("传递依赖" in r for r in gpl["recommendations"]))
        # 直接依赖未被误标
        self.assertFalse(by_name["acme-video-tool"]["is_transitive"])
        self.assertEqual(info["direct_count"], 1)
        self.assertEqual(info["transitive_count"], 1)
        self.assertEqual(len(info["strong"]), 1)

    def test_report_contains_transitive_section(self):
        _make_project(self.tmp)
        results, info = scan_with_graph(
            [os.path.join(self.tmp, "package.json")],
            project_license="MIT", project_name="demo",
        )
        md = render_markdown(results, project_name="demo",
                             project_license="MIT", transitive=info)
        self.assertIn("## 传递依赖传染分析", md)
        self.assertIn("直接依赖", md)
        self.assertIn("gpl-pkg@1.0.0", md)
        self.assertIn("传染终点", md)

    def test_missing_lock_degrades_gracefully(self):
        _make_project(self.tmp, with_lock=False)
        results, info = scan_with_graph(
            [os.path.join(self.tmp, "package.json")],
            project_license="MIT", project_name="demo",
        )
        self.assertTrue(any("降级" in w for w in info["warnings"]))
        # 仅直接依赖被分析，且不误标为传递依赖
        self.assertEqual([r["package"] for r in results], ["acme-video-tool"])
        self.assertFalse(results[0]["is_transitive"])


if __name__ == "__main__":
    unittest.main()

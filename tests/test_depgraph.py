"""依赖图构建 + 传递依赖传染路径的测试。

覆盖：npm lock v3/v1、Python METADATA、Go vendor/go.mod 降级、
直接 vs 传递判定、传染最短路径、依赖环与深度上限保护、lock 缺失降级。
"""
import json
import os
import shutil
import tempfile
import unittest

from oss_license_checker.depgraph import (
    MAX_DEPTH,
    analyze_transitive,
    build_go_graph,
    build_graph,
    build_npm_graph,
    build_python_graph,
    classify_contagion,
)


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class NpmLockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_v3_direct_and_transitive(self):
        lock = os.path.join(self.tmp, "package-lock.json")
        _write(lock, {
            "lockfileVersion": 3,
            "packages": {
                "": {"dependencies": {"app-dep": "^1.0.0"}},
                "node_modules/app-dep": {"version": "1.0.0",
                                         "dependencies": {"mid-dep": "^2.0.0"}},
                "node_modules/mid-dep": {"version": "2.0.0",
                                         "dependencies": {"leaf-dep": "^3.0.0"}},
                "node_modules/leaf-dep": {"version": "3.0.0"},
            },
        })
        nodes, warns = build_npm_graph(lock)
        self.assertEqual(warns, [])
        self.assertEqual(len(nodes), 3)
        self.assertTrue(nodes["node_modules/app-dep"].is_direct)
        self.assertFalse(nodes["node_modules/mid-dep"].is_direct)
        self.assertFalse(nodes["node_modules/leaf-dep"].is_direct)
        # 边方向正确
        self.assertIn("node_modules/mid-dep", nodes["node_modules/app-dep"].children)
        self.assertIn("node_modules/app-dep", nodes["node_modules/mid-dep"].parents)

    def test_v3_scoped_nested_resolution(self):
        """@scope 包安装在嵌套 node_modules 下也能正确解析。"""
        lock = os.path.join(self.tmp, "package-lock.json")
        _write(lock, {
            "lockfileVersion": 3,
            "packages": {
                "": {"dependencies": {"parent": "^1"}},
                "node_modules/parent": {"version": "1.0.0",
                                        "dependencies": {"@scope/child": "^1"}},
                "node_modules/parent/node_modules/@scope/child": {"version": "1.2.0"},
            },
        })
        nodes, _ = build_npm_graph(lock)
        child = nodes["node_modules/parent/node_modules/@scope/child"]
        self.assertEqual(child.name, "@scope/child")
        self.assertEqual(child.version, "1.2.0")
        self.assertIn("node_modules/parent/node_modules/@scope/child",
                      nodes["node_modules/parent"].children)

    def test_v1_nested_fallback(self):
        lock = os.path.join(self.tmp, "package-lock.json")
        _write(lock, {"lockfileVersion": 1, "dependencies": {
            "a": {"version": "1.0.0", "dependencies": {
                "b": {"version": "2.0.0"}}}}})
        nodes, warns = build_npm_graph(lock)
        self.assertTrue(any("lockfileVersion 1" in w for w in warns))
        self.assertTrue(nodes["a"].is_direct)
        self.assertFalse(nodes["a->b"].is_direct)   # v1 嵌套键为 "父->子"
        self.assertIn("a->b", nodes["a"].children)


class PythonGraphTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _site(self, name):
        return os.path.join(self.tmp, name, "Lib", "site-packages")

    def test_requires_dist_graph_and_extras_skipped(self):
        site = self._site("venv")
        _write_text(os.path.join(site, "requests-2.31.0.dist-info", "METADATA"),
                    "Name: requests\n"
                    "Version: 2.31.0\n"
                    "Requires-Dist: urllib3 (<3)\n"
                    'Requires-Dist: pytest ; extra == "test"\n')
        _write_text(os.path.join(site, "urllib3-2.0.0.dist-info", "METADATA"),
                    "Name: urllib3\nVersion: 2.0.0\n")
        nodes, warns = build_python_graph([site])
        self.assertEqual(warns, [])
        self.assertEqual(len(nodes), 2)
        req = nodes["requests==2.31.0"]
        urllib = nodes["urllib3==2.0.0"]
        self.assertTrue(req.is_direct)          # 无父节点 → 顶层
        self.assertFalse(urllib.is_direct)      # 被 requests 依赖 → 传递
        self.assertIn("urllib3==2.0.0", req.children)
        # pytest 未安装 → 不应产生边
        self.assertNotIn("pytest", [n.name for n in nodes.values()])

    def test_direct_names_from_requirements(self):
        site = self._site("venv2")
        _write_text(os.path.join(site, "flask-3.0.0.dist-info", "METADATA"),
                    "Name: flask\nVersion: 3.0.0\nRequires-Dist: werkzeug\n")
        _write_text(os.path.join(site, "werkzeug-3.0.0.dist-info", "METADATA"),
                    "Name: werkzeug\nVersion: 3.0.0\n")
        nodes, _ = build_python_graph([site], direct_names=["flask"])
        self.assertTrue(nodes["flask==3.0.0"].is_direct)
        self.assertFalse(nodes["werkzeug==3.0.0"].is_direct)


class GoGraphTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_vendor_modules_txt_explicit_marks_direct(self):
        _write_text(os.path.join(self.tmp, "vendor", "modules.txt"),
                    "# github.com/pkg/errors v0.9.1\n"
                    "## explicit; go 1.13\n"
                    "github.com/pkg/errors\n"
                    "# github.com/sirupsen/logrus v1.9.0\n"
                    "github.com/sirupsen/logrus\n")
        nodes, warns = build_go_graph(self.tmp)
        self.assertEqual(len(nodes), 2)
        self.assertTrue(nodes["github.com/pkg/errors@v0.9.1"].is_direct)
        self.assertFalse(nodes["github.com/sirupsen/logrus@v1.9.0"].is_direct)
        self.assertTrue(any("未分析" in w for w in warns))

    def test_gomod_gosum_degrades_with_warning(self):
        _write_text(os.path.join(self.tmp, "go.mod"),
                    "module example.com/app\n\ngo 1.21\n\n"
                    "require github.com/pkg/errors v0.9.1\n")
        _write_text(os.path.join(self.tmp, "go.sum"),
                    "github.com/pkg/errors v0.9.1 h1:abc=\n"
                    "github.com/pkg/errors v0.9.1/go.mod h1:def=\n"
                    "github.com/sirupsen/logrus v1.9.0 h1:ghi=\n")
        nodes, warns = build_go_graph(self.tmp)
        self.assertTrue(nodes["github.com/pkg/errors@v0.9.1"].is_direct)
        self.assertIn("github.com/sirupsen/logrus@v1.9.0", nodes)
        self.assertTrue(any("传染路径未分析" in w for w in warns))


class InfectionPathTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _chain_lock(self):
        lock = os.path.join(self.tmp, "package-lock.json")
        _write(lock, {
            "lockfileVersion": 3,
            "packages": {
                "": {"dependencies": {"app-dep": "^1.0.0"}},
                "node_modules/app-dep": {"version": "1.0.0",
                                         "dependencies": {"mid-dep": "^2.0.0"}},
                "node_modules/mid-dep": {"version": "2.0.0",
                                         "dependencies": {"gpl-leaf": "^3.0.0"}},
                "node_modules/gpl-leaf": {"version": "3.0.0"},
            },
        })
        return build_npm_graph(lock)[0]

    def test_shortest_infection_path(self):
        nodes = self._chain_lock()
        nodes["node_modules/gpl-leaf"].spdx_id = "GPL-3.0-only"
        nodes["node_modules/gpl-leaf"].license = "GPL-3.0"
        info = analyze_transitive(nodes, project_name="my-project")
        self.assertEqual(info["direct_count"], 1)
        self.assertEqual(info["transitive_count"], 2)  # mid-dep + gpl-leaf
        self.assertEqual(len(info["strong"]), 1)
        entry = info["strong"][0]
        self.assertFalse(entry["is_direct"])          # 传递依赖
        self.assertEqual(entry["path"],
                         ["my-project", "app-dep@1.0.0", "mid-dep@2.0.0",
                          "gpl-leaf@3.0.0"])

    def test_weak_contagion_listed_separately(self):
        nodes = self._chain_lock()
        nodes["node_modules/mid-dep"].spdx_id = "LGPL-3.0-only"
        info = analyze_transitive(nodes, project_name="p")
        self.assertEqual(len(info["strong"]), 0)
        self.assertEqual(len(info["weak"]), 1)
        self.assertEqual(info["weak"][0]["name"], "mid-dep")

    def test_transitive_sorted_before_direct(self):
        """传递依赖的强传染优先于直接依赖（因其常被忽略）。"""
        nodes = self._chain_lock()
        nodes["node_modules/app-dep"].spdx_id = "GPL-2.0-only"   # 直接
        nodes["node_modules/gpl-leaf"].spdx_id = "AGPL-3.0-only"  # 传递
        info = analyze_transitive(nodes, project_name="p")
        self.assertEqual(info["strong"][0]["name"], "gpl-leaf")
        self.assertTrue(info["strong"][0]["is_direct"] is False)
        self.assertEqual(info["strong"][1]["name"], "app-dep")


class RobustnessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_cycle_does_not_hang(self):
        lock = os.path.join(self.tmp, "package-lock.json")
        _write(lock, {
            "lockfileVersion": 3,
            "packages": {
                "": {"dependencies": {"a": "^1"}},
                "node_modules/a": {"version": "1", "dependencies": {"b": "^1"}},
                "node_modules/b": {"version": "1", "dependencies": {"a": "^1"}},
            },
        })
        nodes, _ = build_npm_graph(lock)
        nodes["node_modules/b"].spdx_id = "GPL-3.0-only"
        info = analyze_transitive(nodes, project_name="p")
        self.assertEqual(info["total"], 2)
        self.assertEqual(len(info["strong"]), 1)

    def test_depth_cap_saturates_deep_nodes(self):
        lock = os.path.join(self.tmp, "package-lock.json")
        packages = {"": {"dependencies": {f"p0": "^1"}}}
        for i in range(25):
            deps = {f"p{i + 1}": "^1"} if i < 24 else {}
            packages[f"node_modules/p{i}"] = {"version": "1", "dependencies": deps}
        _write(lock, {"lockfileVersion": 3, "packages": packages})
        nodes, _ = build_npm_graph(lock)
        info = analyze_transitive(nodes, project_name="p")
        deepest = max(n.depth for n in nodes.values())
        self.assertLessEqual(deepest, MAX_DEPTH)
        self.assertTrue(any("上限" in w for w in info["warnings"]))

    def test_lock_missing_degrades(self):
        nodes, warns = build_graph(self.tmp, "npm")
        self.assertEqual(nodes, {})
        self.assertTrue(any("降级" in w for w in warns))


class ContagionClassifyTest(unittest.TestCase):
    def test_strong_weak_none(self):
        self.assertEqual(classify_contagion("GPL-3.0-only"), "strong")
        self.assertEqual(classify_contagion("AGPL-3.0-only"), "strong")
        self.assertEqual(classify_contagion("LGPL-2.1-only"), "weak")
        self.assertEqual(classify_contagion("MPL-2.0"), "weak")
        self.assertEqual(classify_contagion("MIT"), "none")
        self.assertEqual(classify_contagion(None), "none")


if __name__ == "__main__":
    unittest.main()

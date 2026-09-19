import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from oss_license_checker.license_resolver import (  # noqa: E402
    normalize_license_string,
    resolve_license,
)


class NormalizeTest(unittest.TestCase):
    def test_known_full_names(self):
        cases = {
            "MIT License": "MIT",
            "The MIT License (MIT)": "MIT",
            "Apache Software License": "Apache-2.0",
            "Apache License 2.0": "Apache-2.0",
            "GNU General Public License v3": "GPL-3.0-only",
            "GNU Lesser General Public License v2.1": "LGPL-2.1-only",
            "MPL-2.0": "MPL-2.0",
        }
        for raw, expected in cases.items():
            self.assertEqual(normalize_license_string(raw), expected, raw)

    def test_ambiguous_bsd_returns_none(self):
        # 含糊 BSD 无版本 → 不猜，宁可 unknown
        self.assertIsNone(normalize_license_string("BSD License"))
        self.assertIsNone(normalize_license_string("BSD"))
        # 但显式版本仍应识别
        self.assertEqual(normalize_license_string("BSD-3-Clause"), "BSD-3-Clause")
        self.assertEqual(normalize_license_string("BSD-2-Clause"), "BSD-2-Clause")


class NpmMetadataTest(unittest.TestCase):
    def test_read_npm_local_metadata(self):
        tmp = tempfile.mkdtemp()
        pkg_dir = os.path.join(tmp, "node_modules", "my-lib")
        os.makedirs(pkg_dir)
        with open(os.path.join(pkg_dir, "package.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "my-lib", "version": "1.2.3", "license": "MIT"}, f)
        from oss_license_checker.license_resolver import read_local_metadata
        self.assertEqual(read_local_metadata("my-lib", "1.2.3", "npm", tmp), "MIT")

    def test_read_npm_licenses_array(self):
        tmp = tempfile.mkdtemp()
        pkg_dir = os.path.join(tmp, "node_modules", "old-lib")
        os.makedirs(pkg_dir)
        with open(os.path.join(pkg_dir, "package.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "old-lib", "version": "0.1.0",
                       "licenses": [{"type": "Apache-2.0"}]}, f)
        from oss_license_checker.license_resolver import read_local_metadata
        self.assertEqual(read_local_metadata("old-lib", "0.1.0", "npm", tmp), "Apache-2.0")


class PythonMetadataTest(unittest.TestCase):
    def test_read_python_metadata(self):
        tmp = tempfile.mkdtemp()
        sp = os.path.join(tmp, "site-packages")
        os.makedirs(sp)
        dist = os.path.join(sp, "demo-pkg-xyz-2.31.0.dist-info")
        os.makedirs(dist)
        with open(os.path.join(dist, "METADATA"), "w", encoding="utf-8") as f:
            f.write("Metadata-Version: 2.1\nName: demo-pkg-xyz\nVersion: 2.31.0\n"
                    "License: MIT\n")
        from oss_license_checker.license_resolver import read_local_metadata
        self.assertEqual(read_local_metadata("demo-pkg-xyz", "2.31.0", "python", tmp), "MIT")

    def test_read_python_metadata_classifier_fallback(self):
        tmp = tempfile.mkdtemp()
        sp = os.path.join(tmp, "site-packages")
        os.makedirs(sp)
        dist = os.path.join(sp, "demo-pkg-clf-1.0.0.dist-info")
        os.makedirs(dist)
        with open(os.path.join(dist, "METADATA"), "w", encoding="utf-8") as f:
            f.write("Name: demo-pkg-clf\nVersion: 1.0.0\n"
                    "Classifier: License :: OSI Approved :: Apache Software License\n")
        from oss_license_checker.license_resolver import read_local_metadata
        self.assertEqual(read_local_metadata("demo-pkg-clf", "1.0.0", "python", tmp),
                         "Apache Software License")

    def test_read_python_metadata_license_file(self):
        # METADATA 无 License:/Classifier:，仅给 License-File: 指针 → 读文件识别
        tmp = tempfile.mkdtemp()
        sp = os.path.join(tmp, "site-packages")
        os.makedirs(sp)
        dist = os.path.join(sp, "demo-pkg-lf-1.0.0.dist-info")
        os.makedirs(dist)
        with open(os.path.join(dist, "METADATA"), "w", encoding="utf-8") as f:
            f.write("Name: demo-pkg-lf\nVersion: 1.0.0\nLicense-File: LICENSE\n")
        with open(os.path.join(dist, "LICENSE"), "w", encoding="utf-8") as f:
            f.write("MIT License\n\nPermission is hereby granted, free of charge, "
                    "to any person obtaining a copy of this software...\n")
        from oss_license_checker.license_resolver import read_local_metadata
        self.assertEqual(read_local_metadata("demo-pkg-lf", "1.0.0", "python", tmp), "MIT")

    def test_read_python_metadata_license_file_unknown(self):
        # License-File 指向无法识别的许可证文本 → 返回 None（走 unknown，不猜）
        tmp = tempfile.mkdtemp()
        sp = os.path.join(tmp, "site-packages")
        os.makedirs(sp)
        dist = os.path.join(sp, "demo-pkg-lu-1.0.0.dist-info")
        os.makedirs(dist)
        with open(os.path.join(dist, "METADATA"), "w", encoding="utf-8") as f:
            f.write("Name: demo-pkg-lu\nVersion: 1.0.0\nLicense-File: COPYING\n")
        with open(os.path.join(dist, "COPYING"), "w", encoding="utf-8") as f:
            f.write("This software is provided as-is with no warranty whatsoever.\n")
        from oss_license_checker.license_resolver import (
            read_local_metadata,
            resolve_license,
        )
        self.assertIsNone(read_local_metadata("demo-pkg-lu", "1.0.0", "python", tmp))
        raw, src = resolve_license("demo-pkg-lu", "1.0.0", "python", tmp, {})
        self.assertIsNone(raw)
        self.assertEqual(src, "unknown")


class GoMetadataTest(unittest.TestCase):
    def test_read_go_license_file(self):
        tmp = tempfile.mkdtemp()
        gopath = os.path.join(tmp, "gohome")
        cache = os.path.join(gopath, "pkg", "mod")
        mod_dir = os.path.join(cache, "github.com", "foo", "bar@v1.2.3")
        os.makedirs(mod_dir)
        with open(os.path.join(mod_dir, "LICENSE"), "w", encoding="utf-8") as f:
            f.write("MIT License\n\nPermission is hereby granted, free of charge, "
                    "to any person obtaining a copy of this software...")
        old_gopath = os.environ.get("GOPATH")
        os.environ["GOPATH"] = gopath
        try:
            from oss_license_checker.license_resolver import read_local_metadata
            self.assertEqual(
                read_local_metadata("github.com/foo/bar", "v1.2.3", "go", tmp), "MIT")
        finally:
            if old_gopath is None:
                os.environ.pop("GOPATH", None)
            else:
                os.environ["GOPATH"] = old_gopath


class FallbackTest(unittest.TestCase):
    def test_three_level_resolution(self):
        tmp = tempfile.mkdtemp()
        # 本地元数据存在的包 → local_metadata（即便不在映射表）
        local_dir = os.path.join(tmp, "node_modules", "local-only")
        os.makedirs(local_dir)
        with open(os.path.join(local_dir, "package.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "local-only", "license": "ISC"}, f)
        pkg_map = {"mapped-only": "MIT"}

        # 1) 本地元数据命中，不在映射表 → local_metadata
        raw, src = resolve_license("local-only", "1.0.0", "npm", tmp, pkg_map)
        self.assertEqual(raw, "ISC")
        self.assertEqual(src, "local_metadata")

        # 2) 本地不存在，但映射表有 → mapping_table
        raw, src = resolve_license("mapped-only", "1.0.0", "npm", tmp, pkg_map)
        self.assertEqual(raw, "MIT")
        self.assertEqual(src, "mapping_table")

        # 3) 两者都无 → unknown
        raw, src = resolve_license("ghost-pkg", "1.0.0", "npm", tmp, pkg_map)
        self.assertIsNone(raw)
        self.assertEqual(src, "unknown")

    def test_local_metadata_priority_over_mapping(self):
        # 本地元数据应与映射表冲突时，本地优先
        tmp = tempfile.mkdtemp()
        local_dir = os.path.join(tmp, "node_modules", "conflict")
        os.makedirs(local_dir)
        with open(os.path.join(local_dir, "package.json"), "w", encoding="utf-8") as f:
            json.dump({"name": "conflict", "license": "Apache-2.0"}, f)
        pkg_map = {"conflict": "GPL-3.0-only"}
        raw, src = resolve_license("conflict", "1.0.0", "npm", tmp, pkg_map)
        self.assertEqual(raw, "Apache-2.0")  # 本地胜出
        self.assertEqual(src, "local_metadata")

    def test_missing_metadata_degrades_to_mapping(self):
        # project_root 为空 / 生态未知 → 走映射表，不尝试本地读取
        pkg_map = {"just-mapped": "MIT"}
        raw, src = resolve_license("just-mapped", "1.0.0", None, None, pkg_map)
        self.assertEqual(raw, "MIT")
        self.assertEqual(src, "mapping_table")


class LicenseExpressionTest(unittest.TestCase):
    def _write_dist(self, meta_text, lic_text="", lic_name="LICENSE.txt", name="demo-exp"):
        tmp = tempfile.mkdtemp()
        sp = os.path.join(tmp, "site-packages")
        os.makedirs(sp)
        dist = os.path.join(sp, f"{name}-1.0.0.dist-info")
        os.makedirs(dist)
        with open(os.path.join(dist, "METADATA"), "w", encoding="utf-8") as f:
            f.write(meta_text)
        if lic_text:
            with open(os.path.join(dist, lic_name), "w", encoding="utf-8") as f:
                f.write(lic_text)
        return tmp

    def test_license_expression_bsd3(self):
        # PEP 639 License-Expression 应被直接读取（Werkzeug/MarkupSafe 实际声明）
        tmp = self._write_dist(
            "Name: demo-exp\nVersion: 1.0.0\n"
            "License-Expression: BSD-3-Clause\nLicense-File: LICENSE.txt\n")
        from oss_license_checker.license_resolver import read_local_metadata
        self.assertEqual(
            read_local_metadata("demo-exp", "1.0.0", "python", tmp), "BSD-3-Clause")

    def test_license_expression_precedence_over_file(self):
        # 即便同时有 License-File 指向无法识别的文本，License-Expression 优先
        tmp = self._write_dist(
            "Name: demo-exp2\nVersion: 1.0.0\n"
            "License-Expression: MIT\nLicense-File: LICENSE.txt\n",
            lic_text="Some proprietary-looking text without SPDX markers.\n",
            name="demo-exp2")
        from oss_license_checker.license_resolver import read_local_metadata
        self.assertEqual(
            read_local_metadata("demo-exp2", "1.0.0", "python", tmp), "MIT")

    def test_python_metadata_bsd3_from_license_text(self):
        # 老包只给 License-File，但 LICENSE 正文含禁止背书条款 → 识别为 BSD-3-Clause
        bsd3 = ("Copyright 2020 X\n\nRedistribution and use in source and binary "
                "forms, with or without modification, are permitted provided that "
                "the following conditions are met:\n\n1. ...\n2. ...\n3. Neither "
                "the name of the copyright holder nor the names of its "
                "contributors may be used to endorse or promote products derived "
                "from this software without specific prior written permission.\n")
        tmp = tempfile.mkdtemp()
        sp = os.path.join(tmp, "site-packages")
        os.makedirs(sp)
        dist = os.path.join(sp, "demo-bsd3-1.0.0.dist-info")
        os.makedirs(dist)
        with open(os.path.join(dist, "METADATA"), "w", encoding="utf-8") as f:
            f.write("Name: demo-bsd3\nVersion: 1.0.0\nLicense-File: LICENSE.txt\n")
        with open(os.path.join(dist, "LICENSE.txt"), "w", encoding="utf-8") as f:
            f.write(bsd3)
        from oss_license_checker.license_resolver import read_local_metadata
        self.assertEqual(
            read_local_metadata("demo-bsd3", "1.0.0", "python", tmp), "BSD-3-Clause")

    def test_python_metadata_bsd2_from_license_text(self):
        # 仅含经典两条 + 免责声明、无背书/广告条款 → 识别为 BSD-2-Clause
        bsd2 = ("Copyright 2020 X\n\nRedistribution and use in source and binary "
                "forms, with or without modification, are permitted provided that "
                "the following conditions are met:\n\n1. ...\n2. ...\nTHIS SOFTWARE "
                "IS PROVIDED AS IS.\n")
        tmp = tempfile.mkdtemp()
        sp = os.path.join(tmp, "site-packages")
        os.makedirs(sp)
        dist = os.path.join(sp, "demo-bsd2-1.0.0.dist-info")
        os.makedirs(dist)
        with open(os.path.join(dist, "METADATA"), "w", encoding="utf-8") as f:
            f.write("Name: demo-bsd2\nVersion: 1.0.0\nLicense-File: LICENSE.txt\n")
        with open(os.path.join(dist, "LICENSE.txt"), "w", encoding="utf-8") as f:
            f.write(bsd2)
        from oss_license_checker.license_resolver import read_local_metadata
        self.assertEqual(
            read_local_metadata("demo-bsd2", "1.0.0", "python", tmp), "BSD-2-Clause")


if __name__ == "__main__":
    unittest.main()

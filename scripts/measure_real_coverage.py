#!/usr/bin/env python3
"""实测真实项目依赖树的 license 覆盖率（复用 license_resolver 三级解析）。

用法：
    # 先在某个目录安装一个真实项目（本脚本不负责安装）：
    mkdir -p /tmp/probe && cd /tmp/probe && npm init -y && npm install express
    python3 -m venv /tmp/pyvenv && /tmp/pyvenv/bin/pip install requests
    # 再跑本脚本：
    python3 scripts/measure_real_coverage.py --project /tmp/probe
    python3 scripts/measure_real_coverage.py --ecosystem python --project /tmp/pyvenv

输出：唯一依赖总数、各 license 来源计数、覆盖率，以及落 unknown 的包清单。
该数字用于 README 的「真实项目实测覆盖率」声明，支持作品集可复现性。
"""
import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from oss_license_checker.license_resolver import (  # noqa: E402
    resolve_license,
    normalize_license_string,
)
from oss_license_checker.engine import load_package_map  # noqa: E402


def iter_packages(node_modules_dir):
    """产出 node_modules 下所有「直接含 package.json 的包目录」(name, path)。"""
    for entry in sorted(os.listdir(node_modules_dir)):
        if entry.startswith("."):
            continue
        full = os.path.join(node_modules_dir, entry)
        if not os.path.isdir(full):
            continue
        if entry.startswith("@"):  # scope 目录，再下一层才是包
            for sub in sorted(os.listdir(full)):
                sub_full = os.path.join(full, sub)
                if os.path.isdir(sub_full) and os.path.isfile(
                    os.path.join(sub_full, "package.json")
                ):
                    yield f"{entry}/{sub}", sub_full
        else:
            if os.path.isfile(os.path.join(full, "package.json")):
                yield entry, full


def walk_node_modules(root):
    for dirpath, dirnames, _ in os.walk(root):
        if os.path.basename(dirpath) == "node_modules":
            project_root = os.path.dirname(dirpath)
            for name, pkg_path in iter_packages(dirpath):
                yield name, pkg_path, project_root


def classify_unknown_reason(meta):
    """落 unknown 的真实原因（用于 README 诚实叙事）。

    仅当 resolve_license 返回 source=="unknown" 时调用——即本地元数据读不到
    可用 SPDX，且内置映射表也未收录。这里从 package.json 反推为什么读不到。
    """
    lic = meta.get("license")
    lics = meta.get("licenses")
    if lic is None and not lics:
        return "无 license 字段（老包/内部包常见）"
    if isinstance(lic, str):
        low = lic.strip().lower()
        if low == "unknown":
            return "license 字段为 UNKNOWN"
        if low == "unlicensed":
            return "license 字段为 UNLICENSED（声明专有/未开源）"
        if "see license" in low:
            return "license 字段为 SEE LICENSE IN LICENSE（需读 LICENSE 文件）"
        if normalize_license_string(lic) is None:
            return f"license 字段存在但为含糊写法（{lic!r}），无法确定 SPDX"
        return f"license 字段无法解析（{lic!r}）"
    if isinstance(lic, dict):
        t = lic.get("type")
        if t and normalize_license_string(t) is None:
            return f"license.type 含糊写法（{t!r}）"
        return "license 字段为非标准对象且无可用 type"
    if isinstance(lics, list):
        return "licenses 数组为空或非标准"
    return "无 license 字段"


def classify_python_unknown_reason(meta_path):
    """Python METADATA 落 unknown 的原因（PyPI 的声明比 npm 混乱得多）。"""
    try:
        with open(meta_path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return "METADATA 不可读"
    lic = None
    classifier = None
    license_file = None
    for line in text.splitlines():
        if line.startswith("License:") and lic is None:
            lic = line[len("License:"):].strip()
        elif line.startswith("Classifier:") and "License ::" in line and classifier is None:
            classifier = line.split("::")[-1].strip()
        elif line.startswith("License-File:") and license_file is None:
            license_file = line[len("License-File:"):].strip()
    if lic:
        if lic.strip().upper() == "UNKNOWN":
            return "License: UNKNOWN"
        if normalize_license_string(lic) is None:
            return f"License 字段为 {lic!r}，无法归一化为 SPDX"
        return f"License 字段 {lic!r} 无法解析"
    if classifier:
        return f"仅有 Classifier 分类器 {classifier!r}，无法归一化为 SPDX"
    if license_file:
        return f"仅声明 License-File: {license_file}，指向文件无法识别 SPDX"
    return "METADATA 无任何 license 声明字段"


# venv 自带的引导工具，不是项目依赖，不计入覆盖率
_PYTHON_BOOTSTRAP = {"pip", "setuptools", "wheel", "pkg_resources", "distribute"}


def iter_python_packages(site_dirs):
    """产出 (name, version, meta_path, project_root)。"""
    for site in site_dirs:
        if not os.path.isdir(site):
            continue
        for entry in sorted(os.listdir(site)):
            if not (entry.endswith(".dist-info") or entry.endswith(".egg-info")):
                continue
            meta = os.path.join(site, entry, "METADATA")
            if not os.path.isfile(meta):
                continue
            name = version = None
            try:
                with open(meta, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if line.startswith("Name:"):
                            name = line[5:].strip()
                        elif line.startswith("Version:"):
                            version = line[8:].strip()
                        if name and version:
                            break
            except OSError:
                continue
            if name and name.lower() not in _PYTHON_BOOTSTRAP:
                # project_root 取 site-packages 的父目录，供 resolver 定位元数据
                yield name, version or "", meta, os.path.dirname(site)


def main():
    ap = argparse.ArgumentParser(description="实测真实项目 license 覆盖率")
    ap.add_argument("--project", required=True,
                    help="已安装依赖的项目目录（npm: 含 node_modules / python: venv 根目录）")
    ap.add_argument("--ecosystem", default="npm", choices=["npm", "python"])
    args = ap.parse_args()

    pkg_map = load_package_map()
    counts = {"local_metadata": 0, "mapping_table": 0, "unknown": 0}
    seen = set()
    unknowns = []

    if args.ecosystem == "npm":
        node_modules = os.path.join(args.project, "node_modules")
        if not os.path.isdir(node_modules):
            sys.exit(f"未在 {args.project} 找到 node_modules，请先 npm install")
        for name, pkg_path, project_root in walk_node_modules(args.project):
            try:
                with open(os.path.join(pkg_path, "package.json"),
                          encoding="utf-8") as f:
                    meta = json.load(f)
            except (OSError, ValueError):
                continue
            version = meta.get("version", "")
            key = (name, version)
            if key in seen:
                continue
            seen.add(key)
            _raw, source = resolve_license(
                name, version, "npm", project_root, pkg_map)
            counts[source] += 1
            if source == "unknown":
                unknowns.append((name, version, classify_unknown_reason(meta)))
    else:
        sites = [os.path.join(dirpath) for dirpath, dirnames, _ in os.walk(args.project)
                 if os.path.basename(dirpath) == "site-packages"]
        if not sites:
            sys.exit(f"未在 {args.project} 找到 site-packages，请先 pip install")
        for name, version, meta_path, project_root in iter_python_packages(sites):
            key = (name, version)
            if key in seen:
                continue
            seen.add(key)
            _raw, source = resolve_license(
                name, version, "python", project_root, pkg_map)
            counts[source] += 1
            if source == "unknown":
                unknowns.append((name, version,
                                 classify_python_unknown_reason(meta_path)))

    total = sum(counts.values())
    covered = counts["local_metadata"] + counts["mapping_table"]
    pct = (covered / total * 100) if total else 0.0

    print(f"## 真实项目实测覆盖率（{args.ecosystem} · {args.project}）")
    print(f"- 唯一依赖总数：{total}")
    print(f"- 来源统计：本地元数据 {counts['local_metadata']} · "
          f"内置映射表 {counts['mapping_table']} · 未知 {counts['unknown']}")
    print(f"- 覆盖率：{pct:.1f}%（{covered}/{total} 自动识别）")
    if unknowns:
        print(f"\n## 落 unknown 的包（{len(unknowns)}）")
        for name, version, reason in sorted(unknowns, key=lambda x: x[0]):
            print(f"- {name}@{version} — {reason}")


if __name__ == "__main__":
    main()

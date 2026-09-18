#!/usr/bin/env python3
"""实测真实项目依赖树的 license 覆盖率（复用 license_resolver 三级解析）。

用法：
    # 先在某个目录安装一个真实项目（本脚本不负责安装）：
    mkdir -p /tmp/probe && cd /tmp/probe && npm init -y && npm install express
    # 再跑本脚本：
    python3 scripts/measure_real_coverage.py --project /tmp/probe

输出：唯一依赖总数、各 license 来源计数、覆盖率，以及落 unknown 的包清单。
该数字用于 README 的「真实项目实测覆盖率」声明，支持作品集可复现性。
"""
import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from oss_license_checker.license_resolver import resolve_license  # noqa: E402
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


def main():
    ap = argparse.ArgumentParser(description="实测真实项目 license 覆盖率")
    ap.add_argument("--project", required=True,
                    help="含 node_modules 的已安装项目目录")
    ap.add_argument("--ecosystem", default="npm", choices=["npm"])
    args = ap.parse_args()

    node_modules = os.path.join(args.project, "node_modules")
    if not os.path.isdir(node_modules):
        sys.exit(f"未在 {args.project} 找到 node_modules，请先 npm install")

    pkg_map = load_package_map()
    counts = {"local_metadata": 0, "mapping_table": 0, "unknown": 0}
    seen = set()
    unknowns = []

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
            name, version, args.ecosystem, project_root, pkg_map
        )
        counts[source] += 1
        if source == "unknown":
            unknowns.append(f"{name}@{version}")

    total = sum(counts.values())
    covered = counts["local_metadata"] + counts["mapping_table"]
    pct = (covered / total * 100) if total else 0.0

    print(f"## 真实项目实测覆盖率（{args.project}）")
    print(f"- 唯一依赖总数：{total}")
    print(f"- 来源统计：本地元数据 {counts['local_metadata']} · "
          f"内置映射表 {counts['mapping_table']} · 未知 {counts['unknown']}")
    print(f"- 覆盖率：{pct:.1f}%（{covered}/{total} 自动识别）")
    if unknowns:
        print(f"\n## 落 unknown 的包（{len(unknowns)}）")
        for u in sorted(unknowns):
            print(f"- {u}")


if __name__ == "__main__":
    main()

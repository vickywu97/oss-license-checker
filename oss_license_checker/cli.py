"""命令行入口。

用法示例：
    python -m oss_license_checker --project-license MIT demo/sample_package.json
    python -m oss_license_checker --format json demo/sample_requirements.txt
    python -m oss_license_checker --list-licenses
"""
import argparse
import sys

from .engine import load_licenses, scan
from .report import render


def _list_licenses():
    licenses = load_licenses()
    print(f"共收录 {len(licenses)} 个 license 事实：")
    for spdx, f in licenses.items():
        copyleft = f["copyleft_scope"]
        commercial = "可商用" if f["commercial_use"] else "禁商用"
        print(f"  {spdx:<16} {f['category']:<18} {commercial}  传染:{copyleft}")


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="oss-license-checker",
        description="离线开源许可证合规判定：解析依赖清单 → 判定商用/传染/义务/冲突 → 输出报告。",
    )
    p.add_argument("files", nargs="*", help="依赖清单文件（package.json / requirements.txt / go.mod）")
    p.add_argument("--project-license", default="MIT", help="项目自身的 license（默认 MIT）")
    p.add_argument("--project-name", default="my-project", help="项目名（用于报告标题）")
    p.add_argument("--format", choices=["md", "json"], default="md", help="输出格式（默认 md）")
    p.add_argument("--output", "-o", default=None, help="输出到文件（默认打印到 stdout）")
    p.add_argument("--list-licenses", action="store_true", help="列出内置 license 事实库")
    args = p.parse_args(argv)

    if args.list_licenses:
        _list_licenses()
        return 0

    if not args.files:
        p.print_help()
        return 2

    results = scan(args.files, project_license=args.project_license)
    out = render(results, project_name=args.project_name,
                 project_license=args.project_license, fmt=args.format)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"报告已写入 {args.output}")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

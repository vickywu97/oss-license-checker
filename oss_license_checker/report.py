"""报告生成：Markdown（法务版）与 JSON（工程版）。"""
import json
from datetime import date

_DISCLAIMER = (
    "本报告由自动化合规检查工具生成，仅供初步筛查参考，"
    "不构成法律意见。最终合规判断请咨询执业律师。"
)

_RISK_LABEL = {"high": "🔴 高风险", "medium": "🟡 中风险", "low": "🟢 低风险"}

_COPYLEFT_LABEL = {
    "none": "无传染",
    "weak": "弱传染（库级）",
    "file": "文件级传染",
    "strong": "强传染（整体）",
    "network": "网络服务也传染（最强）",
}


def _risk_summary(results):
    s = {"high": 0, "medium": 0, "low": 0}
    for r in results:
        s[r["risk_level"]] = s.get(r["risk_level"], 0) + 1
    return s


def _fmt_obligations(obligations):
    if not obligations:
        return "无"
    return "；".join(obligations)


def render_markdown(results, project_name="my-project", project_license="MIT"):
    summary = _risk_summary(results)
    total = len(results)
    lines = []
    lines.append("# 开源许可证合规报告")
    lines.append("")
    lines.append(f"- **项目**：{project_name}")
    lines.append(f"- **项目 license**：{project_license}")
    lines.append(f"- **扫描时间**：{date.today().isoformat()}")
    lines.append(f"- **依赖总数**：{total}")
    lines.append(
        f"- **风险统计**：🔴 高风险 {summary['high']} · "
        f"🟡 中风险 {summary['medium']} · 🟢 低风险 {summary['low']}"
    )
    lines.append("")

    for level, title in (("high", "高风险依赖（需立即处理）"),
                         ("medium", "中风险依赖（需评估）"),
                         ("low", "低风险依赖（合规）")):
        group = [r for r in results if r["risk_level"] == level]
        if not group:
            continue
        lines.append(f"## {title}")
        lines.append("")
        for i, r in enumerate(group, 1):
            lines.append(f"### {i}. `{r['package']}@{r['version']}`")
            lines.append("")
            lines.append(f"- **License**：{r['license']}"
                         + (f"（{r['spdx_id']}）" if r["spdx_id"] else ""))
            if r["commercial_use"] is False:
                lines.append("- **商用**：❌ 禁止商业使用")
            if r["modification"] is False:
                lines.append("- **修改**：❌ 禁止演绎")
            lines.append(f"- **传染性**：{_COPYLEFT_LABEL.get(r['copyleft_scope'], r['copyleft_scope'] or '未知')}")
            lines.append(f"- **义务**：{_fmt_obligations(r['obligations'])}")
            lines.append(f"- **与项目 license 兼容性**：{r['compatibility']}")
            for rec in r["recommendations"]:
                lines.append(f"- **建议**：{rec}")
            lines.append("")

    lines.append("## 免责声明")
    lines.append("")
    lines.append(_DISCLAIMER)
    lines.append("")
    return "\n".join(lines)


def render_json(results, project_name="my-project", project_license="MIT"):
    summary = _risk_summary(results)
    return {
        "project": project_name,
        "project_license": project_license,
        "scanned_at": date.today().isoformat(),
        "total_dependencies": len(results),
        "risk_summary": summary,
        "dependencies": results,
        "disclaimer": _DISCLAIMER,
    }


def render(results, project_name="my-project", project_license="MIT", fmt="md"):
    if fmt == "json":
        return json.dumps(render_json(results, project_name, project_license),
                          ensure_ascii=False, indent=2)
    return render_markdown(results, project_name, project_license)

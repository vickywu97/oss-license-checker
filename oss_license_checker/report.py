"""报告生成：Markdown（法务版）与 JSON（工程版）与 CycloneDX SBOM。"""
import json
from datetime import date, datetime, timezone

from .engine import normalize_license

_DISCLAIMER = (
    "本报告由自动化合规检查工具生成，仅供初步筛查参考，"
    "不构成法律意见。最终合规判断请咨询执业律师。"
)

_RISK_LABEL = {"high": "🔴 高风险", "medium": "🟡 中风险", "low": "🟢 低风险"}

_SOURCE_LABEL = {
    "local_metadata": "本地元数据（已安装依赖）",
    "mapping_table": "内置映射表",
    "unknown": "未知（需人工核实）",
}

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


def _source_summary(results):
    s = {"local_metadata": 0, "mapping_table": 0, "unknown": 0}
    for r in results:
        key = r.get("license_source", "unknown")
        s[key] = s.get(key, 0) + 1
    total = len(results)
    covered = s["local_metadata"] + s["mapping_table"]
    coverage = round(covered / total * 100) if total else 0
    return s, coverage


def _fmt_obligations(obligations):
    if not obligations:
        return "无"
    return "；".join(obligations)


def render_markdown(results, project_name="my-project", project_license="MIT"):
    summary = _risk_summary(results)
    src_summary, coverage = _source_summary(results)
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
    lines.append(
        f"- **license 来源**：本地元数据 {src_summary['local_metadata']} · "
        f"内置映射表 {src_summary['mapping_table']} · 未知 {src_summary['unknown']}"
        f"（覆盖率 {coverage}%）"
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
            lines.append(f"- **License 来源**：{_SOURCE_LABEL.get(r.get('license_source'), r.get('license_source'))}")
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
    src_summary, coverage = _source_summary(results)
    return {
        "project": project_name,
        "project_license": project_license,
        "scanned_at": date.today().isoformat(),
        "total_dependencies": len(results),
        "risk_summary": summary,
        "license_source_summary": src_summary,
        "coverage_pct": coverage,
        "dependencies": results,
        "disclaimer": _DISCLAIMER,
    }


def render_cyclonedx(results, project_name="my-project", project_license="MIT"):
    """生成 CycloneDX 1.5 SBOM（JSON），使 SBOM 合规（EO 14028 / EU CRA）宣称可落地。"""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    proj_spdx = normalize_license(project_license) or "NOASSERTION"
    components = []
    for r in results:
        comp = {
            "type": "library",
            "name": r["package"],
            "version": r["version"],
            "licenses": [{"license": {"id": r["spdx_id"]}}] if r["spdx_id"] else [],
            "properties": [
                {"name": "vickywu:risk_level", "value": r["risk_level"]},
                {"name": "vickywu:compatibility", "value": r["compatibility"]},
                {"name": "vickywu:commercial_use", "value": str(r["commercial_use"])},
                {"name": "vickywu:copyleft_scope", "value": str(r["copyleft_scope"])},
                {"name": "vickywu:license_source", "value": r.get("license_source", "unknown")},
            ],
        }
        components.append(comp)
    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": ts,
            "component": {
                "type": "application",
                "name": project_name,
                "version": "0.0.0",
                "licenses": [{"license": {"id": proj_spdx}}],
            },
        },
        "components": components,
    }
    return json.dumps(bom, ensure_ascii=False, indent=2)


def render(results, project_name="my-project", project_license="MIT", fmt="md"):
    if fmt == "json":
        return json.dumps(render_json(results, project_name, project_license),
                          ensure_ascii=False, indent=2)
    if fmt == "cyclonedx":
        return render_cyclonedx(results, project_name, project_license)
    return render_markdown(results, project_name, project_license)

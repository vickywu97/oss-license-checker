"""判定引擎：license 归一化 / SPDX 表达式解析 / 商用·传染·义务·冲突判定 / 风险分级。

零网络、纯标准库。数据来源为 data/ 下的事实库、兼容矩阵与包名映射。
所有结论均为自动化初筛，不构成法律意见（见 report.py 的免责声明）。
"""
import json
import re
from pathlib import Path

from .parsers import detect

DATA_DIR = Path(__file__).parent / "data"

# 常见别名 → SPDX id。键已经过 _normalize_key 归一化处理。
_ALIASES = {
    "mit": "MIT",
    "apache-2.0": "Apache-2.0", "apache-2": "Apache-2.0", "apache": "Apache-2.0",
    "bsd-2-clause": "BSD-2-Clause", "bsd-2": "BSD-2-Clause",
    "bsd-3-clause": "BSD-3-Clause", "bsd-3": "BSD-3-Clause",
    "bsd": "BSD-3-Clause",
    "isc": "ISC",
    "unlicense": "Unlicense",
    "cc0-1.0": "CC0-1.0", "cc0": "CC0-1.0",
    "gpl-2.0-only": "GPL-2.0-only", "gpl-2.0": "GPL-2.0-only", "gpl-2": "GPL-2.0-only",
    "gpl-2.0-or-later": "GPL-2.0-only", "gpl-2.0+": "GPL-2.0-only",
    "gpl-3.0-only": "GPL-3.0-only", "gpl-3.0": "GPL-3.0-only", "gpl-3": "GPL-3.0-only",
    "gpl-3.0-or-later": "GPL-3.0-only", "gpl-3.0+": "GPL-3.0-only",
    "gpl": "GPL-3.0-only",
    "agpl-3.0-only": "AGPL-3.0-only", "agpl-3.0": "AGPL-3.0-only", "agpl-3": "AGPL-3.0-only",
    "agpl": "AGPL-3.0-only",
    "lgpl-2.1-only": "LGPL-2.1-only", "lgpl-2.1": "LGPL-2.1-only",
    "lgpl-3.0-only": "LGPL-3.0-only", "lgpl-3.0": "LGPL-3.0-only", "lgpl": "LGPL-3.0-only",
    "mpl-2.0": "MPL-2.0", "mpl-2": "MPL-2.0", "mpl": "MPL-2.0",
    "epl-2.0": "EPL-2.0", "epl-2": "EPL-2.0", "epl": "EPL-2.0",
    "cddl-1.0": "CDDL-1.0", "cddl-1": "CDDL-1.0", "cddl": "CDDL-1.0",
    "cc-by-4.0": "CC-BY-4.0", "cc-by": "CC-BY-4.0",
    "cc-by-sa-4.0": "CC-BY-SA-4.0", "cc-by-sa": "CC-BY-SA-4.0",
    "cc-by-nc-4.0": "CC-BY-NC-4.0", "cc-by-nc": "CC-BY-NC-4.0",
    "cc-by-nd-4.0": "CC-BY-ND-4.0", "cc-by-nd": "CC-BY-ND-4.0",
    "wtfpl": "WTFPL",
    "psf-2.0": "PSF-2.0", "python-2.0": "PSF-2.0",
    "hpnd": "HPND",
}


def _normalize_key(s):
    s = s.strip().lower()
    s = re.sub(r"\blicen[cs]e\b", "", s)
    s = s.replace("(", "").replace(")", "")
    s = re.sub(r"[^\w.+-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    # "gplv2" -> "gpl-2", "agplv3" -> "agpl-3"
    s = re.sub(r"v(\d)", r"-\1", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def normalize_license(license_str):
    """把任意 license 字符串归一化为 SPDX id；无法识别返回 None。"""
    if not license_str:
        return None
    return _ALIASES.get(_normalize_key(license_str))


def _load_jsonl(path):
    recs = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            recs[r["spdx_id"]] = r
    return recs


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_licenses():
    return _load_jsonl(DATA_DIR / "licenses.jsonl")


def load_compatibility():
    return _load_json(DATA_DIR / "compatibility.json")


def load_package_map():
    return _load_json(DATA_DIR / "package_licenses.json").get("packages", {})


def parse_expression(expr):
    """解析 license 表达式，返回 dict{spdx_ids, op, raw}。

    op ∈ {"single", "or", "and"}。OR 表示可任选其一（按最宽松理解），
    AND 表示须同时满足（全部义务叠加）。
    """
    if not expr:
        return {"spdx_ids": [], "op": "single", "raw": expr}
    raw = expr.strip()
    if re.search(r"\bAND\b", raw, re.I):
        parts = re.split(r"\bAND\b", raw, flags=re.I)
        ids = [normalize_license(p) for p in parts]
        return {"spdx_ids": [i for i in ids if i], "op": "and", "raw": raw}
    if re.search(r"\bOR\b", raw, re.I):
        parts = re.split(r"\bOR\b", raw, flags=re.I)
        ids = [normalize_license(p) for p in parts]
        return {"spdx_ids": [i for i in ids if i], "op": "or", "raw": raw}
    sid = normalize_license(raw)
    return {"spdx_ids": [sid] if sid else [], "op": "single", "raw": raw}


def _aggregate_facts(spdx_ids, licenses):
    """多个 spdx_id（AND 情形）合并事实：义务取并集、copyleft 取最强、商用取全真。"""
    if not spdx_ids:
        return None
    facts = [licenses[i] for i in spdx_ids if i in licenses]
    if not facts:
        return None
    scope_rank = {"none": 0, "weak": 1, "file": 2, "strong": 3, "network": 4}
    merged = {
        "commercial_use": all(f["commercial_use"] for f in facts),
        "modification": all(f["modification"] for f in facts),
        "copyleft_scope": max(facts, key=lambda f: scope_rank[f["copyleft_scope"]])["copyleft_scope"],
        "network_copyleft": any(f["network_copyleft"] for f in facts),
        "source_disclosure": any(f["source_disclosure"] for f in facts),
        "obligations": [],
        "patent_grant": any(f["patent_grant"] for f in facts),
    }
    seen = set()
    for f in facts:
        for o in f.get("obligations", []):
            if o not in seen:
                seen.add(o)
                merged["obligations"].append(o)
    return merged


def _risk_level(spdx_ids, facts, rel, spdx_known):
    if not spdx_known:
        return "medium"          # 无法自动识别 → 需人工核实
    if facts is None:
        return "medium"
    if not facts["commercial_use"]:
        return "high"            # 非商用许可
    scope = facts["copyleft_scope"]
    if scope == "network":
        return "high"
    if scope == "strong":
        return "low" if rel == "compatible" else "high"
    if scope in ("weak", "file"):
        return "medium"
    # permissive / none
    if rel == "incompatible":
        return "high"
    if rel in ("disputed", "conditional"):
        return "medium"
    return "low"


def _recommendations(spdx_known, facts, risk, rel):
    recs = []
    if not spdx_known or facts is None:
        recs.append("license 无法自动识别，需人工核实该包的 LICENSE 文件")
    if risk == "high":
        recs.append("寻找更宽松的替代包，或将依赖隔离为独立进程/服务以避免传染")
    elif risk == "medium":
        recs.append("评估是否需公开修改部分，或采用动态链接隔离")
    else:
        recs.append("正常使用，按要求保留版权声明与许可文本即可")
    if rel == "unknown":
        recs.append("与项目 license 的兼容性未收录，建议人工确认")
    elif rel == "one-way":
        recs.append("单向兼容：可并入，但反向不可，注意保持许可边界")
    return recs


def analyze(deps, project_license="MIT", licenses=None, compat=None, pkg_map=None):
    """对依赖清单做合规判定，返回结果列表（按风险从高到低排序）。"""
    licenses = licenses or load_licenses()
    compat = compat or load_compatibility()
    pkg_map = pkg_map or load_package_map()
    matrix = compat.get("matrix", {})

    proj_spdx = normalize_license(project_license)
    results = []

    for name, ver in deps.items():
        raw = pkg_map.get(name.lower())
        expr = parse_expression(raw)
        spdx_ids = expr["spdx_ids"]
        spdx_known = bool(spdx_ids)
        facts = _aggregate_facts(spdx_ids, licenses)

        # 与项目 license 的兼容关系（取第一个识别出的 spdx 判定；AND 时保守取最不利）
        rel = "unknown"
        if spdx_ids and proj_spdx:
            rels = []
            for sid in spdx_ids:
                r = matrix.get(sid, {}).get(proj_spdx, "unknown")
                rels.append(r)
            if "incompatible" in rels:
                rel = "incompatible"
            elif "disputed" in rels:
                rel = "disputed"
            elif "conditional" in rels:
                rel = "conditional"
            elif all(r == "unknown" for r in rels):
                rel = "unknown"
            else:
                rel = "compatible" if "compatible" in rels else rels[0]

        risk = _risk_level(spdx_ids, facts, rel, spdx_known)
        results.append({
            "package": name,
            "version": ver,
            "license": raw if raw else "unknown",
            "spdx_id": spdx_ids[0] if spdx_ids else None,
            "license_expression": expr["op"],
            "commercial_use": facts["commercial_use"] if facts else None,
            "modification": facts["modification"] if facts else None,
            "copyleft_scope": facts["copyleft_scope"] if facts else None,
            "network_copyleft": facts["network_copyleft"] if facts else None,
            "source_disclosure_required": facts["source_disclosure"] if facts else None,
            "patent_grant": facts["patent_grant"] if facts else None,
            "obligations": facts["obligations"] if facts else [],
            "risk_level": risk,
            "compatibility": rel,
            "recommendations": _recommendations(spdx_known, facts, risk, rel),
        })

    order = {"high": 0, "medium": 1, "low": 2}
    results.sort(key=lambda r: order.get(r["risk_level"], 9))
    return results


def scan(manifest_paths, project_license="MIT"):
    """解析多个清单文件（自动识别格式），合并去重后做判定。"""
    deps = {}
    for p in manifest_paths:
        parser = detect(p)
        if parser is None:
            continue
        for name, ver in parser(p).items():
            # 同名依赖保留（后出现的覆盖版本）；不影响 license 判定
            deps[name] = ver
    return analyze(deps, project_license=project_license)

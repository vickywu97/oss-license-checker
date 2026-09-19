"""判定引擎：license 归一化 / SPDX 表达式解析 / 商用·传染·义务·冲突判定 / 风险分级。

零网络、纯标准库。数据来源为 data/ 下的事实库、兼容矩阵与包名映射。
所有结论均为自动化初筛，不构成法律意见（见 report.py 的免责声明）。
"""
import json
import os
import re
import sys
from pathlib import Path

from .parsers import detect
from .license_resolver import resolve_license
from .depgraph import analyze_transitive, build_graph

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
    "gpl-2.0-or-later": "GPL-2.0-or-later", "gpl-2.0+": "GPL-2.0-or-later",
    "gpl-3.0-only": "GPL-3.0-only", "gpl-3.0": "GPL-3.0-only", "gpl-3": "GPL-3.0-only",
    "gpl-3.0-or-later": "GPL-3.0-or-later", "gpl-3.0+": "GPL-3.0-or-later",
    "gpl": "GPL-3.0-only",
    "agpl-3.0-only": "AGPL-3.0-only", "agpl-3.0": "AGPL-3.0-only", "agpl-3": "AGPL-3.0-only",
    "agpl-3.0-or-later": "AGPL-3.0-or-later", "agpl-3.0+": "AGPL-3.0-or-later",
    "agpl": "AGPL-3.0-only",
    "lgpl-2.1-only": "LGPL-2.1-only", "lgpl-2.1": "LGPL-2.1-only",
    "lgpl-2.1-or-later": "LGPL-2.1-or-later", "lgpl-2.1+": "LGPL-2.1-or-later",
    "lgpl-3.0-only": "LGPL-3.0-only", "lgpl-3.0": "LGPL-3.0-only",
    "lgpl-3.0-or-later": "LGPL-3.0-or-later", "lgpl-3.0+": "LGPL-3.0-or-later",
    "lgpl": "LGPL-3.0-only",
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

# SPDX 表达式解析占位符：临时遮蔽 -or-later，避免被 OR 运算符切割
_ORLATER_PH = "\x01OL\x01"


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


# ---------------------------------------------------------------------------
# SPDX 表达式解析（递归下降）：支持 AND / OR / WITH / 括号分组。
# ---------------------------------------------------------------------------
_TOK_RE = re.compile(r"\s*(\(|\)|AND|OR|WITH|[^\s()]+)\s*", re.I)


def _tokenize(work):
    return [m.group(1) for m in _TOK_RE.finditer(work)]


def _parse_or(toks, i):
    node, i = _parse_and(toks, i)
    nodes = [node]
    while i < len(toks) and toks[i].upper() == "OR":
        i += 1
        n, i = _parse_and(toks, i)
        nodes.append(n)
    if len(nodes) == 1:
        return nodes[0], i
    return ("OR", nodes), i


def _parse_and(toks, i):
    node, i = _parse_atom(toks, i)
    nodes = [node]
    while i < len(toks) and toks[i].upper() == "AND":
        i += 1
        n, i = _parse_atom(toks, i)
        nodes.append(n)
    if len(nodes) == 1:
        return nodes[0], i
    return ("AND", nodes), i


def _parse_atom(toks, i):
    if i >= len(toks):
        return None, i
    t = toks[i]
    if t == "(":
        node, i = _parse_or(toks, i + 1)
        if i < len(toks) and toks[i] == ")":
            i += 1
        return node, i
    lic = t
    i += 1
    exc = None
    if i < len(toks) and toks[i].upper() == "WITH":
        i += 1
        if i < len(toks):
            exc = toks[i]
            i += 1
    return ("LIC", lic, exc), i


def _iter_leaves(tree):
    if tree is None:
        return
    if isinstance(tree, tuple):
        tag = tree[0]
        if tag == "LIC":
            yield tree
        else:
            for child in tree[1]:
                yield from _iter_leaves(child)


def _restore(tok):
    return tok.replace(_ORLATER_PH, "-or-later")


def parse_expression(expr):
    """解析 SPDX 表达式，返回 dict{spdx_ids, op, raw, tree, exceptions}。

    op ∈ {"single", "and", "or"}。OR 表示可任选其一（按最宽松理解），
    AND 表示须同时满足（全部义务叠加）。支持括号分组与 WITH <例外>。
    """
    if not expr:
        return {"spdx_ids": [], "op": "single", "raw": expr, "tree": None, "exceptions": []}
    raw = " ".join(expr.strip().split())
    # 遮蔽 -or-later，避免被 OR 运算符误切
    work = raw.replace("-or-later", _ORLATER_PH).replace("-OR-LATER", _ORLATER_PH)
    toks = _tokenize(work)
    tree, _ = _parse_or(toks, 0)

    flat = []
    excs = set()
    for leaf in _iter_leaves(tree):
        lic = _restore(leaf[1])
        sid = normalize_license(lic)
        if sid:
            flat.append(sid)
        if leaf[2]:
            excs.add(leaf[2])
    op = tree[0].lower() if isinstance(tree, tuple) and tree[0] in ("AND", "OR") else "single"
    return {
        "spdx_ids": flat,
        "op": op,
        "raw": raw,
        "tree": tree,
        "exceptions": sorted(excs),
    }


def _flatten_options(tree):
    """OR 展开为多条备选方案；AND / 叶子各自为一条方案。"""
    if tree is None:
        return []
    if isinstance(tree, tuple) and tree[0] == "OR":
        opts = []
        for child in tree[1]:
            opts.extend(_flatten_options(child))
        return opts
    return [tree]


def _agg_rel(rels):
    if not rels:
        return "unknown"
    if "incompatible" in rels:
        return "incompatible"
    if "disputed" in rels:
        return "disputed"
    if "conditional" in rels:
        return "conditional"
    if all(r == "unknown" for r in rels):
        return "unknown"
    return "compatible" if "compatible" in rels else rels[0]


def _eval_option(opt_tree, proj_spdx, licenses, matrix):
    leaves = list(_iter_leaves(opt_tree))
    ids = [normalize_license(_restore(l[1])) for l in leaves]
    ids = [i for i in ids if i]
    facts = _aggregate_facts(ids, licenses)
    rels = [matrix.get(sid, {}).get(proj_spdx, "unknown") for sid in ids]
    return {"ids": ids, "facts": facts, "rel": _agg_rel(rels)}


_RISK_RANK = {"low": 0, "medium": 1, "high": 2, "none": 0}
_COMPAT_RANK = {"compatible": 0, "one-way": 1, "conditional": 2,
                "disputed": 3, "incompatible": 4, "unknown": 5}


def _option_score(rel, facts):
    risk = _risk_level([], facts, rel, bool(facts))
    return (_RISK_RANK.get(risk, 1), _COMPAT_RANK.get(rel, 5))


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
        # 强传染依赖：与项目兼容（compatible）或可单向并入（one-way，如
        # GPL-3.0-or-later 并入 GPL-3.0-only）即合规，判低；仅 incompatible 判高。
        # 否则会把「GPL 项目使用 GPL 依赖」这类正常合规场景误报为高风险。
        return "low" if rel in ("compatible", "one-way") else "high"
    if scope in ("weak", "file"):
        return "medium"
    # permissive / none
    if rel == "incompatible":
        return "high"
    if rel in ("disputed", "conditional"):
        return "medium"
    return "low"


def _recommendations(spdx_known, facts, risk, rel, op="single", raw_license=None):
    recs = []
    if not spdx_known or facts is None:
        recs.append("license 无法自动识别，需人工核实该包的 LICENSE 文件")
        if raw_license and ("dual" in raw_license.lower()
                            or " or " in raw_license.lower()
                            or " and " in raw_license.lower()):
            recs.append("该声明疑似双许可/复合许可（如 Apache-2.0 OR BSD-3-Clause）："
                        "因 SPDX 单一值限制无法自动判定，建议人工确认后从最宽松条款选择")
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
    elif op == "or":
        recs.append("双许可（OR）：可择最宽松条款使用，已按最宽松方案评估")
    return recs


def _find_python_sites(project_root, include_global=True):
    """定位项目内可用的 site-packages（venv / Lib / 当前解释器）。

    ``include_global=False`` 时只认项目本地的 site-packages——用于**生态判定**：
    否则任何项目都会因为解释器自带 site-packages 而被误判成 Python 项目。
    """
    sites = []
    root = project_root
    for _ in range(3):
        for cand in (os.path.join(root, "site-packages"),
                     os.path.join(root, "Lib", "site-packages")):
            if os.path.isdir(cand):
                sites.append(cand)
        try:
            for entry in os.listdir(root):
                lib = os.path.join(root, entry, "lib")
                if not os.path.isdir(lib):
                    continue
                for ver in os.listdir(lib):
                    sp = os.path.join(lib, ver, "site-packages")
                    if os.path.isdir(sp):
                        sites.append(sp)
        except OSError:
            pass
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    if include_global:
        sites.extend(s for s in sys.path if s.endswith("site-packages"))
    return list(dict.fromkeys(sites))


def _detect_graph_ecosystem(project_root):
    if os.path.isfile(os.path.join(project_root, "package-lock.json")):
        return "npm"
    if (os.path.isfile(os.path.join(project_root, "go.mod"))
            or os.path.isdir(os.path.join(project_root, "vendor"))):
        return "go"
    if _find_python_sites(project_root, include_global=False):
        return "python"
    return None


def resolve_graph(project_root, project_name="my-project", python_direct=None,
                  pkg_map=None):
    """构建依赖图 → ``(marks, transitive_info, graph_deps)``。

    ``marks`` 以包名索引：``{"is_transitive": bool, "depth": int,
    "infection_path": [...]}``（仅强传染传递依赖带路径）。
    ``graph_deps`` 是图里出现的全部依赖 ``{name: version}``，用于把传递依赖
    也纳入逐依赖判定（开启 ``--transitive`` 时）。
    """
    pkg_map = pkg_map or load_package_map()
    eco = _detect_graph_ecosystem(project_root)
    if eco is None:
        return {}, {"total": 0, "direct_count": 0, "transitive_count": 0,
                    "strong": [], "weak": [],
                    "warnings": ["未识别到依赖图来源（无 package-lock.json / "
                                 "go.mod / site-packages），已降级为仅分析直接依赖"]}, {}

    def lookup(name, version):
        raw, _src = resolve_license(name, version, eco, project_root, pkg_map)
        return raw

    nodes, warns = build_graph(
        project_root, eco, license_lookup=lookup,
        python_sites=(_find_python_sites(project_root) if eco == "python" else None),
        python_direct=python_direct,
    )
    info = analyze_transitive(nodes, project_name=project_name, warnings=warns)
    marks = {}
    graph_deps = {}
    for node in nodes.values():
        marks[node.name] = {"is_transitive": not node.is_direct, "depth": node.depth}
        if node.name not in graph_deps or node.version:
            graph_deps[node.name] = node.version
    for s in info["strong"]:
        marks.setdefault(s["name"], {})["infection_path"] = s["path"]
    return marks, info, graph_deps


def analyze(deps, project_license="MIT", licenses=None, compat=None, pkg_map=None,
            project_root=None, ecosystem_map=None, graph_marks=None):
    """对依赖清单做合规判定，返回结果列表（按风险从高到低排序）。

    ``project_root`` 与 ``ecosystem_map`` 用于真实依赖检测：若提供，则优先
    读取已安装依赖自带的 license 元数据（见 license_resolver）；否则仅依赖
    内置映射表（与旧行为一致，旧测试无需改动）。
    """
    licenses = licenses or load_licenses()
    compat = compat or load_compatibility()
    pkg_map = pkg_map or load_package_map()
    matrix = compat.get("matrix", {})

    proj_spdx = normalize_license(project_license)
    results = []

    for name, ver in deps.items():
        eco = ecosystem_map.get(name) if ecosystem_map else None
        raw, source = resolve_license(name, ver, eco, project_root, pkg_map)
        expr = parse_expression(raw) if raw else parse_expression(None)
        spdx_ids = expr["spdx_ids"]
        spdx_known = bool(spdx_ids)
        tree = expr["tree"]

        # 与项目 license 的兼容关系
        if expr["op"] == "or" and tree:
            opts = _flatten_options(tree)
            scored = []
            for o in opts:
                ev = _eval_option(o, proj_spdx, licenses, matrix)
                ev["score"] = _option_score(ev["rel"], ev["facts"])
                scored.append(ev)
            best = min(scored, key=lambda e: e["score"])
            rel = best["rel"]
            facts = best["facts"]
            chosen_ids = best["ids"]
        elif expr["op"] == "and" and tree:
            ev = _eval_option(tree, proj_spdx, licenses, matrix)
            rel = ev["rel"]
            facts = ev["facts"]
            chosen_ids = ev["ids"]
        else:
            facts = _aggregate_facts(spdx_ids, licenses)
            chosen_ids = spdx_ids
            rels = [matrix.get(sid, {}).get(proj_spdx, "unknown") for sid in spdx_ids] if (spdx_ids and proj_spdx) else []
            rel = _agg_rel(rels)

        risk = _risk_level(chosen_ids, facts, rel, spdx_known)
        mark = (graph_marks or {}).get(name, {})
        is_transitive = bool(mark.get("is_transitive", False))
        strong_transitive = (is_transitive and facts
                             and facts["copyleft_scope"] in ("strong", "network"))

        recs = _recommendations(spdx_known, facts, risk, rel, expr["op"], raw)
        if strong_transitive:
            # 传递依赖的强传染最易被忽略：即使与项目 license 判定为兼容，
            # 也要显式提示沿依赖链复核传染范围。
            recs.append(
                f"⚠️ 传递依赖（第 {mark.get('depth', '?')} 层）含强传染许可："
                "请沿依赖链复核传染范围，必要时以独立进程/服务隔离"
            )
        results.append({
            "package": name,
            "version": ver,
            "license": raw if raw else "unknown",
            "spdx_id": chosen_ids[0] if chosen_ids else None,
            "license_expression": expr["op"],
            "chosen_license": (chosen_ids[0] if len(chosen_ids) == 1 else None),
            "exceptions": expr["exceptions"],
            "commercial_use": facts["commercial_use"] if facts else None,
            "modification": facts["modification"] if facts else None,
            "copyleft_scope": facts["copyleft_scope"] if facts else None,
            "network_copyleft": facts["network_copyleft"] if facts else None,
            "source_disclosure_required": facts["source_disclosure"] if facts else None,
            "patent_grant": facts["patent_grant"] if facts else None,
            "obligations": facts["obligations"] if facts else [],
            "license_source": source,
            "risk_level": risk,
            "compatibility": rel,
            "is_transitive": is_transitive,
            "depth": mark.get("depth", 0),
            "infection_path": mark.get("infection_path"),
            "recommendations": recs,
        })

    order = {"high": 0, "medium": 1, "low": 2}
    # 同风险级别内，传递依赖的强传染排在直接依赖之前（更易被忽略）
    results.sort(key=lambda r: (
        order.get(r["risk_level"], 9),
        0 if (r.get("is_transitive") and r.get("infection_path")) else 1,
        r["package"],
    ))
    return results


def _ecosystem_for(path):
    """按清单文件名推断生态（用于定位本地已安装依赖的元数据）。"""
    name = str(path).lower()
    if name.endswith("package.json"):
        return "npm"
    if name.endswith("go.mod"):
        return "go"
    if name.endswith("requirements.txt") or name.endswith(".txt"):
        return "python"
    return None


def _common_parent(paths):
    if not paths:
        return None
    common = os.path.abspath(paths[0])
    for p in paths[1:]:
        # 逐层上溯求公共祖先
        while not p.startswith(common + os.sep) and common != os.path.dirname(common):
            common = os.path.dirname(common)
    return common if os.path.isdir(common) else os.path.dirname(common)


def scan(manifest_paths, project_license="MIT", project_root=None,
         graph_marks=None):
    """解析多个清单文件（自动识别格式），合并去重后做判定。

    同时记录每个依赖所属生态，并将 ``project_root``（默认取清单文件公共父目录）
    传入判定引擎，以便优先读取已安装依赖的真实 license 元数据。
    ``graph_marks`` 来自 :func:`resolve_graph`，用于标注直接/传递依赖与传染路径。
    """
    deps = {}
    ecosystem_map = {}
    roots = []
    for p in manifest_paths:
        parser = detect(p)
        if parser is None:
            continue
        eco = _ecosystem_for(p)
        for name, ver in parser(p).items():
            # 同名依赖保留（后出现的覆盖版本）；不影响 license 判定
            deps[name] = ver
            ecosystem_map[name] = eco
        roots.append(os.path.dirname(os.path.abspath(p)))
    root = project_root or _common_parent(roots) or os.getcwd()
    return analyze(deps, project_license=project_license,
                  project_root=root, ecosystem_map=ecosystem_map,
                  graph_marks=graph_marks)


def scan_with_graph(manifest_paths, project_license="MIT", project_root=None,
                    project_name="my-project", python_direct=None):
    """在 :func:`scan` 之上构建依赖图，返回 ``(results, transitive_info)``。

    依赖图缺失（如未 npm install）时优雅降级：仅分析直接依赖，并在
    ``transitive_info["warnings"]`` 中说明原因。
    """
    roots = []
    deps = {}
    ecosystem_map = {}
    for p in manifest_paths:
        parser = detect(p)
        if parser is None:
            continue
        eco = _ecosystem_for(p)
        for name, ver in parser(p).items():
            deps[name] = ver
            ecosystem_map[name] = eco
        roots.append(os.path.dirname(os.path.abspath(p)))
    root = project_root or _common_parent(roots) or os.getcwd()
    marks, info, graph_deps = resolve_graph(root, project_name=project_name,
                                            python_direct=python_direct)
    # 传递依赖也纳入逐依赖判定：图里的包补充进 deps（清单里的直接依赖优先保留）
    eco = _detect_graph_ecosystem(root)
    for name, ver in graph_deps.items():
        if name not in deps:
            deps[name] = ver
            ecosystem_map.setdefault(name, eco)
    results = analyze(deps, project_license=project_license,
                      project_root=root, ecosystem_map=ecosystem_map,
                      graph_marks=marks)
    return results, info

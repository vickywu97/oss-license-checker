"""依赖图构建 + 传递依赖传染路径分析。

零网络、纯标准库。三种生态：

- **npm**：``package-lock.json``（lockfileVersion 2/3 的 ``packages`` 字段；
  v1 的嵌套 ``dependencies`` 递归兜底）
- **Python**：``site-packages/*/METADATA`` 的 ``Requires-Dist:`` 递归（不依赖 pipdeptree）
- **Go**：``vendor/modules.txt``（``## explicit`` 标直接依赖）→ 否则 ``go.mod`` +
  ``go.sum``。Go 的模块图本身不提供边信息，故传递依赖**无法计算传染路径**，
  显式标注「传递依赖未分析」而不是假装算得出。

安全约束：BFS 用 visited 集合 + 深度上限（``MAX_DEPTH``）防止依赖环导致无限递归。
"""
import json
import os
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

ROOT_KEY = "__root__"
MAX_DEPTH = 20

# 强传染（整体/网络级 copyleft）：项目一旦链接即可能被要求整体开源
_STRONG_PREFIXES = ("GPL-", "AGPL-")
# 弱传染（库级/文件级 copyleft）
_WEAK_PREFIXES = ("LGPL-", "MPL-", "EPL-", "CDDL-")


@dataclass
class DependencyNode:
    name: str
    version: str
    license: Optional[str] = None
    spdx_id: Optional[str] = None
    is_direct: bool = False
    parents: List[str] = field(default_factory=list)
    children: List[str] = field(default_factory=list)
    depth: int = 0
    key: str = ""


def classify_contagion(spdx_id):
    """把 SPDX id 归为 strong / weak / none 三档传染强度。"""
    if not spdx_id:
        return "none"
    s = str(spdx_id)
    if s.startswith(_STRONG_PREFIXES):
        return "strong"
    if s.startswith(_WEAK_PREFIXES):
        return "weak"
    return "none"


# ---------------------------------------------------------------------------
# npm
# ---------------------------------------------------------------------------
def _npm_pkg_name(path):
    """``node_modules/a/node_modules/@scope/b`` → ``@scope/b``。"""
    idx = path.rfind("node_modules/")
    if idx == -1:
        return path
    return path[idx + len("node_modules/"):]


def _npm_resolve(from_path, dep_name, packages):
    """按 npm 的向上查找规则解析依赖路径（先就近，再逐级上溯到根）。"""
    cur = from_path
    while True:
        cand = f"{cur}/node_modules/{dep_name}" if cur else f"node_modules/{dep_name}"
        if cand in packages:
            return cand
        if not cur:
            return None
        idx = cur.rfind("node_modules/")
        cur = "" if idx == -1 else cur[:idx].rstrip("/")


def _build_from_packages(packages, nodes, warnings):
    """lockfileVersion 2/3：``packages`` 字段，key 是安装路径。"""
    root_entry = packages.get("") or {}

    # npm 对 file: / workspace 依赖会写两条记录：
    #   "node_modules/x": {"resolved": "x", "link": true}   ← 符号链接别名，无 dependencies
    #   "x": {...真实包，带 dependencies...}
    # 必须跟随别名到真实条目，否则直接依赖会被连到一个没有子节点的空壳上。
    alias = {}
    for path, entry in packages.items():
        if path == "":
            continue
        if entry.get("link") and entry.get("resolved"):
            tgt = str(entry["resolved"]).replace("\\", "/").rstrip("/")
            if tgt in packages:
                alias[path] = tgt

    def resolve(from_path, dep_name):
        target = _npm_resolve(from_path, dep_name, packages)
        if target is None:
            return None
        return alias.get(target, target)

    for path, entry in packages.items():
        if path == "" or path in alias:   # 别名条目不单独建节点
            continue
        nodes[path] = DependencyNode(
            name=_npm_pkg_name(path),
            version=entry.get("version", ""),
            key=path,
        )

    # optionalDependencies 也要连边：sharp 等包的平台二进制包挂在 optional 下，
    # 若忽略会变成「无父节点的孤儿」，进而误报深度上限告警。
    def _declared(entry):
        names = list((entry.get("dependencies") or {}).keys())
        for n in (entry.get("optionalDependencies") or {}):
            if n not in names:
                names.append(n)
        return names

    direct = []
    for dep_name in _declared(root_entry):
        target = resolve("", dep_name)
        if target and target in nodes:
            nodes[target].is_direct = True
            direct.append(target)
        elif target is None:
            warnings.append(f"直接依赖 {dep_name} 未在 lock 中找到对应条目")
    for path, entry in packages.items():
        if path == "" or path in alias:
            continue
        for dep_name in _declared(entry):
            target = resolve(path, dep_name)
            if not target or target not in nodes:
                continue
            if target not in nodes[path].children:
                nodes[path].children.append(target)
            if path not in nodes[target].parents:
                nodes[target].parents.append(path)
    return direct


def _walk_v1(deps, packages_by_name, nodes, parent_key, warnings, depth=0):
    """lockfileVersion 1：嵌套 ``dependencies`` 递归（带深度上限防环）。"""
    if depth > MAX_DEPTH:
        warnings.append("依赖层级超过上限，已截断（lockfileVersion 1 嵌套过深）")
        return
    for name, entry in (deps or {}).items():
        key = f"{parent_key}->{name}" if parent_key else name
        ver = entry.get("version", "")
        if key not in nodes:
            nodes[key] = DependencyNode(
                name=name, version=ver, key=key,
                is_direct=(parent_key is None),
            )
        node = nodes[key]
        if parent_key and parent_key in nodes:
            if key not in nodes[parent_key].children:
                nodes[parent_key].children.append(key)
            if parent_key not in node.parents:
                node.parents.append(parent_key)
        _walk_v1(entry.get("dependencies"), packages_by_name, nodes,
                 key, warnings, depth + 1)


def build_npm_graph(lock_path):
    """解析 package-lock.json → (nodes, warnings)。"""
    with open(lock_path, encoding="utf-8") as f:
        data = json.load(f)
    nodes = {}
    warnings = []
    packages = data.get("packages")
    if packages:
        _build_from_packages(packages, nodes, warnings)
    elif data.get("dependencies"):
        _walk_v1(data.get("dependencies"), None, nodes, None, warnings)
        warnings.append("lockfileVersion 1：依赖图按嵌套结构重建，"
                        "可能与 npm 实际扁平化安装结果略有差异")
    else:
        warnings.append("package-lock.json 既无 packages 也无 dependencies 字段")
    return nodes, warnings


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------
_REQ_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _parse_dist_metadata(path):
    """读 METADATA → (name, version, [requires names])。"""
    name = version = None
    requires = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("Name:"):
                    name = line[5:].strip()
                elif line.startswith("Version:"):
                    version = line[8:].strip()
                elif line.startswith("Requires-Dist:"):
                    body = line.split(":", 1)[1].split(";", 1)[0].strip()
                    m = _REQ_RE.match(body)
                    if m:
                        requires.append(m.group(1))
                elif line.startswith("Requires:") and not line.startswith("Requires-Dist"):
                    # egg-info 旧格式：逗号分隔
                    for part in line.split(":", 1)[1].split(","):
                        p = part.strip()
                        if p:
                            requires.append(p)
    except OSError:
        return None, None, []
    return name, version, requires


def _norm_py(name):
    return re.sub(r"[-_.]+", "-", (name or "").lower())


def build_python_graph(site_dirs, direct_names=None):
    """扫描 site-packages 的 dist-info/egg-info METADATA → (nodes, warnings)。

    ``direct_names`` 为项目直接依赖名（如来自 requirements.txt）；未提供时，
    **未被任何其他已安装包依赖**的包视为直接依赖（图的根）。
    """
    nodes = {}
    warnings = []
    by_norm = {}

    for site in site_dirs:
        if not os.path.isdir(site):
            continue
        for entry in sorted(os.listdir(site)):
            if not (entry.endswith(".dist-info") or entry.endswith(".egg-info")):
                continue
            meta = os.path.join(site, entry, "METADATA")
            if not os.path.isfile(meta):
                continue
            name, version, requires = _parse_dist_metadata(meta)
            if not name:
                continue
            key = f"{name}=={version}" if version else name
            node = DependencyNode(name=name, version=version or "", key=key)
            node.children = []
            nodes[key] = node
            by_norm.setdefault(_norm_py(name), key)
            node._requires = requires  # 临时挂载，稍后连边

    for key, node in nodes.items():
        for req in getattr(node, "_requires", []):
            target = by_norm.get(_norm_py(req))
            if target and target != key:
                if target not in node.children:
                    node.children.append(target)
                if key not in nodes[target].parents:
                    nodes[target].parents.append(key)

    if direct_names:
        wanted = {_norm_py(n) for n in direct_names}
        matched = False
        for key, node in nodes.items():
            if _norm_py(node.name) in wanted:
                node.is_direct = True
                matched = True
        if not matched:
            warnings.append("requirements.txt 中的直接依赖均未在当前环境中找到，"
                            "已回退为「按无父节点判定直接依赖」")
            direct_names = None
    if not direct_names:
        # 无任何父节点 → 视为顶层（直接）依赖
        for node in nodes.values():
            if not node.parents:
                node.is_direct = True

    for node in nodes.values():
        if hasattr(node, "_requires"):
            delattr(node, "_requires")
    return nodes, warnings


# ---------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------
def _parse_modules_txt(path):
    """vendor/modules.txt → [(module, version, is_explicit)]。"""
    out = []
    cur = None
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if line.startswith("## explicit"):
                    if cur:
                        cur[2] = True
                elif line.startswith("# "):
                    parts = line[2:].split()
                    if len(parts) >= 2:
                        cur = [parts[0], parts[1], False]
                        out.append(cur)
    except OSError:
        return []
    return [(m, v, e) for m, v, e in out]


def _parse_go_mod(path):
    """go.mod 的 require 块 → [(module, version)]（仅直接依赖）。"""
    out = []
    in_block = False
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("require ("):
                    in_block = True
                    continue
                if in_block and line == ")":
                    in_block = False
                    continue
                if in_block or line.startswith("require "):
                    body = line[len("require "):] if line.startswith("require ") else line
                    body = body.split("//")[0].strip()
                    parts = body.split()
                    if len(parts) >= 2:
                        out.append((parts[0], parts[1]))
    except OSError:
        return []
    return out


def build_go_graph(project_root):
    """Go 依赖图。注意：模块图不提供边信息，传染路径无法计算。"""
    nodes = {}
    warnings = []
    vendor = os.path.join(project_root, "vendor", "modules.txt")
    go_mod = os.path.join(project_root, "go.mod")

    if os.path.isfile(vendor):
        for module, version, explicit in _parse_modules_txt(vendor):
            key = f"{module}@{version}"
            nodes[key] = DependencyNode(name=module, version=version,
                                        key=key, is_direct=explicit)
        warnings.append("Go：vendor/modules.txt 不提供模块间依赖边，"
                        "传递依赖传染路径未分析")
        return nodes, warnings

    if os.path.isfile(go_mod):
        for module, version in _parse_go_mod(go_mod):
            key = f"{module}@{version}"
            nodes[key] = DependencyNode(name=module, version=version,
                                        key=key, is_direct=True)
        go_sum = os.path.join(project_root, "go.sum")
        if os.path.isfile(go_sum):
            try:
                with open(go_sum, encoding="utf-8") as f:
                    for line in f:
                        parts = line.split()
                        if len(parts) >= 2 and not parts[1].endswith("/go.mod"):
                            key = f"{parts[0]}@{parts[1]}"
                            if key not in nodes:
                                nodes[key] = DependencyNode(
                                    name=parts[0], version=parts[1], key=key)
            except OSError:
                pass
        warnings.append("Go：无 vendor 目录，仅能区分直接依赖（go.mod）与"
                        "模块清单（go.sum）；模块间依赖边缺失，传递依赖传染路径未分析")
        return nodes, warnings

    warnings.append("未找到 go.mod / vendor/modules.txt，Go 依赖未分析")
    return nodes, warnings


# ---------------------------------------------------------------------------
# 图分析：深度、直接/传递、传染路径
# ---------------------------------------------------------------------------
def _effective_roots(nodes):
    """BFS 起点：直接依赖 + 无父节点的孤儿。

    孤儿可能来自 lock 中未被任何包声明的条目（如 npm link / 局部包），
    若只从 is_direct 出发，它们的下游会全部触达不到，导致深度与路径失真。
    """
    return [k for k, n in nodes.items() if n.is_direct or not n.parents]


def _assign_depths(nodes):
    """从直接依赖出发 BFS 赋 depth（visited 防环 + MAX_DEPTH 截断）。

    超出上限的节点饱和记为 ``MAX_DEPTH``（并给出告警），避免被误标为浅层依赖。
    """
    for node in nodes.values():
        node.depth = 1 if node.is_direct else 0
    frontier = _effective_roots(nodes)
    visited = set(frontier)
    depth = 1
    while frontier and depth < MAX_DEPTH:
        nxt = []
        for key in frontier:
            for child in nodes[key].children:
                if child in visited or child not in nodes:
                    continue
                visited.add(child)
                nodes[child].depth = depth + 1
                nxt.append(child)
        frontier = nxt
        depth += 1
    truncated = False
    for node in nodes.values():
        if node.depth == 0 and not node.is_direct:
            if node.parents:          # 有父节点但未被 BFS 触达 → 超出深度上限
                node.depth = MAX_DEPTH
                truncated = True
            else:                     # 无父节点（如 Go 无边信息）→ 按顶层处理
                node.depth = 1
    return truncated


def _shortest_paths(nodes):
    """BFS 求每个节点自「项目根」出发的最短路径（prev 指针回溯）。"""
    prev = {}
    visited = set()
    frontier = _effective_roots(nodes)
    for k in frontier:
        prev[k] = ROOT_KEY
        visited.add(k)
    depth = 1
    while frontier and depth < MAX_DEPTH:
        nxt = []
        for key in frontier:
            for child in nodes[key].children:
                if child in visited or child not in nodes:
                    continue
                visited.add(child)
                prev[child] = key
                nxt.append(child)
        frontier = nxt
        depth += 1

    def path_of(key):
        chain = []
        cur = key
        seen = set()
        while cur and cur != ROOT_KEY and cur not in seen:
            seen.add(cur)
            chain.append(cur)
            cur = prev.get(cur)
        chain.reverse()
        return chain
    return path_of


def _describe(nodes, key, project_name):
    node = nodes.get(key)
    if node is None:
        return str(key)
    return f"{node.name}@{node.version}" if node.version else node.name


def analyze_transitive(nodes, project_name="my-project", project_license="MIT",
                       warnings=None):
    """汇总依赖图：直接/传递计数 + 强/弱传染清单 + 传染路径。"""
    warnings = list(warnings or [])
    if _assign_depths(nodes):
        warnings.append(f"依赖层级超过上限（{MAX_DEPTH} 层），"
                        "更深的依赖已按上限层数饱和处理，请人工复核")
    path_of = _shortest_paths(nodes)

    direct = [n for n in nodes.values() if n.is_direct]
    transitive = [n for n in nodes.values() if not n.is_direct]
    strong, weak = [], []
    for key, node in nodes.items():
        strength = classify_contagion(node.spdx_id)
        if strength == "strong":
            chain = path_of(key)
            strong.append({
                "name": node.name,
                "version": node.version,
                "license": node.license or "unknown",
                "spdx_id": node.spdx_id,
                "is_direct": node.is_direct,
                "depth": node.depth,
                "path": [project_name] + [_describe(nodes, c, project_name)
                                          for c in chain],
            })
        elif strength == "weak":
            weak.append({
                "name": node.name,
                "version": node.version,
                "license": node.license or "unknown",
                "spdx_id": node.spdx_id,
                "is_direct": node.is_direct,
                "depth": node.depth,
            })
    # 传递依赖优先（常被忽略，故排在前），其次按深度浅者优先
    strong.sort(key=lambda x: (x["is_direct"], x["depth"], x["name"]))
    weak.sort(key=lambda x: (x["is_direct"], x["depth"], x["name"]))
    return {
        "total": len(nodes),
        "direct_count": len(direct),
        "transitive_count": len(transitive),
        "strong": strong,
        "weak": weak,
        "warnings": warnings,
    }


def build_graph(project_root, ecosystem, license_lookup=None,
                python_sites=None, python_direct=None):
    """按生态构建依赖图；``license_lookup(name, version) -> license 字符串``。"""
    if ecosystem == "npm":
        lock = os.path.join(project_root, "package-lock.json")
        if not os.path.isfile(lock):
            # 未 npm install 过 → 降级：不构建图，由调用方回退为「仅直接依赖」
            return {}, ["未找到 package-lock.json（依赖未安装或未生成 lock 文件），"
                        "依赖图未构建，已降级为仅分析 package.json 中的直接依赖"]
        nodes, warnings = build_npm_graph(lock)
    elif ecosystem == "python":
        sites = python_sites or []
        if not sites:
            warnings = ["未提供 site-packages 路径，Python 依赖图未构建"]
            nodes = {}
        else:
            nodes, warnings = build_python_graph(sites, python_direct)
    elif ecosystem == "go":
        nodes, warnings = build_go_graph(project_root)
    else:
        return {}, [f"未知生态：{ecosystem}"]

    if license_lookup:
        for node in nodes.values():
            node.license = license_lookup(node.name, node.version)
            node.spdx_id = _lookup_spdx(node.license)
    return nodes, warnings


def _lookup_spdx(license_str):
    """延迟导入避免与 engine 循环依赖。"""
    from .engine import normalize_license
    return normalize_license(license_str) if license_str else None

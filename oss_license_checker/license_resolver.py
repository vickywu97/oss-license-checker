"""依赖 license 真实来源解析：本地安装元数据 → 内置映射表 → unknown。

零网络、纯标准库。三级优先级：

1. **本地元数据**（最高可信度）：直接读取已安装依赖自带的 license 字段
   - npm：``node_modules/<pkg>/package.json`` 的 ``license`` / ``licenses``
   - Python：``site-packages/<pkg>-<ver>.dist-info/METADATA`` 的 ``License:`` /
     ``Classifier: License :: ...``
   - Go：``$GOMODCACHE/<module>@<ver>/LICENSE`` 文件（不调用 ``go list``，
     用轻量关键字识别 SPDX）
2. **内置映射表** ``data/package_licenses.json``（覆盖主流包，可能滞后）
3. **unknown**：两者都未命中 → 需人工核实

设计原则：模糊写法（如 ``BSD License`` 无版本）宁可返回 unknown，绝不猜测，
避免错判带来的合规风险。
"""
import json
import os
import re
import subprocess
import sys

# 注意：normalize_license 在 normalize_license_string 内部按需导入，
# 以避免与 engine 的循环依赖（engine 顶部导入本模块）。

# 常见全名写法 → SPDX。仅收录「可明确判定」的写法；含糊写法显式置 None。
_FULLNAME_MAP = {
    "mit license": "MIT",
    "the mit license": "MIT",
    "apache license": "Apache-2.0",
    "apache software license": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "gnu general public license v3": "GPL-3.0-only",
    "gnu general public license v3.0": "GPL-3.0-only",
    "gnu gpl v3": "GPL-3.0-only",
    "gnu general public license v2": "GPL-2.0-only",
    "gnu lesser general public license v2.1": "LGPL-2.1-only",
    "gnu lesser general public license v3": "LGPL-3.0-only",
    "mozilla public license 2.0": "MPL-2.0",
    "isc license": "ISC",
    "unlicense": "Unlicense",
    # 含糊写法 → 不猜
    "bsd license": None,
    "the bsd license": None,
}

# 含糊 BSD（无版本号）→ 不猜
_BSD_AMBIGUOUS = {"bsd", "bsd license", "the bsd license"}


def normalize_license_string(raw):
    """比 ``engine.normalize_license`` 更宽容：先试 SPDX/别名，再试常见全名。

    含糊写法（如 ``BSD License``）按 unknown 处理，不猜测具体版本。
    """
    if not raw:
        return None
    from .engine import normalize_license
    raw = raw.strip()
    # 先处理含糊 BSD：必须早于 engine（engine 会把 bsd→BSD-3-Clause）
    key = re.sub(r"\s+", " ", raw.lower()).strip()
    key = re.sub(r"\(.*?\)", "", key).strip()
    key = re.sub(r"\s+", " ", key).strip()
    if key in _BSD_AMBIGUOUS:
        return None
    # 1) SPDX id / 别名（engine 已含去 license 字样、v→- 等归一化）
    spdx = normalize_license(raw)
    if spdx:
        return spdx
    # 2) 常见全名模糊映射
    if key in _FULLNAME_MAP:
        return _FULLNAME_MAP.get(key)
    return None


def read_local_metadata(name, version, ecosystem, project_root):
    """读取已安装依赖自带的 license 字符串；读不到返回 None。"""
    if not project_root or not ecosystem:
        return None
    if ecosystem == "npm":
        return _read_npm_metadata(name, project_root)
    if ecosystem == "python":
        return _read_python_metadata(name, project_root)
    if ecosystem == "go":
        return _read_go_metadata(name, version, project_root)
    return None


def _read_npm_metadata(name, project_root):
    root = project_root
    for _ in range(3):  # 在 project_root 及向上两级目录寻找 node_modules
        pj = os.path.join(root, "node_modules", name, "package.json")
        if os.path.isfile(pj):
            try:
                with open(pj, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                return None
            lic = data.get("license")
            if isinstance(lic, str) and lic.strip():
                return lic.strip()
            if isinstance(lic, dict) and lic.get("type"):
                return lic["type"].strip()
            lics = data.get("licenses")
            if isinstance(lics, list) and lics:
                first = lics[0]
                t = first.get("type") if isinstance(first, dict) else None
                if t:
                    return t.strip()
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    return None


def _read_python_metadata(name, project_root):
    norm = name.replace("_", "-").lower()
    candidates = set()
    root = project_root
    for _ in range(3):  # 项目本地 venv / site-packages（向上两级）
        candidates.add(os.path.join(root, "site-packages"))
        candidates.add(os.path.join(root, "Lib", "site-packages"))
        for entry in os.listdir(root) if os.path.isdir(root) else []:
            if entry.startswith("python") and entry[6:].replace(".", "").isdigit():
                candidates.add(os.path.join(root, entry, "site-packages"))
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    # 当前解释器的 site-packages（作为最后兜底）
    candidates.update(s for s in sys.path if s.endswith("site-packages"))

    for site in candidates:
        if not os.path.isdir(site):
            continue
        for entry in os.listdir(site):
            el = entry.lower()
            if not el.startswith(norm):
                continue
            if el.endswith(".dist-info") or el.endswith(".egg-info"):
                meta = os.path.join(site, entry, "METADATA")
                lic = _parse_python_metadata(meta)
                if lic:
                    return lic
    return None


def _parse_python_metadata(meta_path):
    try:
        with open(meta_path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return None
    # 优先 License-Expression（PEP 639 标准 SPDX 表达式，如 BSD-3-Clause）
    for line in text.splitlines():
        if line.startswith("License-Expression:"):
            expr = line[len("License-Expression:"):].strip()
            if expr:
                spdx = normalize_license_string(expr)
                if spdx:
                    return spdx
            # 含 OR/AND 的复合表达式不猜测，继续尝试其它字段
    # 优先 License: 字段
    for line in text.splitlines():
        if line.startswith("License:"):
            lic = line[len("License:"):].strip()
            if lic:
                return lic
    # 兜底：Classifier: License :: OSI Approved :: <Name>
    for line in text.splitlines():
        if line.startswith("Classifier:") and "License ::" in line:
            lic = line.split("::")[-1].strip()
            if lic:
                return lic
    # 兜底：License-File: 指向的文件（按 SPDX 关键字识别）
    # 老包常在 License/Classifier 缺省时仅给出 License-File 指针
    base = os.path.dirname(meta_path)
    for line in text.splitlines():
        if line.startswith("License-File:"):
            rel = line[len("License-File:"):].strip()
            if not rel:
                continue
            cand = os.path.normpath(os.path.join(base, rel))
            spdx = _identify_spdx_from_license_file(cand)
            if spdx:
                return spdx
    return None


def _go_mod_cache(project_root):
    # 优先 go env GOMODCACHE；失败则回退 GOPATH 环境变量；再回退 ~/go/pkg/mod
    try:
        out = subprocess.run(
            ["go", "env", "GOMODCACHE"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    gopath = os.environ.get("GOPATH") or os.path.join(
        os.path.expanduser("~"), "go"
    )
    return os.path.join(gopath, "pkg", "mod")


def _identify_spdx_from_license_file(path):
    """轻量识别 LICENSE 文件正文 → SPDX；含糊/不确定返回 None（不猜）。"""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read().lower()
    except OSError:
        return None
    if "permission is hereby granted" in text and "mit" in text:
        return "MIT"
    if "apache license" in text or "apache software" in text or "licensed under the apache" in text:
        return "Apache-2.0"
    if "gnu general public license" in text and "version 3" in text:
        return "GPL-3.0-only"
    if "gnu general public license" in text and "version 2" in text:
        return "GPL-2.0-only"
    if "gnu lesser general public license" in text and "version 3" in text:
        return "LGPL-3.0-only"
    if "gnu lesser general public license" in text and "version 2.1" in text:
        return "LGPL-2.1-only"
    if "mozilla public license" in text and "2.0" in text:
        return "MPL-2.0"
    # BSD：3-Clause 与 2-Clause 的决定性区别在于「禁止背书条款」（第 3 条），
    # 该句在 LICENSE 正文中为高置信特征，识别它属于「读正文」而非「猜测」。
    if ("neither the name of the copyright holder" in text
            or "names of its contributors may be used to endorse" in text
            or "endorse or promote products derived from this software" in text):
        return "BSD-3-Clause"
    # BSD-2-Clause：含经典「redistribution and use」两条 + 免责声明，
    # 且既无背书条款（排除 3-Clause）也无广告条款（排除 4-Clause）→ 可确定 2-Clause。
    if ("redistribution and use in source and binary forms" in text
            and "endorse or promote" not in text
            and "advertising" not in text):
        return "BSD-2-Clause"
    # 其余含糊 BSD 写法（如纯 "BSD"、含广告条款的 4-Clause 等）→ 不猜
    return None


def _read_go_metadata(name, version, project_root):
    cache = _go_mod_cache(project_root)
    if not cache or not os.path.isdir(cache):
        return None
    ver = version.split("+")[0]  # 去掉 +incompatible 等后缀
    base = name
    # Go 对大写模块路径做 ! 转义；此处只处理纯小写路径（常见情形）
    for candidate_dir in (base, base.lower()):
        lic_path = os.path.join(cache, f"{candidate_dir}@{ver}", "LICENSE")
        if os.path.isfile(lic_path):
            return _identify_spdx_from_license_file(lic_path)
    return None


def resolve_license(name, version, ecosystem, project_root, pkg_map):
    """三级解析：本地元数据 → 映射表 → unknown。

    返回 ``(raw_license_str_or_None, source)``，
    ``source`` ∈ ``{"local_metadata", "mapping_table", "unknown"}``。
    """
    local = read_local_metadata(name, version, ecosystem, project_root)
    if local:
        return local, "local_metadata"
    mapped = pkg_map.get(name.lower()) if pkg_map else None
    if mapped:
        return mapped, "mapping_table"
    return None, "unknown"

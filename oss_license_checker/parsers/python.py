"""解析 requirements.txt / Pipfile 风格依赖清单。"""
import re

# 版本比较符（含环境标记后置的 ";" 之前部分）
_SPEC_RE = re.compile(r"^(?P<name>[A-Za-z0-9._\-\[\]]+)")


def parse(path):
    deps = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                # 跳过空行、注释、以及 -r / -e 等指令行
                continue
            # 去掉 extras 与环境标记：requests[socks]>=2.0 ; python_version<'3.10'
            base = line.split(";", 1)[0].strip()
            m = _SPEC_RE.match(base)
            if not m:
                continue
            name = m.group("name")
            # 去掉 extras 后缀（方括号）
            name = re.sub(r"\[.*\]$", "", name)
            # 提取版本（若存在）
            ver = "*"
            for sep in ("==", ">=", "<=", "~=", "!=", ">", "<"):
                if sep in base:
                    ver = base.split(sep, 1)[1].strip()
                    break
            deps[name] = ver
    return deps

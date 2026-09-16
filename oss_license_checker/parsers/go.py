"""解析 go.mod 的 require 依赖清单。"""
import re

_SINGLE = re.compile(r"^require\s+(\S+)\s+(\S+)")


def parse(path):
    deps = {}
    in_block = False
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("require ("):
                in_block = True
                continue
            if in_block:
                if line == ")":
                    in_block = False
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    deps[parts[0]] = parts[1]
                continue
            m = _SINGLE.match(line)
            if m:
                deps[m.group(1)] = m.group(2)
    return deps

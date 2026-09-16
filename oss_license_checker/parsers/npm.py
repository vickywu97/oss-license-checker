"""解析 package.json 的依赖清单（npm / pnpm / yarn 均兼容）。"""
import json


def parse(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    deps = {}
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        for name, spec in (data.get(section) or {}).items():
            # 支持 "workspace:*"、"^1.0.0"、"npm:pkg@1.0" 等写法，只取名字
            deps[name] = spec if isinstance(spec, str) else "*"
    return deps

"""依赖清单解析器：零网络、纯标准库。

每个解析器提供 ``parse(path) -> dict[str, str]``，返回 ``{依赖名: 版本}``。
"""
from .npm import parse as parse_npm
from .python import parse as parse_python
from .go import parse as parse_go

__all__ = ["parse_npm", "parse_python", "parse_go"]


def detect(path):
    """按文件名/扩展名返回对应的解析函数，未知格式返回 None。"""
    name = str(path).lower()
    if name.endswith("package.json"):
        return parse_npm
    if name.endswith("requirements.txt") or name.endswith(".txt"):
        return parse_python
    if name.endswith("go.mod"):
        return parse_go
    return None

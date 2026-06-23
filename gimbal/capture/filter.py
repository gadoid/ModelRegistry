"""gimbal.capture.filter — path 前缀过滤。

匹配规则:
  - /api/order 匹配 /api/order、/api/order/123,**不匹配** /api/orderlist
  - 多个前缀任一匹配即通过(OR 语义)
  - 空 filter 字符串 → 不过滤
"""
from __future__ import annotations


class PathFilter:
    """path 前缀匹配。空列表 = 不过滤(全部记录)。"""

    def __init__(self, prefixes: list[str]) -> None:
        # 去重 + 去尾 /
        self.prefixes = list({p.rstrip("/") for p in prefixes if p})

    @classmethod
    def from_csv(cls, csv: str) -> "PathFilter":
        return cls([p.strip() for p in csv.split(",") if p.strip()])

    def match(self, path: str) -> bool:
        if not self.prefixes:
            return True  # 无过滤
        return any(path == p or path.startswith(p + "/") for p in self.prefixes)

    def __bool__(self) -> bool:
        return bool(self.prefixes)

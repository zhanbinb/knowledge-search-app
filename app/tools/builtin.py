from __future__ import annotations

import ast
import json
import operator
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


SAFE_BINARY = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
SAFE_UNARY = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def calculate(expression: str) -> dict[str, Any]:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("数学表达式语法错误") from exc

    def evaluate(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.UnaryOp) and type(node.op) in SAFE_UNARY:
            return SAFE_UNARY[type(node.op)](evaluate(node.operand))
        if isinstance(node, ast.BinOp) and type(node.op) in SAFE_BINARY:
            left = evaluate(node.left)
            right = evaluate(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 12:
                raise ValueError("幂运算指数过大")
            return SAFE_BINARY[type(node.op)](left, right)
        raise ValueError("表达式包含不支持的运算")

    value = evaluate(tree)
    return {"expression": expression, "result": value}


def get_current_time(timezone: str = "Asia/Shanghai") -> dict[str, Any]:
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"未知时区：{timezone}") from exc

    current = datetime.now(zone)
    return {
        "timezone": timezone,
        "iso": current.isoformat(),
        "date": current.date().isoformat(),
        "time": current.strftime("%H:%M:%S"),
    }


def calculate_business_days(start_date: str, end_date: str) -> dict[str, Any]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError("结束日期不能早于开始日期")

    current = start
    business_days = 0
    while current <= end:
        if current.weekday() < 5:
            business_days += 1
        current += timedelta(days=1)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "business_days": business_days,
        "calendar_days": (end - start).days + 1,
    }


def lookup_policy(topic: str) -> dict[str, Any]:
    policies = {
        "差旅": {
            "title": "员工差旅费用管理办法",
            "summary": "一类城市住宿标准为每人每晚不超过 500 元，报销需提供合规住宿发票。",
        },
        "报销": {
            "title": "财务报销 FAQ",
            "summary": "报销金额按实际发生金额与制度标准中的较低者核定。",
        },
        "信息安全": {
            "title": "信息安全管理制度",
            "summary": "公司数据不得上传到未经批准的外部服务，密钥不得写入代码仓库。",
        },
    }
    matched = next((value for key, value in policies.items() if key in topic), None)
    return {
        "topic": topic,
        "policy": matched
        or {
            "title": "未找到政策",
            "summary": "没有匹配的政策主题，请尝试差旅、报销或信息安全。",
        },
    }


def dump_result(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

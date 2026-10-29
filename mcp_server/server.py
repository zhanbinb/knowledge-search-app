from __future__ import annotations

import json
from datetime import date, timedelta

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("knowledge-search-demo")


@mcp.tool()
def lookup_policy(topic: str) -> str:
    """根据主题查询演示企业制度。"""
    policies = {
        "差旅": {
            "title": "员工差旅费用管理办法",
            "summary": "一类城市住宿标准为每人每晚不超过 500 元。",
        },
        "报销": {
            "title": "财务报销 FAQ",
            "summary": "报销金额按实际发生金额与制度标准中的较低者核定。",
        },
        "信息安全": {
            "title": "信息安全管理制度",
            "summary": "密钥不得写入代码仓库，公司数据不得上传到未批准服务。",
        },
    }
    matched = next((value for key, value in policies.items() if key in topic), None)
    return json.dumps(
        {
            "topic": topic,
            "policy": matched or {"title": "未找到政策", "summary": "没有匹配主题。"},
        },
        ensure_ascii=False,
    )


@mcp.tool()
def calculate_business_days(start_date: str, end_date: str) -> str:
    """计算两个 ISO 日期之间的工作日数量。"""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError("结束日期不能早于开始日期")

    current = start
    count = 0
    while current <= end:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)

    return json.dumps(
        {
            "start_date": start_date,
            "end_date": end_date,
            "business_days": count,
            "calendar_days": (end - start).days + 1,
        },
        ensure_ascii=False,
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from app.config import Settings
from app.tools import builtin


class ToolRegistry:
    def __init__(self, settings: Settings, mcp_client: Any | None = None) -> None:
        self.settings = settings
        self.mcp_client = mcp_client

    def list_tools(self) -> list[dict[str, Any]]:
        tools = [
            {
                "name": "get_current_time",
                "source": "langchain",
                "description": "获取指定时区的当前日期和时间",
                "input_schema": {
                    "type": "object",
                    "properties": {"timezone": {"type": "string", "default": "Asia/Shanghai"}},
                },
            },
            {
                "name": "calculator",
                "source": "langchain",
                "description": "安全计算数学表达式",
                "input_schema": {
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
            },
            {
                "name": "lookup_policy",
                "source": "mcp",
                "description": "通过 MCP 查询企业制度主题",
                "input_schema": {
                    "type": "object",
                    "properties": {"topic": {"type": "string"}},
                    "required": ["topic"],
                },
            },
            {
                "name": "calculate_business_days",
                "source": "mcp",
                "description": "通过 MCP 计算两个日期之间的工作日",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "start_date": {"type": "string"},
                        "end_date": {"type": "string"},
                    },
                    "required": ["start_date", "end_date"],
                },
            },
        ]
        return tools

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        source = "mcp" if name in {"lookup_policy", "calculate_business_days"} else "langchain"
        allowed_fields = {
            "get_current_time": {"timezone"},
            "calculator": {"expression"},
            "lookup_policy": {"topic"},
            "calculate_business_days": {"start_date", "end_date"},
        }
        arguments = {
            key: value
            for key, value in arguments.items()
            if key in allowed_fields.get(name, set())
        }

        try:
            if name == "get_current_time":
                result = builtin.get_current_time(**arguments)
            elif name == "calculator":
                result = builtin.calculate(**arguments)
            elif name == "lookup_policy":
                result = await self._call_lookup_policy(**arguments)
            elif name == "calculate_business_days":
                result = await self._call_business_days(**arguments)
            else:
                raise ValueError(f"未知工具：{name}")
            status = "succeeded"
        except Exception as exc:
            result = {"error": str(exc)}
            status = "failed"

        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "id": f"call_{uuid.uuid4().hex}",
            "tool_name": name,
            "tool_source": source,
            "arguments": arguments,
            "result": result,
            "result_summary": builtin.dump_result(result)[:1000],
            "status": status,
            "latency_ms": latency_ms,
        }

    async def _call_lookup_policy(self, topic: str) -> dict[str, Any]:
        if self.mcp_client and self.settings.mcp_enabled:
            try:
                return await self.mcp_client.call_tool("lookup_policy", {"topic": topic})
            except Exception:
                return builtin.lookup_policy(topic)
        return builtin.lookup_policy(topic)

    async def _call_business_days(self, start_date: str, end_date: str) -> dict[str, Any]:
        if self.mcp_client and self.settings.mcp_enabled:
            try:
                return await self.mcp_client.call_tool(
                    "calculate_business_days",
                    {"start_date": start_date, "end_date": end_date},
                )
            except Exception:
                return builtin.calculate_business_days(start_date, end_date)
        return builtin.calculate_business_days(start_date, end_date)

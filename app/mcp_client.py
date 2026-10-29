from __future__ import annotations

import json
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import Settings


class MCPToolClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def list_tools(self) -> list[dict[str, Any]]:
        async with self._session() as session:
            result = await session.list_tools()
            return [
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": tool.inputSchema,
                }
                for tool in result.tools
            ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        async with self._session() as session:
            result = await session.call_tool(name, arguments)
            text = "\n".join(
                block.text for block in result.content if getattr(block, "text", None)
            )
            try:
                parsed = json.loads(text)
                return parsed if isinstance(parsed, dict) else {"result": parsed}
            except json.JSONDecodeError:
                return {"result": text}

    def _session(self) -> "_MCPSession":
        return _MCPSession(self.settings)


class _MCPSession:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._stack: AsyncExitStack | None = None

    async def __aenter__(self) -> ClientSession:
        self._stack = AsyncExitStack()
        params = StdioServerParameters(
            command=self.settings.mcp_server_command,
            args=self.settings.mcp_command_args,
        )
        read_stream, write_stream = await self._stack.enter_async_context(
            stdio_client(params)
        )
        session = await self._stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()
        return session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._stack:
            await self._stack.aclose()

from __future__ import annotations

import ast
import re
from typing import Any, Literal, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from app.agents.prompts import ANSWER_PROMPT, ROUTE_PROMPT, TOOL_PROMPT
from app.config import Settings
from app.models import RouteDecision, ToolPlan
from app.rag.retrieval import HybridRetriever
from app.tools.registry import ToolRegistry


class AgentState(TypedDict, total=False):
    session_id: str
    run_id: str
    trace_id: str
    question: str
    standalone_query: str
    messages: list[dict[str, Any]]
    route: Literal["knowledge", "tool", "hybrid", "clarify"]
    route_reason: str
    route_confidence: float
    retrieved: dict[str, Any]
    reranked: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    answer: str


class KnowledgeAgentGraph:
    def __init__(
        self,
        settings: Settings,
        retriever: HybridRetriever,
        tool_registry: ToolRegistry,
    ) -> None:
        self.settings = settings
        self.retriever = retriever
        self.tool_registry = tool_registry

        self.model = ChatOpenAI(
            model=settings.agent_model,
            api_key=settings.openai_api_key.get_secret_value(),
            base_url=settings.openai_base_url,
            temperature=settings.agent_temperature,
            max_tokens=settings.agent_max_tokens,
            timeout=settings.model_timeout_seconds,
            max_retries=settings.model_max_retries,
        )
        self.route_model = self.model.with_structured_output(RouteDecision)
        self.tool_model = self.model.with_structured_output(ToolPlan)
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(AgentState)
        builder.add_node("route_intent", self._route_intent)
        builder.add_node("retrieve_knowledge", self._retrieve_knowledge)
        builder.add_node("execute_tools", self._execute_tools)
        builder.add_node("generate_answer", self._generate_answer)

        builder.add_edge(START, "route_intent")
        builder.add_conditional_edges(
            "route_intent",
            self._route_after_intent,
            {
                "knowledge": "retrieve_knowledge",
                "hybrid": "retrieve_knowledge",
                "tool": "execute_tools",
                "clarify": "generate_answer",
            },
        )
        builder.add_conditional_edges(
            "retrieve_knowledge",
            self._route_after_retrieval,
            {"hybrid": "execute_tools", "generate": "generate_answer"},
        )
        builder.add_edge("execute_tools", "generate_answer")
        builder.add_edge("generate_answer", END)
        return builder.compile()

    async def run(self, state: AgentState) -> AgentState:
        return await self.graph.ainvoke(state, config={"recursion_limit": 12})

    async def _route_intent(self, state: AgentState) -> dict[str, Any]:
        conversation = self._conversation_text(state["messages"])
        try:
            decision: RouteDecision = await self.route_model.ainvoke(
                [
                    SystemMessage(content=ROUTE_PROMPT),
                    HumanMessage(content=f"最近对话：\n{conversation}\n\n当前问题：{state['question']}"),
                ]
            )
        except Exception:
            decision = self._fallback_route(state["question"])

        return {
            "route": decision.route,
            "route_reason": decision.reason,
            "route_confidence": decision.confidence,
            "standalone_query": state["question"],
        }

    async def _retrieve_knowledge(self, state: AgentState) -> dict[str, Any]:
        result = self.retriever.search(state.get("standalone_query") or state["question"])
        return {"retrieved": result, "reranked": result.get("reranked", [])}

    async def _execute_tools(self, state: AgentState) -> dict[str, Any]:
        try:
            plan: ToolPlan = await self.tool_model.ainvoke(
                [
                    SystemMessage(content=TOOL_PROMPT),
                    HumanMessage(content=f"用户问题：{state['question']}"),
                ]
            )
        except Exception:
            plan = self._fallback_tool_plan(state["question"])

        if plan.tool_name == "none":
            return {"tool_results": []}

        if plan.tool_name == "calculator":
            expression = self._extract_expression(state["question"])
            if expression:
                plan.arguments["expression"] = expression

        result = await self.tool_registry.call(plan.tool_name, plan.arguments)
        return {"tool_results": [result]}

    async def _generate_answer(self, state: AgentState) -> dict[str, Any]:
        context_blocks: list[str] = []
        for index, item in enumerate(state.get("reranked", []), start=1):
            payload = item.get("payload", {})
            source = payload.get("filename", "未知文档")
            heading = payload.get("heading_path", "")
            page = payload.get("page_number")
            location = f"{source} / {heading}" if heading else source
            if page:
                location += f" / 第 {page} 页"
            context_blocks.append(f"[{index}] {location}\n{item.get('content', '')}")

        tool_blocks = [
            f"{item.get('tool_name')} -> {item.get('result_summary', '')}"
            for item in state.get("tool_results", [])
        ]
        if not context_blocks and not tool_blocks and state.get("route") != "clarify":
            return {
                "answer": "知识库中未找到可靠答案。请补充更具体的问题或上传相关文档后重试。"
            }

        messages = [
            SystemMessage(content=ANSWER_PROMPT),
            HumanMessage(
                content=(
                    f"路由：{state.get('route')}\n\n"
                    f"知识库证据：\n{chr(10).join(context_blocks) or '无'}\n\n"
                    f"工具结果：\n{chr(10).join(tool_blocks) or '无'}\n\n"
                    f"最近对话：\n{self._conversation_text(state['messages'])}\n\n"
                    f"当前问题：{state['question']}"
                )
            ),
        ]
        response = await self.model.ainvoke(messages)
        content = response.content if isinstance(response.content, str) else str(response.content)
        return {"answer": content.strip()}

    @staticmethod
    def _conversation_text(messages: list[dict[str, Any]]) -> str:
        return "\n".join(
            f"{item.get('role', 'user')}: {item.get('content', '')}"
            for item in messages[-12:]
        )

    @staticmethod
    def _route_after_intent(state: AgentState) -> str:
        return state["route"]

    @staticmethod
    def _route_after_retrieval(state: AgentState) -> str:
        return "hybrid" if state.get("route") == "hybrid" else "generate"

    @staticmethod
    def _fallback_route(question: str) -> RouteDecision:
        text = question.lower()
        if any(word in text for word in ["几点", "日期", "时间", "今天"]):
            return RouteDecision(route="tool", confidence=0.75, reason="时间类问题")
        if any(word in text for word in ["计算", "等于", "多少钱", "工作日"]):
            return RouteDecision(route="hybrid", confidence=0.7, reason="计算类问题")
        if len(question.strip()) < 4 or question.strip().endswith("？") and "什么" not in question:
            return RouteDecision(route="clarify", confidence=0.55, reason="问题信息不足")
        return RouteDecision(route="knowledge", confidence=0.65, reason="默认知识检索")

    @staticmethod
    def _extract_expression(question: str) -> str | None:
        candidates = re.findall(r"[0-9+\-*/().\s]+", question)
        for candidate in sorted(candidates, key=len, reverse=True):
            expression = candidate.strip()
            if not expression or not re.search(r"\d", expression):
                continue
            try:
                tree = ast.parse(expression, mode="eval")
            except SyntaxError:
                continue
            if any(isinstance(node, ast.BinOp) for node in ast.walk(tree)):
                return expression
        return None

    @staticmethod
    def _fallback_tool_plan(question: str) -> ToolPlan:
        text = question.lower()
        if any(word in text for word in ["几点", "日期", "时间", "今天"]):
            return ToolPlan(tool_name="get_current_time", arguments={"timezone": "Asia/Shanghai"})
        if "工作日" in text:
            return ToolPlan(tool_name="calculate_business_days", arguments={})
        if any(word in text for word in ["制度", "政策", "规定"]):
            return ToolPlan(tool_name="lookup_policy", arguments={"topic": question})

        expression = re.search(r"[-+*/().\d\s]+", question)
        if expression and any(char.isdigit() for char in expression.group()):
            return ToolPlan(tool_name="calculator", arguments={"expression": expression.group().strip()})
        return ToolPlan(tool_name="none", arguments={})

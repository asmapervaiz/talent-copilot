"""LangGraph agent with HITL: conversation, tool_decision, confirmation_pending, tool_execution, response_generation."""
from typing import TypedDict, Annotated, Literal, Optional, Any
from uuid import UUID
import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langchain_core.tools import tool

from ..config import get_settings


# ----- State -----
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], "chat history"]
    session_summary: str
    workspace_context: str
    # Tool decision output
    tool_decision: Optional[str]  # "respond" | "request_github" | "request_save_cv"
    repo_url: Optional[str]
    candidate_to_save: Optional[dict]
    # After confirmation
    confirmation_id: Optional[str]
    confirmation_approved: Optional[bool]
    tool_result: Optional[str]
    # Outputs
    response: Optional[str]
    confirmation_prompt: Optional[str]
    confirmation_tool_name: Optional[str]
    confirmation_payload: Optional[dict]


# ----- System prompt -----
SYSTEM_PROMPT = """You are TalentCopilot, an AI assistant for recruiting teams. You help with:
- Answering questions about candidate experience and skills (using workspace context when available).
- Answering questions about ingested GitHub repositories (structure, stack, quality).
- Generating interview questions and evaluation notes.

You have access to workspace context that may include candidate profiles and repository artifacts. Use it when relevant.

Critical rules:
1. When the user provides a GitHub repository URL and wants you to use it, you MUST request confirmation before ingesting. Say you will need to crawl the repo and ask for approval. Output the exact tool request so the system can show: "Would you like me to crawl this repository: <repo_url>? (yes/no)".
2. When a candidate CV has been parsed and the user (or system) asks to save it, you MUST request confirmation before saving. Output the exact tool request so the system can show: "Do you want me to save this candidate profile to the workspace? (yes/no)".
3. For normal chat, just respond. For tool actions that change workspace (GitHub ingest, save candidate), you must request confirmation first; never perform them without user approval.

Respond in a helpful, professional tone. When you need to request confirmation for a tool, output a structured decision (request_github with repo_url, or request_save_cv with candidate summary); the system will then show the yes/no prompt to the user."""


def _build_system(session_summary: str, workspace_context: str) -> str:
    parts = [SYSTEM_PROMPT]
    if session_summary:
        parts.append(f"\n\nSession summary (earlier context):\n{session_summary}")
    if workspace_context:
        parts.append(f"\n\nWorkspace context (candidates and repos):\n{workspace_context}")
    return "\n".join(parts)


# ----- Tool definitions (for LLM to decide; actual execution is HITL-gated) -----
@tool
def request_github_ingestion(repo_url: str) -> str:
    """Call this when the user wants to ingest a GitHub repository. You must request confirmation before actually ingesting. Provide the repo URL."""
    return f"CONFIRM_GITHUB:{repo_url}"


@tool
def request_save_candidate(
    contact_info: dict,
    skills: list,
    experience: list,
    projects: list,
    education: list,
) -> str:
    """Call this when the user wants to save a parsed candidate profile to the workspace. You must request confirmation before saving."""
    return "CONFIRM_SAVE_CANDIDATE"


def _parse_tool_decision(tool_calls: list, messages: list) -> tuple[str, Optional[str], Optional[dict]]:
    """Returns (tool_decision, repo_url or None, candidate_to_save or None)."""
    for tc in tool_calls:
        if not hasattr(tc, "name"):
            continue
        name = getattr(tc, "name", "")
        args = getattr(tc, "args", {}) or {}
        if name == "request_github_ingestion":
            return "request_github", args.get("repo_url") or "", None
        if name == "request_save_candidate":
            return "request_save_cv", None, {
                "contact_info": args.get("contact_info", {}),
                "skills": args.get("skills", []),
                "experience": args.get("experience", []),
                "projects": args.get("projects", []),
                "education": args.get("education", []),
            }
    return "respond", None, None


def create_agent_graph():
    api_key = (os.environ.get("OPENAI_API_KEY") or get_settings().openai_api_key or "").strip()
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is not set. Add it to your .env file or set the OPENAI_API_KEY environment variable."
        )
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        api_key=api_key,
        temperature=0,
    )
    tools = [request_github_ingestion, request_save_candidate]
    llm_with_tools = llm.bind_tools(tools)

    def tool_decision_node(state: AgentState) -> AgentState:
        messages = state["messages"]
        session_summary = state.get("session_summary") or ""
        workspace_context = state.get("workspace_context") or ""
        system = _build_system(session_summary, workspace_context)
        msgs = [SystemMessage(content=system)] + messages
        response = llm_with_tools.invoke(msgs)
        out: AgentState = {
            "messages": state["messages"] + [response],
            "session_summary": state.get("session_summary") or "",
            "workspace_context": state.get("workspace_context") or "",
            "tool_decision": None,
            "repo_url": None,
            "candidate_to_save": None,
            "confirmation_id": state.get("confirmation_id"),
            "confirmation_approved": state.get("confirmation_approved"),
            "tool_result": state.get("tool_result"),
            "response": None,
            "confirmation_prompt": None,
            "confirmation_tool_name": None,
            "confirmation_payload": None,
        }
        tool_calls = getattr(response, "tool_calls", None) or []
        if tool_calls:
            decision, repo_url, candidate = _parse_tool_decision(tool_calls, state["messages"])
            out["tool_decision"] = decision
            out["repo_url"] = repo_url
            out["candidate_to_save"] = candidate
            if decision == "request_github" and repo_url:
                out["confirmation_prompt"] = f"Would you like me to crawl this repository: {repo_url} ? (yes/no)"
                out["confirmation_tool_name"] = "ingest_github"
                out["confirmation_payload"] = {"repo_url": repo_url}
            elif decision == "request_save_cv" and candidate:
                out["confirmation_prompt"] = "Do you want me to save this candidate profile to the workspace? (yes/no)"
                out["confirmation_tool_name"] = "save_candidate"
                out["confirmation_payload"] = candidate
        else:
            # Direct reply
            out["response"] = response.content if hasattr(response, "content") else str(response)
        return out

    def confirmation_pending_node(state: AgentState) -> AgentState:
        """Just pass through; API creates confirmation and returns. No graph advancement until /confirm."""
        return state

    def _sanitize_messages_for_llm(messages: list) -> list:
        """Replace any AIMessage with tool_calls by a plain AIMessage so OpenAI API accepts the history."""
        out = []
        for m in messages:
            if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
                out.append(AIMessage(content=m.content or "I've asked for your confirmation."))
            else:
                out.append(m)
        return out

    def response_generation_node(state: AgentState) -> AgentState:
        messages = state["messages"]
        session_summary = state.get("session_summary") or ""
        workspace_context = state.get("workspace_context") or ""
        tool_result = state.get("tool_result") or ""
        system = _build_system(session_summary, workspace_context)
        if tool_result:
            system += f"\n\nTool execution result: {tool_result}"
        msgs = [SystemMessage(content=system)] + _sanitize_messages_for_llm(messages)
        # Final response without tools
        llm_simple = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=api_key,
            temperature=0,
        )
        response = llm_simple.invoke(msgs)
        content = response.content if hasattr(response, "content") else str(response)
        return {
            **state,
            "response": content,
        }

    def route_after_tool_decision(state: AgentState):
        if state.get("confirmation_prompt"):
            return "confirmation_pending"
        if state.get("response"):
            return END
        return "response_generation"

    def route_from_confirmation(state: AgentState) -> Literal["response_generation"]:
        return "response_generation"

    graph = StateGraph(AgentState)

    graph.add_node("decide_tool", tool_decision_node)
    graph.add_node("confirmation_pending", confirmation_pending_node)
    graph.add_node("response_generation", response_generation_node)

    graph.set_entry_point("decide_tool")
    graph.add_conditional_edges(
        "decide_tool",
        route_after_tool_decision,
        {
            "confirmation_pending": "confirmation_pending",
            "response_generation": "response_generation",
            END: END,
        },
    )
    graph.add_edge("confirmation_pending", END)
    graph.add_edge("response_generation", END)

    return graph.compile()


# Singleton compiled graph
_agent_graph = None


def get_agent_graph():
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = create_agent_graph()
    return _agent_graph


class AgentService:
    """Orchestrates agent invocation with memory and HITL."""

    def __init__(self, get_context_fn, get_repos_fn):
        """
        get_context_fn(tenant_id, user_id, session_id) -> (recent_messages, session_summary, workspace_text)
        get_repos_fn() -> db session / repos for creating confirmations, etc.
        """
        self.get_context_fn = get_context_fn
        self.get_repos_fn = get_repos_fn

    async def chat(
        self,
        tenant_id: UUID,
        user_id: UUID,
        session_id: UUID,
        message: str,
    ) -> dict:
        """
        Run agent for one user message. Returns either:
        - { "type": "message", "content": "..." }
        - { "type": "confirmation", "confirmation_id": ..., "tool_name": ..., "prompt": ..., "payload": ... }
        """
        recent_messages, session_summary, workspace_context = await self.get_context_fn(tenant_id, user_id, session_id)
        # Build message list for LangGraph
        lc_messages = []
        for role, content in recent_messages:
            if role == "user":
                lc_messages.append(HumanMessage(content=content))
            else:
                lc_messages.append(AIMessage(content=content))
        lc_messages.append(HumanMessage(content=message))

        state: AgentState = {
            "messages": lc_messages,
            "session_summary": session_summary or "",
            "workspace_context": workspace_context or "",
            "tool_decision": None,
            "repo_url": None,
            "candidate_to_save": None,
            "confirmation_id": None,
            "confirmation_approved": None,
            "tool_result": None,
            "response": None,
            "confirmation_prompt": None,
            "confirmation_tool_name": None,
            "confirmation_payload": None,
        }

        graph = get_agent_graph()
        result = graph.invoke(state)

        if result.get("confirmation_prompt"):
            # API layer must create Confirmation and return; we return the payload for that
            return {
                "type": "confirmation",
                "prompt": result["confirmation_prompt"],
                "tool_name": result["confirmation_tool_name"],
                "payload": result["confirmation_payload"],
            }
        return {
            "type": "message",
            "content": result.get("response") or "",
        }

    async def respond_after_confirmation(
        self,
        approved: bool,
        tool_result_message: str,
    ) -> str:
        """Return follow-up message after HITL."""
        if approved:
            return tool_result_message
        return "Understood, I did not perform that action."

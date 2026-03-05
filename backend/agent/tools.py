"""Tool schemas and dispatch. Step 1 (no tools): full graph in context, no tools to call."""
import json
import logging
from typing import Callable

ToolHandler = Callable[[str, dict, str | None], str]
logger = logging.getLogger("consularis.agent")

# No tools: agent gets the full graph in context and answers from it.
TOOL_SCHEMAS: list[dict] = []
TOOLS = TOOL_SCHEMAS
TOOL_HANDLERS: dict[str, ToolHandler] = {}


def run_tool(session_id: str, name: str, arguments: dict, process_id: str | None = None) -> str:
    logger.info("[AGENT][GRAPH] %s (no handler) session_id=%s", name, session_id)
    return json.dumps({"error": "Unknown tool"})

"""An MCP server that mends a bad argument rather than refusing the call.

The callers are models, and a small one given only a tool's argument names
guesses the values. Cider's 27B asked for a lecture at quality "high" when
the choices are draft and final, and got back a pydantic error, which is
neither an answer nor anything it can act on. A person handing over the
same request would expect to hear "there is no high, so draft" and get the
video.

So a value outside a closed set becomes that argument's default, a number
past a bound becomes the bound, and the result opens with a sentence saying
what was changed. Anything that cannot be mended -- a required argument
left out, a value with no default to fall back on -- comes back as one
sentence saying what the tool needs, not as a validation dump.

The schema is left exactly as declared, enums and ranges included, so a
client that does read it still sees the real choices.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent

LOWER = {"greater_than_equal": "ge", "greater_than": "gt"}
UPPER = {"less_than_equal": "le", "less_than": "lt"}


def _said(value: Any) -> str:
    if isinstance(value, str):
        return f"'{value}'"
    return f"{value:g}" if isinstance(value, float) else f"{value}"


class ForgivingServer(MCPServer):

    async def call_tool(self, name: str, arguments: dict[str, Any],
                        context: Any = None) -> Any:
        try:
            return await super().call_tool(name, arguments, context)
        except ToolError as exc:
            if not isinstance(exc.__cause__, ValidationError):
                raise
            fixed, notes, unmet = self._mend(name, arguments, exc.__cause__)
        if unmet:
            return CallToolResult(is_error=True, content=[TextContent(
                type="text", text=f"{name} did not run: {'; '.join(unmet)}.")])
        result = await super().call_tool(name, fixed, context)
        return _opened_with(result, " ".join(notes))

    def _mend(self, name: str, arguments: dict[str, Any],
              error: ValidationError) -> tuple[dict, list[str], list[str]]:
        schema = self._tool_manager.get_tool(name).parameters
        props = schema.get("properties", {})
        fixed, notes, unmet = dict(arguments), [], []
        for e in error.errors():
            if len(e["loc"]) != 1:
                unmet.append(f"{'.'.join(map(str, e['loc']))}: {e['msg'].lower()}")
                continue
            field = str(e["loc"][0])
            given, prop, ctx = e["input"], props.get(field, {}), e.get("ctx", {})
            if e["type"] == "missing":
                unmet.append(f"it needs {field}")
            elif e["type"] in LOWER or e["type"] in UPPER:
                bound = ctx.get(LOWER.get(e["type"]) or UPPER[e["type"]])
                side = "less" if e["type"] in LOWER else "more"
                fixed[field] = bound
                notes.append(f"{field} {_said(given)} is {side} than this "
                             f"tool allows, so it is {_said(bound)}.")
            elif "default" in prop:
                fixed[field] = prop["default"]
                choices = prop.get("enum")
                known = (f"is not one of {', '.join(map(str, choices))}"
                         if choices else f"is not a {prop.get('type', 'value')}")
                notes.append(f"{field} {_said(given)} {known}, so it is "
                             f"{_said(prop['default']).strip(chr(39))}.")
            else:
                unmet.append(f"{field} {_said(given)}: {e['msg'].lower()}")
        return fixed, notes, unmet


def _opened_with(result: Any, note: str) -> Any:
    """The result with `note` in front of its text, where a model reads it."""
    if not note or not isinstance(result, CallToolResult) or not result.content:
        return result
    first = result.content[0]
    if isinstance(first, TextContent):
        result.content[0] = TextContent(type="text", text=f"{note} {first.text}")
    if isinstance(result.structured_content, dict) and \
            isinstance(result.structured_content.get("result"), str):
        result.structured_content["result"] = \
            f"{note} {result.structured_content['result']}"
    return result

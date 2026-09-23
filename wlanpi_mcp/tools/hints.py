"""
MCP tool annotations shared by every tool module.

Clients may gate or prompt on these hints. MCP treats a tool that is not
read-only as destructive by default, so every tool states one of these
classes; tests/test_tool_annotations.py pins which tool has which.
readOnlyHint defaults to false, so the two mutating classes leave it out.
"""

from mcp.types import ToolAnnotations

#: Only reads device or server state.
READ_ONLY = ToolAnnotations(readOnlyHint=True)

#: Changes state without removing, replacing or interrupting anything:
#: creates something new, or starts/stops something only this server owns.
ADDITIVE = ToolAnnotations(destructiveHint=False)

#: Removes or overwrites state, or interrupts something in use (a service,
#: a radio, a link, the device itself).
DESTRUCTIVE = ToolAnnotations(destructiveHint=True)

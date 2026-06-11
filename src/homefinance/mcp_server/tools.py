"""MCP tool implementations as plain functions. The stdio server wraps these
with ``@mcp.tool()`` decorators in ``__main__.py``. Defined as functions (not
decorators) so tests can call them directly without spinning up the MCP runtime.
"""

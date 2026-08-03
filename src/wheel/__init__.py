"""The Wheel deterministic core (Layer 1).

Pure, rule-mapped screening: hard gates, score filters, flags, the ST-SEL-07
diff, and the CSV interchange. No network, no provider imports, no LLM. The
fetch that feeds this lives at the MCP boundary in `wheel_mcp`.
"""

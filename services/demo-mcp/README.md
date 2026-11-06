# Demo MCP
S01 reserves this fifth Compose service under the `mcp` profile. It deliberately exits nonzero: it is not an MCP implementation and must not report healthy. S02 replaces the profile stub with the official SDK Streamable HTTP server, initialize/list_tools integration and explicit readiness. No fake tools are exposed.

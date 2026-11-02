# SpielOS local plugin

This thin package uses the same installed Python runtime as the CLI. It stores
no company home, state or credentials. Install the current SpielOS distribution
so `spielos mcp` is available on the host's PATH, then load this local plugin with
the host's supported local-plugin flow. Select an existing company through the
`select_company` tool; plugin installation never initializes one.

The package has no lifecycle hooks, remote server, account upload or public
listing. MCP runs over local standard input/output. Its optional bearer principal
comes from the host process's `SPIELOS_PRINCIPAL_TOKEN`; never put a token in these
files. Without it, the local OS owner is the trust root. Shared enterprise hosting
and staged qualification are separate deployment work.

Source protocol references: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
and https://modelcontextprotocol.io/specification/2025-06-18/server/tools.


Release10.3.4 includes `/report`, live report links from `inspect_company`, mandatory workflow evaluation gates, metadata-only Codex usage capture and sourced reference-price reporting. It shares the installed Python package and selected company runtime. Host lifecycle hooks belong to the company installation, not this plugin; the plugin does not secretly add hooks or select a workspace. Native rich-card rendering is host-dependent; human Markdown receipts remain the supported baseline.

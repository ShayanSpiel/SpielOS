# Connection preparation and activation

Verified against official documentation on 29 October 2026:
https://www.activepieces.com/docs/mcp/overview
https://www.activepieces.com/docs/mcp/tools

The official MCP server belongs to the chosen Activepieces instance/project. A dashboard URL is not an MCP URL. When activation is requested, the owner obtains the actual server URL from Settings > MCP Server and enables only the needed tool categories. OAuth runs through the host's normal connection flow; do not extract browser tokens or put secrets in skill/plugin files.

Until activation is requested, keep `mcp.json.example` as an example only. `configure.py --url <copied-server-url> --output <new-directory>` produces a portable `mcp.json` and skill package without making a network request, installing a plugin or changing host settings. URL syntax validation does not prove a server exists. The script refuses existing output directories. Do not substitute a guessed cloud URL or automatically run this script against an unselected account.

After authorized connection, discover actual tool schemas. Use `ap_set_project_context` only when exposed: inspect its returned project list and select the intended project. Confirm read-only discovery works before any mutation. Discovery may be available while flow-building/testing categories are disabled; report this accurately. Search tools can be absent or return keyword mode rather than semantic mode. Use catalog research instead of inventing missing tools.

Keep credentials in the provider/host's connection store. Portable manifests contain connection references only. Report the exact distinction between package prepared, connection authenticated, tools discovered, draft validated, run tested and release enabled.

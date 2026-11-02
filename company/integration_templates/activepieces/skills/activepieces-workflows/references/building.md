# Building through the official MCP server

Official references (verified 29 October 2026):
- Tool contracts: https://www.activepieces.com/docs/mcp/tools
- Discovery semantics: https://www.activepieces.com/docs/mcp/tool-search
- Piece flow control: https://www.activepieces.com/docs/build-pieces/piece-reference/flow-control

Discover the live definitions before calls. Typical progression:

1. Inspect existing flows with `ap_list_flows` and `ap_flow_structure`; inspect full current settings/code with `ap_read_step_settings` or `ap_read_step_code` before editing. The structure overview can truncate values.
2. Find pieces using `ap_search_triggers`/`ap_search_actions`, or `ap_research_pieces` when search is unavailable. Read `ap_get_piece_props` for the exact trigger/action and connection reference. Resolve dependent options using `ap_resolve_property_chain` or `ap_resolve_property_options`; use returned internal values, not display labels. Inspect existing connections with `ap_list_connections`; missing authentication belongs in the UI setup flow described by `ap_setup_guide`.
3. Create or duplicate a disabled candidate only within the authorized task. Use the exposed build/step tools and their current schemas. Duplication does not carry connections or sample data. Re-read the resulting graph and full settings, including error handling and data mappings.
4. Run `ap_validate_step_config` and `ap_validate_flow` before a test. These checks establish configuration/structure, not artifact quality or safety of live actions. A connector test may execute real effects; `ap_run_action` is an action, not harmless discovery.
5. For authorized tests use the current test tool contract. Persist the returned run identity and inspect `ap_get_run`/`ap_list_runs`. A run status of SUCCEEDED still requires output evaluation. Reconcile timeouts and ambiguous responses before any retry. Never assume generic waitpoints exist in an installed piece; inspect the selected version and deployment.
6. Present the exact candidate and case-level evidence for review. Invoke publication/status-change tools only after the needed authorization. Read back the published version and enabled status. Distinguish publishing from enabling, and preserve the previous version's lineage.

Evaluation record for every case: stable case/criterion IDs, split, input/reference artifact digests, applicable rubric version, evaluator identity/version, pass/fail/missing/error/not-applicable, rating anchor, explanation, observed artifact and provider run reference. Required coverage must be exact and unique. Blocking failures cannot be averaged away. Human/model disagreement and self-evaluation must be visible. A negative case must demonstrate a real rejection, not be labeled negative after it passed.

Retain request-to-provider correlation, exact approved payload/version, input/output mapping, failure state and recovery decision. Remote retries and callbacks must not replay approved effects silently. Provider-native implementation details stay in Activepieces; scoped versions, acceptance results and durable business-level state stay in SpielOS. Telemetry is evidence about execution and evaluation, not an authorization record.

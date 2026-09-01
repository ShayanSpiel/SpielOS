"""Host-first logical Connections used by Department Workflows."""

from ..runtime.models import ConnectionSpec


_CONNECTIONS = {
    item.id: item for item in (
        ConnectionSpec(
            "buffer",
            "Direct Buffer GraphQL publishing for approved content packages.",
            ("create_draft", "schedule", "publish", "verify", "metrics", "delete"),
            ("direct",), True, ("BUFFER_API_KEY",),
        ),
        ConnectionSpec(
            "posthog",
            "Product and funnel analytics through the active host Connection.",
            ("query_events", "query_funnel", "query_timeseries"),
        ),
        ConnectionSpec(
            "search-console",
            "Organic search evidence through the active host Connection.",
            ("query_performance", "query_pages", "query_keywords"),
        ),
        ConnectionSpec(
            "website",
            "Repository publishing through the active coding host.",
            ("create_article", "publish_article", "modify_site", "verify"),
        ),
        ConnectionSpec(
            "web-research",
            "Public web research through the active Codex or OpenCode host.",
            ("search", "open_page", "collect_public_evidence"),
        ),
        ConnectionSpec(
            "cal-booking",
            "Cal.com scheduling read for booked Discovery Calls through the official "
            "API v2 (GET https://api.cal.com/v2/bookings). Reads are direct with the "
            "local CALCOM_API_KEY; writes stay host-mediated (runtime booked_call "
            "evidence + attio MCP notes via the outbound calcom_sync adapter).",
            ("fetch_bookings", "sync_booked_calls", "verify"),
            ("direct",), True, ("CALCOM_API_KEY",),
        ),
        ConnectionSpec(
            "email-delivery",
            "Direct provider delivery required by unattended Outbound runs.",
            ("send", "delivery_events", "reply_events"),
            ("direct",), True, ("EMAIL_PROVIDER",),
        ),
        ConnectionSpec(
            "attio",
            "Attio CRM through the active OpenCode host OAuth MCP at https://mcp.attio.com/mcp.",
            ("records_query", "records_search", "records_create", "records_update",
             "list_entries", "notes"),
            ("opencode",),
        ),
        ConnectionSpec(
            "activepieces",
            "Workflow automation through the active host Activepieces MCP.",
            ("list_flows", "create_flow", "update_flow", "validate_flow",
             "publish_flow", "read_run", "retry_run"),
            ("opencode",),
        ),
        ConnectionSpec(
            "google-drive",
            "Google Drive files and folders through the active host Connection.",
            ("create_folder", "upload_file", "list_files", "share"),
            ("opencode",),
        ),
        ConnectionSpec(
            "google-sheets",
            "Google Sheets records and trackers through the active host Connection.",
            ("create_spreadsheet", "append_row", "read_rows", "update_row"),
            ("opencode",),
        ),
    )
}


def connections() -> dict[str, ConnectionSpec]:
    return dict(_CONNECTIONS)


def connection(connection_id: str) -> ConnectionSpec:
    try:
        return _CONNECTIONS[connection_id]
    except KeyError as exc:
        raise KeyError(f"unknown Connection: {connection_id}") from exc

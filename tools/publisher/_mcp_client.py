#!/usr/bin/env python3
"""publisher/_mcp_client.py — Generic MCP subprocess client (JSON-RPC over stdio).

Spawns a stdio-based MCP server as a child process and handles the
JSON-RPC lifecycle (initialize → initialized notifications → tool calls).
Used by buffer.py and blog.py to communicate with MCP servers.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path


class MCPError(Exception):
    pass


class MCPClient:
    def __init__(self, command: list[str], env: dict[str, str] | None = None,
                 name: str = "spielos-mcp", version: str = "1.0.0"):
        self.command = command
        self.env = {**os.environ, **(env or {})}
        self.name = name
        self.version = version
        self._proc: subprocess.Popen | None = None
        self._pending: dict[str, threading.Event] = {}
        self._responses: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._buf = ""
        self._reader_thread: threading.Thread | None = None
        self._req_id = 0

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()

    def start(self):
        self._proc = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.env,
            text=True,
        )
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        self._init()

    def stop(self):
        if self._proc:
            self._proc.terminate()
            self._proc.wait(timeout=5)
            self._proc = None

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _init(self):
        resp = self._send_raw("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": self.name, "version": self.version},
        })
        if resp is None or "result" not in resp:
            raise MCPError("MCP initialization failed")
        self._send_notification("notifications/initialized")

    def _send_notification(self, method: str, params: dict | None = None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._write_line(msg)

    def _send_raw(self, method: str, params: dict | None = None,
                  timeout: float = 30.0) -> dict | None:
        req_id = self._next_id()
        msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            msg["params"] = params
        event = threading.Event()
        with self._lock:
            self._pending[str(req_id)] = event
        self._write_line(msg)
        event.wait(timeout=timeout)
        with self._lock:
            resp = self._responses.pop(str(req_id), None)
            self._pending.pop(str(req_id), None)
        return resp

    def call_tool(self, tool_name: str, arguments: dict | None = None,
                  timeout: float = 30.0) -> dict:
        params = {"name": tool_name}
        if arguments is not None:
            params["arguments"] = arguments
        resp = self._send_raw("tools/call", params, timeout=timeout)
        if resp is None:
            raise MCPError(f"Tool {tool_name!r}: no response (timeout {timeout}s)")
        result = resp.get("result") or {}
        content = result.get("content") or []
        if not content:
            error = result.get("isError")
            if error:
                raise MCPError(f"Tool {tool_name!r} returned error: {result}")
            return result
        text = content[0].get("text", "")
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return {"_raw": text}

    def _write_line(self, msg: dict):
        if self._proc and self._proc.stdin:
            line = json.dumps(msg, ensure_ascii=False) + "\n"
            self._proc.stdin.write(line)
            self._proc.stdin.flush()

    def _read_loop(self):
        while self._proc and self._proc.stdout:
            line = self._proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            req_id = msg.get("id")
            if req_id is not None:
                sid = str(req_id)
                with self._lock:
                    if sid in self._pending:
                        self._responses[sid] = msg
                        self._pending[sid].set()

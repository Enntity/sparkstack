#!/usr/bin/env python3
"""Smoke-test the blender-mcp stdio server: initialize handshake + tools/list."""
import json
import os
import shutil
import subprocess
import sys
import threading

# Resolve the server rather than assuming a checkout path:
#   BLENDER_MCP=/path/to/blender-mcp python3 test_mcp_server.py
def find_server():
    env = os.environ.get("BLENDER_MCP")
    if env:
        return [env]
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         ".venv", "bin", "blender-mcp")
    if os.path.exists(local):
        return [local]
    found = shutil.which("blender-mcp")
    if found:
        return [found]
    print("FAIL: blender-mcp not found. Install it, or set BLENDER_MCP=/path/to/it")
    sys.exit(3)


CMD = find_server()
TIMEOUT = 45


def main():
    proc = subprocess.Popen(
        CMD, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, bufsize=1,
    )

    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    responses = {}
    errors = []

    def reader():
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "id" in msg:
                responses[msg["id"]] = msg

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()

    send({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "dsh-smoke-test", "version": "1.0"},
        },
    })
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})

    thread.join(timeout=TIMEOUT)
    proc.terminate()

    init = responses.get(1)
    if not init:
        err = proc.stderr.read() if proc.stderr else ""
        print("FAIL: no initialize response")
        print("stderr:", err[:2000])
        return 1

    info = init.get("result", {}).get("serverInfo", {})
    print(f"server: {info.get('name')} {info.get('version')}")
    print(f"protocol: {init.get('result', {}).get('protocolVersion')}")

    tools = responses.get(2, {}).get("result", {}).get("tools", [])
    print(f"tools: {len(tools)}")
    for tool in tools:
        print(f"  - {tool['name']}")
    return 0 if tools else 2


if __name__ == "__main__":
    sys.exit(main())

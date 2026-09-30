#!/usr/bin/env python3
"""local-shell-mcp: a one-file MCP server that gives an AI chat a shell on this computer.

Speaks MCP over stdio (newline-delimited JSON-RPC 2.0). Python 3.8+ standard library only.
One tool, `bash`: runs a command with `bash -lc` as the user who launched the server.

Environment variables (all optional):
  SHELL_MCP_DENY        path to a file of regular expressions, one per line (# comments allowed).
                        A command matching any of them is refused and never run.
  SHELL_MCP_LOG         log file for every command, run or refused
                        (default ~/.local/state/local-shell-mcp.log; set to "" to disable).
  SHELL_MCP_TIMEOUT     default timeout in seconds (default 120).
  SHELL_MCP_MAX_TIMEOUT largest timeout a caller may ask for (default 1800).
  SHELL_MCP_MAX_OUTPUT  characters kept per stream before truncating (default 100000).
"""
import json
import os
import re
import subprocess
import sys
import time

VERSION = "1.0.0"


def _int_env(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


DEFAULT_TIMEOUT = _int_env("SHELL_MCP_TIMEOUT", 120)
MAX_TIMEOUT = _int_env("SHELL_MCP_MAX_TIMEOUT", 1800)
MAX_OUT = _int_env("SHELL_MCP_MAX_OUTPUT", 100_000)
LOG = os.path.expanduser(os.environ.get("SHELL_MCP_LOG", "~/.local/state/local-shell-mcp.log"))

TOOL = {
    "name": "bash",
    "description": (
        "Run a bash command on the user's computer (bash -lc, as the user who started this server). "
        "Returns the exit code, stdout and stderr. Default working directory is $HOME. "
        "Long jobs: start them in the background and poll their log, because the client may time out."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Command passed to bash -lc."},
            "cwd": {"type": "string", "description": "Working directory (default $HOME)."},
            "timeout_s": {
                "type": "integer",
                "description": f"Timeout in seconds (default {DEFAULT_TIMEOUT}, max {MAX_TIMEOUT}).",
            },
        },
        "required": ["command"],
    },
}


def load_deny():
    path = os.environ.get("SHELL_MCP_DENY")
    if not path:
        return []
    patterns = []
    with open(os.path.expanduser(path)) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(re.compile(line))
    return patterns


DENY = load_deny()


def log(line):
    if not LOG:
        return
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + line.replace("\n", "\\n") + "\n")
    except OSError:
        pass


def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def clip(s):
    if len(s) <= MAX_OUT:
        return s
    return s[:MAX_OUT] + f"\n... [truncated {len(s) - MAX_OUT} chars]"


def _text(x):
    if x is None:
        return ""
    return x.decode(errors="replace") if isinstance(x, bytes) else x


def run(args):
    cmd = args.get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return "error: `command` must be a non-empty string", True
    cwd = os.path.expanduser(args.get("cwd") or "~")
    try:
        timeout = max(1, min(int(args.get("timeout_s") or DEFAULT_TIMEOUT), MAX_TIMEOUT))
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT

    for pat in DENY:
        if pat.search(cmd):
            log(f"REFUSED [{pat.pattern}] [cwd={cwd}] {cmd}")
            return f"refused: the command matches deny pattern {pat.pattern!r}", True

    log(f"RUN [cwd={cwd}] {cmd}")
    try:
        p = subprocess.run(
            ["bash", "-lc", cmd], cwd=cwd, capture_output=True, text=True,
            timeout=timeout, stdin=subprocess.DEVNULL,
        )
        out = f"exit={p.returncode}\n--- stdout ---\n{clip(p.stdout)}\n--- stderr ---\n{clip(p.stderr)}"
        return out, p.returncode != 0
    except subprocess.TimeoutExpired as e:
        return (f"TIMEOUT after {timeout}s\n--- stdout ---\n{clip(_text(e.stdout))}"
                f"\n--- stderr ---\n{clip(_text(e.stderr))}"), True
    except OSError as e:
        return f"error: {e}", True


def handle(req):
    method = req.get("method")
    rid = req.get("id")
    if rid is None:  # a notification (e.g. notifications/initialized): no reply
        return
    if method == "initialize":
        ver = (req.get("params") or {}).get("protocolVersion") or "2024-11-05"
        send({"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": ver,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "shell", "version": VERSION},
        }})
    elif method == "ping":
        send({"jsonrpc": "2.0", "id": rid, "result": {}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": rid, "result": {"tools": [TOOL]}})
    elif method == "tools/call":
        params = req.get("params") or {}
        if params.get("name") != "bash":
            send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": "unknown tool"}})
            return
        text, is_err = run(params.get("arguments") or {})
        send({"jsonrpc": "2.0", "id": rid, "result": {
            "content": [{"type": "text", "text": text}], "isError": is_err,
        }})
    else:
        send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {method}"}})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        try:
            handle(req)
        except Exception as e:  # never let one bad request kill the server
            if isinstance(req, dict) and req.get("id") is not None:
                send({"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32603, "message": str(e)}})


if __name__ == "__main__":
    main()

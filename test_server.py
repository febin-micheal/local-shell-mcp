import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def talk(messages, env=None):
    e = dict(os.environ, SHELL_MCP_LOG="")
    e.update(env or {})
    p = subprocess.run([sys.executable, os.path.join(HERE, "server.py")],
                       input="\n".join(json.dumps(m) for m in messages) + "\n",
                       capture_output=True, text=True, env=e, timeout=30)
    return [json.loads(l) for l in p.stdout.splitlines() if l.strip()]


def call(args, env=None):
    return talk([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                  "params": {"name": "bash", "arguments": args}}], env)[0]["result"]


class ServerTest(unittest.TestCase):
    def test_handshake_and_list(self):
        r = talk([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                  {"jsonrpc": "2.0", "method": "notifications/initialized"},
                  {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                  {"jsonrpc": "2.0", "id": 3, "method": "ping"}])
        self.assertEqual([m["id"] for m in r], [1, 2, 3])
        self.assertEqual(r[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(r[1]["result"]["tools"][0]["name"], "bash")

    def test_runs_and_reports_exit_code(self):
        ok = call({"command": "echo hello"})
        self.assertFalse(ok["isError"])
        self.assertIn("exit=0", ok["content"][0]["text"])
        self.assertIn("hello", ok["content"][0]["text"])
        bad = call({"command": "echo oops >&2; exit 3"})
        self.assertTrue(bad["isError"])
        self.assertIn("exit=3", bad["content"][0]["text"])
        self.assertIn("oops", bad["content"][0]["text"])

    def test_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIn(os.path.realpath(d), call({"command": "pwd -P", "cwd": d})["content"][0]["text"])

    def test_timeout(self):
        r = call({"command": "sleep 5", "timeout_s": 1})
        self.assertTrue(r["isError"])
        self.assertIn("TIMEOUT after 1s", r["content"][0]["text"])

    def test_deny_list(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("# no sudo\n\\bsudo\\b\n")
        try:
            r = call({"command": "sudo -n true"}, {"SHELL_MCP_DENY": f.name})
            self.assertTrue(r["isError"])
            self.assertIn("refused", r["content"][0]["text"])
            self.assertFalse(call({"command": "echo fine"}, {"SHELL_MCP_DENY": f.name})["isError"])
        finally:
            os.unlink(f.name)

    def test_log(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "log.txt")
            call({"command": "echo logged"}, {"SHELL_MCP_LOG": path})
            with open(path) as f:
                self.assertIn("RUN [cwd=", f.read())

    def test_bad_input(self):
        r = talk([{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "nope"}},
                  {"jsonrpc": "2.0", "id": 2, "method": "whatever"}])
        self.assertEqual(r[0]["error"]["code"], -32602)
        self.assertEqual(r[1]["error"]["code"], -32601)
        self.assertTrue(call({"command": ""})["isError"])


if __name__ == "__main__":
    unittest.main()

# local-shell-mcp

Give a Claude chat a real shell on your own computer — from any device, without leaving the chat.

One Python file. No dependencies. One tool: `bash`.

## Why

A claude.ai chat that is **linked to your computer** (through the Claude desktop app) can use the
local MCP servers configured in that desktop app. Add this one, and the chat can run commands on
your machine: read and edit files, run tests, use `git`, `ssh`, your CLIs — while keeping the whole
conversation's context.

- No copy-pasting commands into a terminal and pasting output back.
- No switching to a separate coding tool for small jobs.
- Works from the phone app too: the chat runs in the cloud and reaches your computer through the
  desktop app.

## Requirements

- Linux or macOS with `bash` and Python 3.8+.
- The Claude desktop app, signed in, with the chat linked to this computer.
- The computer awake and online, with the desktop app open (it can be minimised).

## Install

1. Put `server.py` anywhere, for example:

   ```bash
   mkdir -p ~/.local/share/local-shell-mcp
   curl -fsSL https://raw.githubusercontent.com/febin-micheal/local-shell-mcp/main/server.py \
     -o ~/.local/share/local-shell-mcp/server.py
   ```

2. Add it to the desktop app's config. This keeps any servers you already have and saves a backup:

   ```bash
   # Linux: ~/.config/Claude   macOS: ~/Library/Application\ Support/Claude
   cfg=~/.config/Claude/claude_desktop_config.json
   [ -f "$cfg" ] && cp "$cfg" "$cfg.bak.$(date +%s)" || echo '{}' > "$cfg"
   python3 - "$cfg" <<'EOF'
   import json, os, sys
   p = sys.argv[1]
   c = json.load(open(p))
   c.setdefault("mcpServers", {})["shell"] = {
       "command": "python3",
       "args": [os.path.expanduser("~/.local/share/local-shell-mcp/server.py")],
   }
   json.dump(c, open(p, "w"), indent=2)
   print(json.dumps(c["mcpServers"], indent=2))
   EOF
   ```

   If `python3` is not on the app's `PATH`, use its full path (`which python3`).

3. **Fully quit and reopen the desktop app.** Closing the window is not enough — quit it from the
   tray / menu bar (or `pkill -f -i claude-desktop` on Linux), then start it again.

4. In a chat linked to this computer, ask Claude to run `uptime`. The first call may ask you to
   approve the tool.

## Options

All optional, set in the server's `env` block in the config:

```json
{
  "mcpServers": {
    "shell": {
      "command": "python3",
      "args": ["/home/you/.local/share/local-shell-mcp/server.py"],
      "env": {
        "SHELL_MCP_DENY": "/home/you/.config/local-shell-mcp/deny.txt",
        "SHELL_MCP_LOG": "/home/you/.local/state/local-shell-mcp.log",
        "SHELL_MCP_TIMEOUT": "120",
        "SHELL_MCP_MAX_TIMEOUT": "1800",
        "SHELL_MCP_MAX_OUTPUT": "100000"
      }
    }
  }
}
```

| Variable | Default | What it does |
|---|---|---|
| `SHELL_MCP_DENY` | none | File of regular expressions, one per line. A matching command is refused and never run. |
| `SHELL_MCP_LOG` | `~/.local/state/local-shell-mcp.log` | Every command, run or refused. Set to `""` to turn off. |
| `SHELL_MCP_TIMEOUT` | `120` | Default timeout per command, in seconds. |
| `SHELL_MCP_MAX_TIMEOUT` | `1800` | Largest timeout a call may ask for. |
| `SHELL_MCP_MAX_OUTPUT` | `100000` | Characters kept per stream (stdout / stderr) before truncating. |

An example deny file is in [`deny.example.txt`](deny.example.txt).

## Limits

- **Calls through a linked chat time out after about 60 seconds**, whatever `timeout_s` says. Run
  long jobs in the background and check their log:

  ```bash
  (setsid nohup make test > /tmp/test.log 2>&1 &)   # start
  tail -n 20 /tmp/test.log                          # check later
  ```

- Not interactive: no prompts, no TTY. `stdin` is empty, so commands that ask for input fail
  instead of hanging. Use non-interactive flags (`-y`, `BatchMode=yes`, `sudo -n`).
- It works only while the computer is awake and the desktop app is open.

## Security

**This gives the chat the same access you have in your own terminal.** Anything your user can do,
it can do: delete files, push code, reach servers your SSH keys open.

- Use it only with your own account and chats you trust.
- Put anything that must never run (production hosts, `sudo`, `rm -rf /`) in a deny file. The deny
  list is a guard rail for honest mistakes, not a sandbox — a determined command can get around a
  regular expression.
- Read the log now and then.
- Content the chat reads (web pages, files, emails) can contain instructions. Keep that in mind
  before approving the tool permanently.

## Test

```bash
python3 -m unittest -v test_server.py
```

## License

MIT

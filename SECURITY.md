# Security policy

grok-agent-threads gives a remote agent the ability to message and start Claude Code chats on your Mac, and those
chats can edit files and run commands. Read [docs/security.md](docs/security.md) before connecting an agent.

Defaults: the server listens on 127.0.0.1 only, is shared on your Tailscale network only (never the public internet),
refuses unknown Host headers, and requires the access key the installer creates. It has no tool that deletes,
archives or stops a chat.

To report a vulnerability, open a private security advisory on GitHub (Security tab, "Report a vulnerability")
rather than a public issue.

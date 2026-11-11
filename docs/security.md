# Security

## Who can reach the server

The server binds to `127.0.0.1` only. `tailscale serve` shares it with devices on your tailnet over HTTPS, never on the public internet; Funnel is not used. Requests whose `Host` header is not loopback or your tailnet name are refused, which also blocks DNS-rebinding from a web page.

**Access key.** `scripts/install.sh` creates a random key (`~/.grok-agent-threads/key`, mode 600) and prints the address with it (`.../mcp?key=...`). Every MCP request must then carry it, in the URL or as `Authorization: Bearer <key>`; other devices on your tailnet are refused with 401. Keep the address private. To change the key, delete the file and run the installer again, then update your agent. To go without a key, run the installer with `GROK_AGENT_THREADS_KEY=""` and the tailnet is the only lock.

**Watch links** carry their own key, an HMAC of the chat's id with a secret in `~/.grok-agent-threads/secret` (mode 600). A link opens one chat's live view and nothing else.

## The Grok Bot device

Grok Bot's Tailscale plugin adds its cloud computer to your tailnet as a device owned by you. With Tailscale's default policy ("everything reaches everything"), it can then reach all your devices, not only this server. To limit it to this server:

1. Add a tag owner and narrow the default rule to your own devices, then add one rule for the tag:

```jsonc
{
  "tagOwners": { "tag:grokbot": ["autogroup:admin"] },
  "grants": [
    // your own devices keep full access to each other
    {"src": ["autogroup:member"], "dst": ["*"], "ip": ["*"]},
    // the Grok Bot device reaches only grok-agent-threads on this Mac
    {"src": ["tag:grokbot"], "dst": ["<this Mac's tailnet IP>"], "ip": ["tcp:8857"]}
  ]
}
```

2. In the Tailscale admin console, Machines, find the `grokbot-...` device and set its tag to `tag:grokbot`. A tagged device loses your user identity, so the `autogroup:member` rule no longer covers it.

On Premium and Enterprise plans you can use the device posture attribute Grok Bot sets instead of a tag (Tailscale's blog: "OAuth apps GA").

## What the calling agent can do

Everything your chats can do. A closed chat wakes in its own permission mode; many Claude app chats run with permissions skipped, so a message can lead to file edits and commands without a prompt. New chats start in auto mode (`GROK_AGENT_THREADS_NEW_CHAT_MODE`). Set it to `default` if you want new chats to refuse anything that needs approval.

No tool deletes, archives or stops a chat or thread.

## What a chat is told

Every relayed message starts with a note naming who typed it and which agent relayed it, and saying it is never the owner's approval for anything outward (sending, posting, paying). Claude treats messages from other sessions as teammate requests, not as the user.

## Prompt injection

The risk is a calling agent that forwards text it read somewhere (an email, a web page, a post) as if you had typed it. The setup prompt tells Grok Bot to pass only your own words. Prefer connecting the server to an agent that does not also read untrusted mail or feeds, or give that agent instructions as strict as the setup prompt's.

## Logs

Every call, with its arguments and the first 500 characters of the result, is appended to `~/.grok-agent-threads/logs/calls.jsonl`.

# The relay chat: live work in the Claude app

The Claude app shows a chat's work live only when the app itself runs the turn. A chat that is open in the app can be
messaged directly through its local inbox. A closed chat, or a brand-new one, has no inbox, and the app gives outside
programs no way to start a turn. Only a chat inside the app can ask for that, with the app's own `SendMessage` tool.

The relay is that insider: one small chat, kept open in the Claude app, titled `⇄ grok-agent-threads relay`
(`GROK_AGENT_THREADS_RELAY`). The server reaches it like any open chat, through its local inbox, and hands it one line:

```
RELAY {"op":"send","to":"local_<id>","text":"<the owner's words, with the relay note>"}
```

The relay calls `SendMessage` with that text, unchanged, and answers `RELAY_OK sent <id>`. The app then wakes the
target chat and runs the turn, live on screen, without switching the owner's view. From then on that chat is open, so
later messages go to it directly and skip the relay.

- `message_chat` to a closed chat: through the relay when it is open; otherwise the chat wakes in the background
  (Agent SDK), and the work shows when the chat is opened.
- `start_chat`: the chat is created with a one-word first turn, added to the sidebar, then handed the request through
  the relay, so the real work runs live.

## Starting the relay

In the Claude app, start a chat (a small, fast model is enough) with the prompt in
[relay-prompt.md](relay-prompt.md) and title it `⇄ grok-agent-threads relay`.

## Limits (the app's rules, not this server's)

- After 20 forwards with nothing typed by the owner in the relay chat, the app pauses its forwarding until the owner
  types anything there. The server then falls back to background runs and says so.
- The relay has to be open in the app. After the app restarts, type anything in it once (or start a new one).
- Each forward is one short model turn in the relay chat (a few seconds).

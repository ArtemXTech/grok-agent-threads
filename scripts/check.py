"""Self-test: call the running server the way a remote agent would and print what it sees.
  uv run scripts/check.py [url]        # default http://127.0.0.1:8857/mcp"""
import asyncio, os, sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main(url):
    async with streamablehttp_client(url) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = [t.name for t in (await s.list_tools()).tools]
            print(f"tools ({len(tools)}): {', '.join(tools)}\n")
            for name, args in (("connector_status", {}), ("list_chats", {"limit": 5})):
                res = await s.call_tool(name, args)
                print(f"{name}:\n{res.content[0].text}\n")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8857/mcp"
    keyfile = Path.home() / ".grok-agent-threads" / "key"
    key = os.environ.get("GROK_AGENT_THREADS_KEY") or (keyfile.read_text().strip() if keyfile.exists() else "")
    if key and "key=" not in url:
        url += ("&" if "?" in url else "?") + "key=" + key
    asyncio.run(main(url))

#!/usr/bin/env python3
"""List an MCP server's tools over streamable HTTP; exit 1 if any expected tool is missing.

    mcp_list.py URL TOOL [TOOL ...]
"""
import sys

import anyio
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def main(url, want):
    async with streamable_http_client(url) as (read, write, *_):
        async with ClientSession(read, write) as s:
            await s.initialize()
            names = {t.name for t in (await s.list_tools()).tools}
    missing = sorted(set(want) - names)
    print(f"{url}: {len(names)} tools" + (f"; missing {missing}" if missing else ""))
    sys.exit(1 if missing else 0)


anyio.run(main, sys.argv[1], sys.argv[2:])

from livekit import api
import inspect
import asyncio

async def run():
    lk = api.LiveKitAPI('http://1', 'a', 's')
    print(inspect.signature(lk.agent_dispatch.create_dispatch))
    await lk.aclose()

asyncio.run(run())

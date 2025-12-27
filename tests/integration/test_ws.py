import asyncio
import websockets

async def test():
    uri = 'ws://localhost:8000/api/applications/v2/ws/interventions'
    print(f'Connecting to {uri}...')
    try:
        ws = await asyncio.wait_for(websockets.connect(uri), timeout=5)
        print(f'Connected! State: {ws.state}')
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=3)
            print(f'Received: {msg[:300]}')
        except asyncio.TimeoutError:
            print('Timeout waiting for message')
        except Exception as e:
            print(f'Recv error: {type(e).__name__}: {e}')
        finally:
            await ws.close()
    except Exception as e:
        print(f'Connect error: {type(e).__name__}: {e}')

asyncio.run(test())

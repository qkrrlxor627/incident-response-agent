"""Ollama 앞에 끼우는 TCP 프록시. --cut-after초 뒤 모든 연결을 강제로 끊는다 (P6 장애 재현용).

Before S6은 `pkill -f "ollama serve"`로 Ollama 자체를 껐다. After에서는 사용자가 띄운 Ollama를
건드리지 않으려고, 서버가 이 프록시를 거쳐 Ollama에 붙게 한 뒤 프록시만 끊는다.
→ 서버 입장에서는 똑같이 '답변 스트림 도중 연결 끊김'(RemoteProtocolError)이다.

사용: python cut_proxy.py --listen 11500 --target 11434 --cut-after 8
"""
import argparse
import asyncio

ap = argparse.ArgumentParser()
ap.add_argument("--listen", type=int, default=11500)
ap.add_argument("--target", type=int, default=11434)
ap.add_argument("--cut-after", type=float, default=8.0, help="첫 연결 후 몇 초 뒤 끊을지 (0이면 끊지 않음)")
a = ap.parse_args()
writers: list[asyncio.StreamWriter] = []
first = asyncio.Event()


async def pipe(r: asyncio.StreamReader, w: asyncio.StreamWriter):
    try:
        while data := await r.read(65536):
            w.write(data)
            await w.drain()
    except Exception:
        pass
    finally:
        w.close()


async def handle(cr, cw):
    first.set()
    ur, uw = await asyncio.open_connection("127.0.0.1", a.target)
    writers.extend([cw, uw])
    await asyncio.gather(pipe(cr, uw), pipe(ur, cw))


async def main():
    server = await asyncio.start_server(handle, "127.0.0.1", a.listen)
    print(f"proxy :{a.listen} → :{a.target}, cut after {a.cut_after}s from first connection", flush=True)
    if a.cut_after:
        await first.wait()
        await asyncio.sleep(a.cut_after)
        print("cutting all connections", flush=True)
        for w in writers:
            w.transport.abort()   # RST — 진행 중인 스트림이 갑자기 끊긴다
        server.close()
        return
    await server.serve_forever()

asyncio.run(main())

"""7단계: /chat/stream 경로 재현 (fake 백엔드, 임시 session DB)."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(sys.argv[1])
VERSION = sys.argv[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.update(LANGCHAIN_TRACING_V2="false", LANGSMITH_TRACING="false",
                  LLM_BACKEND="fake", SUPERVISOR_VERSION=VERSION)

import server  # noqa: E402
from agent.session_store import SqliteSessionStore  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

tmp_db = Path(tempfile.mkdtemp()) / "session.db"
server.SqliteSessionStore = lambda: SqliteSessionStore(tmp_db)


def stream(c, msg, tid):
    r = c.get("/chat/stream", params={"message": msg, "thread_id": tid})
    lines = [l for l in r.text.split("\n\n") if l]
    return r, lines


with TestClient(server.app) as c:
    print(f"--- SUPERVISOR_VERSION={VERSION}")
    r, lines = stream(c, "web-01 장애 진단해줘", "t1")
    print(f"- 정상 요청: status={r.status_code} 이벤트 {len(lines)}개, 마지막={lines[-1]!r}")
    print(f"  응답 헤더 Cache-Control={r.headers.get('cache-control')} "
          f"X-Accel-Buffering={r.headers.get('x-accel-buffering')}")
    hist = server.app.state.deps.session_store.load("t1")
    print(f"- 스트림 완료 후 이력 저장 건수: {len(hist)}")

    r, lines = stream(c, "", "t2")
    print(f"- 빈 메시지: status={r.status_code} (기대 422), 이벤트 {len(lines)}개")

    if VERSION == "v2":
        async def boom(*a, **k):
            raise RuntimeError("LLM 연결 끊김(시뮬레이션)")
            yield
        orig = server.app.state.graph.astream
        server.app.state.graph.astream = boom
        try:
            r, lines = stream(c, "web-01 장애 진단해줘", "t3")
            print(f"- 처리 중 예외: status={r.status_code} 이벤트 {lines}")
        except Exception as e:
            print(f"- 처리 중 예외: 스트림이 예외로 끊김 → {type(e).__name__}: {e}")
            print("  ([DONE]도, 오류 이벤트도 안 내려감 → 화면은 onerror로 조용히 입력창만 복구)")
        finally:
            server.app.state.graph.astream = orig
        hist = server.app.state.deps.session_store.load("t3")
        print(f"- 예외 난 턴의 사용자 메시지 저장 건수: {len(hist)}")

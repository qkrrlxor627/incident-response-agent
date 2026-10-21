"""Wave 12 — 프로세스 밖(SQLite 파일)에 두는 세션 저장소.

서버가 재시작돼도(새 프로세스, 새 인스턴스) 같은 session.db 파일을 다시 열므로
대화 이력이 유지된다. in-memory dict였다면 재시작 즉시 소실됐을 상태다.

[E15 BEFORE] async 서버(FastAPI)에서 동기 sqlite3 호출을 그대로 했다.
  - load/append가 이벤트 루프 스레드에서 디스크 I/O를 한다 → 그동안 다른 요청이 멈춘다 (P4와 같은 종류의 문제)
  - 연결 하나를 check_same_thread=False로 모든 요청이 공유했다
  - thread_id 인덱스가 없어 이력이 쌓일수록 load가 전체 테이블을 훑는다
[E15 AFTER]
  - load/append를 async로 바꾸고, 실제 sqlite 작업은 asyncio.to_thread로 스레드 풀에서 한다 (K13)
  - 호출마다 짧은 연결을 연다 → 스레드끼리 연결을 공유하지 않는다 (WAL 모드로 읽기·쓰기 동시 가능)
  - (thread_id, rowid) 인덱스
  - create_session_store() 팩토리 → server.py lifespan이 이것으로 주입한다 (K14, 테스트에서 교체 쉬움)
"""
import asyncio
import os
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "session.db"


class SqliteSessionStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        # [E15 BEFORE] self.conn = sqlite3.connect(db_path, check_same_thread=False)   ← 모든 요청이 연결 1개 공유
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")   # 쓰는 동안에도 다른 연결이 읽을 수 있다
            conn.execute(
                "CREATE TABLE IF NOT EXISTS messages ("
                " thread_id TEXT, role TEXT, content TEXT, created TEXT)"
            )
            # [E15 AFTER] thread_id로 찾는 쿼리(load)를 위한 인덱스
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id)")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=5.0)

    # ── 동기 구현: 스레드 풀 안에서만 실행된다 ──
    def _load_sync(self, thread_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE thread_id=? ORDER BY rowid",
                (thread_id,),
            ).fetchall()
        return [{"role": r, "content": c} for r, c in rows]

    def _append_sync(self, thread_id: str, role: str, content: str) -> None:
        with self._connect() as conn:   # with 블록이 끝나면 commit
            conn.execute(
                "INSERT INTO messages VALUES (?,?,?,?)",
                (thread_id, role, content, datetime.now().isoformat()),
            )

    # ── [E15 AFTER] async 인터페이스: 이벤트 루프를 막지 않는다 ──
    # [E15 BEFORE] def load(self, thread_id: str) -> list[dict]: rows = self.conn.execute(...)
    async def load(self, thread_id: str) -> list[dict]:
        return await asyncio.to_thread(self._load_sync, thread_id)

    # [E15 BEFORE] def append(self, thread_id, role, content): self.conn.execute(...); self.conn.commit()
    async def append(self, thread_id: str, role: str, content: str) -> None:
        await asyncio.to_thread(self._append_sync, thread_id, role, content)

    def close(self) -> None:
        pass   # 호출마다 연결을 닫으므로 정리할 것이 없다 (Before: 공유 연결 close)


def create_session_store() -> SqliteSessionStore:
    """[E15 AFTER] 저장소 팩토리. SESSION_DB 환경변수로 파일 위치를 바꿀 수 있다 (테스트·스모크용)."""
    return SqliteSessionStore(Path(os.environ.get("SESSION_DB", DB_PATH)))

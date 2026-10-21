#!/usr/bin/env bash
# P6 재현: (1) Ollama 앞 프록시를 답변 도중 끊기 → /chat/stream 이벤트, (2) 연결 불가 주소 → /chat 응답
cd "$(dirname "$0")/../../.."
export LANGCHAIN_TRACING_V2=false LANGSMITH_TRACING=false LLM_BACKEND=ollama
./.venv/bin/python3 outputs/after/scripts/cut_proxy.py --listen 11500 --target 11434 --cut-after 4 &
PROXY=$!
OLLAMA_URL=http://127.0.0.1:11500/api/chat ./.venv/bin/python3 -m uvicorn server:app --port 8199 --log-level warning > /tmp/p6_server.log 2>&1 &
PID=$!
for _ in $(seq 1 60); do curl -s localhost:8199/health >/dev/null && break; sleep 0.5; done
echo "== (1) /chat/stream: 'log-service 디스크 공간이 부족하다는 알림이 왔어요' — 4초 뒤 Ollama 연결 강제 종료 =="
curl -sN --max-time 120 -G localhost:8199/chat/stream --data-urlencode "message=log-service 디스크 공간이 부족하다는 알림이 왔어요" --data-urlencode "thread_id=p6" | grep -v AnswerToken | cut -c1-220
kill $PID; wait $PID 2>/dev/null; kill $PROXY 2>/dev/null
echo "== 서버 로그 (구조화 로그) =="; grep -v "^INFO\|node_done" /tmp/p6_server.log | cut -c1-250 | tail -5
echo
echo "== (2) /chat: Ollama 주소가 연결 불가(:11999) =="
OLLAMA_URL=http://127.0.0.1:11999/api/chat ./.venv/bin/python3 -m uvicorn server:app --port 8199 --log-level warning > /tmp/p6_server2.log 2>&1 &
PID=$!
for _ in $(seq 1 60); do curl -s localhost:8199/health >/dev/null && break; sleep 0.5; done
curl -s -w "\nHTTP %{http_code}\n" -X POST localhost:8199/chat -H 'content-type: application/json' -d '{"message":"web-01 장애 진단해줘","thread_id":"p6b"}'
kill $PID; wait $PID 2>/dev/null

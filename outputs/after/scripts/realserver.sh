#!/usr/bin/env bash
# 실모델(ollama) 서버를 :8199에 띄우고, 인자로 받은 python 스크립트들을 실행한 뒤 종료한다.
cd /Users/qkrrlxor627/subject/1020/all_total_vue_student
export LANGCHAIN_TRACING_V2=false LANGSMITH_TRACING=false LLM_BACKEND=ollama
./.venv/bin/python3 -m uvicorn server:app --port 8199 --log-level warning > /private/tmp/claude-501/real8199.log 2>&1 &
PID=$!
for _ in $(seq 1 60); do curl -s localhost:8199/health >/dev/null && break; sleep 0.5; done
"$@"
kill $PID; wait $PID 2>/dev/null

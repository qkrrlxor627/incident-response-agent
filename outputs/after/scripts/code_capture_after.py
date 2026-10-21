"""[After] 고친 코드 캡처 (outputs/before/scripts/code_capture.py와 같은 렌더러, ITEMS만 After 위치)\n\n문제 코드 캡처 — 실제 소스 파일에서 줄 범위를 읽어 줄 번호·강조와 함께 PNG로 저장한다.

사용: python code_capture.py <project_root> <out_dir>
"""
import html
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)

# (파일명, 제목, 문제 정의, [(경로, 시작, 끝, {강조 줄})])
ITEMS = [
    ("C01_P1_plan_supplement_only_when_empty", "P1 After · 질문에 나온 시스템을 항상 보충",
     "목록에 없는 target(실모델은 'get_monitoring_status Tool for web-01' 같은 문장을 냄)은 버리고(251), 질문에 나온 시스템을 언급 순서대로 항상 보충한다(274-287).",
     [("agent/ollama_llm.py", 244, 253, {251, 252}), ("agent/ollama_llm.py", 274, 287, {276, 277, 279, 287})]),
    ("C02_P1_prompt_single_system", "P1·#14 After · MCP Prompt에 시스템 전부 + 공통 모듈",
     "_extract_system_name이 'web-01, auth-service'처럼 전부 넘긴다(57). 3개 파일에 복사돼 있던 추출 로직은 agent/systems.py 하나로 모았다(36).",
     [("agent/graph.py", 46, 57, {46, 57}), ("agent/systems.py", 36, 42, {41, 42})]),
    ("C03_P2_db_down_fallback", "P2 After · 이상 있는 시스템을 언급 순서로, 근거 없으면 None",
     "정상(healthy/unknown) 시스템은 건너뛰고(286), 먼저 나온 이상 시스템의 알림으로 분류한다. 아무 근거가 없으면 db-down 대신 None(292) → runbook을 붙이지 않는다.",
     [("agent/graph.py", 275, 292, {286, 287, 292})]),
    ("C04_P3_gate_trusts_model", "P3 After · 이중 게이트 (LLM 판단 + research ≥ 2)",
     "모델의 needs_analysis가 true여도 비교할 시스템이 2개 미만이면 analysis를 제거한다(155-156).",
     [("agent/graph.py", 150, 161, {154, 155, 156})]),
    ("C05_P4_sync_llm_call_in_async_node", "P4 After · httpx.AsyncClient + await",
     "_chat이 async def가 되고(123) AsyncClient로 await 호출한다(135-136). 노드도 await로 부른다(94).",
     [("agent/ollama_llm.py", 123, 137, {123, 135, 136}), ("agent/graph.py", 91, 94, {94})]),
    ("C06_P5_retry_and_mcp_timeout", "P5 After · MCP 시간 제한 + 예외 번역 + 재시도 분류",
     "모든 MCP 요청이 _call을 지나며 10초 제한(92). SDK timeout도 TimeoutError로 번역(97) → with_retry의 _is_transient가 재시도 대상으로 판단(15, 32).",
     [("agent/mcp_client.py", 82, 100, {92, 94, 97, 98, 100}), ("agent/retry.py", 15, 37, {17, 31, 32})]),
    ("C07_P6_no_isolation_no_error_event", "P6 After · task별 격리 + 스트림 Error 이벤트 + 화면 표시",
     "run_one이 예외를 잡아 그 task만 실패 처리(210, 224). 스트림은 예외를 Error 이벤트로 바꾸고 항상 [DONE](209-210). 화면은 Error를 빨간 말풍선으로(223).",
     [("agent/graph.py", 194, 214, {194, 210}), ("server.py", 202, 210, {206, 209, 210}), ("web_chat.html", 222, 229, {223})]),
    ("C08_P7_stream_endpoint_unprotected", "P7 After · 입력 계약 · 스트림 검증 · SSE 헤더",
     "ChatRequest에 길이·공백·thread_id 형식(51-62), 스트림도 같은 모델로 검증(195), SSE 헤더(255-256).",
     [("server.py", 47, 62, {52, 53, 57}), ("server.py", 193, 197, {195}), ("server.py", 253, 258, {255, 256})]),
    ("C10_P9_timeout_and_think", "P9 After · 단계별 timeout · think 끔 · 노드 시간 기록",
     "빠른 단계 60초/write 180초(27-28), think=false(33, 130), 노드별 elapsed_ms를 state·로그에 기록(_timed, 484).",
     [("agent/ollama_llm.py", 22, 33, {27, 28, 33}), ("agent/graph.py", 473, 489, {484, 485})]),
    ("C11_P10_v1_rollback_condition", "P10 After (기준 외) · v1이 질문으로 장애 판단",
     "응답 문구('도와드릴까요') 대신 질문의 키워드·시스템 이름으로 판단하고(40), 질문에 나온 시스템을 모두 조회한다(42).",
     [("agent/supervisor_v1.py", 38, 52, {40, 42})]),
    ("C12_P11_validate_format_only", "P11 After · 규칙 검사 + LLM judge, 재작성 1회",
     "규칙 3개(형식·조사 시스템 누락·근거 없는 시스템)를 먼저 보고(410), 통과하면 8b judge로 사실 일치를 확인한다(437). 재작성은 1회까지.",
     [("agent/graph.py", 410, 424, {417, 418, 421}), ("agent/graph.py", 426, 448, {431, 437, 439, 442})]),
    ("C13_E15_sync_sqlite_session", "E15 After · 비동기 세션 저장소",
     "load/append가 async이고 sqlite 작업은 asyncio.to_thread로 스레드 풀에서 실행(59-64). 호출마다 짧은 연결 + WAL + thread_id 인덱스.",
     [("agent/session_store.py", 26, 36, {30, 36}), ("agent/session_store.py", 57, 72, {60, 64, 70})]),
]

CSS = """
body{margin:0;background:#0f1117;font-family:-apple-system,'Apple SD Gothic Neo',sans-serif;color:#e6e6e6}
.wrap{padding:28px 32px;width:1180px}
h1{font-size:22px;margin:0 0 8px;color:#fff}
p.def{font-size:15px;line-height:1.55;margin:0 0 18px;color:#f2c97d;background:#2a2416;border-left:4px solid #f2c97d;padding:10px 14px;border-radius:4px}
.file{font:600 13px Menlo,monospace;color:#8ab4f8;margin:14px 0 4px}
pre{margin:0;background:#161922;border:1px solid #2a2f3a;border-radius:6px;padding:8px 0;font:13px/1.55 Menlo,monospace;overflow:hidden}
.l{display:block;padding:0 14px;white-space:pre}
.l.hl{background:#4a1f24;border-left:4px solid #ff6b6b;padding-left:10px}
.n{display:inline-block;width:42px;color:#5c6370;text-align:right;margin-right:14px;user-select:none}
.foot{margin-top:14px;font-size:12px;color:#7d8590}
"""


def render(title, definition, snippets):
    parts = [f"<h1>{html.escape(title)}</h1><p class='def'>{html.escape(definition)}</p>"]
    for path, s, e, hl in snippets:
        lines = (ROOT / path).read_text().splitlines()
        body = "".join(
            f"<span class='l{' hl' if i in hl else ''}'><span class='n'>{i}</span>{html.escape(lines[i - 1])}</span>"
            for i in range(s, min(e, len(lines)) + 1))
        parts.append(f"<div class='file'>{path}:{s}-{e}</div><pre>{body}</pre>")
    parts.append("<div class='foot'>After 코드 (HEAD) · 빨간 줄 = 고친 지점</div>")
    return f"<!doctype html><meta charset='utf-8'><style>{CSS}</style><div class='wrap'>{''.join(parts)}</div>"


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 1250, "height": 800}, device_scale_factor=2)
    for name, title, definition, snippets in ITEMS:
        pg.set_content(render(title, definition, snippets))
        pg.locator(".wrap").screenshot(path=str(OUT / f"{name}.png"))
        print("saved", name)
    b.close()

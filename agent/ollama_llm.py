"""LLM_BACKEND=ollama — 로컬 Ollama 실모델 백엔드 (fake_llm과 동일 인터페이스).

Wave 10a 구도를 실물로: fast(기본 qwen3:0.6b)는 분류·계획·단순 대화, quality(기본
qwen3:8b)는 최종 답변 작성 전담. Ollama의 구조화 출력(format=<JSON Schema>)과
temperature=0으로 변동을 줄이지만 실모델이므로 결정론은 아니다 — 그래서 gate(W6)·
replan(W7)·validator(W8)가 연출이 아니라 실제 방어선으로 동작한다.
fc
비용(cost_usd)은 '가상 단가 × 실측 토큰 수(prompt_eval_count+eval_count)'다 — 로컬
추론이라 실제 과금은 0이지만, W10a의 모델 분리 효과를 같은 잣대로 비교하기 위함이다.

사전 조건: `ollama serve` 실행 중 + `ollama pull qwen3:0.6b qwen3:8b`.
"""
import json
import os
import re
from pathlib import Path

import httpx
from langsmith import traceable

# [P6 AFTER] 환경변수로 바꿀 수 있게 했다 — 장애 재현 때 중간 프록시를 끼워 "답변 도중 끊김"을 만들기 위함
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")

# ── [P9 AFTER] 단계별 시간 제한 (Before: 모든 호출이 timeout=300.0 하나) ──
#    route·plan·analyze는 짧은 JSON 출력이라 60초면 충분하다. 넘으면 '멈춤'으로 보고 빨리 실패시킨다.
#    q01 Before: analyze 한 번이 300.07초 동안 멈춘 뒤 ReadTimeout (outputs/before/evidence/S11)
FAST_TIMEOUT = float(os.environ.get("OLLAMA_FAST_TIMEOUT", "60"))     # route / plan / analyze / chat
WRITE_TIMEOUT = float(os.environ.get("OLLAMA_WRITE_TIMEOUT", "180"))  # 최종 답변(qwen3:8b, 토큰 스트림)
# ── [P9 AFTER] qwen3의 '생각(thinking)' 토큰을 끈다 ──
#    think를 지정하지 않으면 qwen3는 답 전에 숨은 사고 토큰을 만든다.
#    실측(outputs/after/evidence/P9_think_tokens.txt): 0.6b 190 → 9 토큰, 8b 409 → 38 토큰, 18.9초 → 1.9초
#    트레이드오프: 답변이 짧아질 수 있다 → After 측정의 judge 점수로 품질을 같이 확인한다
OLLAMA_THINK = os.environ.get("OLLAMA_THINK", "false").lower() == "true"


# ── [#14 BEFORE] graph.py·ollama_llm.py·openai_llm.py에 똑같이 복사돼 있던 시스템 추출 로직 ──
# def _load_known_systems() -> set[str]:
#     """KNOWN_SYSTEMS를 data/monitoring.json의 실제 시스템 키들로 동적으로 맞춘다 —
#     하드코딩된 2개짜리 목록이 모니터링 데이터와 어긋나던 문제(payments/cache/gateway/
#     log-service 미인식) 수정."""
#     path = Path(__file__).resolve().parent.parent / "data" / "monitoring.json"
#     try:
        # return set(json.loads(path.read_text()).keys())
#     except (OSError, json.JSONDecodeError):
        # return {"auth-service", "web-01"}
#
#
# KNOWN_SYSTEMS = _load_known_systems()
#
#
# def _guess_target(query: str) -> str:
#     """plan()의 코드 레벨 정규화에서 쓰는 안전망 — 소형 모델(fast_llm, 이전 기본값
#     qwen2.5:0.5b에서 실측된 사례)이 target을
#     아예 안 내놓거나(예: agent=analysis만 던지고 research task를 하나도 안 만듦) 오타
#     (예: "payment_service")를 내놓으면, 하드코딩된 "auth-service"로 덮어쓰는 대신
#     KNOWN_SYSTEMS 멤버십 매칭으로 쿼리에서 실제 시스템명을 다시 찾는다(W6 정신:
#     모델 출력을 그대로 믿지 않고 코드가 보정). 아무것도 안 걸리면 auth-service로 폴백."""
#     matches = [(query.index(s), s) for s in KNOWN_SYSTEMS if s in query]
#     return min(matches)[1] if matches else "auth-service"
#
#
# def _guess_targets(query: str) -> list[str]:
#     """research task가 통째로 0개일 때(모델이 agent=analysis만 던지는 등 계획 자체가
#     붕괴됐을 때) 쓰는 복구용 — _guess_target처럼 하나만 고르면 쿼리에 언급된 다른
#     시스템이 조사에서 통째로 빠지고, write 단계가 그 빈 자리를 수치까지 지어내서
#     채우는 할루시네이션으로 이어진다(실측 사례: cache-service 미조사 → "CPU 53.5%"
#     조작). 쿼리에 등장하는 KNOWN_SYSTEMS 전부를 복구한다."""
#     matched = sorted(s for s in KNOWN_SYSTEMS if s in query)
#     return matched or ["auth-service"]
# ── [#14 AFTER] 공통 모듈 agent/systems.py 하나로 모았다 (K14 모듈화) ──
# mentioned_systems: 질문에 나온 시스템을 '언급 순서'대로 돌려준다 (Before는 sorted로 순서를 잃었다)
from .systems import DEFAULT_SYSTEM, KNOWN_SYSTEMS, mentioned_systems, unmonitored_systems  # noqa: E402


ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "route": {"type": "string", "enum": ["chat", "incident"]},
        "needs_analysis": {"type": "boolean"},
    },
    "required": ["route", "needs_analysis"],
}

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "needs_analysis": {"type": "boolean"},
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "agent": {"type": "string",
                              "enum": ["research", "analysis"]},
                    "target": {"type": "string"},
                },
                "required": ["agent"],
            },
        },
    },
    "required": ["needs_analysis", "tasks"],
}

JUDGE_SCHEMA = {   # [P11 AFTER] judge 출력 형식
    "type": "object",
    "properties": {"grounded": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["grounded", "reason"],
}


class OllamaLLM:
    def __init__(self, model: str, usd_per_1k_tokens: float):
        self.name = f"ollama:{model}"
        self.model = model
        self.usd_per_1k = usd_per_1k_tokens

    # ── [P4 BEFORE] async 노드 안에서 '동기' HTTP 호출 → 응답을 기다리는 동안 이벤트 루프 전체가 멈춤 ──
    #    (다른 사용자의 /health가 최대 1.73초 지연(S5), q01은 300초 동안 서버가 이 호출에 묶임(S11))
    # def _chat(self, system: str, user: str, schema: dict | None = None) -> tuple[str, dict]:
    #     payload = {..., "stream": False, "options": {"temperature": 0.0}}
    #     resp = httpx.post(OLLAMA_URL, json=payload, timeout=300.0)
    # ── [P4 AFTER] httpx.AsyncClient + await → 기다리는 동안 다른 요청을 처리한다 (K12 블로킹 금지) ──
    async def _chat(self, system: str, user: str, schema: dict | None = None,
                    timeout: float = FAST_TIMEOUT) -> tuple[str, dict]:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "stream": False,
            "think": OLLAMA_THINK,            # [P9 AFTER] 숨은 사고 토큰 끔
            "options": {"temperature": 0.0},
        }
        if schema is not None:
            payload["format"] = schema
        async with httpx.AsyncClient(timeout=timeout) as client:   # [P9 AFTER] 단계별 timeout
            resp = await client.post(OLLAMA_URL, json=payload)       # await: 여기서 이벤트 루프를 양보한다
        resp.raise_for_status()
        data = resp.json()
        content = data["message"]["content"]
        tokens = (data.get("prompt_eval_count") or 0) + (data.get("eval_count") or 0)
        usage = {"model": self.name, "tokens": tokens,
                 "usd": round(tokens / 1000 * self.usd_per_1k, 6)}
        return content, usage

    async def _chat_stream(self, system: str, user: str, on_token=None,
                           timeout: float = FAST_TIMEOUT) -> tuple[str, dict]:
        """사용자 대면 텍스트(최종 답변류) 전용 — Ollama NDJSON 스트림을 토큰 단위로
        받아 on_token(조각)을 즉시 호출해 SSE로 실시간 중계할 수 있게 한다. 분류/계획
        등 JSON 스키마 출력(route/plan/analyze)은 부분 출력이 의미가 없어 그대로 _chat을
        쓴다."""
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "stream": True,
            "think": OLLAMA_THINK,            # [P9 AFTER]
            "options": {"temperature": 0.0},
        }
        chunks: list[str] = []
        usage = {"model": self.name, "tokens": 0, "usd": 0.0}
        # [P9 BEFORE] async with httpx.AsyncClient(timeout=300.0) as client:
        async with httpx.AsyncClient(timeout=timeout) as client:   # [P9 AFTER] 호출한 단계의 timeout
            async with client.stream("POST", OLLAMA_URL, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    piece = data.get("message", {}).get("content", "")
                    if piece:
                        chunks.append(piece)
                        if on_token is not None:
                            on_token(piece)
                    if data.get("done"):
                        tokens = ((data.get("prompt_eval_count") or 0)
                                  + (data.get("eval_count") or 0))
                        usage = {"model": self.name, "tokens": tokens,
                                 "usd": round(tokens / 1000 * self.usd_per_1k, 6)}
        usage["prompt"] = f"[SYSTEM]\n{system}\n\n[USER]\n{user}"
        return "".join(chunks), usage


    # ── [P11 AFTER] LLM-as-a-Judge: 답변이 '수집된 사실'에 근거하는지 판정 (K9) ──
    #    Before validate는 30자 + "1)"만 봤다 → 사실과 다른 진단도 23/23건 첫 시도에 합격했다.
    @traceable(run_type="llm", name="ollama.judge")
    async def judge(self, query: str, facts: str, draft: str) -> tuple[dict, dict]:
        system = ("당신은 장애 대응 보고서 검수자다. '수집된 사실'과 '답변'을 비교하라. "
                  "답변이 수집된 사실에 없는 시스템 상태나 수치를 단정하거나, 사실과 반대되는 진단을 하면 "
                  "grounded=false다. 사실을 요약·인용하고 runbook 본문의 조치나 일반적인 조치 절차를 덧붙이는 것은 grounded=true다. "
                  "reason에는 한국어 한 문장으로 근거를 쓴다.")
        user = f"## 사용자 요청\n{query}\n\n## 수집된 사실\n{facts}\n\n## 답변\n{draft}"
        content, usage = await self._chat(system, user, schema=JUDGE_SCHEMA)
        try:
            raw = json.loads(content)
            verdict = {"grounded": bool(raw.get("grounded", True)), "reason": str(raw.get("reason", ""))[:200]}
        except (json.JSONDecodeError, AttributeError):
            verdict = {"grounded": True, "reason": "judge 출력 파싱 실패 — 규칙 검사 결과만 사용"}
        return verdict, usage


class OllamaFastLLM(OllamaLLM):
    """분류·계획·단순 대화 전담 (저사양 소형 모델)."""

    @traceable(run_type="llm", name="ollama_fast.route")
    async def route(self, query: str) -> tuple[dict, dict]:   # [P4 AFTER] def → async def
        system = ("당신은 ICT 운영 지원 라우터다. 사용자 요청을 분류하라. "
                  "장애·성능 저하·지연·진단·모니터링·티켓 등 운영 이슈면 route=incident, "
                  "인사·잡담·일반 질문이면 route=chat. "
                  "needs_analysis는 패턴 비교/통계 분석이 꼭 필요할 때만 true.")
        content, usage = await self._chat(system, query, schema=ROUTE_SCHEMA)
        try:
            raw = json.loads(content)
            route = raw.get("route") if raw.get("route") in ("chat", "incident") else None
            result = {"route": route or "chat",
                      "needs_analysis": bool(raw.get("needs_analysis", False))}
        except (json.JSONDecodeError, AttributeError):
            # 소형 모델의 형식 붕괴 대비 — 코드 레벨 fallback (W6 정신)
            incident = bool(re.search(r"장애|진단|다운|지연|급증|incident|티켓", query))
            result = {"route": "incident" if incident else "chat",
                      "needs_analysis": False}
        return result, usage

    @traceable(run_type="llm", name="ollama_fast.plan")
    async def plan(self, query: str, procedure_prompt: str) -> tuple[dict, dict]:   # [P4 AFTER]
        system = ("당신은 ICT 운영 Supervisor의 planning 노드다. 표준 진단 절차에 따라 "
                  "실행 계획(tasks)을 JSON으로 세워라. "
                  "사용자 요청에 등장한 시스템마다 agent=research task를 하나씩 세워라 "
                  f"(알려진 시스템: {', '.join(sorted(KNOWN_SYSTEMS))} — 특정 시스템이 "
                  "언급되지 않았으면 auth-service를 기본으로 조사하라). "
                  "패턴 분석이 꼭 필요하다고 판단되면 agent=analysis task를 추가해도 된다.")
        user = f"## 표준 절차\n{procedure_prompt}\n\n## 사용자 요청\n{query}"
        content, usage = await self._chat(system, user, schema=PLAN_SCHEMA)

        # 소형 모델 출력에 대한 코드 레벨 정규화 — 스키마는 강제돼도 내용은 흔들릴 수
        # 있으므로(대상 시스템 오타, task 누락/중복) 실행 가능한 형태로 보정한다.
        try:
            raw = json.loads(content)
        except json.JSONDecodeError:
            raw = {"needs_analysis": False, "tasks": []}
        tasks, seen, idx = [], set(), 0
        analysis_added = False
        for t in raw.get("tasks", []):
            agent = t.get("agent")
            if agent == "research":
                target = t.get("target", "")
                # ── [P1 BEFORE] 목록에 없는 target을 '질문의 첫 시스템'으로 바꿔 버림 → 같은 시스템이 중복돼 제거되고 나머지는 사라짐 ──
                #    실모델(qwen3:0.6b)은 target에 "get_monitoring_status Tool for web-01" 같은 문장을 넣는다
                #    (확인: outputs/after/evidence/P1_real_model_plan.txt) → 이것이 P1의 실제 원인이었다
                # target = target if target in KNOWN_SYSTEMS else _guess_target(query)
                # ── [P1 AFTER] 모르는 이름은 버린다. 질문에 나온 시스템은 아래 '누락 보충'이 다시 채운다 ──
                if target not in KNOWN_SYSTEMS:
                    continue
                if target in seen:
                    continue
                seen.add(target)
                tasks.append({"id": f"task-{idx}", "agent": "research",
                              "kind": "monitoring", "target": target,
                              "status": "pending"})
                idx += 1
            elif agent == "analysis" and not analysis_added:
                analysis_added = True
                tasks.append({"id": "task-analysis", "agent": "analysis",
                              "kind": "pattern-analysis", "status": "pending"})
        # ── [P1 BEFORE] research가 '0개'일 때만 보충 → 모델이 1개만 내면 나머지 시스템은 조사 누락 ──
        #    (q04·q05·q06 9/9건이 시스템 1개만 조사, recall 0.5)
        # if not seen:   # research가 하나도 없으면 실행 불능 — 쿼리에 등장하는
        #     # KNOWN_SYSTEMS 전부를 복구(하나만 복구하면 나머지가 조사 누락된 채
        #     # write 단계에서 수치가 조작될 수 있음)
        #     recovered = [{"id": f"task-{i}", "agent": "research",
        #                   "kind": "monitoring", "target": target,
        #                   "status": "pending"}
        #                  for i, target in enumerate(_guess_targets(query))]
        #     tasks = recovered + tasks
        # ── [P1 AFTER] 모델이 몇 개를 내든, 질문에 나온 시스템 중 빠진 것을 '항상' 보충한다 ──
        #    모델 출력은 참고만 하고, 조사 범위는 코드가 최종 결정한다 (K6 권위 정규화, K7 gate와 같은 원칙)
        model_targets = [t["target"] for t in tasks if t["agent"] == "research"]
        wanted = mentioned_systems(query)   # 질문에 나온 시스템 (언급 순서)
        # 순서: 질문에 나온 순서 먼저, 그다음 모델이 추가로 고른 시스템 → P2가 '먼저 말한 시스템'을 주 시스템으로 쓴다
        # [N6 BEFORE] ordered = list(dict.fromkeys(wanted + model_targets)) or [DEFAULT_SYSTEM]
        #    → 질문에 시스템이 있어도 모델이 덧붙인 시스템까지 조사. 긴 입력에서 6개 전부 조사(30초)
        # [N6 AFTER] 질문에 시스템이 나오면 그것만 조사한다. 질문에 없을 때만 모델 선택을 쓴다
        ordered = wanted or list(dict.fromkeys(model_targets)) or [DEFAULT_SYSTEM]
        # ── [P2 AFTER] 감시 대상이 아닌 시스템만 나온 질문(q08 billing-service)은 조사하지 않는다 ──
        #    Before는 기본값 auth-service(또는 모델이 고른 엉뚱한 시스템)를 대신 조사해 high-latency runbook을 붙였다
        if not wanted and unmonitored_systems(query):
            ordered = []
        research = [{"id": f"task-{k}", "agent": "research", "kind": "monitoring",
                     "target": target, "status": "pending"}
                    for k, target in enumerate(ordered)]
        tasks = research + [t for t in tasks if t["agent"] != "research"]   # analysis task는 뒤에 그대로
        result = {"needs_analysis": bool(raw.get("needs_analysis", False)),
                  "tasks": tasks}
        return result, usage

    @traceable(run_type="llm", name="ollama_fast.analyze")
    async def analyze(self, collected: list[dict]) -> tuple[str, dict]:   # [P4 AFTER]
        system = ("당신은 ICT 운영 패턴 분석가다. 여러 시스템의 모니터링 결과를 비교해 "
                  "공통 원인이 의심되는 패턴이 있는지 한두 문장으로 짧게 답하라. "
                  "패턴이 없으면 '특이 패턴 없음'이라고만 답하라.")
        mon = [c["data"] for c in collected if c["source"] == "monitoring"]
        facts = "\n".join(
            f"- {d['system_name']}: 상태={d['status']}, CPU {d['cpu_percent']}%, "
            f"알림 {d['alerts']}" for d in mon) or "(모니터링 데이터 없음)"
        return await self._chat(system, facts)

    @traceable(run_type="llm", name="ollama_fast.chat")
    async def chat(self, query: str, history: list[dict], on_token=None) -> tuple[str, dict]:
        system = ("당신은 간결한 한국어 비서다. 한두 문장으로 답하라. "
                  "대화 이력에서 사용자가 밝힌 이름이 있으면 정확히 기억해 답하라.")
        rendered = "\n".join(f"{m['role']}: {m['content']}" for m in history[-10:])
        user = (f"## 지금까지의 대화\n{rendered or '(없음)'}\n\n"
                f"## 사용자의 새 메시지\n{query}")
        return await self._chat_stream(system, user, on_token=on_token)


class OllamaQualityLLM(OllamaLLM):
    """최종 답변 작성 전담 (상대적으로 큰 모델)."""

    @traceable(run_type="llm", name="ollama_quality.write")
    async def write(self, query: str, collected: list[dict], attempt: int,
              feedback: str | None, on_token=None) -> tuple[str, dict]:
        system = ("당신은 ICT 운영 보고 작성자다. 수집된 사실만 사용해 한국어로 "
                  "간결한 대응 보고를 작성하라. 반드시 '1) ... 2) ... 3) ...' 형식의 "
                  "번호 절차로 답하고, 수치는 수집된 값을 그대로 인용하라.")
        facts = []
        for c in collected:
            if c["source"] == "monitoring":
                d = c["data"]
                facts.append(f"- 모니터링 {d['system_name']}: 상태={d['status']}, "
                             f"CPU {d['cpu_percent']}%, 메모리 {d['memory_percent']}%, "
                             f"알림 {len(d['alerts'])}건 {d['alerts']}")
            elif c["source"] == "runbook":
                facts.append(f"- runbook 발췌:\n{c['data'].strip()}")
            elif c["source"] == "analysis":
                facts.append(f"- 패턴 분석: {c['data'].strip()}")
            elif c["source"] == "note":   # [P2 AFTER] runbook을 붙이지 않은 이유 (graph._no_runbook_note)
                facts.append(f"- 확인 결과: {c['data']}")
        user = f"## 사용자 요청\n{query}\n\n## 수집된 사실\n" + "\n".join(facts)
        if feedback:
            user += f"\n\n## 이전 초안에 대한 검증 반려 사유 (반드시 반영)\n{feedback}"
        return await self._chat_stream(system, user, on_token=on_token, timeout=WRITE_TIMEOUT)   # [P9 AFTER] write만 180초

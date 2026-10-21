"""[P1·#14 AFTER] 시스템 이름 추출 공통 모듈.

Before에는 같은 로직이 3개 파일에 복사돼 있었다.
  - agent/graph.py      : _load_known_systems + _extract_system_name (첫 시스템 1개만)
  - agent/ollama_llm.py : _load_known_systems + _guess_target + _guess_targets (알파벳 정렬)
  - agent/openai_llm.py : 위와 똑같은 복사본
한 곳만 고치면 백엔드마다 동작이 달라지는 위험이 있어서(사용자 문제 목록 #14), 여기 한 곳으로 모았다.

핵심 규칙: 시스템은 "질문에 처음 나온 순서"를 지킨다.
  Before의 _guess_targets는 sorted()로 알파벳 정렬 → "web-01 ..., auth-service ..."가
  ['auth-service', 'web-01']로 뒤집혀 '먼저 말한 시스템(주 시스템)' 정보가 사라졌다.
  P2(장애 유형 분류)는 이 순서를 쓴다.
"""
import json
import re
from pathlib import Path

DEFAULT_SYSTEM = "auth-service"   # 시스템 이름이 하나도 없을 때(예: "로그인 응답이 느려요") 조사할 기본값


def _load_known_systems() -> set[str]:
    """data/monitoring.json의 키 = 모니터링하는 시스템 목록. 읽기 실패 시 최소 목록으로 폴백."""
    path = Path(__file__).resolve().parent.parent / "data" / "monitoring.json"
    try:
        return set(json.loads(path.read_text()).keys())
    except (OSError, json.JSONDecodeError):
        return {"auth-service", "web-01"}


KNOWN_SYSTEMS = _load_known_systems()

# "billing-service", "web-02"처럼 시스템 이름처럼 생긴 단어 (모니터링 목록에 없는 시스템을 찾을 때 쓴다)
_SYSTEM_LIKE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*-(?:service|\d+)")


# ── [N2 AFTER] 시스템 별칭 사전 — 시스템 이름 없이 '역할'로 말해도 알아듣는다 ──
#    Before: "결제 서버 응답이 너무 느려요" → 이름이 없어 기본값 auth-service를 조사 (엉뚱한 시스템)
#    긴 별칭부터 검사하고 매칭된 구간은 지운다 → "로그인"(auth)이 "로그"(log)로 다시 잡히지 않는다
SYSTEM_ALIASES = {
    "auth-service": ["로그인", "인증", "login", "auth"],
    "payments-service": ["결제", "payments", "payment"],
    "cache-service": ["캐시", "cache"],
    "gateway-service": ["게이트웨이", "gateway"],
    "log-service": ["로그 서버", "로그서버", "로그 서비스", "로그 수집"],
    "web-01": ["웹 서버", "웹서버"],
}


def mentioned_systems(query: str) -> list[str]:
    """질문에 나온 시스템을 '처음 나온 위치' 순서로 돌려준다(중복 없음).

    예: "web-01 CPU 급증, auth-service 커넥션 풀" → ['web-01', 'auth-service']
    [N3 AFTER] 대소문자 무시: "WEB-01" → web-01 (Before: 인식 못 해 auth-service를 조사)
    [N2 AFTER] 별칭: "결제 서버" → payments-service
    """
    # [N3 BEFORE] hits = [(query.index(s), s) for s in KNOWN_SYSTEMS if s in query]
    text = query.lower()   # [N3 AFTER] 시스템 이름은 모두 소문자다
    hits = {}
    for s in KNOWN_SYSTEMS:   # 1) 정식 이름 (가장 확실) — 매칭 구간은 공백으로 지워 별칭이 다시 잡지 않게 한다
        i = text.find(s)
        if i >= 0:
            hits[s] = i
            text = text.replace(s, " " * len(s))
    pairs = sorted(((alias, s) for s, aliases in SYSTEM_ALIASES.items() for alias in aliases),
                   key=lambda p: -len(p[0]))   # 2) 별칭 — 긴 것부터 ("로그인"을 "로그"보다 먼저)
    for alias, s in pairs:
        i = text.find(alias)
        if s in KNOWN_SYSTEMS and i >= 0:
            hits[s] = min(hits.get(s, i), i)
            text = text.replace(alias, " " * len(alias))
    return [s for s, _ in sorted(hits.items(), key=lambda kv: kv[1])]   # 위치로 정렬 = 언급 순서


def unmonitored_systems(query: str) -> list[str]:
    """시스템 이름처럼 생겼지만 모니터링 목록에 없는 이름 (예: q08 'billing-service').

    P2에서 '감시 대상이 아님'을 답하는 데 쓴다. 모니터링 시스템 이름의 일부는 제외한다.
    """
    found = []
    for m in _SYSTEM_LIKE.finditer(query.lower()):   # [N3 AFTER] 대소문자 무시
        name = m.group(0)
        if name not in KNOWN_SYSTEMS and not any(name in s or s in name for s in KNOWN_SYSTEMS):
            found.append(name)
    return list(dict.fromkeys(found))


def research_targets(query: str) -> list[str]:
    """조사해야 할 시스템 목록. 하나도 안 나오면 기본 시스템 1개.

    단, 감시하지 않는 시스템 이름만 나온 경우(q08)는 빈 목록이다.
    엉뚱한 auth-service를 대신 조사하지 않는다 (P2).
    """
    found = mentioned_systems(query)
    if found:
        return found
    return [] if unmonitored_systems(query) else [DEFAULT_SYSTEM]


# 장애 질문의 증상 단어 (v1 롤백 경로와 v2 route 보정이 같이 쓴다)
# [N4 BEFORE] 증상 단어가 좁아서 "payments 서비스 CPU가 높아요"를 chat으로 잘못 보정 (P9 후속 보정의 부작용)
# INCIDENT_PATTERN = re.compile(r"장애|진단|다운|지연|급증|저하|느려|느리|타임아웃|부족|오류|에러|원인|"
#                               r"치솟|올라가|알림|incident|티켓")
# [N4 AFTER] 지표 이름(cpu·메모리·디스크·응답·커넥션)과 상태 표현(높|안 돼|실패|5xx)을 더했다. 대소문자 무시
INCIDENT_PATTERN = re.compile(r"장애|진단|다운|지연|급증|저하|느려|느리|타임아웃|부족|오류|에러|원인|"
                              r"치솟|올라가|알림|높아|높음|안 ?돼|실패|cpu|메모리|디스크|응답|커넥션|"
                              r"\b5\d\d\b|down|slow|error|incident|티켓", re.IGNORECASE)


def looks_like_incident(query: str) -> bool:
    """증상 단어가 있거나, 시스템 이름(감시 대상이든 아니든)이 나오면 장애 질문으로 본다."""
    return bool(INCIDENT_PATTERN.search(query) or mentioned_systems(query) or unmonitored_systems(query))


def primary_system(query: str) -> str:
    """주 시스템 = 질문에서 가장 먼저 나온 시스템. 없으면 기본 시스템."""
    found = mentioned_systems(query)
    return found[0] if found else DEFAULT_SYSTEM

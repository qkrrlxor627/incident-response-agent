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


def mentioned_systems(query: str) -> list[str]:
    """질문에 나온 KNOWN_SYSTEMS를 '처음 나온 위치' 순서로 돌려준다(중복 없음).

    예: "web-01 CPU 급증, auth-service 커넥션 풀" → ['web-01', 'auth-service']
    """
    hits = [(query.index(s), s) for s in KNOWN_SYSTEMS if s in query]
    return [s for _, s in sorted(hits)]   # 위치(index)로 정렬 = 언급 순서


def unmonitored_systems(query: str) -> list[str]:
    """시스템 이름처럼 생겼지만 모니터링 목록에 없는 이름 (예: q08 'billing-service').

    P2에서 '감시 대상이 아님'을 답하는 데 쓴다. 모니터링 시스템 이름의 일부는 제외한다.
    """
    found = []
    for m in _SYSTEM_LIKE.finditer(query):
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


def primary_system(query: str) -> str:
    """주 시스템 = 질문에서 가장 먼저 나온 시스템. 없으면 기본 시스템."""
    found = mentioned_systems(query)
    return found[0] if found else DEFAULT_SYSTEM

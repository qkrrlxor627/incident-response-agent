"""테스트 공통 설정 — 프로젝트 루트를 import 경로에 넣고, LangSmith 전송을 끈다."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["LANGCHAIN_TRACING_V2"] = "false"   # 테스트가 외부로 trace를 보내지 않도록
os.environ["LANGSMITH_TRACING"] = "false"

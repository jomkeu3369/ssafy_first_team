# LocalHub AI Backend

부산 관광 정보와 커뮤니티 데이터를 활용해 질문에 답하는 AI API입니다. FastAPI는 애플리케이션 진입점과 HTTP 라우팅만 담당하고, 검색·판단·답변 생성 흐름은 `src/agent/` 패키지의 LangGraph 기반 RAG 파이프라인으로 분리할 예정입니다.

> 이 문서는 구현 전 팀 합의를 위한 사전 README입니다. 현재 `main.py`는 `uv init`으로 생성된 초기 상태이며, 아래 구조와 API는 아직 구현되지 않았습니다.

## 담당 범위

현재 작업 범위는 다음으로 제한합니다.

- FastAPI 애플리케이션 진입점인 `main.py`
- AI 기능을 담는 `src/agent/` 패키지
- `POST /api/chat` 라우터 연결
- LangChain·LangGraph 기반 RAG 흐름
- OpenAI 채팅 모델 및 임베딩 연동
- LangSmith 실행 추적

게시판, 댓글, 회원, 관광 데이터 적재, SQLAlchemy 모델 및 일반 CRUD API는 다른 백엔드 담당자가 구현합니다. AI 모듈은 해당 기능의 내부 구현에 직접 의존하지 않고, 합의된 검색 인터페이스 또는 서비스 계층을 통해 데이터를 전달받는 것을 원칙으로 합니다.

## 기술 스택

- Python 3.12+
- FastAPI / Uvicorn
- LangChain
- LangGraph
- LangChain OpenAI
- Chroma
- LangSmith
- uv
- pytest / pytest-asyncio / HTTPX / Ruff

정확한 버전은 `pyproject.toml`과 `uv.lock`을 기준으로 합니다.

## 디렉터리 구조

```text
localhubwin/
├─ main.py                 # FastAPI 앱 생성 및 라우터 등록
├─ src/
│  ├─ core/
│  │  ├─ config.py         # 환경 설정
│  │  ├─ database.py       # SQLAlchemy 엔진 및 세션
│  │  └─ logging.py        # 애플리케이션 로깅
│  ├─ models/
│  │  └─ base.py           # ORM Base 및 공통 Mixin
│  ├─ api/                 # REST API 라우터
│  └─ agent/               # LangGraph 기반 RAG
├─ alembic/
│  ├─ env.py
│  └─ versions/
├─ scripts/
│  ├─ manage_db.bat
│  ├─ manage_db.sh
│  └─ reset_alembic_version.py
├─ tests/
├─ .env.example
├─ alembic.ini
├─ pyproject.toml
├─ uv.lock
└─ README.md
```

SQLAlchemy 모델은 `src/models/`, API 라우터는 `src/api/`, AI 그래프와 검색 로직은 `src/agent/`에 배치합니다.

## 아키텍처 원칙

### FastAPI

`main.py`에는 다음 책임만 둡니다.

- `FastAPI` 인스턴스 생성
- 공통 미들웨어와 예외 처리기 등록
- 헬스 체크 등록 또는 연결
- `src.agent.router`를 `include_router()`로 연결

검색, 프롬프트, 모델 호출과 같은 AI 로직은 `main.py`나 라우터에 직접 작성하지 않습니다.

### RAG

초기 RAG는 키워드·구조화 검색과 벡터 검색을 결합하는 하이브리드 방식으로 구성합니다.

1. 사용자 질문과 요청 언어를 검증합니다.
2. 질문 의도와 검색 조건을 추출합니다.
3. 관광 데이터, 커뮤니티 게시글, QA 문서를 검색합니다.
4. SQL 또는 키워드 검색 결과와 Chroma 벡터 검색 결과를 결합합니다.
5. 검색 결과의 관련성과 근거 충분성을 판단합니다.
6. 필요한 경우 검색어를 보정해 제한적으로 재검색합니다.
7. 검색 근거만 사용해 답변을 생성합니다.
8. 답변과 함께 참조 데이터 목록을 반환합니다.

근거가 부족하면 사실을 추측하지 않고 정보 부족을 안내합니다. 행사명, 날짜, 주소, 전화번호와 같은 사실 정보는 검색 결과에 존재하는 값만 답변에 사용합니다.

### LangGraph

LangGraph는 다음 노드를 연결하는 상태 기반 오케스트레이션 계층으로 사용합니다.

```text
질문 검증
  → 의도·조건 분석
  → 데이터 검색
  → 근거 평가
  → 선택적 재검색
  → 답변 생성
  → 출처·사실 검증
```

초기 버전에서는 불필요한 자율 도구 호출이나 무제한 반복을 허용하지 않습니다. 재검색 횟수와 검색 문서 수를 제한해 응답 시간과 API 비용을 관리합니다.

### LangSmith

LangChain과 LangGraph 실행은 LangSmith로 추적합니다. 추적 데이터에는 비밀번호, API 키, 사용자 식별자 등 민감정보를 포함하지 않습니다. 운영 환경에서는 입력 및 메타데이터 마스킹 정책을 별도로 검토합니다.

## 환경 준비

### 1. 의존성 동기화

```powershell
Set-Location backend
uv sync
```

`uv sync`는 `pyproject.toml`과 `uv.lock`을 기준으로 `.venv` 환경을 구성합니다. `.venv`는 Git에 커밋하지 않습니다.

### 2. 환경변수

구현 시 다음 내용을 포함한 `.env.example`을 추가합니다.

```dotenv
OPENAI_API_KEY=
OPENAI_MODEL=
OPENAI_EMBEDDING_MODEL=
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=localhub-rag-agent
CHROMA_PERSIST_DIRECTORY=./data/chroma
```

실제 키는 로컬 `.env` 또는 배포 환경의 비밀 변수로 주입합니다. `.env`는 저장소에 커밋하지 않습니다.

### 3. 개발 서버 실행

FastAPI 앱 구현 후 다음 명령을 사용합니다.

```powershell
uv run uvicorn main:app --reload
```

기본 개발 주소는 `http://127.0.0.1:8000`이며 Swagger UI는 `http://127.0.0.1:8000/docs`에서 확인합니다.

## 예정 API

### `POST /api/chat`

요청 예시:

```json
{
  "message": "이번 주 부산에서 열리는 축제를 추천해 주세요.",
  "language": "ko",
  "history": [
    {
      "role": "user",
      "content": "부산 여행을 계획하고 있어요."
    }
  ]
}
```

응답 예시:

```json
{
  "answer": "검색된 행사 정보를 바탕으로 작성한 답변",
  "language": "ko",
  "references": [
    {
      "type": "regional_content",
      "id": "2644679",
      "title": "행사명",
      "address": "검색 결과에 저장된 주소",
      "imageUrl": "https://example.com/image.jpg"
    }
  ]
}
```

`references`는 모델이 새로 생성하지 않고 검색 계층이 반환한 원본 식별자와 메타데이터로 구성합니다.

## 백엔드 팀 연동 계약

AI 담당 영역과 일반 백엔드 영역 사이에는 다음 인터페이스가 필요합니다.

- 관광 콘텐츠 검색: 키워드, 지역, 콘텐츠 유형, 날짜 조건, 최대 결과 수
- 게시글 검색: 키워드, 태그, 언어, 최대 결과 수
- QA 문서 조회 또는 인덱싱 대상 전달
- 검색 결과 공통 필드: 원본 유형, 원본 ID, 제목, 본문 요약, 주소, 날짜, 이미지 URL

데이터베이스 세션이나 ORM 모델을 `src/agent/` 전역 상태로 직접 보관하지 않습니다. FastAPI 의존성 주입 또는 별도 검색 서비스 인터페이스를 통해 요청 단위로 전달합니다.

## 개발 명령어

구현이 추가된 이후 사용할 기본 명령입니다.

```powershell
# 서버
uv run uvicorn main:app --reload

# 테스트
uv run pytest

# 린트
uv run ruff check .

# 포맷
uv run ruff format .
```

### Alembic 관리 도구

Windows:

```powershell
.\scripts\manage_db.bat
```

macOS 또는 Linux:

```bash
bash scripts/manage_db.sh
```

관리 도구에서 migration 생성, `upgrade head`, 현재 버전과 이력 확인, `stamp head`를 실행할 수 있습니다. 모든 명령은 프로젝트 루트의 `alembic.ini`와 `src/core/config.py`가 제공하는 동일한 `DATABASE_URL`을 사용합니다.

Alembic 버전 초기화는 실제 테이블을 변경하지 않고 버전 기록만 `base` 상태로 되돌립니다. 충돌 복구가 필요한 경우에만 사용하며, 실행 시 `RESET`을 직접 입력해야 합니다.

## 테스트 계획

- `/api/chat` 요청·응답 스키마 검증
- 한국어 및 영어 요청 처리
- 관광·게시글·QA 검색 결과 결합
- 검색 결과가 없을 때의 안전한 응답
- 검색되지 않은 날짜·주소·전화번호 생성 방지
- `references`와 실제 검색 결과의 일치 여부
- OpenAI 장애 시 제한된 대체 응답
- LangGraph 재검색 횟수 제한
- OpenAI 및 LangSmith 네트워크 호출 Mock 처리

## 보안 및 운영 주의사항

- API 키와 `.env`를 커밋하지 않습니다.
- 프롬프트나 LangSmith trace에 비밀번호 및 민감정보를 기록하지 않습니다.
- 사용자 입력, 대화 기록, 검색 결과 수에 상한을 둡니다.
- 모델이 반환한 출처를 신뢰하지 않고 서버가 원본 검색 결과를 기준으로 조립합니다.
- Chroma 영속 디렉터리와 운영 배포 환경의 디스크 유지 정책을 확인합니다.
- CORS, 요청 제한, 인증 정책은 전체 백엔드 담당자와 합의해 공통 설정을 사용합니다.

## 현재 상태 및 다음 작업

- [x] uv 프로젝트 초기화
- [x] FastAPI·LangChain·LangGraph·OpenAI·Chroma·LangSmith 의존성 등록
- [ ] FastAPI `app`과 `include_router()` 구성
- [x] `src/agent/` 패키지 생성
- [ ] `/api/chat` 요청·응답 스키마 정의
- [ ] LangGraph 상태와 노드 구현
- [ ] 백엔드 검색 서비스 연동 계약 확정
- [ ] QA 및 관광 데이터 인덱싱 방식 확정
- [ ] LangSmith 추적 및 민감정보 처리 설정
- [ ] 테스트 작성 및 실행 검증

## 참고 문서

- [uv 프로젝트 의존성 관리](https://docs.astral.sh/uv/concepts/projects/dependencies/)
- [FastAPI 공식 문서](https://fastapi.tiangolo.com/)
- [LangGraph 설치](https://docs.langchain.com/oss/python/langgraph/install)
- [LangChain OpenAI 연동](https://docs.langchain.com/oss/python/integrations/llms/openai)
- [Chroma 연동](https://docs.langchain.com/oss/python/integrations/vectorstores/chroma)
- [LangSmith 추적 시작하기](https://docs.langchain.com/langsmith/observability-quickstart)

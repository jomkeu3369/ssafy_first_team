# LocalHub AI Backend

부산 관광·커뮤니티 정보를 답변하는 FastAPI 백엔드입니다. 일반 백엔드 기능은 다른 팀원이 담당하고, 이 저장소의 AI 영역은 LangChain `create_agent`와 두 개의 로컬 MCP 서버로 구성합니다.

## 구조

```text
localhubwin/
├─ main.py                         # FastAPI 앱, lifespan, CORS, 라우터 등록
├─ src/
│  ├─ agent/
│  │  ├─ router.py                 # POST /api/v1/chat
│  │  ├─ schemas.py                # 요청·응답 모델
│  │  ├─ service.py                # create_agent와 MCP 세션 수명주기
│  │  └─ prompts.py                # 도구 선택·근거 정책
│  ├─ mcp_servers/
│  │  ├─ local_search.py           # FAISS 검색 + 제한된 SQLite 검색
│  │  └─ web_search.py             # Tavily Search API 웹 검색
│  ├─ core/                         # 설정, DB, 로깅
│  └─ models/                       # SQLAlchemy Base 및 도메인 모델
├─ scripts/
│  ├─ build_faiss_index.py
│  └─ manage_db.*
├─ alembic/
├─ data/
└─ tests/
```

에이전트는 SQL 정확 조회가 필요하면 `search_sqlite`, 의미 기반 QA 검색은 `search_faiss`, 최신 외부 정보가 필요하면 `search_web`을 선택합니다. `create_agent`는 내부적으로 LangGraph 런타임을 사용하므로 별도의 그래프를 직접 관리하지 않습니다.

## 설치와 실행

Python 3.12 이상과 uv가 필요합니다.

```powershell
uv sync
Copy-Item .env.example .env
uv run uvicorn main:app --reload
```

필수 AI 설정은 다음과 같습니다.

```dotenv
OPENAI_API_KEY=...
OPENAI_MODEL=사용할_채팅_모델
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
TAVILY_API_KEY=tvly-...
FAISS_INDEX_DIR=./data/faiss

LANGSMITH_TRACING=true
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=localhub-rag-agent
```

웹 검색은 Tavily Search API를 사용하며 `TAVILY_API_KEY`가 필요합니다. OpenAI 설정은 채팅 에이전트와 로컬 FAISS 임베딩에만 사용합니다. OpenAI 설정이 없더라도 서버와 `/health`는 시작되며 채팅 API만 503을 반환합니다.

## FAISS 인덱스 만들기

`data/faiss_documents.jsonl`을 UTF-8 JSON Lines 형식으로 준비합니다. 각 줄은 `content`가 필수이며 나머지는 출처 메타데이터입니다.

```json
{"content":"광안리 해수욕장 소개와 이용 정보", "source_type":"regional_contents", "source_id":"42", "title":"광안리 해수욕장", "address":"부산광역시 수영구", "image_url":"https://example.com/image.jpg"}
```

```powershell
uv run python scripts/build_faiss_index.py
```

생성되는 `data/faiss/index.faiss`와 `documents.json`은 실행 산출물이므로 Git에서 제외합니다. LangChain의 폐기 예정 community 래퍼 대신 `faiss-cpu` API를 직접 사용하고, 임베딩과 에이전트 계층에는 LangChain을 사용합니다.

## SQLite 검색 계약

보안을 위해 MCP 도구는 임의 SQL을 받지 않습니다. 아래 허용 테이블이 실제로 존재할 때만 조회하며, 존재하는 열 이름을 확인한 뒤 바인딩된 검색어와 지역 조건을 사용합니다.

- `regional_contents`
- `posts`
- `qa_documents`

지원 열 후보는 `id/content_id`, `title/name/question`, `content/description/answer`, `address`, `image_url`, `region/district`입니다. 다른 팀원이 확정한 스키마가 이 이름과 다르면 `src/mcp_servers/local_search.py`의 `SEARCHABLE_TABLES` 매핑만 수정하면 됩니다.

## API

`POST /api/v1/chat` (`X-Client-Id` UUID 헤더 필수)

```json
{
  "message": "이번 주 부산에서 열리는 행사를 알려 주세요.",
  "language": "ko",
  "history": []
}
```

```json
{
  "answer": "검색 근거를 사용한 답변",
  "language": "ko",
  "references": [
    {
      "type": "web",
      "id": null,
      "title": "출처 제목",
      "address": null,
      "imageUrl": null,
      "url": "https://example.com/source"
    }
  ]
}
```

도구가 실제로 반환한 로컬 레코드와 웹 URL만 `references`에 포함합니다.

## 부산 JSON 데이터 업로드

Render 환경 변수에 충분히 긴 임의 문자열을 등록합니다.

```dotenv
DATA_IMPORT_API_KEY=replace-with-a-long-random-secret
```

Swagger의 `POST /api/v1/admin/data-import/boards`에서 `부산_*.json` 파일들을 한 번에 선택하고 `X-Import-Key` 헤더에 같은 값을 전달합니다. 가져오기 API는 각 항목의 이미지 주소, 관광 콘텐츠 ID, 주소, 축제 기간과 장소를 `Board`에 저장합니다. 이후 관광지·축제 GET API는 JSON 파일이 아니라 이 DB 데이터를 직접 조회합니다. 동일한 이름과 카테고리는 다시 삽입하지 않으며, 기존 행의 관광 필드까지 보강하려면 `updateExisting=true`를 사용합니다.

마이그레이션을 수동으로 진행하는 환경에서는 배포 전에 `Board` 테이블에 nullable `image`, `contentId`, `address`, `eventStartDate`, `eventEndDate`, `eventPlace` 컬럼을 추가해야 합니다. SQLite는 서버 시작 시 누락된 컬럼을 호환성 처리로 자동 추가합니다.

```sql
ALTER TABLE "Board" ADD COLUMN image VARCHAR(2000) NULL;
```

```powershell
curl.exe -X POST "https://YOUR-SERVICE.onrender.com/api/v1/admin/data-import/boards?updateExisting=true" -H "X-Import-Key: YOUR_SECRET" -F "files=@C:/Users/SSAFY/Desktop/data2/부산/부산_관광지.json" -F "files=@C:/Users/SSAFY/Desktop/data2/부산/부산_축제공연행사.json"
```

## 태그와 통합 검색

`POST /api/v1/tags`에 `{"name":"야경"}`을 전달하면 `tagId` 10 이상의 `CUSTOM` 태그를 생성합니다. 게시글에는 `GET /api/v1/tags` 또는 태그 생성 응답으로 받은 정확한 `tagId`, `name`, `category`를 전달해야 합니다.

`GET /api/v1/search?q=해운대&page=1&size=20`은 보드 이름·설명·카테고리와 게시글 제목·본문·태그명을 검색합니다. 결과의 `resultType`은 `BOARD` 또는 `POST`입니다.

보드·관광지·축제·댓글·태그 목록 GET API도 `page`와 `size`를 받으며 기본값은 `page=1`, `size=20`, 최대 크기는 `100`입니다. 응답은 `{"items":[],"total":0,"page":1,"size":20}` 형식입니다. 댓글은 부모 댓글을 페이지 단위로 조회하고 각 부모의 대댓글을 `children`에 함께 반환합니다.

챗봇은 로컬 SQL 및 문서 검색 결과가 없거나 질문의 일부만 답할 수 있을 정도로 부족하면 별도 확인 없이 Tavily 웹 검색을 자동 실행합니다.

보드·관광지·축제·태그 응답은 `nameEn`을 포함하며 유형별로 `descriptionEn`, `summaryEn`, `categoryEn`, `addressEn`, `placeEn`, `periodEn`을 제공합니다. 영문 원본이 없는 고유명사와 주소는 한국어 원문을 폴백으로 사용합니다. 관광지와 축제 응답의 `boardId`는 가져오기 API가 생성하거나 갱신한 같은 Board 행을 가리킵니다.

`GET /api/v1/posts/popular?page=1&size=10`은 모든 게시판의 게시글을 좋아요·댓글·조회 수 순으로 통합 조회합니다.

## ID 발급 규칙

보드·게시글·댓글·미디어·사용자 정의 태그 ID는 작은 순차 번호로 발급합니다. 명세에 고정된 전체 자유게시판 `boardId=0`과 기본 태그 `tagId=1~9`는 유지합니다. 이전 버전에서 생성된 JavaScript 안전 정수 범위를 초과하는 난수 ID는 서버 시작 시 한 번 순차 번호로 변환하며 관련 외래키도 함께 변경합니다.

## 개발 명령

```powershell
uv run pytest -q
uv run ruff check .
uv run alembic current
```

Windows DB 관리 메뉴는 `scripts/manage_db.bat`, macOS/Linux는 `scripts/manage_db.sh`를 사용합니다.

## 참고 문서

- [LangChain Agents](https://docs.langchain.com/oss/python/langchain/agents)
- [LangChain MCP](https://docs.langchain.com/oss/python/langchain/mcp)
- [OpenAI Models and tools](https://developers.openai.com/api/docs/models)

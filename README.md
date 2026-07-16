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

## FAISS 인덱스

FAISS 문서는 SQLite의 `Board`와 `post` 데이터로 자동 구성됩니다. 검색할 때 인덱스가 없거나 DB 지문이 기존 manifest와 다르면 OpenAI 임베딩을 사용해 자동 재구축합니다. 최초에는 전체 문서를 임베딩하고 이후에는 기존 벡터를 재사용해 추가·수정된 문서만 다시 임베딩합니다. 첫 검색은 오래 걸릴 수 있지만 이후 검색은 메모리와 `data/faiss` 인덱스를 재사용합니다.

배포 직후 첫 사용자 요청 전에 미리 생성하려면 보호된 관리자 API를 호출합니다.

```powershell
curl.exe -X POST "https://YOUR-SERVICE.onrender.com/api/v1/admin/data-import/faiss" -H "X-Import-Key: YOUR_SECRET"
```

`GET /api/v1/admin/data-import/faiss`에 같은 `X-Import-Key`를 보내면 현재 DB 문서 수, 인덱스 문서 수, `ready`, `stale`, 생성 시각을 확인할 수 있습니다.

로컬에서는 다음 명령을 사용할 수 있습니다. `--force`를 추가하면 DB 지문이 같아도 다시 생성합니다.

```powershell
uv run python scripts/build_faiss_index.py
```

생성되는 `data/faiss/index.faiss`, `documents.json`, `manifest.json`은 실행 산출물이므로 Git에서 제외합니다. Render의 기본 파일 시스템에서는 재배포 시 사라질 수 있지만 다음 FAISS 검색에서 자동 복구됩니다. `search_sqlite`는 정확 키워드 조회에, `search_faiss`는 의미 기반 검색에 사용되며 저장 데이터 질문에는 두 검색을 모두 실행합니다.

## SQLite 검색 계약

보안을 위해 MCP 도구는 임의 SQL을 받지 않습니다. 아래 허용 테이블이 실제로 존재할 때만 조회하며, 존재하는 열 이름을 확인한 뒤 바인딩된 검색어를 사용합니다.

- `Board`
- `post`

보드 이름·설명·주소와 게시글 제목·본문을 정확 키워드로 검색합니다. FAISS 인덱스에는 여기에 보드 카테고리, 축제 기간·장소, 게시글 태그까지 포함해 의미 기반 검색의 재현율을 보강합니다.

## API

`POST /api/v1/chat` (`X-Client-Id`, `X-Session-Id` UUID 헤더 필수)

`X-Client-Id`는 브라우저를 식별하는 안정적인 익명 UUID로 유지하고, `X-Session-Id`는 새 채팅을 시작할 때마다 새 UUID를 생성합니다. 같은 두 값을 보내는 요청만 이전 대화 메모리를 이어가며, 어느 하나라도 다르면 별도 대화로 격리됩니다. LangSmith에는 두 값을 조합해 해시한 `thread_id`만 기록합니다.

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

## 게시글 자동 번역

게시글 생성과 수정 API는 `OPENAI_API_KEY`와 `OPENAI_MODEL`로 GPT 구조화 번역을 실행합니다. 한글 원문은 영어로, 영어 원문은 한글로 번역하며 기존 `title`, `content`에는 입력 원문을 유지합니다. 모든 게시글 GET 응답은 다음 필드를 함께 제공합니다.

```json
{
  "title": "해운대 야경",
  "titleKr": "해운대 야경",
  "titleEn": "Haeundae Night View",
  "content": "달맞이길 전망대 후기",
  "contentKr": "달맞이길 전망대 후기",
  "contentEn": "A review of the Dalmaji-gil observatory"
}
```

번역 설정이 없으면 생성·수정은 `503`, GPT 호출이나 구조화 결과가 실패하면 `502`를 반환하며 게시글은 저장하지 않습니다. 기존 게시글의 번역 컬럼이 비어 있으면 GET 응답은 원문을 양쪽 언어 필드에 폴백합니다. SQLite는 서버 시작 시 컬럼을 자동 추가하며, 수동 마이그레이션 환경에서는 다음 컬럼이 필요합니다.

```sql
ALTER TABLE post ADD COLUMN "titleKr" VARCHAR(500) NULL;
ALTER TABLE post ADD COLUMN "titleEn" VARCHAR(500) NULL;
ALTER TABLE post ADD COLUMN "contentKr" TEXT NULL;
ALTER TABLE post ADD COLUMN "contentEn" TEXT NULL;
ALTER TABLE post ADD COLUMN "createdAt" DATETIME NULL;
ALTER TABLE post ADD COLUMN "updatedAt" DATETIME NULL;
```

## WebSocket 실시간 알림

프론트엔드는 송신 없이 다음 주소로 연결해 이벤트를 수신합니다. 브라우저별 익명 UUID를 `clientId`로 전달하면 여러 탭을 열어도 한 명으로 집계합니다.

```text
ws://localhost:8000/api/v1/ws?clientId=UUID
wss://YOUR-RENDER-SERVICE.onrender.com/api/v1/ws?clientId=UUID
```

연결·해제 시에는 고유 클라이언트 수를 알립니다.

```json
{"event":"presence.updated","data":{"connectedCount":14}}
```

게시글 생성 트랜잭션이 커밋되면 모든 연결에 새 글 알림을 전송합니다. `createdAt`은 KST 오프셋이 포함된 ISO 8601 값입니다.

```json
{"event":"post.created","data":{"postId":101,"boardId":1,"title":"해운대 야경을 보기 좋은 장소","createdAt":"2026-07-16T15:30:00+09:00"}}
```

## 부산 JSON 데이터 업로드

Render 환경 변수에 충분히 긴 임의 문자열을 등록합니다.

```dotenv
DATA_IMPORT_API_KEY=replace-with-a-long-random-secret
```

Swagger의 `POST /api/v1/admin/data-import/boards`에서 `부산_*.json` 파일들을 한 번에 선택하고 `X-Import-Key` 헤더에 같은 값을 전달합니다. 가져오기 API는 각 항목의 이미지 주소, 관광 콘텐츠 ID, 주소, 축제 기간과 장소를 `Board`에 저장합니다. 원본 JSON에 `titleEn`, `descriptionEn`, `addr1En`, `addr2En`, `eventplaceEn`이 있으면 한글이 섞이지 않은 값만 영문 컬럼에 저장합니다. 이후 관광지·축제 GET API는 JSON 파일이 아니라 이 DB 데이터를 직접 조회합니다. 동일한 이름과 카테고리는 다시 삽입하지 않으며, 기존 행의 관광 필드까지 보강하려면 `updateExisting=true`를 사용합니다.

마이그레이션을 수동으로 진행하는 환경에서는 배포 전에 `Board` 테이블에 nullable `nameEn`, `descriptionEn`, `image`, `contentId`, `address`, `addressEn`, `eventStartDate`, `eventEndDate`, `eventPlace`, `eventPlaceEn` 컬럼을 추가해야 합니다. 서버는 시작 시 누락된 컬럼을 호환성 처리로도 추가합니다.

```sql
ALTER TABLE "Board" ADD COLUMN image VARCHAR(2000) NULL;
```

```powershell
curl.exe -X POST "https://YOUR-SERVICE.onrender.com/api/v1/admin/data-import/boards?updateExisting=true" -H "X-Import-Key: YOUR_SECRET" -F "files=@C:/Users/SSAFY/Desktop/data2/부산/부산_관광지.json" -F "files=@C:/Users/SSAFY/Desktop/data2/부산/부산_축제공연행사.json"
```

원본에 영문 데이터가 없는 기존 행은 아래 API가 GPT로 최대 100개씩 번역해 `nameEn`, `descriptionEn`, `addressEn`, `eventPlaceEn`에 저장합니다. 응답의 `remainingCount`가 0이 될 때까지 반복 호출할 수 있으며 호출량만큼 OpenAI API 비용이 발생합니다. 번역 전에는 한국어를 영문 필드에 복사하지 않고 빈 값으로 응답합니다.

```powershell
curl.exe -X POST "https://YOUR-SERVICE.onrender.com/api/v1/admin/data-import/board-translations?limit=100" -H "X-Import-Key: YOUR_SECRET"
```

## 태그와 통합 검색

`POST /api/v1/tags`에 `{"name":"야경"}`을 전달하면 `tagId` 10 이상의 `CUSTOM` 태그를 생성합니다. 게시글에는 `GET /api/v1/tags` 또는 태그 생성 응답으로 받은 정확한 `tagId`, `name`, `category`를 전달해야 합니다.

`GET /api/v1/search?q=해운대&page=1&size=20`은 보드 이름·설명·카테고리와 게시글 제목·본문·태그명을 검색합니다. 결과의 `resultType`은 `BOARD` 또는 `POST`입니다.

보드·관광지·축제·댓글·태그 목록 GET API도 `page`와 `size`를 받으며 기본값은 `page=1`, `size=20`, 최대 크기는 `100`입니다. 응답은 `{"items":[],"total":0,"page":1,"size":20}` 형식입니다. 댓글은 부모 댓글을 페이지 단위로 조회하고 각 부모의 대댓글을 `children`에 함께 반환합니다.

챗봇은 로컬 SQL 및 문서 검색 결과가 없거나 질문의 일부만 답할 수 있을 정도로 부족하면 별도 확인 없이 Tavily 웹 검색을 자동 실행합니다.

Board는 DB와 API 응답에서 `nameKr/nameEn`, `categoryKr/categoryEn`, `descriptionKr/descriptionEn`을 명시적으로 분리합니다. 기존 `name/category/description`은 이전 프론트와의 호환을 위해 기존 값을 유지합니다. 새 게시판 생성은 GPT 번역을 완료한 뒤 두 언어를 같은 트랜잭션에 저장합니다. 대량 관광 데이터는 관리자 번역 API로 영문 값을 채우며, 영문 필드에 한글이 포함된 기존 값은 마이그레이션에서 제거되어 다시 번역 대상이 됩니다. 관광지와 축제 응답의 `boardId`는 가져오기 API가 생성하거나 갱신한 같은 Board 행을 가리킵니다.

댓글과 대댓글도 `contentKr/contentEn`을 함께 저장하고 응답합니다. 한국어 또는 영어 댓글의 생성·수정은 GPT 번역이 성공한 경우에만 커밋됩니다. 기존 댓글은 `POST /api/v1/admin/data-import/comment-translations?limit=20`을 `remainingCount`가 0이 될 때까지 호출해 번역할 수 있습니다.

`GET /api/v1/posts/popular?page=1&size=10`은 모든 게시판의 게시글을 좋아요·댓글·조회 수 순으로 통합 조회합니다.

## Render DB 영속 배포

Render의 기본 파일시스템은 재배포 시 초기화되므로 SQLite를 유지하려면 서비스의 **Disks** 메뉴에서 영속 디스크를 `/var/data`에 연결하고 다음 환경 변수를 설정합니다.

```dotenv
DATABASE_URL=sqlite+aiosqlite:////var/data/localhub.db
```

Start Command는 다음과 같이 설정합니다.

```bash
bash scripts/start.sh
```

시작 스크립트는 영속 디스크에 DB가 처음 생성되는 경우에만 저장소의 `data/localhub.db`를 복사합니다. 이후 배포에서는 기존 파일을 덮어쓰지 않고 `alembic upgrade head`만 실행합니다. 버전 정보가 없던 기존 DB는 현재 데이터를 유지한 채 안전 기준 리비전을 기록한 후 증분 마이그레이션을 적용합니다. 애플리케이션 시작 과정에도 같은 Alembic 검사가 있어 Start Command가 기존 명령으로 남아 있어도 스키마 마이그레이션은 실행됩니다.

Render의 Pre-Deploy Command는 연결된 영속 디스크에 접근할 수 없으므로 SQLite 마이그레이션 용도로 사용하지 않습니다.

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

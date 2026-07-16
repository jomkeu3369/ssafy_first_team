# ngrok 원격 Vector MCP 실행

이 구성은 Render에 SQL 검색과 Tavily 검색을 남기고, FAISS 및 OpenAI 임베딩 작업만 로컬 PC에서 실행합니다. Render DB의 검색 문서는 보호된 API를 통해 로컬 MCP로 동기화되며 기본 캐시 시간은 5분입니다. 동기화 API가 일시적으로 실패하면 메모리 캐시 또는 디스크에 저장된 기존 인덱스 문서를 사용합니다.

## 1. 공통 비밀키 생성

서로 다른 긴 무작위 문자열 두 개를 생성합니다.

- `VECTOR_MCP_API_KEY`: Render가 ngrok의 MCP 서버에 접속할 때 사용
- `VECTOR_SOURCE_API_KEY`: 로컬 MCP가 Render 검색 문서를 동기화할 때 사용

키를 URL이나 Git 저장소에 넣지 말고 Render 환경변수와 로컬 `.env`에만 저장합니다.

## 2. Render 환경변수

```dotenv
VECTOR_MCP_URL=https://YOUR-NGROK-DOMAIN.ngrok.app/mcp
VECTOR_MCP_API_KEY=YOUR_VECTOR_MCP_SECRET
VECTOR_MCP_TIMEOUT_SECONDS=5
VECTOR_SOURCE_API_KEY=YOUR_VECTOR_SOURCE_SECRET
```

`VECTOR_MCP_URL`이 비어 있으면 기존처럼 Render 내부의 로컬 Vector MCP를 사용합니다. 원격 Vector 도구는 실제 검색 시점에 MCP 세션을 생성하므로 Render보다 로컬 MCP를 늦게 실행해도 재배포할 필요가 없습니다. ngrok 연결이 실패하면 빈 Vector 검색 결과를 반환하고 SQL과 Tavily 도구는 계속 사용할 수 있습니다.

## 3. 로컬 환경변수

로컬 프로젝트의 `.env`에 다음 값을 추가합니다.

```dotenv
OPENAI_API_KEY=YOUR_OPENAI_KEY
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
FAISS_INDEX_DIR=./data/faiss

VECTOR_MCP_API_KEY=YOUR_VECTOR_MCP_SECRET
VECTOR_MCP_HOST=127.0.0.1
VECTOR_MCP_PORT=8001
VECTOR_MCP_PUBLIC_HOST=YOUR-NGROK-DOMAIN.ngrok.app

VECTOR_SOURCE_URL=https://ssafy-first-team.onrender.com/api/v1/admin/data-import/search-documents
VECTOR_SOURCE_API_KEY=YOUR_VECTOR_SOURCE_SECRET
VECTOR_SOURCE_TIMEOUT_SECONDS=30
VECTOR_SOURCE_CACHE_SECONDS=300
```

`VECTOR_MCP_PUBLIC_HOST`에는 `https://`와 경로를 제외한 호스트 이름만 입력합니다. 이 값은 MCP의 DNS rebinding 방어에서 ngrok Host 헤더를 허용하기 위해 필요합니다.

## 4. 로컬 MCP와 ngrok 실행

첫 번째 PowerShell 터미널에서 다음 명령을 실행합니다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_vector_mcp.ps1
```

두 번째 터미널에서 ngrok을 실행합니다.

```powershell
ngrok http 8001 --url https://YOUR-NGROK-DOMAIN.ngrok.app
```

상태 확인:

```powershell
curl.exe https://YOUR-NGROK-DOMAIN.ngrok.app/health
```

정상 응답은 `{"status":"healthy","service":"vector-mcp"}`입니다. `/mcp`는 `Authorization: Bearer ...`가 없으면 401을 반환합니다.

## 5. Render 재배포

환경변수를 저장하고 Render를 재배포합니다. 시작 로그에 `AI agent and MCP sessions are ready`가 출력되는지 확인한 뒤 관광지 질문으로 채팅 API를 테스트합니다. 로컬 MCP 터미널에는 Render가 보낸 `/mcp` 요청이 나타나야 합니다.

로컬 PC가 절전되거나 ngrok이 종료되면 Vector 검색은 사용할 수 없습니다. 운영 중에는 절전 기능을 끄고 ngrok 프로세스와 MCP 프로세스를 함께 유지해야 합니다.

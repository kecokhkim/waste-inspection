# 폐기물처리시설 검사업무 AI 지원 플랫폼

시설별 검사 법령·기준 검색, 검사시기 산정, 사전 모의점검을 지원하는 업무도구입니다.

## 배포 방법 (GitHub Pages)

1. GitHub에서 새 저장소를 만듭니다. 예: `waste-facility-inspection`
   - **Public** 으로 만들어야 GitHub Pages가 무료로 동작합니다.
2. 이 폴더의 파일을 저장소 최상위에 그대로 올립니다.
   - 저장소 화면의 `Add file` → `Upload files` 로 전부 끌어다 놓고 `Commit changes`
3. 저장소 `Settings` → 좌측 `Pages` 로 이동합니다.
4. `Source` 를 **Deploy from a branch** 로 두고, Branch 를 `main` / `/ (root)` 로 지정한 뒤 `Save`
5. 1~2분 뒤 아래 주소로 접속됩니다.
   `https://<사용자명>.github.io/<저장소명>/`

## 수정 후 반영

`index.html` 을 고쳐 다시 올리면 됩니다. 다만 오프라인 캐시가 남아 옛 화면이 보일 수 있으므로,
내용을 고칠 때는 `sw.js` 첫 줄의 `VERSION` 값도 함께 바꾸십시오. 그래야 이용자에게 새 판이 내려갑니다.

```js
const VERSION = "v261002-152126";   // ← 이 값을 새 날짜로 변경
```

`index.html` 상단 바에 표시되는 버전 문자열도 같이 맞춰두면 이용자가 어느 판을 보고 있는지 확인할 수 있습니다.

## 파일 구성

| 파일 | 역할 |
|---|---|
| `index.html` | 본체. 이 파일 하나로 모든 기능이 동작합니다 |
| `manifest.webmanifest` | 홈 화면 추가(앱처럼 실행)용 설정 |
| `sw.js` | 오프라인 지원. 한 번 접속하면 이후 인터넷 없이도 열립니다 |
| `icon-192.png` / `icon-512.png` / `apple-touch-icon.png` | 앱 아이콘 |

## 법령 실시간 연동 · 법령 AI 챗봇 (시범)

- **현행 원문 조회**: 조문마다 국가법령정보 OPEN API로 최신 조문을 불러옵니다. 인증키(OC)는 등록 도메인(`kecokhkim.github.io`)에서만 통하므로 `index.html`의 `LAW_OC`에 둡니다.
- **법령 AI 챗봇 탭**: 첫 접속 시 브라우저가 법령 API에서 폐기물관리법·시행령·시행규칙과 「폐기물처리시설의 검사방법에 관한 규정」 전체 조문·별표를 받아 DB를 구성하고(하루 보관), 질문과 관련된 조문을 찾아 AI에 함께 보냅니다. 답변의 [번호]를 누르면 근거 조문과 현행 원문 조회가 열립니다.
- **AI 키는 저장소에 넣지 않습니다.** 공개 사이트에서는 이용자가 화면의 “AI 키 설정”에 OpenRouter 키를 입력합니다(그 브라우저에만 저장). 중계 서버(Cloudflare Worker 등)를 두면 `WORKER_URL`에 주소를 넣어 키 입력 없이 쓸 수 있습니다.
- 사용 모델은 `index.html`의 `CHAT_MODELS` 순서대로 시도합니다(무료 모델, 키당 하루 50회).

### 로컬 테스트

```
copy .env.example .env      # 값 채우기 (.env 는 git에 올라가지 않음)
python tools/dev_server.py  # http://localhost:8000 — .env 의 키로 AI·법령 API 중계
```

로컬에서 법령 API를 쓰려면 이 PC의 공인 IP를 open.law.go.kr 마이페이지에 등록해야 합니다. `python tools/build_law_db.py`로 `data/laws.json`을 미리 만들어 두면 API를 못 쓸 때 대신 사용합니다.

## 배포 전 확인사항

- **GitHub Pages는 누구나 볼 수 있는 공개 웹입니다.** 대외주의 자료나 내부 지침은 올리지 마십시오.
- 검색엔진 노출은 `noindex` 로 막아두었으나, 주소를 아는 사람은 접근할 수 있습니다.
- 기관 공식 채널로 운영하시려면 개인 계정이 아닌 기관 저장소 사용 여부를 먼저 협의하십시오.
- 이용자가 입력한 날짜·점검값은 각자 기기에만 저장되며 서버로 전송되지 않습니다.

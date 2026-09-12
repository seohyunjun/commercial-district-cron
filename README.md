# 공공데이터 변경 감지

공공데이터포털(data.go.kr) 데이터셋이 갱신되면 Slack으로 알려주는 모니터링 도구입니다.

## 기능

- 오픈API 문서(OpenAPI/Swagger) 변경 감지 — 엔드포인트 추가·삭제, 스키마 변경, 버전 변경
- 파일데이터 갱신 감지 — 새 파일로 교체되었는지, 기준일이 언제로 바뀌었는지
- Slack 웹훅을 통한 알림
- GitHub Actions를 통한 자동 실행 (매일 오전 9시 KST)

## 모니터링 대상

| 대상 | 방식 | 스크립트 |
|---|---|---|
| [국민연금공단_국민연금 가입 사업장 내역](https://www.data.go.kr/data/15083277/openapi.do) | OpenAPI 문서 비교 | `check_api_changes.py` |
| [소상공인시장진흥공단_상가(상권)정보](https://www.data.go.kr/data/15083033/fileData.do) | 상세 페이지 메타데이터 비교 | `check_filedata_changes.py` |

### 두 스크립트가 나뉜 이유

오픈API는 `infuser.odcloud.kr` 에서 OpenAPI 문서를 주므로 그 문서를 통째로 비교하면 됩니다.

파일데이터에는 그런 문서가 없습니다. 대신 포털 상세 페이지가 서버에서 렌더되므로 거기
박혀 있는 값을 읽습니다.

| 보는 값 | 예 | 의미 |
|---|---|---|
| `publicDataDetailPk` | `uddi:b3094bc9-…` | 파일을 갈아끼우면 새로 발급된다. 가장 확실한 신호 |
| `updtDt` | `2026-08-05 21:54:06` | 수정 일시 |
| 파일데이터명 | `…_20260630` | 끝의 기준일이 분기마다 바뀐다 |
| 차기 등록 예정일 | `2026-10-31` | 다음 갱신 예정 |

다운로드 수는 일부러 보지 않습니다. 시시각각 변해서 매일 "변경됨"이 뜹니다.

페이지 구조가 바뀌어 위 값을 읽지 못하면 `:warning:` 알림을 **한 번** 보냅니다. 조용히
"변경 없음"으로 넘어가면 감시가 죽은 줄 모르고 몇 분기를 놓치기 때문입니다.

### 감시 대상 추가

`check_filedata_changes.py` 의 `DATASETS` 에 한 줄 더하면 됩니다.

```python
DATASETS = [
    {"pk": "15083033", "kind": "fileData", "label": "소상공인시장진흥공단_상가(상권)정보"},
    {"pk": "15067631", "kind": "fileData", "label": "상가(상권)정보 업종코드"},
]
```

`pk` 는 포털 주소의 숫자, `kind` 는 그 뒤의 경로(`fileData` 또는 `openapi`)입니다.

## 설치

### 요구 사항

- Python 3.11+

### 의존성 설치

```bash
pip install -r requirements.txt
```

## 설정

### 환경 변수

`.env.example`을 참고하여 `.env` 파일을 생성합니다:

```bash
cp .env.example .env
```

`.env` 파일에 Slack 웹훅 URL을 설정합니다:

```
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### GitHub Actions 설정

GitHub 저장소의 Settings > Secrets and variables > Actions에서 다음 시크릿을 추가합니다:

- `SLACK_WEBHOOK_URL`: Slack 웹훅 URL

## 사용법

### 수동 실행

```bash
python check_api_changes.py        # 오픈API 문서
python check_filedata_changes.py   # 파일데이터

python check_filedata_changes.py --test-slack   # 웹훅이 살아 있는지만 확인
```

### 자동 실행

GitHub Actions 워크플로우가 매일 오전 9시(KST)에 자동으로 실행됩니다.

수동으로 워크플로우를 실행하려면 GitHub 저장소의 Actions 탭에서 "Check API Changes" 워크플로우를 선택하고 "Run workflow"를 클릭합니다.

## 알림 내용

변경이 감지되면 바뀐 항목이 `이전 값 → 새 값` 형태로 전송됩니다.

```
:card_file_box: 공공데이터 갱신 감지 — 소상공인시장진흥공단_상가(상권)정보

파일데이터명: ..._20260331 → ..._20260630
수정 일시: 2026-05-07 10:11:12 → 2026-08-05 21:54:06
파일 식별자: uddi:0cb1... → uddi:b309...
차기 등록 예정일: 2026-07-31 → 2026-10-31
```

## 파일 구조

```
.
├── check_api_changes.py        # 오픈API 문서 감시
├── check_filedata_changes.py   # 파일데이터 감시
├── requirements.txt        # Python 의존성
├── .env.example           # 환경 변수 예시
├── .github/
│   └── workflows/
│       └── check-api-changes.yml  # GitHub Actions 워크플로우
├── last_state.json         # 오픈API 문서 상태 (자동 생성·커밋됨)
└── filedata_state.json     # 파일데이터 상태 (자동 생성·커밋됨)
```

상태 파일이 곧 "지난번에 본 값"입니다. 워크플로가 매 실행 후 커밋하며, 커밋되지 않으면
매번 첫 실행이 되어 갱신을 영영 감지하지 못합니다.

## 라이선스

MIT

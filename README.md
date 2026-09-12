# 상가(상권)정보 갱신 감지

공공데이터포털(data.go.kr)의 **소상공인시장진흥공단_상가(상권)정보** 가 새 파일로 갱신되면
Slack으로 알려줍니다. 분기에 한 번 바뀌는 데이터라 사람이 들여다보고 있기 어렵습니다.

- 대상: [소상공인시장진흥공단_상가(상권)정보](https://www.data.go.kr/data/15083033/fileData.do)
- 갱신 주기: 분기 (차기 등록 예정일이 페이지에 표시됩니다)
- 확인 주기: 매일 오전 9시 KST — 등록일이 예정일보다 밀리거나 당겨지기 때문입니다

## 어떻게 감지하나

파일데이터에는 오픈API와 달리 OpenAPI 문서가 없어 문서를 비교하는 방법을 쓸 수 없습니다.
대신 포털 상세 페이지가 서버에서 렌더되므로 거기 박혀 있는 값을 읽습니다.

| 보는 값 | 예 | 의미 |
|---|---|---|
| `publicDataDetailPk` | `uddi:b3094bc9-…` | 파일을 갈아끼우면 새로 발급된다. 가장 확실한 신호 |
| `updtDt` | `2026-08-05 21:54:06` | 수정 일시 |
| 파일데이터명 | `…_20260630` | 끝의 기준일이 분기마다 바뀐다 |
| 차기 등록 예정일 | `2026-10-31` | 다음 갱신 예정 |
| 등록일 / 수정일 / 업데이트 주기 | | 함께 비교 |

다운로드 수는 일부러 보지 않습니다. 시시각각 변해서 매일 "변경됨"이 뜹니다.

페이지 구조가 바뀌어 위 값을 읽지 못하면 `:warning:` 알림을 **한 번** 보냅니다. 조용히
"변경 없음"으로 넘어가면 감시가 죽은 줄 모르고 몇 분기를 놓치기 때문입니다.

## 알림 내용

바뀐 항목만 `이전 값 → 새 값` 형태로 전송됩니다.

```
:card_file_box: 공공데이터 갱신 감지 — 소상공인시장진흥공단_상가(상권)정보

파일데이터명: ..._20260331 → ..._20260630
수정 일시: 2026-05-07 10:11:12 → 2026-08-05 21:54:06
파일 식별자: uddi:0cb1... → uddi:b309...
차기 등록 예정일: 2026-07-31 → 2026-10-31
```

## 설정

### GitHub Actions

저장소 Settings > Secrets and variables > Actions 에 시크릿을 추가합니다.

- `SLACK_WEBHOOK_URL`: Slack 수신 웹훅 URL

워크플로는 `.github/workflows/check-dataset-updates.yml` 이며 매일 오전 9시(KST)에
자동 실행됩니다. Actions 탭의 **Run workflow** 로 즉시 실행할 수도 있습니다.

### 로컬 실행

```bash
pip install -r requirements.txt
cp .env.example .env        # SLACK_WEBHOOK_URL 을 채운다

python check_filedata_changes.py                # 확인
python check_filedata_changes.py --test-slack   # 웹훅이 살아 있는지만 확인
```

## 감시 대상 추가

`check_filedata_changes.py` 의 `DATASETS` 에 한 줄 더하면 됩니다.

```python
DATASETS = [
    {"pk": "15083033", "kind": "fileData", "label": "소상공인시장진흥공단_상가(상권)정보"},
    {"pk": "15067631", "kind": "fileData", "label": "상가(상권)정보 업종코드"},
]
```

`pk` 는 포털 주소의 숫자, `kind` 는 그 뒤의 경로(`fileData` 또는 `openapi`)입니다.

## 파일 구조

```
.
├── check_filedata_changes.py   # 감시 스크립트
├── filedata_state.json         # 마지막으로 본 값 (자동 생성·커밋됨)
├── requirements.txt
├── .env.example
└── .github/workflows/check-dataset-updates.yml
```

`filedata_state.json` 이 곧 "지난번에 본 값"입니다. 워크플로가 매 실행 후 되커밋하며,
커밋되지 않으면 매번 첫 실행이 되어 갱신을 영영 감지하지 못합니다.

변경이 없는 날에도 확인 시각이 바뀌어 커밋이 남습니다. 일부러 그대로 둡니다 — GitHub 은
60일 동안 활동이 없는 저장소의 예약 워크플로를 꺼버리는데, 이 데이터는 분기에 한 번만
바뀌므로 그 사이에 감시가 멈춥니다.

---

`check_api_changes.py` 와 `last_state.json` 은 이 저장소의 출처인
[insure-detect-cron](https://github.com/seohyunjun/insure-detect-cron) 에서 함께 옮겨온
국민연금 오픈API 감시 파일입니다. 그쪽에서 계속 돌고 있어 여기 워크플로는 실행하지
않습니다. 두 번 알림이 오게 되기 때문입니다.

## 라이선스

MIT

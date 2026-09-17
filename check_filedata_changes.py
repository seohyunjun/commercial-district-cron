#!/usr/bin/env python3
"""
data.go.kr 파일데이터 갱신 감지 및 Slack 알림 스크립트

check_api_changes.py 는 오픈API 문서(OpenAPI/Swagger)를 본다. 파일데이터는 그런 문서가
없어서 같은 방법을 쓸 수 없다. 대신 포털의 상세 페이지가 서버에서 렌더되므로, 거기 박혀
있는 메타데이터를 읽어 비교한다.

페이지에서 보는 값
  publicDataDetailPk  파일을 갈아끼우면 새로 발급되는 uddi — 가장 확실한 신호다
  updtDt              수정 일시(초 단위)
  파일데이터명        끝에 기준일이 붙는다 (..._20260630)
  차기 등록 예정일    다음 분기 갱신 예정일

다운로드 수는 일부러 보지 않는다. 시시각각 변해서 매일 "변경됨"이 뜬다.
"""

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

STATE_FILE = Path(__file__).parent / "filedata_state.json"
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
# (연결, 읽기). 포털이 GitHub 러너에서 간헐적으로 연결을 받지 않는다 — 한 번에 30초를
# 기다리기보다 짧게 끊고 여러 번 다시 시도하는 편이 잘 붙는다.
TIMEOUT = (10, 30)
RETRY = Retry(
    total=5,
    backoff_factor=5,  # 0, 10, 20, 40, 80초 간격
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=("GET",),
)

# 감시 대상. 한 줄 더하면 데이터셋이 하나 더 늘어난다.
# kind 는 포털의 상세 페이지 경로다 — 파일데이터는 fileData, 오픈API는 openapi.
DATASETS = [
    {
        "pk": "15083033",
        "kind": "fileData",
        "label": "소상공인시장진흥공단_상가(상권)정보",
    },
]

# 비교할 항목. 값이 하나라도 달라지면 알린다.
TRACKED_FIELDS = [
    ("title", "파일데이터명"),
    ("updated_at", "수정 일시"),
    ("detail_pk", "파일 식별자"),
    ("registered", "등록일"),
    ("modified", "수정일"),
    ("next_release", "차기 등록 예정일"),
    ("cycle", "업데이트 주기"),
]


def dataset_url(dataset):
    return f"https://www.data.go.kr/data/{dataset['pk']}/{dataset['kind']}.do"


def fetch(url):
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=RETRY))
    response = session.get(
        url,
        timeout=TIMEOUT,
        # 기본 User-Agent 로도 열리지만, 차단 정책이 생기면 여기부터 손보게 된다.
        headers={"User-Agent": "insure-detect-cron/1.0 (dataset update monitor)"},
    )
    response.raise_for_status()
    return response.text


def hidden_input(page, name):
    """<input type="hidden" id="name" ... value="..."> 에서 값을 꺼낸다."""
    match = re.search(
        rf'<input[^>]*id="{name}"[^>]*value="([^"]*)"', page
    )
    return html.unescape(match.group(1)).strip() if match else None


def labelled_value(page, label):
    """<strong class="key">label</strong> <div class="value">값</div> 에서 값을 꺼낸다."""
    match = re.search(
        rf'<strong class="key">\s*{re.escape(label)}\s*</strong>\s*'
        r'<div class="value">(.*?)</div>',
        page,
        re.DOTALL,
    )
    if not match:
        return None
    text = re.sub(r"<[^>]+>", " ", match.group(1))
    return re.sub(r"\s+", " ", html.unescape(text)).strip() or None


def parse(page):
    return {
        "title": labelled_value(page, "파일데이터명") or labelled_value(page, "오픈API명"),
        "updated_at": hidden_input(page, "updtDt"),
        "detail_pk": hidden_input(page, "publicDataDetailPk"),
        "registered": labelled_value(page, "등록일"),
        "modified": labelled_value(page, "수정일"),
        "next_release": labelled_value(page, "차기 등록 예정일"),
        "cycle": labelled_value(page, "업데이트 주기"),
    }


def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_state(state):
    state["last_check"] = datetime.now().isoformat(timespec="seconds")
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)


def diff(before, after):
    """바뀐 항목만 '이름: 옛값 → 새값' 으로 돌려준다."""
    lines = []
    for key, label in TRACKED_FIELDS:
        old, new = before.get(key), after.get(key)
        if old != new:
            lines.append(f"{label}: {old or '(없음)'} → {new or '(없음)'}")
    return lines


def send_slack(text):
    if not SLACK_WEBHOOK_URL:
        print("[ERROR] SLACK_WEBHOOK_URL 이 없어 알림을 보내지 못했다")
        return False
    try:
        response = requests.post(
            SLACK_WEBHOOK_URL,
            json={
                "text": text,
                "username": "Data Monitor Bot",
                "icon_emoji": ":card_index_dividers:",
            },
            timeout=10,
        )
        response.raise_for_status()
        print("[INFO] Slack 알림 전송 완료")
        return True
    except requests.RequestException as error:
        print(f"[ERROR] Slack 알림 전송 실패: {error}")
        return False


def notify_update(dataset, changes):
    body = "\n".join(changes)
    send_slack(
        f":card_file_box: *공공데이터 갱신 감지 — {dataset['label']}*\n\n"
        f"```\n{body}\n```\n\n"
        f":link: <{dataset_url(dataset)}|포털에서 내려받기>"
    )


def notify_broken(dataset, reason):
    send_slack(
        f":warning: *공공데이터 감시 실패 — {dataset['label']}*\n\n"
        f"```\n{reason}\n```\n\n"
        f"페이지 구조가 바뀌었거나 접근이 막혔을 수 있다. "
        f"고치기 전까지 이 데이터셋의 갱신을 놓친다.\n"
        f":link: <{dataset_url(dataset)}|페이지 확인>"
    )


def check(dataset, state, first_run_notify=False):
    """데이터셋 하나를 확인한다. 무언가 알렸으면 True."""
    url = dataset_url(dataset)
    print(f"[INFO] {dataset['label']} ({url})")

    try:
        current = parse(fetch(url))
    except requests.RequestException as error:
        # 일시적인 네트워크 오류로 경보를 울리지는 않는다. 워크플로가 실패로 끝난다.
        raise RuntimeError(f"페이지를 가져오지 못했다: {error}") from error

    previous = state.get(dataset["pk"], {})
    broken_before = previous.get("broken", False)

    # 핵심 값이 비면 파싱이 깨진 것이다. 조용히 "변경 없음" 으로 넘어가면 감시가 죽은 줄
    # 모르고 몇 분기를 놓친다. 그래서 한 번은 알린다 — 매일 반복하지 않도록 상태에 남긴다.
    if not current.get("title") or not current.get("detail_pk"):
        print("[ERROR] 메타데이터를 읽지 못했다 (파싱 실패)")
        if not broken_before:
            notify_broken(dataset, "파일데이터명 또는 파일 식별자를 페이지에서 찾지 못했다")
        state[dataset["pk"]] = {**previous, "broken": True}
        return True

    current["broken"] = False

    if not previous or "detail_pk" not in previous:
        print(f"[INFO] 첫 실행 — 기준값을 기록한다: {current['title']}")
        if first_run_notify:
            notify_update(dataset, [f"{label}: {current.get(key) or '(없음)'}"
                                    for key, label in TRACKED_FIELDS])
        state[dataset["pk"]] = current
        return first_run_notify

    changes = diff(previous, current)
    state[dataset["pk"]] = current

    if not changes and not broken_before:
        print(f"[INFO] 변경 없음 ({current['updated_at']})")
        return False

    if broken_before and not changes:
        print("[INFO] 파싱이 다시 정상이다")
        return False

    print("[INFO] 변경 감지:\n  " + "\n  ".join(changes))
    notify_update(dataset, changes)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--test-slack",
        action="store_true",
        help="웹훅이 살아 있는지 확인하는 메시지를 보내고 끝낸다",
    )
    parser.add_argument(
        "--notify-first-run",
        action="store_true",
        help="기준값이 없을 때도 현재 값을 한 번 알린다",
    )
    args = parser.parse_args()

    if args.test_slack:
        ok = send_slack(
            ":white_check_mark: *공공데이터 감시 테스트*\n"
            f"감시 대상 {len(DATASETS)}건, {datetime.now():%Y-%m-%d %H:%M}"
        )
        sys.exit(0 if ok else 1)

    print(f"[INFO] 확인 시작: {datetime.now().isoformat(timespec='seconds')}")
    state = load_state()
    failures = []

    for dataset in DATASETS:
        try:
            check(dataset, state, first_run_notify=args.notify_first_run)
        except RuntimeError as error:
            print(f"[ERROR] {dataset['label']}: {error}")
            failures.append(dataset["label"])

    save_state(state)
    print("[INFO] 완료")

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()

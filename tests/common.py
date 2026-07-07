# -*- coding: utf-8 -*-
"""테스트 공용 헬퍼 — 스크립트 경로 주입, 샘플 사양, 결정적 빌드."""
import os
import random
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "kasa-hwpx", "scripts")
TEMPLATE = os.path.join(ROOT, "kasa-hwpx", "assets", "kasa-standard-report.hwpx")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import kasa_lib as K  # noqa: E402

SAMPLE_SPEC = {
    "title": "누리호 4차 발사 준비현황 보고",
    "pub_date": "2026. 7.",
    "author": "(’26.07.07., 발사체개발부문)",
    "body": [
        {"level": "title", "text": "추진 배경"},
        {"level": "content", "text": "신뢰성 확보 및 우주수송 역량 강화"},
        {"level": "sub", "text": "2027년 상반기 발사 목표"},
        {"level": "note", "text": "3차 대비 탑재 중량 12% 증가"},
        {"type": "table", "title": "발사 일정",
         "headers": ["구분", "일정", "비고"],
         "rows": [["조립", "2026. 10.", "-"], ["발사", "2027. 3.", "예정"]]},
        {"level": "footnote", "text": "세부 일정은 기상 여건에 따라 변동 가능"},
    ],
    "appendix": [
        {"label": "참고 1", "heading": "발사체 제원",
         "body": [{"level": "content", "text": "총중량 200톤급"}]},
    ],
}


def build_sample(out_path, spec=None):
    """엔진 내부 상태(문단 id·표 id 난수)를 고정해 결정적으로 빌드한다."""
    K._id_state[0] = 4000
    random.seed(20260707)
    return K.build_report(TEMPLATE, spec or SAMPLE_SPEC, out_path)


def zip_entries(path):
    """{엔트리 이름: 압축 해제 바이트} — 컨테이너(zip 시각)와 무관한 내용 비교용."""
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}

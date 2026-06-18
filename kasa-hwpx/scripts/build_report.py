#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_report.py — 우주항공청 표준보고서(.hwpx) 생성 CLI

사용법:
    # JSON 사양으로 생성
    python3 build_report.py --spec spec.json --output 결과.hwpx

    # 간이 마커 텍스트(.md/.txt)로 생성
    #   첫 줄  = 제목,  '@날짜:' '@작성:' 메타 가능
    #   □/ㅇ/-/※/* 마커로 본문 위계 지정
    python3 build_report.py --markdown 본문.md --title "제목" --output 결과.hwpx

옵션:
    --template <path>  : 기준 양식(미지정 시 번들 assets/kasa-standard-report.hwpx)
"""
import os, sys, json, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kasa_lib as K

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE = os.path.normpath(os.path.join(HERE, "..", "assets", "kasa-standard-report.hwpx"))

MARKER2LEVEL = {"□": "title", "ㅇ": "content", "○": "content",
                "-": "sub", "–": "sub", "※": "note", "*": "footnote"}

def parse_markdown(text):
    spec = {"body": []}
    lines = text.splitlines()
    if lines and not lines[0].lstrip().startswith(tuple(MARKER2LEVEL)):
        spec["title"] = lines[0].strip(); lines = lines[1:]
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        if s.startswith("@날짜:"):
            spec["pub_date"] = s[4:].strip(); continue
        if s.startswith("@작성:"):
            spec["author"] = s[4:].strip(); continue
        if s.startswith("@슬로건:"):
            spec["slogan_lead"] = s[5:].strip(); continue
        mk = s[0]
        if mk in MARKER2LEVEL:
            spec["body"].append({"level": MARKER2LEVEL[mk], "text": s[1:].strip()})
        else:
            spec["body"].append({"level": "content", "text": s})
    return spec

def main():
    ap = argparse.ArgumentParser(description="우주항공청 표준보고서 HWPX 생성")
    ap.add_argument("--spec"); ap.add_argument("--markdown")
    ap.add_argument("--title"); ap.add_argument("--output", required=True)
    ap.add_argument("--template", default=DEFAULT_TEMPLATE)
    a = ap.parse_args()

    if a.spec:
        spec = json.load(open(a.spec, encoding="utf-8"))
    elif a.markdown:
        spec = parse_markdown(open(a.markdown, encoding="utf-8").read())
    else:
        print("오류: --spec 또는 --markdown 중 하나가 필요합니다."); sys.exit(1)
    if a.title:
        spec["title"] = a.title

    out = K.build_report(a.template, spec, a.output)
    print(f"생성 완료: {out}")
    # 자동 검증
    from validate import validate_structure
    issues = validate_structure(out)
    print("구조 검증:", "통과" if not issues else f"문제 {len(issues)}건 → {issues}")

if __name__ == "__main__":
    main()

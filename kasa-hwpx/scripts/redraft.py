#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""재기안(re-draft) — 기존 HWPX의 서식·구조를 그대로 보존한 채 본문 텍스트만 교체한다.

설계(참고: Canine89/hwpxskill, ai-public-peasant/hwpx-rekian의 '재기안' 접근):
  - 외부 프로그램(한컴오피스) 불필요, 파이썬 표준 라이브러리만 사용.
  - <hp:t>(leaf) 단위로 텍스트만 치환하여 charPr/paraPr·표·셀병합·여백 등 서식을 보존.
  - 치환 후 흐름 문단의 줄 위치 캐시(linesegarray)를 제거 → 한글이 열 때 재계산(relayout).
    (kasa-hwpx의 핵심 규칙과 동일: vertpos 누적 캐시로 인한 줄 겹침 방지)

사용법:
  python3 redraft.py --input 원본.hwpx --map repl.json --output 결과.hwpx [--mode contains|exact]
  repl.json 예: {"2025년": "2026년", "(부서명)": "우주수송정책과"}
  - contains(기본): <hp:t> 안에 키가 포함되면 부분 치환
  - exact      : <hp:t> 전체가 키와 정확히 일치할 때만 치환(오치환 방지)
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kasa_lib as K  # noqa: E402

_ENTITIES = (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
             ("&quot;", '"'), ("&apos;", "'"))


def _unescape(t):
    for ent, ch in _ENTITIES:
        t = t.replace(ent, ch)
    return t


def redraft(input_path, replacements, output_path, mode="contains"):
    """원본 HWPX를 읽어 replacements(찾을문구→바꿀문구)를 적용하고 저장한다.
    반환: 변경된 <hp:t> 개수."""
    parts, order = K.read_package(input_path)
    if "Contents/section0.xml" not in parts:
        raise SystemExit("section0.xml을 찾을 수 없습니다(유효한 HWPX가 아님).")
    sec = parts["Contents/section0.xml"].decode("utf-8")

    changed = [0]

    def _sub_t(m):
        raw = m.group(1)
        plain = _unescape(raw)
        new = plain
        for find, to in replacements.items():
            if mode == "exact":
                if new == find:
                    new = to
            else:  # contains
                if find in new:
                    new = new.replace(find, to)
        if new != plain:
            changed[0] += 1
            return "<hp:t>" + K.xml_escape(new) + "</hp:t>"
        return m.group(0)

    # 1) <hp:t> 단위 텍스트 치환(서식 보존)
    sec = re.sub(r"<hp:t>(.*?)</hp:t>", _sub_t, sec, flags=re.S)
    # 2) 모든 줄 위치 캐시 제거 → 한글이 열 때 전체 재계산(줄 겹침 방지)
    sec = re.sub(r"<hp:linesegarray>.*?</hp:linesegarray>", "", sec, flags=re.S)

    parts["Contents/section0.xml"] = sec.encode("utf-8")
    K.write_package(output_path, parts, order)
    K.fix_namespaces(output_path)
    return changed[0]


def main():
    ap = argparse.ArgumentParser(description="재기안: 기존 HWPX 서식 보존 본문 치환")
    ap.add_argument("--input", required=True, help="원본 HWPX 경로")
    ap.add_argument("--map", required=True, help="치환 매핑 JSON 경로({찾을문구: 바꿀문구})")
    ap.add_argument("--output", required=True, help="결과 HWPX 경로")
    ap.add_argument("--mode", choices=["contains", "exact"], default="contains",
                    help="치환 방식(기본 contains)")
    args = ap.parse_args()

    with open(args.map, encoding="utf-8") as f:
        replacements = json.load(f)
    if not isinstance(replacements, dict) or not replacements:
        raise SystemExit("--map JSON은 비어있지 않은 {문자열:문자열} 객체여야 합니다.")

    n = redraft(args.input, {str(k): str(v) for k, v in replacements.items()},
                args.output, mode=args.mode)
    print(f"재기안 완료: {args.output} (치환 {n}건)")


if __name__ == "__main__":
    main()

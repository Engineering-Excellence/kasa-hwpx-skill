#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""재기안(re-draft) — 기존 HWPX의 서식·구조를 그대로 보존한 채 본문 텍스트만 교체한다.

설계(참고: Canine89/hwpxskill, ai-public-peasant/hwpx-rekian의 '재기안' 접근):
  - 외부 프로그램(한컴오피스) 불필요, 파이썬 표준 라이브러리만 사용.
  - <hp:t>(leaf) 단위로 텍스트만 치환하여 charPr/paraPr·표·셀병합·여백 등 서식을 보존.
  - 치환 후 흐름 문단의 줄 위치 캐시(linesegarray)를 제거 → 한글이 열 때 재계산(relayout).
    (kasa-hwpx의 핵심 규칙과 동일: vertpos 누적 캐시로 인한 줄 겹침 방지)

가드레일(v0.5.0 — upstream 반영):
  - 모든 섹션(Contents/section0..N.xml)을 처리한다.
  - <hp:t> 안에 컨트롤 태그가 섞인 경우(mixed content) 태그를 건드리지 않고
    텍스트 구간에만 치환한다. exact 모드에서는 mixed 노드를 건너뛴다.
  - 미변경 zip 엔트리는 원본 메타데이터(ZipInfo) 그대로 유지한다.
  - 치환 결과를 키별로 집계하고, 한 번도 적중하지 않은 키는 경고한다.

동시 치환(연쇄 오치환 방지):
  - 모든 키를 하나의 정규식 alternation으로 컴파일해 **원본 텍스트 기준 1회 스캔**으로
    치환한다. 앞 규칙의 결과가 뒤 규칙의 입력이 되는 연쇄(도미노) 치환이 생기지 않으므로,
    시각 순연({"09:00~09:30": "09:30~10:00", "09:30~10:00": "10:00~10:30", ...})처럼
    새 값이 다른 항목의 기존 값과 겹치는 매핑도 안전하다.
  - 키가 서로 겹치면 긴 키를 우선 매칭한다("10:00"보다 "10:00~11:00"이 먼저).

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

_T_RE = re.compile(r"(<hp:t(?:\s[^>]*)?>)(.*?)</hp:t>", re.S)
_TAG_SPLIT_RE = re.compile(r"(<[^>]+>)")


def _unescape(t):
    for ent, ch in _ENTITIES:
        t = t.replace(ent, ch)
    return t


def _compile_rules(replacements):
    """치환 맵을 (정규식, 매핑)으로 1회 컴파일한다(모든 섹션에서 재사용).

    - 키를 길이 내림차순으로 정렬해 alternation을 만든다 → 겹치는 키는 긴 쪽이 먼저 매칭.
    - 빈 키는 무한 매칭 위험이 있어 거부한다.
    - 키와 값이 같은 항목은 치환에서 제외한다(불필요한 변경·집계 방지).
    - 매칭이 하나도 불가능하면 정규식은 None.
    """
    if any(k == "" for k in replacements):
        raise SystemExit("치환 맵에 빈 문자열 키가 있습니다 — 모든 위치에 매칭되어 "
                         "문서를 훼손할 수 있으므로 거부합니다(키를 확인하세요).")
    mapping = {k: v for k, v in replacements.items() if k != v}
    keys = sorted(mapping, key=len, reverse=True)  # 긴 키 우선 매칭
    pattern = re.compile("|".join(re.escape(k) for k in keys)) if keys else None
    return pattern, mapping


def _apply_rules(plain, rules, mode, counts):
    """텍스트 한 조각에 규칙을 원본 기준으로 '동시' 적용하고 적중 수를 집계한다.
    치환 결과는 다시 스캔되지 않으므로 규칙 간 연쇄 치환이 발생하지 않는다."""
    pattern, mapping = rules
    if pattern is None:
        return plain
    if mode == "exact":
        # <hp:t> 전체가 키와 정확히 일치할 때만 1회 치환하고 즉시 확정한다
        # (다른 키를 추가로 적용하지 않는다 — 도미노 차단)
        to = mapping.get(plain)
        if to is None:
            return plain
        counts[plain] += 1
        return to

    def _one(m):
        key = m.group(0)
        counts[key] += 1
        return mapping[key]  # 함수형 replacement: 값의 \1·\g<> 등이 그대로 삽입된다

    return pattern.sub(_one, plain)


def _redraft_section(sec, rules, mode, counts, changed):
    def _sub_t(m):
        open_tag, inner = m.group(1), m.group(2)
        if "<" in inner:
            # mixed content: 컨트롤 태그를 보존한 채 텍스트 구간에만 치환.
            # exact 모드는 <hp:t> 전체 일치가 성립하지 않으므로 건너뛴다.
            if mode == "exact":
                return m.group(0)
            out = []
            dirty = False
            for seg in _TAG_SPLIT_RE.split(inner):
                if seg.startswith("<"):
                    out.append(seg)
                    continue
                plain = _unescape(seg)
                new = _apply_rules(plain, rules, mode, counts)
                if new != plain:
                    dirty = True
                out.append(K.xml_escape(new))
            if dirty:
                changed[0] += 1
                return open_tag + "".join(out) + "</hp:t>"
            return m.group(0)
        plain = _unescape(inner)
        new = _apply_rules(plain, rules, mode, counts)
        if new != plain:
            changed[0] += 1
            return open_tag + K.xml_escape(new) + "</hp:t>"
        return m.group(0)

    # 1) <hp:t> 단위 텍스트 치환(서식 보존)
    sec = _T_RE.sub(_sub_t, sec)
    # 2) 모든 줄 위치 캐시 제거 → 한글이 열 때 전체 재계산(줄 겹침 방지)
    sec, _ = K.strip_linesegarray(sec)
    return sec


def redraft(input_path, replacements, output_path, mode="contains"):
    """원본 HWPX를 읽어 replacements(찾을문구→바꿀문구)를 적용하고 저장한다.
    반환: (변경된 <hp:t> 개수, 키별 적중 수 dict)."""
    parts, _ = K.read_package(input_path)
    section_names = sorted(n for n in parts
                           if re.match(r"Contents/section\d+\.xml$", n))
    if not section_names:
        raise SystemExit("section*.xml을 찾을 수 없습니다(유효한 HWPX가 아님).")

    changed = [0]
    counts = {k: 0 for k in replacements}
    rules = _compile_rules(replacements)  # 1회 컴파일 → 전 섹션에서 재사용
    new_parts = {}
    for name in section_names:
        sec = parts[name].decode("utf-8")
        new_sec = _redraft_section(sec, rules, mode, counts, changed)
        if new_sec != sec:
            new_parts[name] = new_sec.encode("utf-8")

    # 본문이 바뀌었으면 미리보기(PrvText)도 새 본문으로 갱신(기존 엔트리가 있을 때만)
    if new_parts:
        merged = dict(parts)
        merged.update(new_parts)
        if K.refresh_prvtext(merged):
            new_parts[K.PRVTEXT_NAME] = merged[K.PRVTEXT_NAME]

    # 미변경 엔트리는 원본 zip 메타데이터 그대로 유지(서식 보존 기록)
    K.write_package_preserving(input_path, output_path, new_parts)
    K.fix_namespaces(output_path)
    return changed[0], counts


def main():
    # Windows cp949 콘솔 등에서 특수문자 출력 크래시 방지
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")
        except Exception:
            pass
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

    n, counts = redraft(args.input,
                        {str(k): str(v) for k, v in replacements.items()},
                        args.output, mode=args.mode)
    print(f"재기안 완료: {args.output} (치환 {n}건)")
    for key, c in counts.items():
        mark = "[경고] 미적중" if c == 0 else f"{c}건"
        print(f"  - {key!r}: {mark}")
    if any(c == 0 for c in counts.values()):
        print("  ※ 미적중 키는 원문 표기(띄어쓰기·특수문자)와 다를 수 있습니다. "
              "extract_text.py로 원문을 확인하세요.")


if __name__ == "__main__":
    main()

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


def _apply_map(plain, replacements, mode, counts):
    """텍스트 한 조각에 치환 맵을 적용하고 키별 적중 수를 집계한다."""
    new = plain
    for find, to in replacements.items():
        if mode == "exact":
            if new == find:
                new = to
                counts[find] += 1
        else:  # contains
            n = new.count(find)
            if n:
                new = new.replace(find, to)
                counts[find] += n
    return new


def _redraft_section(sec, replacements, mode, counts, changed):
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
                new = _apply_map(plain, replacements, mode, counts)
                if new != plain:
                    dirty = True
                out.append(K.xml_escape(new))
            if dirty:
                changed[0] += 1
                return open_tag + "".join(out) + "</hp:t>"
            return m.group(0)
        plain = _unescape(inner)
        new = _apply_map(plain, replacements, mode, counts)
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
    new_parts = {}
    for name in section_names:
        sec = parts[name].decode("utf-8")
        new_sec = _redraft_section(sec, replacements, mode, counts, changed)
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

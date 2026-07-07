#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hwpx_diff.py — 신구대조: 두 HWPX의 문단·표 셀 단위 비교 보고(읽기 전용).

재기안 전후 검수용. 문서를 블록(문단/표) 시퀀스로 펼쳐 순서 정렬 비교하고,
짝지어진 표는 셀 단위까지 비교한다. 원본을 일절 수정하지 않는다.
(참고: chrisryugj/kordoc compare의 블록·셀 diff 아이디어를 표준 라이브러리로 재구현)

사용법:
    python3 hwpx_diff.py 구버전.hwpx 신버전.hwpx           # 사람용 보고
    python3 hwpx_diff.py 구버전.hwpx 신버전.hwpx --stats   # 통계 한 줄만
"""
import difflib
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _cell_text(tc):
    return "".join(t.text or "" for t in tc.iter(_HP + "t")).strip()


def _table_matrix(tbl):
    """표 요소 → 행렬 [[셀텍스트]] (rowAddr/colAddr 기준, 병합 셀은 앵커 위치)."""
    cells = {}
    for tc in tbl.iter(_HP + "tc"):
        addr = tc.find(_HP + "cellAddr")
        if addr is None:
            continue
        cells[(int(addr.get("rowAddr")), int(addr.get("colAddr")))] = _cell_text(tc)
    if not cells:
        return []
    nrow = max(r for r, _ in cells) + 1
    ncol = max(c for _, c in cells) + 1
    return [[cells.get((r, c), "") for c in range(ncol)] for r in range(nrow)]


def _walk(el, blocks):
    """문서 순서대로 블록 수집: ('p', 텍스트) / ('table', 행렬).
    머리말/꼬리말은 본문 비교 대상이 아니므로 제외한다."""
    for child in el:
        tag = child.tag
        if tag in (_HP + "header", _HP + "footer"):
            continue
        if tag == _HP + "tbl":
            blocks.append(("table", _table_matrix(child)))
            continue
        if tag == _HP + "p":
            txt = "".join("".join(t.text or "" for t in run.findall(_HP + "t"))
                          for run in child.findall(_HP + "run")).strip()
            if txt:
                blocks.append(("p", txt))
        _walk(child, blocks)


def extract_blocks(path):
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist()
                       if re.match(r"Contents/section\d+\.xml$", n))
        blocks = []
        for n in names:
            _walk(ET.fromstring(z.read(n)), blocks)
    return blocks


def _key(block):
    kind, body = block
    return (kind, tuple(tuple(r) for r in body)) if kind == "table" else (kind, body)


def _diff_tables(old, new):
    """짝지어진 표의 셀 diff: [(r, c, 구값, 신값)]. 크기 다르면 겹친 영역만."""
    out = []
    for r in range(max(len(old), len(new))):
        orow = old[r] if r < len(old) else []
        nrow = new[r] if r < len(new) else []
        for c in range(max(len(orow), len(nrow))):
            ov = orow[c] if c < len(orow) else None
            nv = nrow[c] if c < len(nrow) else None
            if ov != nv:
                out.append((r, c, ov, nv))
    return out


def compare(old_path, new_path):
    """(stats, events) — stats: {added, removed, modified, unchanged},
    events: [('unchanged'|'added'|'removed'|'modified', 설명 dict)]."""
    a, b = extract_blocks(old_path), extract_blocks(new_path)
    sm = difflib.SequenceMatcher(a=[_key(x) for x in a], b=[_key(x) for x in b],
                                 autojunk=False)
    stats = {"added": 0, "removed": 0, "modified": 0, "unchanged": 0}
    events = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            stats["unchanged"] += i2 - i1
            continue
        olds, news = a[i1:i2], b[j1:j2]
        # 같은 종류·같은 순번끼리 짝지어 '수정'으로, 남는 쪽은 추가/삭제로 본다
        n_pair = min(len(olds), len(news))
        for k in range(n_pair):
            (ok, ob), (nk, nb) = olds[k], news[k]
            stats["modified"] += 1
            if ok == "table" and nk == "table":
                events.append(("modified", {
                    "kind": "table", "cells": _diff_tables(ob, nb),
                    "dims": (f"{len(ob)}×{len(ob[0]) if ob else 0}",
                             f"{len(nb)}×{len(nb[0]) if nb else 0}")}))
            else:
                events.append(("modified", {
                    "kind": "p",
                    "old": ob if ok == "p" else "[표]",
                    "new": nb if nk == "p" else "[표]"}))
        for kind, body in olds[n_pair:]:
            stats["removed"] += 1
            events.append(("removed", {"kind": kind, "text": _summ(kind, body)}))
        for kind, body in news[n_pair:]:
            stats["added"] += 1
            events.append(("added", {"kind": kind, "text": _summ(kind, body)}))
    return stats, events


def _summ(kind, body, n=60):
    s = f"[표 {len(body)}행]" if kind == "table" else body
    if kind == "table" and body:
        s += " " + " | ".join(body[0])[:40]
    return s if len(s) <= n else s[:n] + "…"


def _clip(s, n=60):
    s = s or "(빈 셀)"
    return s if len(s) <= n else s[:n] + "…"


def render(stats, events):
    lines = [f"통계: 추가 {stats['added']} · 삭제 {stats['removed']} · "
             f"수정 {stats['modified']} · 동일 {stats['unchanged']}"]
    tbl_no = 0
    for ev, d in events:
        if ev == "modified" and d["kind"] == "table":
            tbl_no += 1
            head = f"[수정] 표({d['dims'][0]}→{d['dims'][1]})" \
                if d["dims"][0] != d["dims"][1] else "[수정] 표"
            lines.append(head)
            for r, c, ov, nv in d["cells"]:
                lines.append(f"    셀({r},{c}): {_clip(ov)} → {_clip(nv)}")
        elif ev == "modified":
            lines.append(f"[수정] {_clip(d['old'])}")
            lines.append(f"    → {_clip(d['new'])}")
        elif ev == "removed":
            lines.append(f"[삭제] {d['text']}")
        else:
            lines.append(f"[추가] {d['text']}")
    if not events:
        lines.append("차이 없음 — 두 문서의 본문·표 내용이 동일합니다.")
    return "\n".join(lines)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")
        except Exception:
            pass
    args = [x for x in sys.argv[1:] if x != "--stats"]
    if len(args) != 2:
        print(__doc__)
        sys.exit(1)
    stats, events = compare(args[0], args[1])
    print(f"# 신구대조: {args[0]} → {args[1]}")
    if "--stats" in sys.argv:
        print(f"추가 {stats['added']} 삭제 {stats['removed']} "
              f"수정 {stats['modified']} 동일 {stats['unchanged']}")
    else:
        print(render(stats, events))


if __name__ == "__main__":
    main()

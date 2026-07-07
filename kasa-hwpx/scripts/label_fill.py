#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""label_fill.py — 라벨 기반 양식 채우기: {{자리표시자}} 없는 표 양식 자동 입력.

"성명:" 같은 라벨 셀을 찾아 그 오른쪽(없으면 아래) 빈 셀에 값을 넣는다.
기존 빈 셀의 <hp:t>에 텍스트만 넣으므로 구조를 창작하지 않으며(빈 셀에 <hp:t>가
없으면 그 항목은 건너뛰고 보고), 서식·zip 메타데이터는 원본 그대로 보존한다.
(참고: chrisryugj/kordoc 라벨 인식 규칙 — 콜론/짧은 명사 라벨 + 값 오인 거름망)

사용법:
    python3 label_fill.py detect 양식.hwpx                # 라벨 후보·채울 위치 미리보기
    python3 label_fill.py fill   양식.hwpx --data d.json --output 결과.hwpx

d.json 예: {"성명": "홍길동", "소속": "우주수송정책과"}
  - 키는 라벨 문구와 콜론·공백 차이를 무시하고 대조한다("성명:" ≡ "성명").
※ 이름·연락처 등 개인정보는 값이 화면·로그에 남지 않는 secure_fill.py 사용을 권장.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kasa_lib as K  # noqa: E402
import hwpx_edit as HE  # noqa: E402

_T_ANY = re.compile(r"<hp:t(?:\s[^>]*)?>.*?</hp:t>|<hp:t/>", re.S)
# 값 오인 거름망: "6개월"·"1억원"처럼 숫자+단위, 또는 전형적 값 표기는 라벨이 아니다
_VALUE_LIKE = re.compile(r"^\d[\d,.]*[가-힣A-Za-z%]*$")
_VALUE_WORDS = {"해당없음", "없음", "-", "—", "―", "O", "X", "예", "아니오"}


def _norm(s):
    return re.sub(r"[\s::]+", "", s).strip()


def _cell_text(tc):
    txt = "".join(re.sub(r"<[^>]+>", "", m.group(0)) for m in _T_ANY.finditer(tc))
    return (txt.replace("&lt;", "<").replace("&gt;", ">")
               .replace("&quot;", '"').replace("&amp;", "&")).strip()


def _grid(tbl):
    """{(row, col): (cs, ce, colspan, rowspan)} — tbl 블록 기준 오프셋."""
    return {(r, c): (cs, ce, csp, rsp)
            for cs, ce, c, r, csp, rsp in HE._cells(tbl)}


def _is_label(text):
    if not text or _norm(text) == "":
        return False
    if text.rstrip().endswith((":", "：")):
        return True
    n = _norm(text)
    if n in _VALUE_WORDS or _VALUE_LIKE.match(n):
        return False
    return len(n) <= 8 and not any(ch.isdigit() for ch in n)


def _target_of(tbl, grid, row, col, colspan, rowspan):
    """라벨 셀의 채움 대상: 오른쪽 빈 셀 → 없으면 아래 빈 셀. (좌표, 위치명) 또는 None."""
    for (r, c), where in [((row, col + colspan), "오른쪽"),
                          ((row + rowspan, col), "아래")]:
        hit = grid.get((r, c))
        if hit and _cell_text(tbl[hit[0]:hit[1]]) == "":
            return (r, c), where
    return None


def scan(parts):
    """[(표순번, 라벨텍스트, 대상좌표, 위치명, 섹션명, 표시작, 표끝)] — 문서 순서."""
    out = []
    for t_idx, (name, s, e) in enumerate(HE._doc_tables(parts), 1):
        tbl = parts[name].decode("utf-8")[s:e]
        grid = _grid(tbl)
        for (r, c), (cs, ce, csp, rsp) in sorted(grid.items()):
            text = _cell_text(tbl[cs:ce])
            if not _is_label(text):
                continue
            tgt = _target_of(tbl, grid, r, c, csp, rsp)
            if tgt:
                out.append((t_idx, text, tgt[0], tgt[1], name, s, e))
    return out


def _fill_cell(sec, tbl_s, grid, rc, value):
    """대상 셀 첫 <hp:t>에 값 기록(없으면 None 반환 — 구조 창작 금지)."""
    cs, ce, *_ = grid[rc]
    tc = sec[tbl_s + cs:tbl_s + ce]
    m = _T_ANY.search(tc)
    if not m:
        return None
    new_tc = tc[:m.start()] + f"<hp:t>{K.xml_escape(value)}</hp:t>" + tc[m.end():]
    new_tc, _ = K.strip_linesegarray(new_tc)
    return sec[:tbl_s + cs] + new_tc + sec[tbl_s + ce:]


def fill(parts, data):
    """data({라벨: 값})를 채운다. (filled, unmatched) 반환 — unmatched는 (키, 사유)."""
    filled, unmatched = [], []
    for key, value in data.items():
        nkey = _norm(key)
        hit = None
        for t_idx, (name, s, e) in enumerate(HE._doc_tables(parts), 1):
            tbl = parts[name].decode("utf-8")[s:e]
            grid = _grid(tbl)
            for (r, c), (cs, ce, csp, rsp) in sorted(grid.items()):
                if _norm(_cell_text(tbl[cs:ce])) != nkey:
                    continue
                tgt = _target_of(tbl, grid, r, c, csp, rsp)
                if tgt is None:
                    unmatched.append((key, "라벨 옆/아래에 빈 셀 없음"))
                else:
                    hit = (name, s, grid, tgt[0], tgt[1], t_idx)
                break
            if hit or unmatched and unmatched[-1][0] == key:
                break
        if hit is None:
            if not (unmatched and unmatched[-1][0] == key):
                unmatched.append((key, "라벨을 찾지 못함(detect로 확인)"))
            continue
        name, s, grid, rc, where, t_idx = hit
        sec = parts[name].decode("utf-8")
        new = _fill_cell(sec, s, grid, rc, str(value))
        if new is None:
            unmatched.append((key, "빈 셀에 <hp:t>가 없어 기록 불가"))
            continue
        parts[name] = new.encode("utf-8")
        filled.append((key, t_idx, rc, where))
    if filled:
        K.refresh_prvtext(parts)
    return filled, unmatched


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="라벨 기반 표 양식 채우기")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("detect", help="라벨 후보와 채울 위치 미리보기")
    d.add_argument("input")
    f = sub.add_parser("fill", help="라벨 옆 빈 셀에 값 기록")
    f.add_argument("input")
    f.add_argument("--data", required=True, help="{라벨: 값} JSON 파일")
    f.add_argument("--output", required=True)
    a = ap.parse_args()

    parts, _ = K.read_package(a.input)
    if a.cmd == "detect":
        rows = scan(parts)
        if not rows:
            print("라벨 후보 없음(표 안의 '라벨: + 빈 셀' 구조를 찾지 못함)")
        for t_idx, text, rc, where, *_ in rows:
            print(f"표 #{t_idx} {text!r} → {where} 셀{rc}")
        return
    with open(a.data, encoding="utf-8") as fp:
        data = json.load(fp)
    orig = dict(parts)
    filled, unmatched = fill(parts, data)
    changed = {n: b for n, b in parts.items() if orig.get(n) != b}
    K.write_package_preserving(a.input, a.output, changed)
    K.fix_namespaces(a.output)
    for key, t_idx, rc, where in filled:
        print(f"[기록] {key!r} → 표 #{t_idx} {where} 셀{rc}")
    for key, why in unmatched:
        print(f"[미적중] {key!r} — {why}")
    print(f"완료: 기록 {len(filled)} · 미적중 {len(unmatched)} → {a.output}")


if __name__ == "__main__":
    main()

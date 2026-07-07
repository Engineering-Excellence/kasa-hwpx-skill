#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hwpx_edit.py — 기존 HWPX의 머리말·꼬리말·쪽번호·표 구조 in-place 편집(서식 보존).

원본의 서식·zip 메타데이터를 보존한 채(변경 엔트리만 교체) 편집한다.
(참고: jkf87/hwpx-skill fill_hwpx의 set-header/set-footer/set-pagenum·표 op 접근)

사용법:
  python3 hwpx_edit.py set-header  문서.hwpx --text "머리말" --output 결과.hwpx
  python3 hwpx_edit.py set-footer  문서.hwpx --text "꼬리말" --output 결과.hwpx
  python3 hwpx_edit.py set-pagenum 문서.hwpx [--pos BOTTOM_CENTER] [--format DIGIT]
                                   [--side-char "-"] --output 결과.hwpx
  python3 hwpx_edit.py remove-header|remove-footer|remove-pagenum 문서.hwpx --output 결과.hwpx
  python3 hwpx_edit.py set-cell     문서.hwpx --table 1 --row 0 --col 0
                                   [--bg D9D9D9|none] [--border on|off] --output 결과.hwpx
  python3 hwpx_edit.py add-col      문서.hwpx --table 1 [--at N] --output 결과.hwpx
  python3 hwpx_edit.py del-row      문서.hwpx --table 1 --row N --output 결과.hwpx
  python3 hwpx_edit.py merge-cells  문서.hwpx --table 1 --from 0,0 --to 1,1 --output 결과.hwpx

규칙:
  - 슬롯(머리말/꼬리말)이 여러 개면 전부 갱신한다.
  - 미지정 옵션은 기존값을 보존한다(set-pagenum의 pos/format/side-char).
  - 슬롯이 없으면 새로 만든다(applyPageType은 --apply, 기본 BOTH).
  - KASA 표준보고서의 머리말에는 MI 로고(표+이미지)가 있다 — set-header는
    개체를 보존한 채 텍스트만 넣지만, KASA 문서에서는 머리말 대신
    꼬리말·쪽번호 편집을 권장한다.
  - 표 op: --table은 문서 전체 표 순번(1-based, 머리말/꼬리말 내부 표 제외 —
    표지 레이아웃 표는 포함되므로 list-tables로 순번을 먼저 확인), --row/--col은 0-based.
    중첩 표를 품은 표는 모든 op을 거부한다. 병합(span)이 있는 표는
    좌표 재계산이 불가능해 구조 op(add-col/del-row/merge-cells)을 거부한다
    (set-cell은 허용). 셀 배경/테두리는 header.xml의 borderFill을
    복제/재사용해 itemCnt까지 보정한다.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kasa_lib as K  # noqa: E402

# 검증된 스타일: 기준 양식의 머리말 문단(paraPr 10, style 8 '머리말', charPr 1)
_HF_PARA = ('<hp:p id="{pid}" paraPrIDRef="10" styleIDRef="8" pageBreak="0" '
            'columnBreak="0" merged="0"><hp:run charPrIDRef="1">'
            '<hp:t>{text}</hp:t></hp:run></hp:p>')

_PAGENUM_RE = re.compile(r'<hp:pageNum\b([^>]*)/>')
_T_RE = re.compile(r"<hp:t(?:\s[^>]*)?>.*?</hp:t>|<hp:t/>", re.S)


def _hf_blocks(sec, tag):
    """<hp:{tag}> ... </hp:{tag}> 블록 (start, end) 목록. 같은 태그는 중첩되지 않는다."""
    return [(m.start(), m.end()) for m in
            re.finditer(rf"<hp:{tag}\b.*?</hp:{tag}>", sec, re.S)]


def _set_block_text(block, text, tag):
    """머리말/꼬리말 블록의 텍스트를 교체한다. 표·이미지 등 개체는 보존하고
    첫 <hp:t>에 text, 나머지는 비운다. <hp:t>가 없으면 문단을 새로 넣는다.
    줄위치 캐시는 제거해 한글이 재계산하게 한다."""
    ts = list(_T_RE.finditer(block))
    esc = K.xml_escape(text)
    if ts:
        out, last = [], 0
        for i, m in enumerate(ts):
            out.append(block[last:m.start()])
            out.append(f"<hp:t>{esc}</hp:t>" if i == 0 else "<hp:t></hp:t>")
            last = m.end()
        out.append(block[last:])
        block = "".join(out)
    else:
        para = _HF_PARA.format(pid=K.next_id(), text=esc)
        block = block.replace("</hp:subList>", para + "</hp:subList>", 1)
    block, _ = K.strip_linesegarray(block)
    return block


def _next_hf_id(sec):
    ids = [int(i) for i in
           re.findall(r'<hp:(?:header|footer)\b[^>]*\bid="(\d+)"', sec)]
    return max(ids, default=1) + 1


def _make_hf_ctrl(sec, tag, text, apply_type):
    para = _HF_PARA.format(pid=K.next_id(), text=K.xml_escape(text))
    return (f'<hp:ctrl><hp:{tag} id="{_next_hf_id(sec)}" '
            f'applyPageType="{apply_type}">'
            f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" '
            f'vertAlign="TOP" linkListIDRef="0" linkListNextIDRef="0" '
            f'textWidth="48190" textHeight="2000" hasTextRef="0" hasNumRef="0">'
            f'{para}</hp:subList></hp:{tag}></hp:ctrl>')


def _insert_ctrl(sec, ctrl_xml):
    """새 ctrl을 기존 머리말/꼬리말 ctrl 뒤(없으면 단 설정 ctrl 뒤)에 넣는다."""
    for anchor in ("</hp:header></hp:ctrl>", "</hp:footer></hp:ctrl>"):
        pos = sec.find(anchor)
        if pos != -1:
            at = pos + len(anchor)
            return sec[:at] + ctrl_xml + sec[at:]
    m = re.search(r"<hp:ctrl><hp:colPr\b[^>]*/></hp:ctrl>", sec)
    if not m:
        raise SystemExit("삽입 위치를 찾을 수 없습니다(colPr ctrl 부재 — 유효한 HWPX인지 확인).")
    return sec[:m.end()] + ctrl_xml + sec[m.end():]


def set_headerfooter(sec, tag, text, apply_type=None):
    """머리말/꼬리말 텍스트 설정. 슬롯 전부 갱신, 없으면 생성. (sec, 슬롯 수) 반환."""
    blocks = _hf_blocks(sec, tag)
    if not blocks:
        return _insert_ctrl(sec, _make_hf_ctrl(sec, tag, text, apply_type or "BOTH")), 1
    out, last = [], 0
    for s, e in blocks:
        block = _set_block_text(sec[s:e], text, tag)
        if apply_type:  # 미지정 시 기존 applyPageType 보존
            block = re.sub(r'(applyPageType=")[^"]*(")',
                           rf"\g<1>{apply_type}\g<2>", block, count=1)
        out.append(sec[last:s]); out.append(block); last = e
    out.append(sec[last:])
    return "".join(out), len(blocks)


def remove_headerfooter(sec, tag):
    """머리말/꼬리말 ctrl 제거. (sec, 제거 수) 반환."""
    return re.subn(rf"<hp:ctrl><hp:{tag}\b.*?</hp:{tag}></hp:ctrl>", "", sec, flags=re.S)


def set_pagenum(sec, pos=None, fmt=None, side_char=None):
    """쪽번호 설정. 기존 <hp:pageNum>이 있으면 지정된 속성만 갱신(나머지 보존),
    없으면 생성. (sec, 슬롯 수) 반환."""
    def _upd(m):
        attrs = m.group(1)
        for key, val in (("pos", pos), ("formatType", fmt), ("sideChar", side_char)):
            if val is None:
                continue
            attrs, n = re.subn(rf'({key}=")[^"]*(")', rf"\g<1>{val}\g<2>", attrs)
            if not n:
                attrs += f' {key}="{val}"'
        return f"<hp:pageNum{attrs}/>"

    new, n = _PAGENUM_RE.subn(_upd, sec)
    if n:
        return new, n
    ctrl = (f'<hp:ctrl><hp:pageNum pos="{pos or "BOTTOM_CENTER"}" '
            f'formatType="{fmt or "DIGIT"}" '
            f'sideChar="{side_char if side_char is not None else "-"}"/></hp:ctrl>')
    return _insert_ctrl(sec, ctrl), 1


def remove_pagenum(sec):
    return re.subn(r"<hp:ctrl><hp:pageNum\b[^>]*/></hp:ctrl>", "", sec)


# ──────────────────────────────────────────────────────────────────────────
# 표 구조 op — 문자열 수술(정규식) + 가드
#   중첩 표를 품은 표는 tc/tr 매칭이 안쪽 표까지 잡으므로 모든 op 거부.
#   병합(span) 표는 colAddr/rowAddr 재계산이 불가능해 구조 op 거부(set-cell 허용).
# ──────────────────────────────────────────────────────────────────────────
_TBL_TOKEN_RE = re.compile(r"<hp:tbl\b|</hp:tbl>")
_TC_RE = re.compile(r"<hp:tc\b.*?</hp:tc>", re.S)
_TR_RE = re.compile(r"<hp:tr\b[^>]*>.*?</hp:tr>", re.S)


def _find_tables(sec):
    """섹션 내 최상위 <hp:tbl> 블록 (start, end) 목록(문서 순서)."""
    spans, depth, start = [], 0, 0
    for m in _TBL_TOKEN_RE.finditer(sec):
        if m.group(0).startswith("<hp:tbl"):
            if depth == 0:
                start = m.start()
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                spans.append((start, m.end()))
    return spans


def _doc_tables(parts):
    """문서 순서의 (섹션명, start, end) 표 목록 — 머리말/꼬리말 내부 표는 제외."""
    out = []
    for name in sorted(n for n in parts if re.match(r"Contents/section\d+\.xml$", n)):
        sec = parts[name].decode("utf-8")
        hf = _hf_blocks(sec, "header") + _hf_blocks(sec, "footer")
        for s, e in _find_tables(sec):
            if any(hs <= s and e <= he for hs, he in hf):
                continue
            out.append((name, s, e))
    return out


def _locate_table(parts, t_idx):
    """문서 전체 표 순번(1-based, 머리말/꼬리말 제외) → (섹션명, start, end)."""
    tables = _doc_tables(parts)
    if not 1 <= t_idx <= len(tables):
        raise SystemExit(f"표 #{t_idx}을 찾을 수 없습니다(문서 내 표 {len(tables)}개 — "
                         f"list-tables로 순번을 확인하세요).")
    return tables[t_idx - 1]


def list_tables(parts):
    """[(순번, rowCnt, colCnt, 첫 텍스트)] — 표 순번 확인용."""
    rows = []
    for i, (name, s, e) in enumerate(_doc_tables(parts), 1):
        tbl = parts[name].decode("utf-8")[s:e]
        texts = re.findall(r"<hp:t(?:\s[^>]*)?>([^<]{1,40})", tbl)
        first = next((t.strip() for t in texts if t.strip()), "")
        rows.append((i, _attr(tbl, "rowCnt"), _attr(tbl, "colCnt"), first))
    return rows


def _attr(block, key, default=None):
    m = re.search(rf'\b{key}="([^"]*)"', block)
    return m.group(1) if m else default


def _set_attr(block, key, value):
    return re.sub(rf'(\b{key}=")[^"]*(")', rf"\g<1>{value}\g<2>", block, count=1)


def _cells(tbl):
    """[(start, end, col, row, colspan, rowspan)] — tbl 블록 기준 오프셋."""
    out = []
    for m in _TC_RE.finditer(tbl):
        tc = m.group(0)
        addr = re.search(r'<hp:cellAddr colAddr="(\d+)" rowAddr="(\d+)"/>', tc)
        span = re.search(r'<hp:cellSpan colSpan="(\d+)" rowSpan="(\d+)"/>', tc)
        out.append((m.start(), m.end(), int(addr.group(1)), int(addr.group(2)),
                    int(span.group(1)) if span else 1,
                    int(span.group(2)) if span else 1))
    return out


def _guard_table(tbl, op, structural):
    inner = tbl[len("<hp:tbl"):]
    if "<hp:tbl" in inner:
        raise SystemExit(f"{op}: 중첩 표를 품은 표는 편집할 수 없습니다.")
    if structural and any(cs > 1 or rs > 1 for *_, cs, rs in _cells(tbl)):
        raise SystemExit(f"{op}: 병합(span)된 표는 구조 변경이 불가능합니다"
                         f"(set-cell은 가능).")


def _clone_borderfill(header_xml, src_id, bg=None, border=None):
    """src borderFill을 복제해 배경/테두리를 바꾼 borderFill의 id를 얻는다.
    동일 정의가 이미 있으면 재사용, 없으면 추가하고 itemCnt를 보정한다.
    반환: (header_xml, id)."""
    m = re.search(rf'<hh:borderFill id="{src_id}".*?</hh:borderFill>', header_xml, re.S)
    if not m:
        raise SystemExit(f"borderFill {src_id}을 header.xml에서 찾을 수 없습니다.")
    body = m.group(0)
    if border is not None:
        t = "SOLID" if border == "on" else "NONE"
        for side in ("leftBorder", "rightBorder", "topBorder", "bottomBorder"):
            body = re.sub(rf'(<hh:{side} type=")[^"]*(")', rf"\g<1>{t}\g<2>", body)
    if bg is not None:
        if bg == "none":
            body = re.sub(r"<hc:fillBrush>.*?</hc:fillBrush>", "", body, flags=re.S)
        elif "<hc:fillBrush>" in body:
            body = re.sub(r'(<hc:winBrush faceColor=")[^"]*(")',
                          rf"\g<1>#{bg}\g<2>", body)
        else:
            body = body.replace("</hh:borderFill>",
                                f'<hc:fillBrush><hc:winBrush faceColor="#{bg}" '
                                f'hatchColor="#999999" alpha="0"/></hc:fillBrush>'
                                f"</hh:borderFill>", 1)
    # 동일 정의(id 제외) 재사용
    canon = re.sub(r'^<hh:borderFill id="\d+"', "<hh:borderFill", body)
    for em in re.finditer(r'<hh:borderFill id="(\d+)".*?</hh:borderFill>',
                          header_xml, re.S):
        if re.sub(r'^<hh:borderFill id="\d+"', "<hh:borderFill", em.group(0)) == canon:
            return header_xml, em.group(1)
    new_id = str(max(int(i) for i in
                     re.findall(r'<hh:borderFill id="(\d+)"', header_xml)) + 1)
    body = re.sub(r'^(<hh:borderFill id=")\d+(")', rf"\g<1>{new_id}\g<2>", body)
    header_xml = header_xml.replace("</hh:borderFills>", body + "</hh:borderFills>", 1)
    cm = re.search(r'(<hh:borderFills itemCnt=")(\d+)(")', header_xml)
    header_xml = (header_xml[:cm.start()] + cm.group(1) + str(int(cm.group(2)) + 1)
                  + cm.group(3) + header_xml[cm.end():])
    return header_xml, new_id


def _splice(sec, s, e, new_block):
    new_block, _ = K.strip_linesegarray(new_block)  # 구조 변경 → 한글이 재계산
    return sec[:s] + new_block + sec[e:]


def op_set_cell(parts, t_idx, row, col, bg=None, border=None):
    name, s, e = _locate_table(parts, t_idx)
    sec = parts[name].decode("utf-8")
    tbl = sec[s:e]
    _guard_table(tbl, "set-cell", structural=False)
    hits = [c for c in _cells(tbl) if c[2] == col and c[3] == row]
    if not hits:
        raise SystemExit(f"set-cell: 셀(row={row}, col={col})을 찾을 수 없습니다.")
    cs, ce, *_ = hits[0]
    tc = tbl[cs:ce]
    hdr = parts["Contents/header.xml"].decode("utf-8")
    hdr, bf_id = _clone_borderfill(hdr, _attr(tc, "borderFillIDRef", "3"),
                                   bg=bg, border=border)
    tc = _set_attr(tc, "borderFillIDRef", bf_id)
    parts["Contents/header.xml"] = hdr.encode("utf-8")
    parts[name] = _splice(sec, s + cs, s + ce, tc).encode("utf-8")
    return f"표 #{t_idx} 셀({row},{col}) borderFill={bf_id}"


def _empty_texts(xml):
    return re.sub(r"(<hp:t(?:\s[^>]*)?>).*?(</hp:t>)", r"\1\2", xml, flags=re.S)


def op_add_col(parts, t_idx, at=None):
    name, s, e = _locate_table(parts, t_idx)
    sec = parts[name].decode("utf-8")
    tbl = sec[s:e]
    _guard_table(tbl, "add-col", structural=True)
    ncols = int(_attr(tbl, "colCnt"))
    at = ncols if at is None else at
    if not 0 <= at <= ncols:
        raise SystemExit(f"add-col: --at은 0..{ncols} 범위여야 합니다.")

    def _fix_tr(tr_m):
        tr = tr_m.group(0)
        cells = list(_TC_RE.finditer(tr))
        src = cells[min(at, ncols - 1)].group(0)  # 삽입 위치(끝이면 마지막) 셀 복제
        clone = _empty_texts(src)
        clone = re.sub(r'(<hp:cellAddr colAddr=")\d+(")', rf"\g<1>{at}\g<2>", clone)
        out, moved = [], False
        for m in cells:
            tc = m.group(0)
            c = int(re.search(r'colAddr="(\d+)"', tc).group(1))
            if c >= at:
                tc = re.sub(r'(<hp:cellAddr colAddr=")\d+(")',
                            rf"\g<1>{c + 1}\g<2>", tc)
            if c == at and not moved:
                out.append(clone); moved = True
            out.append(tc)
        if not moved:
            out.append(clone)  # 맨 끝에 추가
        head = tr[:cells[0].start()]
        tail = tr[cells[-1].end():]
        return head + "".join(out) + tail

    tbl = _TR_RE.sub(_fix_tr, tbl)
    tbl = _set_attr(tbl, "colCnt", ncols + 1)
    parts[name] = _splice(sec, s, e, tbl).encode("utf-8")
    return f"표 #{t_idx} 열 추가(at={at}) → colCnt={ncols + 1}"


def op_del_row(parts, t_idx, row):
    name, s, e = _locate_table(parts, t_idx)
    sec = parts[name].decode("utf-8")
    tbl = sec[s:e]
    _guard_table(tbl, "del-row", structural=True)
    nrows = int(_attr(tbl, "rowCnt"))
    if not 0 <= row < nrows:
        raise SystemExit(f"del-row: --row는 0..{nrows - 1} 범위여야 합니다.")
    if nrows == 1:
        raise SystemExit("del-row: 마지막 남은 행은 삭제할 수 없습니다(표 자체를 지우세요).")

    def _fix_tr(tr_m):
        tr = tr_m.group(0)
        r = int(re.search(r'rowAddr="(\d+)"', tr).group(1))
        if r == row:
            return ""
        if r > row:
            tr = re.sub(r'(<hp:cellAddr colAddr="\d+" rowAddr=")\d+(")',
                        lambda m: m.group(1) + str(r - 1) + m.group(2), tr)
        return tr

    tbl = _TR_RE.sub(_fix_tr, tbl)
    tbl = _set_attr(tbl, "rowCnt", nrows - 1)
    parts[name] = _splice(sec, s, e, tbl).encode("utf-8")
    return f"표 #{t_idx} 행 {row} 삭제 → rowCnt={nrows - 1}"


def op_merge_cells(parts, t_idx, r0, c0, r1, c1):
    name, s, e = _locate_table(parts, t_idx)
    sec = parts[name].decode("utf-8")
    tbl = sec[s:e]
    _guard_table(tbl, "merge-cells", structural=True)
    if r1 < r0 or c1 < c0:
        raise SystemExit("merge-cells: --to는 --from보다 크거나 같아야 합니다.")
    if (r0, c0) == (r1, c1):
        raise SystemExit("merge-cells: 병합 범위가 한 칸입니다.")
    cells = _cells(tbl)
    grid = {(c[3], c[2]): c for c in cells}
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            if (r, c) not in grid:
                raise SystemExit(f"merge-cells: 셀({r},{c})이 없습니다(범위 초과).")
    width = sum(int(_attr(tbl[grid[(r0, c)][0]:grid[(r0, c)][1]], "width"))
                for c in range(c0, c1 + 1))
    height = sum(int(_attr(tbl[grid[(r, c0)][0]:grid[(r, c0)][1]], "height"))
                 for r in range(r0, r1 + 1))
    out, last = [], 0
    for cs, ce, c, r, *_ in cells:
        out.append(tbl[last:cs])
        tc = tbl[cs:ce]
        if (r, c) == (r0, c0):  # 앵커: span·크기 확장
            tc = tc.replace('<hp:cellSpan colSpan="1" rowSpan="1"/>',
                            f'<hp:cellSpan colSpan="{c1 - c0 + 1}" '
                            f'rowSpan="{r1 - r0 + 1}"/>', 1)
            tc = re.sub(r'(<hp:cellSz width=")\d+(" height=")\d+(")',
                        rf"\g<1>{width}\g<2>{height}\g<3>", tc, count=1)
            out.append(tc)
        elif r0 <= r <= r1 and c0 <= c <= c1:
            pass  # 덮인 셀 제거
        else:
            out.append(tc)
        last = ce
    out.append(tbl[last:])
    parts[name] = _splice(sec, s, e, "".join(out)).encode("utf-8")
    return f"표 #{t_idx} 셀 병합 ({r0},{c0})-({r1},{c1})"


def _edit_table(input_path, output_path, fn):
    """표 op 실행: parts를 fn으로 수술하고 변경 엔트리만 서식 보존 기록."""
    parts, _ = K.read_package(input_path)
    orig = dict(parts)
    msg = fn(parts)
    changed = {n: d for n, d in parts.items() if orig.get(n) != d}
    K.write_package_preserving(input_path, output_path, changed)
    K.fix_namespaces(output_path)
    return msg


def _edit_sections(input_path, output_path, fn, first_only=False):
    """섹션별로 fn(sec)->(sec, n)을 적용하고 서식 보존 기록. 총 적용 수 반환."""
    parts, _ = K.read_package(input_path)
    names = sorted(n for n in parts if re.match(r"Contents/section\d+\.xml$", n))
    if not names:
        raise SystemExit("section*.xml을 찾을 수 없습니다(유효한 HWPX가 아님).")
    total, changed = 0, {}
    for name in names:
        sec = parts[name].decode("utf-8")
        new, n = fn(sec)
        total += n
        if new != sec:
            changed[name] = new.encode("utf-8")
        if first_only:
            break
    K.write_package_preserving(input_path, output_path, changed)
    K.fix_namespaces(output_path)
    return total


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="HWPX 머리말·꼬리말·쪽번호 in-place 편집")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, text=False):
        p.add_argument("input", help="원본 HWPX")
        p.add_argument("--output", required=True, help="결과 HWPX")
        if text:
            p.add_argument("--text", required=True, help="넣을 텍스트")
            p.add_argument("--apply", choices=["BOTH", "EVEN", "ODD"],
                           help="적용 쪽(미지정 시 기존값 보존/생성 시 BOTH)")

    common(sub.add_parser("set-header", help="머리말 텍스트 설정(전 슬롯)"), text=True)
    common(sub.add_parser("set-footer", help="꼬리말 텍스트 설정(전 슬롯)"), text=True)
    common(sub.add_parser("remove-header", help="머리말 제거"))
    common(sub.add_parser("remove-footer", help="꼬리말 제거"))
    common(sub.add_parser("remove-pagenum", help="쪽번호 제거"))
    pn = sub.add_parser("set-pagenum", help="쪽번호 설정(기존값 보존 갱신)")
    common(pn)
    pn.add_argument("--pos", choices=["TOP_LEFT", "TOP_CENTER", "TOP_RIGHT",
                                      "BOTTOM_LEFT", "BOTTOM_CENTER", "BOTTOM_RIGHT"])
    pn.add_argument("--format", dest="fmt",
                    choices=["DIGIT", "CIRCLED_DIGIT", "ROMAN_CAPITAL", "ROMAN_SMALL",
                             "LATIN_CAPITAL", "LATIN_SMALL", "HANGUL_SYLLABLE"])
    pn.add_argument("--side-char", dest="side_char", help='쪽번호 양옆 문자(예: "-", "")')

    def table_common(p, need_row=False, need_col=False):
        p.add_argument("input", help="원본 HWPX")
        p.add_argument("--output", required=True, help="결과 HWPX")
        p.add_argument("--table", type=int, required=True,
                       help="문서 전체 표 순번(1-based)")
        if need_row:
            p.add_argument("--row", type=int, required=True, help="행(0-based)")
        if need_col:
            p.add_argument("--col", type=int, required=True, help="열(0-based)")

    lt = sub.add_parser("list-tables", help="표 순번·크기·첫 텍스트 나열")
    lt.add_argument("input", help="HWPX 경로")

    sc = sub.add_parser("set-cell", help="셀 배경/테두리 변경")
    table_common(sc, need_row=True, need_col=True)
    sc.add_argument("--bg", help="배경색 6자리 hex(예: D9D9D9) 또는 none(채움 제거)")
    sc.add_argument("--border", choices=["on", "off"], help="네 방향 테두리 켬/끔")
    ac = sub.add_parser("add-col", help="열 추가(기본 맨 끝)")
    table_common(ac)
    ac.add_argument("--at", type=int, help="삽입 위치(0-based, 기본 맨 끝)")
    table_common(sub.add_parser("del-row", help="행 삭제"), need_row=True)
    mc = sub.add_parser("merge-cells", help="사각 범위 셀 병합")
    table_common(mc)
    mc.add_argument("--from", dest="frm", required=True, metavar="R,C",
                    help="병합 시작 셀(예: 0,0)")
    mc.add_argument("--to", dest="to", required=True, metavar="R,C",
                    help="병합 끝 셀(예: 1,1)")

    a = ap.parse_args()

    if a.cmd in ("set-header", "set-footer"):
        tag = a.cmd.split("-")[1]
        n = _edit_sections(a.input, a.output,
                           lambda s: set_headerfooter(s, tag, a.text, a.apply))
        print(f"{'머리말' if tag == 'header' else '꼬리말'} 갱신: {n}개 슬롯 → {a.output}")
    elif a.cmd in ("remove-header", "remove-footer"):
        tag = a.cmd.split("-")[1]
        n = _edit_sections(a.input, a.output, lambda s: remove_headerfooter(s, tag))
        print(f"{'머리말' if tag == 'header' else '꼬리말'} 제거: {n}개 → {a.output}")
    elif a.cmd == "set-pagenum":
        n = _edit_sections(a.input, a.output,
                           lambda s: set_pagenum(s, a.pos, a.fmt, a.side_char))
        print(f"쪽번호 설정: {n}곳 → {a.output}")
    elif a.cmd == "remove-pagenum":
        n = _edit_sections(a.input, a.output, lambda s: remove_pagenum(s))
        print(f"쪽번호 제거: {n}곳 → {a.output}")
    elif a.cmd == "list-tables":
        parts, _ = K.read_package(a.input)
        rows = list_tables(parts)
        if not rows:
            print("표 없음(머리말/꼬리말 내부 표는 제외)")
        for i, rc, cc, first in rows:
            print(f"표 #{i}: {rc}행 × {cc}열  {first!r}")
    elif a.cmd == "set-cell":
        if a.bg is None and a.border is None:
            raise SystemExit("set-cell: --bg 또는 --border 중 하나는 필요합니다.")
        if a.bg and a.bg != "none" and not re.fullmatch(r"[0-9A-Fa-f]{6}", a.bg):
            raise SystemExit("set-cell: --bg는 6자리 hex(예: D9D9D9) 또는 none.")
        msg = _edit_table(a.input, a.output,
                          lambda p: op_set_cell(p, a.table, a.row, a.col,
                                                bg=a.bg, border=a.border))
        print(f"{msg} → {a.output}")
    elif a.cmd == "add-col":
        msg = _edit_table(a.input, a.output,
                          lambda p: op_add_col(p, a.table, a.at))
        print(f"{msg} → {a.output}")
    elif a.cmd == "del-row":
        msg = _edit_table(a.input, a.output,
                          lambda p: op_del_row(p, a.table, a.row))
        print(f"{msg} → {a.output}")
    elif a.cmd == "merge-cells":
        try:
            r0, c0 = map(int, a.frm.split(","))
            r1, c1 = map(int, a.to.split(","))
        except ValueError:
            raise SystemExit('merge-cells: --from/--to는 "행,열" 형식(예: 0,0).')
        msg = _edit_table(a.input, a.output,
                          lambda p: op_merge_cells(p, a.table, r0, c0, r1, c1))
        print(f"{msg} → {a.output}")


if __name__ == "__main__":
    main()

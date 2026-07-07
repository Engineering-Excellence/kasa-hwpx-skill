#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hwpx_edit.py — 기존 HWPX의 머리말·꼬리말·쪽번호 in-place 편집(서식 보존).

원본의 서식·zip 메타데이터를 보존한 채(변경 섹션만 교체) 편집한다.
(참고: jkf87/hwpx-skill fill_hwpx의 set-header/set-footer/set-pagenum 접근)

사용법:
  python3 hwpx_edit.py set-header  문서.hwpx --text "머리말" --output 결과.hwpx
  python3 hwpx_edit.py set-footer  문서.hwpx --text "꼬리말" --output 결과.hwpx
  python3 hwpx_edit.py set-pagenum 문서.hwpx [--pos BOTTOM_CENTER] [--format DIGIT]
                                   [--side-char "-"] --output 결과.hwpx
  python3 hwpx_edit.py remove-header|remove-footer|remove-pagenum 문서.hwpx --output 결과.hwpx

규칙:
  - 슬롯(머리말/꼬리말)이 여러 개면 전부 갱신한다.
  - 미지정 옵션은 기존값을 보존한다(set-pagenum의 pos/format/side-char).
  - 슬롯이 없으면 새로 만든다(applyPageType은 --apply, 기본 BOTH).
  - KASA 표준보고서의 머리말에는 MI 로고(표+이미지)가 있다 — set-header는
    개체를 보존한 채 텍스트만 넣지만, KASA 문서에서는 머리말 대신
    꼬리말·쪽번호 편집을 권장한다.
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


if __name__ == "__main__":
    main()

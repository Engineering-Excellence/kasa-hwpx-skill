#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kasa_lib.py — 우주항공청(KASA) 표준보고서 HWPX 엔진 (표준 라이브러리만 사용)

설계 원칙
  - 첨부된 우주항공청 표준양식(.hwpx)을 단일 기준(SSOT)으로 삼는다.
  - 표지·MI 로고·머리말·편집용지(여백/줄간격)는 원본 바이트를 그대로 보존한다.
  - 표지 필드 텍스트만 치환하고, 본문 영역만 사양(spec)에 따라 재생성한다.
  - charPr/paraPr 등 스타일 ID는 양식에서 추출한 검증된 값만 사용한다(임의 생성 금지).

외부 패키지 의존성 없음(zipfile, re, os, json만 사용) → 네트워크 없는 환경에서 동작.
"""
import os, re, io, json, zipfile, random

# ──────────────────────────────────────────────────────────────────────────
# 검증된 스타일 ID 맵 (templates/kasa 분석 결과)
#   글꼴: 0=맑은 고딕, 3=함초롬바탕, 5=HY견고딕, 6=HY헤드라인M
# ──────────────────────────────────────────────────────────────────────────
# 본문 위계: (마커, 들여쓰기, charPrIDRef, height[HWPUNIT=pt*100])  paraPr는 공통 3
BODY_LEVELS = {
    "title":    {"marker": "□ ", "indent": "",      "cp": "30", "h": 1500},  # HY헤드라인M 15pt
    "content":  {"marker": "ㅇ ", "indent": " ",     "cp": "41", "h": 1500},  # 함초롬바탕 15pt
    "sub":      {"marker": "- ", "indent": "   ",    "cp": "41", "h": 1500},  # 함초롬바탕 15pt
    "note":     {"marker": "※ ", "indent": "     ",  "cp": "29", "h": 1200},  # 맑은 고딕 12pt
    "footnote": {"marker": "* ", "indent": "     ",  "cp": "29", "h": 1200},  # 맑은 고딕 12pt
    "plain":    {"marker": "",   "indent": "",       "cp": "41", "h": 1500},
}
BODY_PARAPR = "3"

# 표지 필드: 양식 내 고유 앵커(주석 텍스트 또는 고유 본문)로 해당 문단을 찾는다.
COVER_ANNOTATIONS = ["(HY헤드라인M, 30Pt)", "(함초롬바탕, 24Pt)", "(HY헤드라인M, 20Pt)"]
SLOGAN_LEAD_DEFAULT = "우주항공 5대 강국 입국을 주도하는"

# 표 스타일(데이터 표 분석 결과)
TBL_TOTAL_W = 47622
TBL_COLS_3 = [13893, 18987, 14742]
TBL_TITLE = {"bf": "8",  "pp": "13", "cp": "9"}    # 제목행(병합) 13pt bold
TBL_HEAD  = {"bf": "11", "pp": "14", "cp": "17"}   # 머리행 12pt bold, 음영
TBL_LABEL = {"bf": "3",  "pp": "14", "cp": "17"}   # 데이터행 첫 칸(구분) 12pt bold
TBL_DATA  = {"bf": "3",  "pp": "17", "cp": "31"}   # 데이터 셀 12pt

# 참고/붙임 — 머리 디자인(좌측 남색 박스 + 굵은 밑줄 제목칸 3칸 표)
#   표준양식 검증 ID로만 구성:
#   - 박스칸  : borderFill 16(남색 #00294B 채움) + charPr 2 (흰색 16pt HY헤드라인M) + paraPr 11(가운데)
#   - 간격칸  : borderFill 1 (무테·무채움)
#   - 제목칸  : borderFill 17(하단 0.5mm 굵은 밑줄) + charPr 63(검정 16pt HY헤드라인M) + paraPr 3
APX_HDR = {
    "total_w": 48159,
    "box_w": 5968,  "gap_w": 565,  "title_w": 41626,  "row_h": 2831,
    "box_bf": "16", "box_cp": "2",  "box_pp": "11",
    "gap_bf": "1",  "gap_cp": "7",  "gap_pp": "3",
    "ttl_bf": "17", "ttl_cp": "63", "ttl_pp": "3",
}

# [중요] 본문 흐름 문단에는 linesegarray(줄 위치 캐시)를 넣지 않는다.
#   원본 양식의 본문 lineseg는 vertpos가 '문단 단위 상대값'이 아니라 텍스트영역
#   기준 '누적 절대값'(예: 8383 → 15583 …)이다. 모든 문단에 vertpos="0"을 박으면
#   한글이 그 캐시를 신뢰해 전 문단을 같은 높이(맨 위)에 겹쳐 그린다.
#   캐시를 비워 두면 한글이 문서를 열 때 줄 위치를 스스로 재계산(relayout)하므로
#   긴 문장의 자동 줄바꿈까지 정확히 배치된다. (한글이 재저장하면 올바른 vertpos를
#   생성하는 것으로 검증됨)
_LINESEG = ""  # 흐름 문단/표 래퍼/셀 모두 캐시 없이 생성 → 한글이 재계산

# ──────────────────────────────────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────────────────────────────────
_id_state = [4000]
def next_id():
    _id_state[0] += 1
    return _id_state[0]

def xml_escape(t):
    return (t.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))

# ──────────────────────────────────────────────────────────────────────────
# HWPX 패키지 입출력 (mimetype 규칙 준수)
# ──────────────────────────────────────────────────────────────────────────
def read_package(path):
    """HWPX(zip)의 모든 엔트리를 {이름: bytes}로 읽는다."""
    parts = {}
    with zipfile.ZipFile(path, "r") as z:
        order = z.namelist()
        for name in order:
            parts[name] = z.read(name)
    return parts, order

def write_package(path, parts, order):
    """mimetype을 첫 엔트리·무압축으로 기록하여 HWPX 규칙을 지킨다."""
    names = [n for n in order if n in parts]
    for n in parts:
        if n not in names:
            names.append(n)
    if "mimetype" in names:
        names.remove("mimetype")
        names.insert(0, "mimetype")
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w") as z:
        for name in names:
            data = parts[name]
            if name == "mimetype":
                zi = zipfile.ZipInfo("mimetype")
                zi.compress_type = zipfile.ZIP_STORED
                z.writestr(zi, data)
            else:
                z.writestr(name, data, zipfile.ZIP_DEFLATED)
    os.replace(tmp, path)

# ──────────────────────────────────────────────────────────────────────────
# 본문 문단/표 빌더
# ──────────────────────────────────────────────────────────────────────────
def make_para(text, cp, pp=BODY_PARAPR, h=1500, w=48188, page_break="0"):
    return (f'<hp:p id="{next_id()}" paraPrIDRef="{pp}" styleIDRef="0" '
            f'pageBreak="{page_break}" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="{cp}"><hp:t>{xml_escape(text)}</hp:t></hp:run>'
            f'{_LINESEG}</hp:p>')

def make_body_line(level, text, page_break="0"):
    if level not in BODY_LEVELS:
        raise ValueError(f"알 수 없는 본문 레벨: {level} (가능: {list(BODY_LEVELS)})")
    L = BODY_LEVELS[level]
    return make_para(L["indent"] + L["marker"] + text, L["cp"],
                     h=L["h"], page_break=page_break)

def make_empty(page_break="0"):
    return make_para("", "41", h=1500, page_break=page_break)

def _cell(text, col, row, colspan, style, w, h=282, header="0"):
    nid = next_id()
    inner = (f'<hp:p id="{nid}" paraPrIDRef="{style["pp"]}" styleIDRef="0" '
             f'pageBreak="0" columnBreak="0" merged="0">'
             f'<hp:run charPrIDRef="{style["cp"]}"><hp:t>{xml_escape(text)}</hp:t></hp:run>'
             + _LINESEG + '</hp:p>')
    return (f'<hp:tc name="" header="{header}" hasMargin="0" protect="0" editable="0" '
            f'dirty="0" borderFillIDRef="{style["bf"]}">'
            f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" '
            f'vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" '
            f'textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">{inner}</hp:subList>'
            f'<hp:cellAddr colAddr="{col}" rowAddr="{row}"/>'
            f'<hp:cellSpan colSpan="{colspan}" rowSpan="1"/>'
            f'<hp:cellSz width="{w}" height="{h}"/>'
            f'<hp:cellMargin left="510" right="510" top="141" bottom="141"/></hp:tc>')

def make_table(headers, rows, title=None):
    """KASA 표준 표 생성. headers: [str], rows: [[str,...]], title: 선택."""
    ncols = len(headers)
    if ncols == 0:
        raise ValueError("표에는 최소 1개 이상의 열 머리글이 필요합니다.")
    for r in rows:
        if len(r) != ncols:
            raise ValueError(f"행의 칸 수({len(r)})가 머리글 수({ncols})와 다릅니다: {r}")
    widths = TBL_COLS_3[:] if ncols == 3 else \
             [TBL_TOTAL_W // ncols] * (ncols - 1) + [TBL_TOTAL_W - (TBL_TOTAL_W // ncols) * (ncols - 1)]

    trs, r = [], 0
    if title:
        trs.append('<hp:tr>' + _cell(title, 0, r, ncols, TBL_TITLE, TBL_TOTAL_W, 300, "1") + '</hp:tr>')
        r += 1
    # 머리행
    cells = "".join(_cell(h, c, r, 1, TBL_HEAD, widths[c], 282, "1") for c, h in enumerate(headers))
    trs.append('<hp:tr>' + cells + '</hp:tr>'); r += 1
    # 데이터행 (첫 칸은 구분 라벨 → bold)
    for row in rows:
        cells = ""
        for c, v in enumerate(row):
            style = TBL_LABEL if c == 0 else TBL_DATA
            cells += _cell(v, c, r, 1, style, widths[c], 282, "0")
        trs.append('<hp:tr>' + cells + '</hp:tr>'); r += 1

    rowcnt = r
    tbl = (f'<hp:tbl id="{random.randint(10**8, 2*10**9)}" zOrder="0" numberingType="TABLE" '
           f'textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" '
           f'pageBreak="CELL" repeatHeader="1" rowCnt="{rowcnt}" colCnt="{ncols}" '
           f'cellSpacing="0" borderFillIDRef="3" noAdjust="0">'
           f'<hp:sz width="{TBL_TOTAL_W}" widthRelTo="ABSOLUTE" height="{rowcnt*600}" '
           f'heightRelTo="ABSOLUTE" protect="0"/>'
           f'<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" '
           f'holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" '
           f'horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
           f'<hp:outMargin left="283" right="283" top="283" bottom="283"/>'
           f'<hp:inMargin left="510" right="510" top="141" bottom="141"/>'
           + "".join(trs) + '</hp:tbl>')
    return (f'<hp:p id="{next_id()}" paraPrIDRef="12" styleIDRef="0" pageBreak="0" '
            f'columnBreak="0" merged="0"><hp:run charPrIDRef="15">{tbl}<hp:t/></hp:run>'
            f'{_LINESEG}</hp:p>')

def _apx_cell(text, col, bf, cp, pp, w, h):
    """참고 머리 표의 단일 셀(캐시 없는 단일 문단 포함)."""
    inner = (f'<hp:p id="{next_id()}" paraPrIDRef="{pp}" styleIDRef="0" '
             f'pageBreak="0" columnBreak="0" merged="0">'
             f'<hp:run charPrIDRef="{cp}"><hp:t>{xml_escape(text)}</hp:t></hp:run>'
             f'{_LINESEG}</hp:p>')
    return (f'<hp:tc name="" header="0" hasMargin="0" protect="0" editable="0" '
            f'dirty="0" borderFillIDRef="{bf}">'
            f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" '
            f'vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" '
            f'textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">{inner}</hp:subList>'
            f'<hp:cellAddr colAddr="{col}" rowAddr="0"/>'
            f'<hp:cellSpan colSpan="1" rowSpan="1"/>'
            f'<hp:cellSz width="{w}" height="{h}"/>'
            f'<hp:cellMargin left="141" right="141" top="141" bottom="141"/></hp:tc>')

def make_appendix_header(label, heading, page_break="1"):
    """참고 머리: [남색 '참고' 박스] [간격] [굵은 밑줄 제목] 3칸 표.
    label   : 박스 텍스트(예: '참고', '참고 1')
    heading : 제목 텍스트(앞에 한 칸 들여 표시)
    """
    A = APX_HDR
    cells = (
        _apx_cell(label, 0, A["box_bf"], A["box_cp"], A["box_pp"], A["box_w"], A["row_h"])
        + _apx_cell("", 1, A["gap_bf"], A["gap_cp"], A["gap_pp"], A["gap_w"], A["row_h"])
        + _apx_cell(" " + (heading or ""), 2, A["ttl_bf"], A["ttl_cp"], A["ttl_pp"],
                    A["title_w"], A["row_h"])
    )
    tbl = (f'<hp:tbl id="{random.randint(10**8, 2*10**9)}" zOrder="0" numberingType="TABLE" '
           f'textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" '
           f'pageBreak="CELL" repeatHeader="1" rowCnt="1" colCnt="3" '
           f'cellSpacing="0" borderFillIDRef="3" noAdjust="0">'
           f'<hp:sz width="{A["total_w"]}" widthRelTo="ABSOLUTE" height="{A["row_h"]}" '
           f'heightRelTo="ABSOLUTE" protect="0"/>'
           f'<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" '
           f'holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" '
           f'horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
           f'<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
           f'<hp:inMargin left="141" right="141" top="141" bottom="141"/>'
           f'<hp:tr>{cells}</hp:tr></hp:tbl>')
    return (f'<hp:p id="{next_id()}" paraPrIDRef="12" styleIDRef="0" pageBreak="{page_break}" '
            f'columnBreak="0" merged="0"><hp:run charPrIDRef="14">{tbl}<hp:t/></hp:run>'
            f'{_LINESEG}</hp:p>')

# ──────────────────────────────────────────────────────────────────────────
# 표지 필드 치환 (앵커 문단 범위에서 <hp:t> 텍스트만 교체, 주석런 제거)
# ──────────────────────────────────────────────────────────────────────────
def _set_field_by_anchor(sec, anchor, value):
    """anchor 문자열이 포함된 (표 비포함) 문단을 찾아 첫 <hp:t>=value, 나머지 비움."""
    pos = sec.find(anchor)
    if pos == -1:
        return sec
    p0 = sec.rfind("<hp:p ", 0, pos)
    p1 = sec.find("</hp:p>", pos) + len("</hp:p>")
    para = sec[p0:p1]
    ts = list(re.finditer(r"<hp:t>.*?</hp:t>|<hp:t/>", para, re.S))
    if not ts:
        return sec
    def repl(i, m):
        if i == 0:
            return f"<hp:t>{xml_escape(value)}</hp:t>"
        return "<hp:t></hp:t>"
    out, last = [], 0
    for i, m in enumerate(ts):
        out.append(para[last:m.start()]); out.append(repl(i, m)); last = m.end()
    out.append(para[last:])
    return sec[:p0] + "".join(out) + sec[p1:]

def _replace_unique_text(sec, old, new):
    return sec.replace(f"<hp:t>{old}</hp:t>", f"<hp:t>{xml_escape(new)}</hp:t>", 1)

# ──────────────────────────────────────────────────────────────────────────
# 본문 생성 (사양 → XML)
# ──────────────────────────────────────────────────────────────────────────
def _build_body_xml(spec):
    parts = []
    first = True
    for item in spec.get("body", []):
        if item.get("type") == "table":
            parts.append(make_table(item.get("headers", []), item.get("rows", []),
                                     item.get("title")))
        else:
            lvl = item.get("level", "content")
            parts.append(make_body_line(lvl, item.get("text", ""),
                                        page_break=("0")))
        first = False
    # 참고/붙임 — 좌측 남색 박스 + 굵은 밑줄 제목칸 머리 디자인
    for n, apx in enumerate(spec.get("appendix", []), start=1):
        label = apx.get("label", f"참고 {n}")
        heading = apx.get("heading", "")
        parts.append(make_appendix_header(label, heading, page_break="1"))
        for item in apx.get("body", []):
            if item.get("type") == "table":
                parts.append(make_table(item.get("headers", []), item.get("rows", []),
                                        item.get("title")))
            else:
                parts.append(make_body_line(item.get("level", "content"), item.get("text", "")))
    return "".join(parts)

# ──────────────────────────────────────────────────────────────────────────
# 메인: 사양 → 보고서 HWPX
# ──────────────────────────────────────────────────────────────────────────
def build_report(template_path, spec, out_path):
    parts, order = read_package(template_path)
    sec = parts["Contents/section0.xml"].decode("utf-8")

    # 1) 표지/제목/작성정보 치환 + 주석런 제거
    if spec.get("slogan_lead"):
        sec = _replace_unique_text(sec, SLOGAN_LEAD_DEFAULT, spec["slogan_lead"])
    if spec.get("pub_date"):
        sec = _set_field_by_anchor(sec, "(함초롬바탕, 24Pt)", spec["pub_date"])
    if spec.get("title"):
        sec = _set_field_by_anchor(sec, "(HY헤드라인M, 20Pt)", spec["title"])
    if spec.get("author"):
        sec = _replace_unique_text(sec, "(’26.00.00., 행정법무담당관)", spec["author"])
    # 표지 슬로건 기관명 주석 제거(텍스트는 우주항공청 유지)
    sec = _set_field_by_anchor(sec, "(HY헤드라인M, 30Pt)", "우주항공청")

    # 2) 본문 영역 교체: 유일 앵커 '□ 제목1' 문단 ~ </hs:sec> 직전까지 제거 후 재생성
    anchor = "□ 제목1"
    apos = sec.find(anchor)
    body_start = sec.rfind("<hp:p ", 0, apos)
    sec_close = sec.rfind("</hs:sec>")
    new_body = _build_body_xml(spec)
    sec = sec[:body_start] + new_body + sec[sec_close:]

    parts["Contents/section0.xml"] = sec.encode("utf-8")
    write_package(out_path, parts, order)
    fix_namespaces(out_path)
    return out_path

# ──────────────────────────────────────────────────────────────────────────
# WF-B: 기존 KASA 양식의 플레이스홀더/텍스트 단순 치환 (서식 100% 보존)
# ──────────────────────────────────────────────────────────────────────────
def fill_template(template_path, replacements, out_path):
    parts, order = read_package(template_path)
    for name in list(parts):
        if name.startswith("Contents/") and name.endswith(".xml"):
            t = parts[name].decode("utf-8")
            for old, new in replacements.items():
                t = t.replace(old, xml_escape(new))
            parts[name] = t.encode("utf-8")
    write_package(out_path, parts, order)
    fix_namespaces(out_path)
    return out_path

# ──────────────────────────────────────────────────────────────────────────
# 네임스페이스 점검(접두사 보존 확인) — 본 엔진은 원본 접두사를 보존하므로 안전망 역할
# ──────────────────────────────────────────────────────────────────────────
REQUIRED_NS = {
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
}
def fix_namespaces(path):
    parts, order = read_package(path)
    sec = parts.get("Contents/section0.xml", b"").decode("utf-8")
    m = re.search(r"<hs:sec\b[^>]*>", sec)
    root = m.group(0) if m else ""
    missing = [p for p in REQUIRED_NS if f"xmlns:{p}=" not in root]
    if missing:
        raise RuntimeError(f"section0.xml 루트에 네임스페이스 선언 누락: {missing}")
    return True

# ──────────────────────────────────────────────────────────────────────────
# 텍스트 추출
# ──────────────────────────────────────────────────────────────────────────
def extract_text(path):
    parts, _ = read_package(path)
    out = []
    for name in sorted(parts):
        if re.match(r"Contents/section\d+\.xml", name):
            xml = parts[name].decode("utf-8")
            for m in re.finditer(r"<hp:t>(.*?)</hp:t>", xml, re.S):
                t = (m.group(1).replace("&lt;", "<").replace("&gt;", ">")
                     .replace("&quot;", '"').replace("&amp;", "&")).strip()
                if t:
                    out.append(t)
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    print("kasa_lib: 직접 실행 대신 build_report.py / validate.py 등을 사용하세요.")

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

# 참고/붙임
APX_LABEL = {"cp": "15", "pp": "12"}   # "참고 N"
APX_TITLE = {"cp": "63", "pp": "3"}    # 참고 제목 16pt

_LINESEG = ('<hp:linesegarray><hp:lineseg textpos="0" vertpos="0" vertsize="{h}" '
            'textheight="{h}" baseline="{b}" spacing="600" horzpos="0" '
            'horzsize="{w}" flags="393216"/></hp:linesegarray>')

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
    seg = _LINESEG.format(h=h, b=int(h * 0.85), w=w)
    return (f'<hp:p id="{next_id()}" paraPrIDRef="{pp}" styleIDRef="0" '
            f'pageBreak="{page_break}" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="{cp}"><hp:t>{xml_escape(text)}</hp:t></hp:run>'
            f'{seg}</hp:p>')

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
             + _LINESEG.format(h=1200, b=1020, w=max(w - 1000, 1000)) + '</hp:p>')
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
    seg = _LINESEG.format(h=rowcnt*600, b=0, w=TBL_TOTAL_W)
    return (f'<hp:p id="{next_id()}" paraPrIDRef="12" styleIDRef="0" pageBreak="0" '
            f'columnBreak="0" merged="0"><hp:run charPrIDRef="15">{tbl}<hp:t/></hp:run>'
            f'{seg}</hp:p>')

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
    # 참고/붙임
    for n, apx in enumerate(spec.get("appendix", []), start=1):
        label = apx.get("label", f"참고 {n}")
        parts.append(make_para(label, APX_LABEL["cp"], pp=APX_LABEL["pp"], h=1500,
                               page_break="1"))
        if apx.get("heading"):
            parts.append(make_para(apx["heading"], APX_TITLE["cp"], pp=APX_TITLE["pp"], h=1600))
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

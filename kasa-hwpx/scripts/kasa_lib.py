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
# 본문 위계: 기준 양식 방식 = '선행 공백으로 항목 시작, 내어쓰기로 2줄 이상 정렬'.
#   [HWP 내어쓰기 모델] 첫 줄 시작 = 왼쪽여백(left), 나머지 줄 시작 = left + |intent|.
#     → 첫 줄 시작 위치는 반드시 0 (left=0). 마커 위치는 '선행 공백'으로만 조정한다.
#     → 2줄 이상일 때만 '나머지 줄 시작'을 첫 글자 위치에 맞춘다: |intent| = 첫 글자 위치(접두부 폭).
#   접두부 폭 = '나머지 줄 시작'(|intent|). 함초롬바탕·맑은고딕은 한글=전각(1em),
#   ASCII(공백·-·*)=반각(0.5em). 접두부를 em 배수로 계산해 글자크기에 정확히 맞춘다.
#     content " ㅇ "      = 0.5+1+0.5 = 2.0em ×15pt = 3000
#     sub     "   - "     = 1.5+0.5+0.5 = 2.5em ×15pt = 3750
#     note    "     ※ "@12= 2.5+1+0.5 = 4.0em ×12pt = 4800
#     footnote"     * "@12= 2.5+0.5+0.5 = 3.5em ×12pt = 4200
#   (id, src=복제원본 paraPr, left[항상 0], intent[=-접두부 폭])
INDENT_PARAPR = [("22", "3", 0, -3000), ("23", "3", 0, -3750),
                 ("24", "3", 0, -4800), ("25", "3", 0, -4200),
                 # 표 셀: 원본 13/14/17은 intent=-2440(내어쓰기) → 0으로 복제(표 내부 내어쓰기 금지)
                 ("26", "13", 0, 0), ("27", "14", 0, 0), ("28", "17", 0, 0)]

# 항목 앞 간격(빈 줄 스페이서) — 첨부 양식과 동일: □ 15pt, ㅇ 10pt, - 5pt, ※/* 3pt, 표 5pt.
#   빈 문단의 글자높이(charPr)로 간격을 만든다(우리 템플릿: 1500=15,1000=1,500=18,300=22).
SPACER_CP = {"title": "15", "content": "1", "sub": "18",
             "note": "22", "footnote": "22", "table": "18", "plain": "1"}
BODY_LEVELS = {
    "title":    {"marker": "□ ",      "pp": "3",  "cp": "30", "h": 1500},  # □: 첫줄 0(기준 동일)
    "content":  {"marker": " ㅇ ",     "pp": "22", "cp": "41", "h": 1500},  # 선행1칸, 첫줄 0 + 내어쓰기
    "sub":      {"marker": "   - ",    "pp": "23", "cp": "41", "h": 1500},  # 선행3칸, 첫줄 0 + 내어쓰기
    "note":     {"marker": "     ※ ",  "pp": "24", "cp": "29", "h": 1200},  # 선행5칸, 첫줄 0 + 내어쓰기
    "footnote": {"marker": "     * ",  "pp": "25", "cp": "29", "h": 1200},  # 선행5칸, 첫줄 0 + 내어쓰기
    "plain":    {"marker": "",         "pp": "3",  "cp": "41", "h": 1500},
}
BODY_PARAPR = "3"

# 표지 필드: 양식 내 고유 앵커(주석 텍스트 또는 고유 본문)로 해당 문단을 찾는다.
COVER_ANNOTATIONS = ["(HY헤드라인M, 30Pt)", "(함초롬바탕, 24Pt)", "(HY헤드라인M, 20Pt)"]
SLOGAN_LEAD_DEFAULT = "우주항공 5대 강국 입국을 주도하는"

# 표 스타일(데이터 표 분석 결과)
TBL_TOTAL_W = 47622
TBL_COLS_3 = [13893, 18987, 14742]
TBL_TITLE = {"bf": "8",  "pp": "26", "cp": "9"}    # 제목행(병합) 13pt bold (무내어쓰기)
TBL_HEAD  = {"bf": "11", "pp": "27", "cp": "17"}   # 머리행 12pt bold, 음영 (무내어쓰기)
TBL_LABEL = {"bf": "3",  "pp": "27", "cp": "17"}   # 데이터행 첫 칸(구분) 12pt bold (무내어쓰기)
TBL_DATA  = {"bf": "3",  "pp": "28", "cp": "31"}   # 데이터 셀 12pt (무내어쓰기)

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

# linesegarray 제거용 정규식 — 속성이 붙거나 self-closing(<hp:linesegarray .../>)인
# 형태까지 포괄한다(참고: Canine89/hwpxskill finalize 가드).
LINESEG_RE = re.compile(
    r"<hp:linesegarray\b[^>]*/>|<hp:linesegarray\b[^>]*>.*?</hp:linesegarray>", re.S)

def strip_linesegarray(xml):
    """XML 문자열에서 줄 위치 캐시(linesegarray)를 모두 제거. (새 문자열, 제거 수) 반환."""
    return LINESEG_RE.subn("", xml)

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

def _inject_indent_parapr(header_xml):
    """본문 위계 들여쓰기 + 표 무내어쓰기용 paraPr을 header.xml에 주입(멱등).
    INDENT_PARAPR의 (새 id, 원본 id, left, intent)대로 원본 paraPr을 복제해
    여백·내어쓰기 값을 강제 설정한다. 본문은 paraPr 3(무번호) 복제, 표는 13/14/17 복제."""
    if all(f'<hh:paraPr id="{pid}"' in header_xml for pid, *_ in INDENT_PARAPR):
        return header_xml
    clones = []
    for pid, src, left, intent in INDENT_PARAPR:
        if f'<hh:paraPr id="{pid}"' in header_xml:
            continue
        m = re.search(rf'<hh:paraPr id="{src}".*?</hh:paraPr>', header_xml, re.S)
        if not m:
            continue
        c = m.group(0).replace(f'id="{src}"', f'id="{pid}"', 1)
        # 여백 left·내어쓰기 intent를 원본 값과 무관하게 강제 설정(hp:case·hp:default 모두)
        c = re.sub(r'(<hc:left value=")-?\d+(")', rf'\g<1>{left}\g<2>', c)
        c = re.sub(r'(<hc:intent value=")-?\d+(")', rf'\g<1>{intent}\g<2>', c)
        clones.append(c)
    if not clones:
        return header_xml
    header_xml = header_xml.replace('</hh:paraProperties>', "".join(clones) + '</hh:paraProperties>', 1)
    cm = re.search(r'(<hh:paraProperties itemCnt=")(\d+)(">)', header_xml)
    if cm:
        new_cnt = int(cm.group(2)) + len(clones)
        header_xml = header_xml[:cm.start()] + f'{cm.group(1)}{new_cnt}{cm.group(3)}' + header_xml[cm.end():]
    return header_xml

def _spacer(level):
    """항목 앞 간격용 빈 문단(스페이서). charPr 높이로 간격 크기를 만든다."""
    cp = SPACER_CP.get(level, "1")
    return (f'<hp:p id="{next_id()}" paraPrIDRef="3" styleIDRef="0" pageBreak="0" '
            f'columnBreak="0" merged="0"><hp:run charPrIDRef="{cp}"><hp:t></hp:t></hp:run></hp:p>')

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

def write_package_preserving(src_path, out_path, replacements,
                             additions=None, removals=None):
    """서식 보존 편집용 기록: 원본 HWPX의 엔트리 메타데이터(ZipInfo — 순서·시각·
    압축방식 등)를 그대로 유지하고, replacements({이름: bytes})에 있는 엔트리만
    새 내용으로 교체한다. 미변경 엔트리는 원본 압축 해제 바이트를 그대로 다시 담는다.
    additions({이름: bytes})는 원본에 없던 엔트리를 끝에 추가하고(이미지 삽입 등),
    removals(이름 집합)는 해당 엔트리를 제외한다.
    (참고: Canine89/hwpxskill 'Preserve HWPX XML bytes' — 한글이 zip 메타데이터에
    민감할 수 있어, 재기안 등 서식 보존 편집에서는 전체 재구성 대신 이 함수를 쓴다.)"""
    tmp = out_path + ".tmp"
    with zipfile.ZipFile(src_path, "r") as zin, zipfile.ZipFile(tmp, "w") as zout:
        for zi in zin.infolist():
            if removals and zi.filename in removals:
                continue
            data = replacements.get(zi.filename)
            if data is None:
                data = zin.read(zi.filename)
            zout.writestr(zi, data)
        for name, data in (additions or {}).items():
            zout.writestr(name, data, zipfile.ZIP_DEFLATED)
    os.replace(tmp, out_path)

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
    return make_para(L["marker"] + text, L["cp"], pp=L["pp"],
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
def _set_field_by_anchor(sec, anchor, value, strip_lineseg=False):
    """anchor 문자열이 포함된 (표 비포함) 문단을 찾아 첫 <hp:t>=value, 나머지 비움.
    strip_lineseg=True면 줄위치 캐시를 제거해 한글이 재계산(긴 제목 2줄 자동 줄바꿈)."""
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
    new_para = "".join(out)
    if strip_lineseg:
        new_para, _ = strip_linesegarray(new_para)
    return sec[:p0] + new_para + sec[p1:]

def _replace_unique_text(sec, old, new):
    return sec.replace(f"<hp:t>{old}</hp:t>", f"<hp:t>{xml_escape(new)}</hp:t>", 1)

# ──────────────────────────────────────────────────────────────────────────
# 본문 생성 (사양 → XML)
# ──────────────────────────────────────────────────────────────────────────
def _build_body_xml(spec):
    parts = []
    state = {"first": True}
    def emit(spacer_level, xml):
        if not state["first"]:
            parts.append(_spacer(spacer_level))   # 항목 앞 간격(빈 줄)
        parts.append(xml)
        state["first"] = False
    # 본문
    for item in spec.get("body", []):
        if item.get("type") == "table":
            emit("table", make_table(item.get("headers", []), item.get("rows", []),
                                     item.get("title")))
        else:
            lvl = item.get("level", "content")
            emit(lvl, make_body_line(lvl, item.get("text", "")))
    # 참고/붙임 — 본문과 동일한 간격·내어쓰기 적용(항목 4)
    for n, apx in enumerate(spec.get("appendix", []), start=1):
        label = apx.get("label", f"참고 {n}")
        heading = apx.get("heading", "")
        parts.append(make_appendix_header(label, heading, page_break="1"))  # 새 페이지(앞 간격 불요)
        state["first"] = False   # 머리 다음 첫 항목부터는 본문과 동일하게 간격 부여
        for item in apx.get("body", []):
            if item.get("type") == "table":
                emit("table", make_table(item.get("headers", []), item.get("rows", []),
                                         item.get("title")))
            else:
                lvl = item.get("level", "content")
                emit(lvl, make_body_line(lvl, item.get("text", "")))
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
        sec = _set_field_by_anchor(sec, "(HY헤드라인M, 20Pt)", spec["title"], strip_lineseg=True)
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
    # 본문 위계용 무번호 들여쓰기 paraPr 주입(header.xml)
    if "Contents/header.xml" in parts:
        hx = parts["Contents/header.xml"].decode("utf-8")
        parts["Contents/header.xml"] = _inject_indent_parapr(hx).encode("utf-8")
    refresh_prvtext(parts)  # 미리보기에 표준양식 원문이 남지 않도록 본문 반영
    write_package(out_path, parts, order)
    fix_namespaces(out_path)
    return out_path

# ──────────────────────────────────────────────────────────────────────────
# WF-B: 기존 KASA 양식의 플레이스홀더/텍스트 단순 치환 (서식 100% 보존)
# ──────────────────────────────────────────────────────────────────────────
def fill_template(template_path, replacements, out_path):
    parts, _ = read_package(template_path)
    changed = {}
    for name in parts:
        if name.startswith("Contents/") and name.endswith(".xml"):
            t = parts[name].decode("utf-8")
            for old, new in replacements.items():
                t = t.replace(old, xml_escape(new))
            data = t.encode("utf-8")
            if data != parts[name]:
                changed[name] = data
    # 본문이 바뀌었으면 미리보기도 새 본문으로 갱신(기존 엔트리가 있을 때만)
    if changed:
        merged = dict(parts); merged.update(changed)
        if refresh_prvtext(merged):
            changed[PRVTEXT_NAME] = merged[PRVTEXT_NAME]
    # 서식 보존 편집: 미변경 엔트리는 원본 ZipInfo 그대로 유지
    write_package_preserving(template_path, out_path, changed)
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
def _section_text_lines(parts):
    """모든 섹션(section0..N)의 <hp:t> 텍스트를 문서 순서대로 나열한다."""
    out = []
    for name in sorted(n for n in parts if re.match(r"Contents/section\d+\.xml$", n)):
        xml = parts[name].decode("utf-8", "ignore")
        for m in re.finditer(r"<hp:t(?:\s[^>]*)?>(.*?)</hp:t>", xml, re.S):
            raw = re.sub(r"<[^>]+>", "", m.group(1))  # 중첩 컨트롤 태그 제거
            t = (raw.replace("&lt;", "<").replace("&gt;", ">")
                 .replace("&quot;", '"').replace("&amp;", "&")).strip()
            if t:
                out.append(t)
    return out

def extract_text(path):
    parts, _ = read_package(path)
    return "\n".join(_section_text_lines(parts))

# ──────────────────────────────────────────────────────────────────────────
# 미리보기 텍스트(Preview/PrvText.txt) 재생성
#   본문을 바꾸고 템플릿의 PrvText를 그대로 두면 탐색기 미리보기·문서 검색에
#   표준양식 원문이 노출된다. 본문 기반으로 다시 만든다.
#   (참고: jkf87/hwpx-skill build_hwpx._write_preview)
# ──────────────────────────────────────────────────────────────────────────
PRVTEXT_NAME = "Preview/PrvText.txt"
PRVTEXT_LIMIT = 4096  # 미리보기 용도 상한(문자 수) — 한글이 재저장 시 갱신

def make_prvtext(parts):
    """섹션 본문 텍스트로 PrvText 바이트(UTF-8)를 만든다."""
    text = "\r\n".join(_section_text_lines(parts))[:PRVTEXT_LIMIT]
    return text.encode("utf-8")

def refresh_prvtext(parts):
    """parts에 PrvText 엔트리가 있으면 본문 기반으로 교체(새 엔트리는 만들지 않음).
    반환: 교체 여부."""
    if PRVTEXT_NAME not in parts:
        return False
    new = make_prvtext(parts)
    if new == parts[PRVTEXT_NAME]:
        return False
    parts[PRVTEXT_NAME] = new
    return True


if __name__ == "__main__":
    import sys
    print("kasa_lib: 직접 실행 대신 build_report.py / validate.py 등을 사용하세요.")

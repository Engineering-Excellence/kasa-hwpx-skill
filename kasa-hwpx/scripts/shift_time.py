#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shift_time.py — 시각 일괄 순연(범위 지정·드라이런·신구대조표).

발사 순연처럼 일정 전체가 밀릴 때 문서의 시각 표기를 산술로 옮긴다.
redraft.py(문자열 매핑)로는 두 가지가 원리적으로 불가능해 별도 도구로 둔다.

  1) 전역 매핑 불가 — 순연 대상 구간과 보존 구간(외부 교통편·셔틀 운행표)에
     같은 시각 문자열이 동시에 등장한다(실측: 고유 시각 156종 중 50종 중복).
     {"12:30": "15:15"}를 문서 전역에 걸면 셔틀 시간표까지 오염된다.
     → 적용 범위(--scope)와 제외 범위(--exclude)가 이 도구의 핵심이다.
  2) 라벨·값 노드 분리 — 값('5:08-8:02')과 라벨('▪열차 이동')이 서로 다른
     <hp:t>에 있어, 노드 단위 키워드 제외는 반드시 새어 나간다.
     → 표/오프셋 구간 단위 제외가 정공법이고, --exclude-keyword는 보조 수단이다.

안전 설계:
  - 범위를 지정하지 않은 전역 순연은 위험한 동작으로 취급한다(경고 + --yes 요구).
  - --exclude는 --scope보다 우선한다(제외는 겹치기만 해도 성립 — 보수적).
  - 변경 전건을 재계산으로 검산하고, 1건이라도 어긋나면 파일을 쓰지 않는다.
  - 시각 토큰 외의 문자가 하나라도 바뀌면 오류로 중단한다(구분자·접미 표기 보존).
  - <hp:t> 노드 수 동일성 검증 → linesegarray 제거 → PrvText 갱신 → 구조 검증.

분리 노드 탐지(조용한 누락 → 보이는 경고):
  사람이 쓴 문서에서는 숫자 일부만 글자 서식이 달라 한 시각이 두 <hp:t>에 걸치는 일이
  생긴다(실측 사례: '…, 12' + ':30 예정' — charPr 508/509 경계).
  이 도구는 노드 단위로 패턴을 찾으므로 어느 쪽에도 온전한 시각이 없어 순연되지 않고,
  드라이런 목록에도 나타나지 않아 사람이 눈으로 볼 때까지 알 수 없었다.
  → 이웃 노드를 이어붙였을 때 비로소 시각이 성립하는 지점을 찾아 경고한다.
  자동 병합·자동 수정은 하지 않는다(서식 경계를 코드가 합치면 글자 모양이 바뀐다).
  적용은 사람이 판단하며, --split-fix-map으로 redraft.py --mode exact용 매핑만 만들어 준다.

사용법:
  python3 shift_time.py --input IN.hwpx --output OUT.hwpx --shift "+2:45" \\
      [--scope SCOPE ...] [--exclude EXCLUDE ...] [--exclude-keyword KW ...] \\
      [--pad-hour] [--dry-run] [--report report.md] [--yes] \\
      [--split-fix-map fix.json] [--fail-on-split]

  범위 지정 문법(--scope·--exclude 공통, 반복 지정 가능):
    section:0,1,2,6                    섹션 번호
    range:section2:78309-109220        섹션 내 바이트 오프셋 구간
    table:N                            문서 내 N번째 표(1-base — list-tables 순번과 동일)
    after:"앵커"                        앵커 등장 지점부터 문서 끝까지
    between:"앵커A".."앵커B"             앵커A 시작부터 앵커B 끝까지

  권장 절차: --dry-run으로 확인 → 범위·제외 확정 → 실행 → --report 대조표 검토

  --pad-hour: 한 자리 시(9:20)를 두 자리(09:20)로 함께 교정한다(KASA 표기법 —
  kasa_lint의 '시·분 두 자리' 규칙). 기본은 꺼져 있다(요청하지 않은 표기 변경 금지).
  교정도 **적용 범위 안에서만** 일어나므로 제외한 교통편·셔틀 시간표의 표기는 그대로다.
  순연 없이 표기만 고치려면 `--shift +0m --pad-hour`.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, namedtuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kasa_lib as K  # noqa: E402
import hwpx_edit as HE  # noqa: E402
import validate as V  # noqa: E402

# 시각 토큰: H:MM / HH:MM. 앞뒤에 숫자·쌍점이 붙으면 시각이 아니다
# (2026:10, 12:345, 1:2:3 등을 배제). 유효 범위(0~23시, 0~59분)는 _shift_token에서 본다.
# 소요시간 (30‘)·상대시각 L+20·L+2h36m은 쌍점이 없어 애초에 걸리지 않는다.
TIME_RE = re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})(?![\d:])")

_T_RE = re.compile(r"(<hp:t(?:\s[^>]*)?>)(.*?)(</hp:t>)", re.S)
_TAG_SPLIT_RE = re.compile(r"(<[^>]+>)")
_SEC_RE = re.compile(r"Contents/section(\d+)\.xml$")
_ENTITIES = (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
             ("&quot;", '"'), ("&apos;", "'"))

# 교통편 등 순연 대상이 아닌 노드의 보조 방어(정공법은 --exclude 구간 지정)
DEFAULT_KEYWORDS = ("OZ", "KTX", "아시아나", "진에어", "항공편", "기차편", "열차")

MINUTES_PER_DAY = 24 * 60
LABEL_LIMIT = 34
LABEL_LOOKBACK = 40  # 맥락 라벨을 찾아 거슬러 올라갈 최대 노드 수

# 이어붙이면 안 되는 경계 — 두 <hp:t> 사이의 XML에 이것이 있으면 한 시각으로 보지 않는다.
# (문단·표 셀·줄바꿈은 사람 눈에도 끊겨 보이는 자리다. 실제 사고 사례에서 두 노드 사이에
#  있던 것은 런 경계(</hp:run><hp:run charPrIDRef="…">)뿐이었고, 그것은 결합 대상이다.)
_BREAK_RE = re.compile(r"<hp:p[\s/>]|</hp:p>|<hp:tc[\s/>]|</hp:tc>|<hp:lineBreak[\s/>]")
SPLIT_WINDOW = 4  # 한 번에 이어붙여 볼 최대 노드 수('12' + ':' + '30'까지 포괄)

# 변경 1건 = <hp:t> 노드 1개(그 안의 시각이 모두 옮겨진 상태)
Change = namedtuple("Change", "section byte_off label old new")

# 분리 1건 = 이어붙여야 시각이 되는 인접 <hp:t> 묶음(순연되지 않은 채 남는다)
#   pieces     조각별 원문, new_pieces 순연했다면 되었을 조각별 결과(불가능하면 None)
#   times      이어붙여야 비로소 성립하는 시각 토큰, mixed 컨트롤 태그가 섞인 노드 포함 여부
Split = namedtuple("Split", "section byte_off pieces new_pieces times mixed")


# ──────────────────────────────────────────────────────────────────────────
# 시각 연산 (순수 함수 — 파일·문서 상태와 무관)
# ──────────────────────────────────────────────────────────────────────────
def parse_shift(text, allow_zero=False):
    """'+2:45' '-1:00' '+165m' '-90m' → 분(int). 부호는 필수.
    allow_zero는 표기 교정(--pad-hour)만 하려는 경우를 위한 것이다(+0m)."""
    s = text.strip()
    m = re.fullmatch(r"([+-])(?:(\d{1,3}):(\d{1,2})|(\d{1,5})m)", s)
    if not m:
        raise SystemExit(f"--shift 형식 오류: {text!r} "
                         f"(예: +2:45, -1:00, +165m, -90m — 부호 필수)")
    sign = 1 if m.group(1) == "+" else -1
    if m.group(2) is not None:
        if int(m.group(3)) > 59:
            raise SystemExit(f"--shift의 분이 60 이상입니다: {text!r}")
        minutes = int(m.group(2)) * 60 + int(m.group(3))
    else:
        minutes = int(m.group(4))
    if minutes == 0 and not allow_zero:
        raise SystemExit("--shift가 0분입니다(옮길 것이 없습니다). "
                         "표기 교정만 하려면 --pad-hour와 함께 쓰세요.")
    return sign * minutes


def format_shift(minutes):
    """분 → '+2:45' 형태의 사람용 표기."""
    sign = "+" if minutes >= 0 else "-"
    h, m = divmod(abs(minutes), 60)
    return f"{sign}{h}:{m:02d}"


def _hour_str(nh, src_hour, pad_hour):
    """시(hour) 표기 규칙 — 기본은 원본 자릿수 유지, pad_hour면 두 자리로 채운다."""
    return f"{nh:02d}" if (pad_hour or len(src_hour) == 2) else str(nh)


def _shift_token(tok, minutes, pad_hour=False):
    """시각 토큰 1개를 옮긴다. 자릿수 표기(9:20 vs 09:20)를 원본대로 유지하고,
    자정을 넘으면 24시간 순환(mod 1440)한다. 시각이 아니면 원본 그대로 둔다.
    pad_hour면 한 자리 시를 두 자리로 채운다(KASA 표기법 — kasa_lint 규칙)."""
    m = TIME_RE.fullmatch(tok)
    if not m:
        return tok
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:  # 24:00 이상·H:60 이상은 시각이 아님(비율·점수 등) → 교정도 안 함
        return tok
    total = (h * 60 + mi + minutes) % MINUTES_PER_DAY
    nh, nm = divmod(total, 60)
    return f"{_hour_str(nh, m.group(1), pad_hour)}:{nm:02d}"


def shift_text(text, minutes, pad_hour=False):
    """텍스트 안의 시각 토큰만 옮긴다. 구분자(~ - ∼)·접미(분·경·까지·부터)는
    토큰 밖이라 손대지 않는다."""
    return TIME_RE.sub(lambda m: _shift_token(m.group(0), minutes, pad_hour), text)


# ──────────────────────────────────────────────────────────────────────────
# 범위 지정 파싱
# ──────────────────────────────────────────────────────────────────────────
def _sections(parts):
    return sorted((n for n in parts if _SEC_RE.search(n)),
                  key=lambda n: int(_SEC_RE.search(n).group(1)))


def _sec_num(name):
    return int(_SEC_RE.search(name).group(1))


def _plain(inner):
    """<hp:t> 내부 → 태그 제거·엔티티 해제한 사람용 텍스트."""
    t = _TAG_SPLIT_RE.sub("", inner)
    for ent, ch in _ENTITIES:
        t = t.replace(ent, ch)
    return t


def _unquote(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


def _snap(sec, s, e):
    """앵커 위치를 그것을 담은 <hp:t> 노드 경계까지 넓힌다.
    앵커는 노드 '안쪽' 텍스트라 그대로 쓰면 정작 그 노드가 범위에서 빠진다."""
    a = sec.rfind("<hp:t", 0, s)
    if a >= 0 and sec.find("</hp:t>", a, s) == -1:  # 사이에 닫는 태그가 없어야 그 노드
        s = a
    b = sec.find("</hp:t>", e)
    if b >= 0:
        e = b + len("</hp:t>")
    return s, e


def _find_anchor(texts, secs, anchor, after=None):
    """앵커 문자열의 첫 등장 위치를 전역 순서로 찾는다.
    반환: (섹션 인덱스, 시작 문자 인덱스, 끝 문자 인덱스)."""
    if not anchor:
        raise SystemExit("앵커 문자열이 비어 있습니다.")
    start_i, start_pos = after if after else (0, 0)
    for i in range(start_i, len(secs)):
        pos = texts[i].find(anchor, start_pos if i == start_i else 0)
        if pos >= 0:
            return i, pos, pos + len(anchor)
    raise SystemExit(f"앵커를 찾지 못했습니다: {anchor!r} "
                     f"(한 <hp:t> 안에 이어져 있는 문구여야 합니다 — "
                     f"extract_text.py로 원문 표기를 확인하세요)")


def _spans_between(secs, texts, p_start, p_end):
    """전역 위치 (섹션 인덱스, 문자 인덱스) 구간을 (섹션명, s, e) 목록으로 편다."""
    (si, sp), (ei, ep) = p_start, p_end
    if (si, sp) > (ei, ep):
        raise SystemExit("범위의 시작이 끝보다 뒤입니다(앵커 순서를 확인하세요).")
    spans = []
    for i in range(si, ei + 1):
        s = sp if i == si else 0
        e = ep if i == ei else len(texts[i])
        if s < e:
            spans.append((secs[i], s, e))
    return spans


def parse_scope(spec, parts):
    """범위 지정 문자열 1개 → [(섹션명, 시작 문자, 끝 문자)]."""
    secs = _sections(parts)
    texts = [parts[n].decode("utf-8") for n in secs]
    spec = spec.strip()

    m = re.fullmatch(r"section:\s*([\d,\s]+)", spec)
    if m:
        spans = []
        for tok in m.group(1).replace(" ", "").split(","):
            if not tok:
                continue
            name = f"Contents/section{int(tok)}.xml"
            if name not in parts:
                raise SystemExit(f"섹션을 찾을 수 없습니다: section{int(tok)} "
                                 f"(문서 섹션 {len(secs)}개)")
            spans.append((name, 0, len(parts[name].decode("utf-8"))))
        if not spans:
            raise SystemExit(f"섹션 번호가 비었습니다: {spec!r}")
        return spans

    m = re.fullmatch(r"range:\s*section(\d+)\s*:\s*(\d+)\s*-\s*(\d+)", spec)
    if m:
        name = f"Contents/section{int(m.group(1))}.xml"
        if name not in parts:
            raise SystemExit(f"섹션을 찾을 수 없습니다: section{int(m.group(1))}")
        raw = parts[name]
        b1, b2 = int(m.group(2)), int(m.group(3))
        if b1 >= b2:
            raise SystemExit(f"오프셋 구간이 비었습니다: {spec!r}")
        # 오프셋은 원본 바이트 기준(문서에서 실측한 값) → 문자 인덱스로 환산
        c1 = len(raw[:b1].decode("utf-8", "ignore"))
        c2 = len(raw[:b2].decode("utf-8", "ignore"))
        return [(name, c1, c2)]

    m = re.fullmatch(r"table:\s*(\d+)", spec)
    if m:
        tables = HE._doc_tables(parts)  # 머리말·꼬리말 내부 표 제외
        idx = int(m.group(1))           # 1-base — hwpx_edit.py list-tables 출력과 동일
        if not 1 <= idx <= len(tables):
            raise SystemExit(f"표 #{idx}을 찾을 수 없습니다(1-base, 문서 내 표 "
                             f"{len(tables)}개 — hwpx_edit.py list-tables로 "
                             f"순번을 확인하세요).")
        name, s, e = tables[idx - 1]
        return [(name, s, e)]

    m = re.fullmatch(r"after:\s*(.+)", spec, re.S)
    if m:
        i, s, e = _find_anchor(texts, secs, _unquote(m.group(1)))
        s, _ = _snap(texts[i], s, e)
        return _spans_between(secs, texts, (i, s),
                              (len(secs) - 1, len(texts[-1])))

    m = (re.fullmatch(r'between:\s*"(.*)"\s*\.\.\s*"(.*)"', spec, re.S)
         or re.fullmatch(r"between:\s*'(.*)'\s*\.\.\s*'(.*)'", spec, re.S)
         or re.fullmatch(r"between:\s*(.+?)\s*\.\.\s*(.+)", spec, re.S))
    if m:
        i1, s1, e1 = _find_anchor(texts, secs, _unquote(m.group(1)))
        i2, s2, e2 = _find_anchor(texts, secs, _unquote(m.group(2)),
                                  after=(i1, e1))
        s1, _ = _snap(texts[i1], s1, e1)
        _, e2 = _snap(texts[i2], s2, e2)
        return _spans_between(secs, texts, (i1, s1), (i2, e2))

    raise SystemExit(f"범위 지정 문법 오류: {spec!r}\n"
                     f"  가능한 형식: section:0,1 / range:section2:1000-2000 / "
                     f"table:0 / after:\"앵커\" / between:\"A\"..\"B\"")


def parse_scopes(specs, parts):
    """범위 지정 여러 개 → {섹션명: [(s, e)]} 합집합."""
    out = {}
    for spec in specs or ():
        for name, s, e in parse_scope(spec, parts):
            out.setdefault(name, []).append((s, e))
    return out


# ──────────────────────────────────────────────────────────────────────────
# 변경 계획
# ──────────────────────────────────────────────────────────────────────────
def _contained(span, ranges):
    """노드가 구간에 속하는가 — 노드는 '자기 시작 위치'가 든 구간에 속한다.
    경계에서 노드가 통째로 누락되지 않게 하려는 규칙(적용 판정)."""
    return any(s <= span[0] < e for s, e in ranges)


def _overlaps(span, ranges):
    """노드가 구간과 조금이라도 겹치는가(제외는 보수적으로)."""
    return any(span[0] < e and s < span[1] for s, e in ranges)


def _applies(span, text, scopes, in_ranges, ex_ranges, keywords):
    """이 노드가 순연 적용 대상인가 — 순연과 분리 노드 탐지가 같은 판정을 쓴다
    (대상이 아닌 구간의 분리 시각까지 경고하면 소음이 된다)."""
    if scopes and not _contained(span, in_ranges):
        return False
    if _overlaps(span, ex_ranges):          # 제외가 범위보다 우선
        return False
    return not any(k and k in text for k in keywords)


def _byte_offsets(sec, nodes):
    """각 <hp:t> 노드의 원본 바이트 오프셋(--exclude range: 지정에 그대로 쓰는 값)."""
    offs, cur_char, cur_byte = [], 0, 0
    for m in nodes:
        cur_byte += len(sec[cur_char:m.start()].encode("utf-8"))
        offs.append(cur_byte)
        cur_byte += len(m.group(0).encode("utf-8"))
        cur_char = m.end()
    return offs


def _is_context(text):
    """맥락 라벨로 쓸 만한 노드인가 — 시각·기호만 있는 노드는 제외한다."""
    return bool(re.search(r"[가-힣A-Za-z]", TIME_RE.sub(" ", text)))


def _clip(text):
    return " ".join(text.split())[:LABEL_LIMIT]


def _label_for(texts, idx):
    """해당 노드 직전의 '시각·기호가 아닌' 텍스트 노드에서 맥락 라벨을 얻는다.
    시각이 섞이지 않은 순수 텍스트 노드를 우선한다(라벨·값이 분리된 실제 문서 구조에서
    '▪열차 이동' 같은 라벨을 집어 오기 위함). 없으면 텍스트가 든 가장 가까운 노드."""
    fallback = None
    for j in range(idx - 1, max(idx - LABEL_LOOKBACK, 0) - 1, -1):
        text = texts[j]
        if not _is_context(text):
            continue
        if not TIME_RE.search(text):
            return _clip(text)
        if fallback is None:
            fallback = text
    if fallback is not None:
        return _clip(fallback)
    own = _clip(TIME_RE.sub(" ", texts[idx]))  # 직전에 쓸 노드가 없을 때만 자기 텍스트
    return own or "-"


def shift_document(parts, minutes, scopes=(), excludes=(), keywords=(),
                   pad_hour=False):
    """문서 전체의 변경 계획을 세운다(파일은 쓰지 않는다).
    반환: (changes, kept, new_sections{섹션명: 새 XML 문자열}).
    kept는 범위·제외·키워드 때문에 옮기지 않은 시각 토큰 수."""
    scope_map = parse_scopes(scopes, parts)
    exclude_map = parse_scopes(excludes, parts)
    changes, kept, new_sections = [], 0, {}

    for name in _sections(parts):
        sec = parts[name].decode("utf-8")
        nodes = list(_T_RE.finditer(sec))
        if not nodes:
            continue
        texts = [_plain(m.group(2)) for m in nodes]
        offsets = _byte_offsets(sec, nodes)
        in_ranges = scope_map.get(name, [])
        ex_ranges = exclude_map.get(name, [])

        pieces, pos = [], 0        # 새 섹션 조각(변경 노드만 갈아 끼운다)
        for idx, m in enumerate(nodes):
            node_byte = offsets[idx]
            span = (m.start(), m.end())
            if not _applies(span, texts[idx], scopes, in_ranges, ex_ranges,
                            keywords):
                kept += sum(1 for t in TIME_RE.finditer(texts[idx])
                            if _shift_token(t.group(0), minutes, pad_hour)
                            != t.group(0))
                continue

            inner = m.group(2)
            # 시각 토큰은 XML 이스케이프 대상 문자를 포함하지 않으므로 원본 문자열을
            # 그대로 치환한다(이스케이프 왕복으로 인한 변형 방지). 태그는 손대지 않는다.
            new_inner = "".join(
                seg if seg.startswith("<") else shift_text(seg, minutes, pad_hour)
                for seg in _TAG_SPLIT_RE.split(inner))
            if new_inner == inner:
                continue
            changes.append(Change(section=name, byte_off=node_byte,
                                  label=_label_for(texts, idx),
                                  old=_plain(inner), new=_plain(new_inner)))
            pieces.append(sec[pos:m.start()])
            pieces.append(m.group(1) + new_inner + m.group(3))
            pos = m.end()

        if pieces:
            pieces.append(sec[pos:])
            new_sections[name] = "".join(pieces)

    return changes, kept, new_sections


# ──────────────────────────────────────────────────────────────────────────
# 분리 노드 시각 탐지 (글자 서식 경계로 쪼개져 순연되지 않는 시각)
# ──────────────────────────────────────────────────────────────────────────
def _trim(pieces, matches):
    """시각에 걸치지 않는 바깥쪽 조각을 떨어낸다. 반환: (첫 인덱스, 끝 인덱스).
    앞뒤로 잘라내도 매칭은 그대로다 — 경계 조각의 끝 글자가 숫자였다면 TIME_RE의
    전후방 탐색(?<![\\d:])·(?![\\d:]) 때문에 애초에 매칭되지 않았을 것이기 때문이다."""
    lo = min(m.start() for m in matches)
    hi = max(m.end() for m in matches)
    starts, pos = [], 0
    for p in pieces:
        starts.append(pos)
        pos += len(p)
    a = next(k for k in range(len(pieces)) if starts[k] + len(pieces[k]) > lo)
    b = next(k for k in range(len(pieces) - 1, -1, -1) if starts[k] < hi)
    return a, b


def _shift_pieces(pieces, minutes, pad_hour=False):
    """조각들을 이어붙여 순연한 뒤 원래 경계대로 다시 나눈다(수정 매핑용).
    경계가 시각 숫자 한가운데인데 자릿수까지 바뀌어 되돌릴 수 없으면 None."""
    joined = "".join(pieces)
    posmap = {}          # 원본 문자 위치 → 결과 문자 위치(불가능하면 None)
    out, opos, npos = [], 0, 0
    for m in TIME_RE.finditer(joined):
        for k in range(opos, m.start() + 1):
            posmap[k] = npos + (k - opos)
        out.append(joined[opos:m.start()])
        npos += m.start() - opos
        old_tok = m.group(0)
        new_tok = _shift_token(old_tok, minutes, pad_hour)
        ci, ci2 = old_tok.index(":"), new_tok.index(":")
        for k in range(len(old_tok) + 1):      # 쌍점을 기준으로 시·분을 각각 맞춘다
            j = (ci2 - (ci - k)) if k <= ci else (ci2 + (k - ci))
            posmap[m.start() + k] = npos + j if j >= 0 else None
        out.append(new_tok)
        npos += len(new_tok)
        opos = m.end()
    for k in range(opos, len(joined) + 1):
        posmap[k] = npos + (k - opos)
    out.append(joined[opos:])
    new_joined = "".join(out)

    new_pieces, prev, at = [], 0, 0
    for p in pieces:
        at += len(p)
        cut = posmap.get(at)
        if cut is None:
            return None
        new_pieces.append(new_joined[prev:cut])
        prev = cut
    return new_pieces


def find_split_times(parts, minutes, scopes=(), excludes=(), keywords=(),
                     pad_hour=False):
    """글자 서식 경계로 <hp:t>가 쪼개져 순연되지 않는 시각을 찾는다.

    판정: 이웃 노드를 이어붙여야 비로소 TIME_RE가 매칭되는 지점(각 노드만 보면
    시각이 없다). 같은 문단 안에서 최대 SPLIT_WINDOW개까지 슬라이딩 윈도로 본다.
    _BREAK_RE(문단·표 셀·줄바꿈) 경계는 넘지 않고, 범위·제외·키워드 판정은
    순연과 동일하게 적용한다. 이미 순연되는 시각(단독 노드)은 대상이 아니다.
    반환: Split 목록(문서 순서)."""
    scope_map = parse_scopes(scopes, parts)
    exclude_map = parse_scopes(excludes, parts)
    splits = []

    for name in _sections(parts):
        sec = parts[name].decode("utf-8")
        nodes = list(_T_RE.finditer(sec))
        if len(nodes) < 2:
            continue
        texts = [_plain(m.group(2)) for m in nodes]
        offsets = _byte_offsets(sec, nodes)
        in_ranges = scope_map.get(name, [])
        ex_ranges = exclude_map.get(name, [])
        ok = [_applies((m.start(), m.end()), texts[i], scopes, in_ranges,
                       ex_ranges, keywords) for i, m in enumerate(nodes)]

        i = 0
        while i < len(nodes) - 1:
            if not ok[i] or TIME_RE.search(texts[i]):
                i += 1
                continue
            hit = None
            for j in range(i + 1, min(i + SPLIT_WINDOW, len(nodes))):
                if _BREAK_RE.search(sec[nodes[j - 1].end():nodes[j].start()]):
                    break
                if not ok[j] or TIME_RE.search(texts[j]):
                    break
                found = [m for m in TIME_RE.finditer("".join(texts[i:j + 1]))
                         if _shift_token(m.group(0), minutes, pad_hour)
                         != m.group(0)]     # 순연 대상이 아닌 숫자쌍(24:00 등)은 제외
                if found:
                    hit = (j, found)
                    break
            if hit is None:
                i += 1
                continue
            j, found = hit
            a, b = _trim(texts[i:j + 1], found)
            lo, hi = i + a, i + b
            pieces = texts[lo:hi + 1]
            splits.append(Split(
                section=name, byte_off=offsets[lo], pieces=pieces,
                new_pieces=_shift_pieces(pieces, minutes, pad_hour),
                times=[m.group(0) for m in found],
                mixed=any("<" in nodes[k].group(2) for k in range(lo, hi + 1))))
            i = j + 1

    return splits


def _node_text_counts(parts):
    """문서 전체의 <hp:t> 텍스트별 등장 횟수(수정 매핑의 유일성 검사용)."""
    counts = Counter()
    for name in _sections(parts):
        for m in _T_RE.finditer(parts[name].decode("utf-8")):
            counts[_plain(m.group(2))] += 1
    return counts


def build_fix_map(splits, parts):
    """분리 노드를 redraft.py --mode exact로 고칠 매핑을 만든다(자동 적용은 하지 않는다).
    문서 안에서 텍스트가 유일한 단순 노드만 넣는다 — 같은 텍스트의 <hp:t>가 여럿이면
    exact 치환이 엉뚱한 곳까지 바꾸므로 매핑에서 빼고 '수동 확인 필요'로 알린다.
    반환: (매핑 dict, 경고 목록)."""
    counts = _node_text_counts(parts)
    mapping, problems = {}, []
    for sp in splits:
        where = _where(sp)
        if sp.new_pieces is None:
            problems.append(f"{where} 조각 경계가 시각 숫자 한가운데라 매핑을 만들 수 "
                            f"없습니다 — 수동 확인 필요")
            continue
        if sp.mixed:
            problems.append(f"{where} 컨트롤 태그가 섞인 노드(mixed content)라 "
                            f"exact 치환 대상이 아닙니다 — 수동 확인 필요")
            continue
        dup = [p for p in sp.pieces if counts[p] > 1]
        if dup:
            problems.append(f"{where} 같은 텍스트의 <hp:t>가 문서에 여러 개입니다"
                            f"({', '.join(repr(d) for d in dup)}) — 수동 확인 필요")
            continue
        pairs = [(o, n) for o, n in zip(sp.pieces, sp.new_pieces) if o != n]
        clash = [o for o, n in pairs if mapping.get(o, n) != n]
        if clash:
            problems.append(f"{where} 앞선 항목과 같은 키에 다른 값이 필요합니다"
                            f"({', '.join(repr(c) for c in clash)}) — 수동 확인 필요")
            continue
        mapping.update(pairs)
    return mapping, problems


# ──────────────────────────────────────────────────────────────────────────
# 자기 검산
# ──────────────────────────────────────────────────────────────────────────
def verify_changes(changes, minutes, pad_hour=False):
    """변경 전건을 재계산으로 검증한다. 문제 목록(빈 목록이면 통과)을 반환.
    검사 두 가지:
      (a) 시각 토큰 외의 문자가 하나도 바뀌지 않았는가(구분자·접미·본문 보존)
      (b) 모든 토큰이 '원본시각 + shift == 결과시각'인가(자릿수 표기 포함)"""
    problems = []
    for ch in changes:
        if TIME_RE.sub("\x00", ch.old) != TIME_RE.sub("\x00", ch.new):
            problems.append(f"시각 외 문자 변경: {ch.old!r} → {ch.new!r}")
            continue
        olds = [m.group(0) for m in TIME_RE.finditer(ch.old)]
        news = [m.group(0) for m in TIME_RE.finditer(ch.new)]
        if len(olds) != len(news):
            problems.append(f"시각 개수 불일치: {ch.old!r} → {ch.new!r}")
            continue
        for o, n in zip(olds, news):
            om = TIME_RE.fullmatch(o)
            h, mi = int(om.group(1)), int(om.group(2))
            if h > 23 or mi > 59:      # 시각이 아닌 숫자쌍은 그대로여야 한다
                expect = o
            else:
                total = (h * 60 + mi + minutes) % MINUTES_PER_DAY
                nh, nm = divmod(total, 60)
                expect = f"{_hour_str(nh, om.group(1), pad_hour)}:{nm:02d}"
            if n != expect:
                problems.append(f"검산 불일치: {o} {format_shift(minutes)} → "
                                f"{n} (기대 {expect}) / 노드 {ch.old!r}")
    return problems


# ──────────────────────────────────────────────────────────────────────────
# 보고(드라이런·신구대조표)
# ──────────────────────────────────────────────────────────────────────────
def _short_hour(text):
    """결과에 한 자리 시가 남아 있는가(kasa_lint '두 자리' 경고 대상)."""
    return any(len(m.group(1)) == 1 and int(m.group(1)) <= 23
               and int(m.group(2)) <= 59 for m in TIME_RE.finditer(text))


def _cell(text):
    return " ".join(str(text).split()).replace("|", "\\|") or "-"


def _where(ch):
    """--exclude range: 지정에 그대로 쓸 수 있는 위치 표기."""
    return f"section{_sec_num(ch.section)}@{ch.byte_off}"


def render_rows(changes):
    """드라이런·대조표가 공유하는 4열 표(구간 | 맥락 | 현행 | 개정)."""
    rows = [(_where(c), _cell(c.label), _cell(c.old), _cell(c.new))
            for c in changes]
    head = ("구간", "맥락", "현행", "개정")
    widths = [max(len(r[i]) for r in ([head] + rows)) for i in range(4)]
    line = "  ".join(h.ljust(w) for h, w in zip(head, widths))
    out = [line, "  ".join("-" * w for w in widths)]
    for r in rows:
        out.append("  ".join(c.ljust(w) for c, w in zip(r, widths)))
    return "\n".join(out)


def render_splits(splits):
    """분리 노드 경고 블록 — 드라이런·실제 실행이 같은 문면을 쓴다."""
    lines = [f"⚠ 분리 노드로 인해 순연되지 않은 시각 {len(splits)}건 — "
             f"글자 서식 경계로 쪼개져 있어 자동 인식되지 않습니다."]
    for sp in splits:
        pieces = " + ".join(f"'{_cell(p)}'" for p in sp.pieces)
        lines.append(f"  {_where(sp)}  {pieces}  → {', '.join(sp.times)}")
    lines.append("  ※ redraft.py로 수동 치환하거나, 원본에서 해당 부분의 글자 서식을 "
                 "통일한 뒤 다시 실행하세요.")
    return "\n".join(lines)


def _split_section(splits):
    """신구대조표의 「순연되지 않은 분리 노드 시각」 절(검토자가 누락을 알아채는 자리)."""
    lines = ["## 순연되지 않은 분리 노드 시각", ""]
    if not splits:
        return lines + ["해당 없음 — 글자 서식 경계로 쪼개진 시각은 발견되지 않았다.", ""]
    lines += [f"글자 서식(charPr) 경계로 <hp:t>가 쪼개져 자동 인식되지 않은 시각 "
              f"{len(splits)}건이다. **순연되지 않았으므로 수동 확인이 필요하다.**", "",
              "| 구간 | 조각 | 시각 |", "| --- | --- | --- |"]
    for sp in splits:
        pieces = " + ".join(f"`{_cell(p)}`" for p in sp.pieces)
        lines.append(f"| {_where(sp)} | {pieces} | {', '.join(sp.times)} |")
    return lines + ["", "※ redraft.py --mode exact로 수동 치환하거나, 원본에서 해당 "
                    "부분의 글자 서식을 통일한 뒤 다시 실행한다.", ""]


def render_report(changes, kept, minutes, input_path, scopes, excludes, keywords,
                  pad_hour=False, splits=()):
    """신구대조표(Markdown) — 드라이런과 같은 변경 목록을 표로 낸다."""
    lines = [
        "# 시각 순연 신구대조표", "",
        f"- 원본 파일: `{os.path.basename(input_path)}`",
        f"- 이동량: {format_shift(minutes)} ({minutes:+d}분)"
        + ("  ※ 표기 교정(--pad-hour: 한 자리 시 → 두 자리) 동시 적용"
           if pad_hour else ""),
        f"- 적용 범위: {', '.join(scopes) if scopes else '문서 전체(범위 미지정)'}",
        f"- 제외 범위: {', '.join(excludes) if excludes else '없음'}",
        f"- 제외 키워드: {', '.join(keywords) if keywords else '없음'}",
        f"- 변경 {len(changes)}건 / 보존 {kept}건", "",
        "| 구간 | 맥락 | 현행 | 개정 |",
        "| --- | --- | --- | --- |",
    ]
    for c in changes:
        lines.append(f"| {_where(c)} | {_cell(c.label)} | "
                     f"{_cell(c.old)} | {_cell(c.new)} |")
    lines.append("")
    lines += _split_section(list(splits))
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────
# 실행
# ──────────────────────────────────────────────────────────────────────────
def shift_file(input_path, output_path, minutes, scopes=(), excludes=(),
               keywords=DEFAULT_KEYWORDS, dry_run=False, pad_hour=False):
    """시각 순연을 수행한다. 반환: (changes, kept).
    dry_run이면 계획만 세우고 파일을 쓰지 않는다."""
    parts, _ = K.read_package(input_path)
    if not _sections(parts):
        raise SystemExit("section*.xml을 찾을 수 없습니다(유효한 HWPX가 아님).")

    changes, kept, new_sections = shift_document(
        parts, minutes, scopes=scopes, excludes=excludes, keywords=keywords,
        pad_hour=pad_hour)

    # 전건 재계산 — 어긋나면 쓰지 않는다
    problems = verify_changes(changes, minutes, pad_hour)
    if problems:
        raise SystemExit("[중단] 자기 검산 실패 — 파일을 쓰지 않았습니다.\n  "
                         + "\n  ".join(problems[:20]))
    if dry_run or not changes:
        return changes, kept

    replacements = {}
    for name, new_sec in new_sections.items():
        before = len(_T_RE.findall(parts[name].decode("utf-8")))
        after = len(_T_RE.findall(new_sec))
        if before != after:
            raise SystemExit(f"[중단] {name}의 <hp:t> 노드 수가 달라졌습니다"
                             f"({before} → {after}) — 파일을 쓰지 않았습니다.")
        stripped, _ = K.strip_linesegarray(new_sec)  # 줄 위치 캐시 제거(줄겹침 방지)
        replacements[name] = stripped.encode("utf-8")

    merged = dict(parts)
    merged.update(replacements)
    if K.refresh_prvtext(merged):
        replacements[K.PRVTEXT_NAME] = merged[K.PRVTEXT_NAME]

    K.write_package_preserving(input_path, output_path, replacements)
    K.fix_namespaces(output_path)
    issues = V.validate_structure(output_path)
    if issues:
        os.remove(output_path)
        raise SystemExit("[중단] 출력물 구조 검증 실패 — 파일을 삭제했습니다.\n  "
                         + "\n  ".join(issues))
    return changes, kept


def _emit_fix_map(splits, parts, path):
    """--split-fix-map 처리 — 매핑 파일을 쓰고 제외 항목을 알린다(자동 적용은 없다).
    path가 없으면 아무 것도 하지 않는다. 반환: 만들어진 매핑."""
    if not path:
        return {}
    mapping, problems = build_fix_map(splits, parts)
    for p in problems:
        print(f"  [주의] {p}")
    if not mapping:
        print("  수정 매핑: 만들 수 있는 항목이 없습니다(위 주의 참고).")
        return {}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    print(f"  수정 매핑: {path} ({len(mapping)}건) — redraft.py --mode exact로 "
          f"적용한 뒤 validate.py --kasa로 다시 검증하세요.")
    return mapping


def fix_negative_shift(argv):
    """'--shift -1:00'을 '--shift=-1:00'으로 바꾼다.
    argparse는 '-'로 시작하는 값을 옵션으로 오인하는데(음수 '숫자'만 예외라
    '-1:00'은 걸린다), 음수 순연은 정상 사용법이라 여기서 흡수한다."""
    out, i = [], 0
    while i < len(argv):
        if (argv[i] == "--shift" and i + 1 < len(argv)
                and re.fullmatch(r"-\d[\d:m]*", argv[i + 1])):
            out.append(f"--shift={argv[i + 1]}")
            i += 2
            continue
        out.append(argv[i])
        i += 1
    return out


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        description="시각 일괄 순연(범위 지정·드라이런·신구대조표)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="범위 문법: section:0,1 / range:section2:1000-2000 / table:1(1-base, "
               "hwpx_edit.py list-tables 순번) / after:\"앵커\" / between:\"A\"..\"B\"")
    ap.add_argument("--input", required=True, help="원본 HWPX 경로")
    ap.add_argument("--output", help="결과 HWPX 경로(--dry-run이면 생략 가능)")
    ap.add_argument("--shift", required=True, help="이동량: +2:45, -1:00, +165m, -90m")
    ap.add_argument("--scope", action="append", default=[],
                    help="적용 범위(반복 지정 가능, 미지정 시 문서 전체)")
    ap.add_argument("--exclude", action="append", default=[],
                    help="제외 범위(--scope보다 우선, 반복 지정 가능)")
    ap.add_argument("--exclude-keyword", action="append", default=[],
                    help="해당 문자열이 든 <hp:t>는 보존(보조 수단)")
    ap.add_argument("--no-default-keywords", action="store_true",
                    help=f"기본 제외 키워드({', '.join(DEFAULT_KEYWORDS)}) 해제")
    ap.add_argument("--pad-hour", action="store_true",
                    help="적용 범위 안에서 한 자리 시를 두 자리로 교정"
                         "(9:20 → 09:20, KASA 표기법). 표기만 고치려면 --shift +0m")
    ap.add_argument("--dry-run", action="store_true", help="쓰지 않고 변경 예정만 출력")
    ap.add_argument("--report", help="신구대조표(Markdown) 저장 경로")
    ap.add_argument("--split-fix-map",
                    help="분리 노드 수정 매핑(JSON) 저장 경로 — "
                         "redraft.py --mode exact에 그대로 넣는다(자동 적용 없음)")
    ap.add_argument("--fail-on-split", action="store_true",
                    help="분리 노드 시각이 있으면 파일을 쓰지 않고 중단(CI용)")
    ap.add_argument("--yes", action="store_true", help="전역 순연(범위 미지정) 확인")
    args = ap.parse_args(fix_negative_shift(sys.argv[1:]))

    minutes = parse_shift(args.shift, allow_zero=args.pad_hour)
    keywords = list(args.exclude_keyword)
    if not args.no_default_keywords:
        keywords = list(DEFAULT_KEYWORDS) + keywords
    if not args.dry_run and not args.output:
        raise SystemExit("--output이 필요합니다(또는 --dry-run으로 먼저 확인하세요).")
    if not args.scope:
        print("[경고] --scope 미지정 — 문서 전체에 적용합니다. 보존해야 할 구간"
              "(외부 교통편·셔틀 운행표 등)에 같은 시각 문자열이 있으면 함께 옮겨집니다.")

    # 분리 노드 탐지는 순연보다 먼저 — --fail-on-split이면 파일을 쓰기 전에 멈춘다
    parts, _ = K.read_package(args.input)
    splits = find_split_times(parts, minutes, scopes=args.scope,
                              excludes=args.exclude, keywords=keywords,
                              pad_hour=args.pad_hour)
    if splits and args.fail_on_split:
        print(render_splits(splits))
        _emit_fix_map(splits, parts, args.split_fix_map)  # 중단해도 매핑은 남긴다
        raise SystemExit("[중단] --fail-on-split — 분리 노드 시각이 있어 "
                         "파일을 쓰지 않았습니다.")

    changes, kept = shift_file(args.input, args.output, minutes,
                               scopes=args.scope, excludes=args.exclude,
                               keywords=keywords, pad_hour=args.pad_hour,
                               dry_run=args.dry_run or (not args.scope and not args.yes))

    scope_txt = ", ".join(args.scope) if args.scope else "문서 전체(범위 미지정)"
    print(f"적용 범위: {scope_txt}")
    print(f"제외 범위: {', '.join(args.exclude) if args.exclude else '없음'}")
    pad_txt = "  (+ 표기 교정: 한 자리 시 → 두 자리)" if args.pad_hour else ""
    print(f"이동량   : {format_shift(minutes)} ({minutes:+d}분){pad_txt}")
    print(f"변경 {len(changes)}건 / 보존(제외) {kept}건")

    if splits:  # 변경 목록과 별도 블록 — 드라이런·실제 실행 모두에서 낸다
        print()
        print(render_splits(splits))
        _emit_fix_map(splits, parts, args.split_fix_map)
    elif args.split_fix_map:
        print("분리 노드 시각이 없어 수정 매핑을 만들지 않았습니다.")

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(render_report(changes, kept, minutes, args.input,
                                  args.scope, args.exclude, keywords,
                                  pad_hour=args.pad_hour, splits=splits))
        print(f"신구대조표: {args.report}")

    if not args.pad_hour and any(_short_hour(c.new) for c in changes):
        print("  ※ 결과에 한 자리 시(예: 9:20)가 남아 있습니다 — "
              "validate --kasa의 표기법 lint가 '두 자리로'를 경고할 수 있습니다. "
              "함께 교정하려면 --pad-hour를 붙이세요(적용 범위 안에서만 바뀝니다).")

    if not changes:
        print("변경할 시각이 없습니다(범위·제외 지정을 확인하세요).")
        return
    if args.dry_run:
        print("\n[드라이런] 변경 예정 목록 — 파일을 쓰지 않았습니다.")
        print(render_rows(changes))
        return
    if not args.scope and not args.yes:
        print(f"\n[중단] 범위 미지정 전역 순연입니다. 위 {len(changes)}건을 그대로 "
              f"적용하려면 --yes를, 먼저 확인하려면 --dry-run을 붙이세요.")
        print(render_rows(changes))
        raise SystemExit(2)
    print(f"순연 완료: {args.output}")
    print("  ※ 대조표(--report)로 변경 내역을 확인하고, 한글에서 열어 점검하세요.")


if __name__ == "__main__":
    main()

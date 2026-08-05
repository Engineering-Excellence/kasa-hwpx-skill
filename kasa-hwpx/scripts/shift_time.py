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

사용법:
  python3 shift_time.py --input IN.hwpx --output OUT.hwpx --shift "+2:45" \\
      [--scope SCOPE ...] [--exclude EXCLUDE ...] [--exclude-keyword KW ...] \\
      [--dry-run] [--report report.md] [--yes]

  범위 지정 문법(--scope·--exclude 공통, 반복 지정 가능):
    section:0,1,2,6                    섹션 번호
    range:section2:78309-109220        섹션 내 바이트 오프셋 구간
    table:N                            문서 내 N번째 표(1-base — list-tables 순번과 동일)
    after:"앵커"                        앵커 등장 지점부터 문서 끝까지
    between:"앵커A".."앵커B"             앵커A 시작부터 앵커B 끝까지

  권장 절차: --dry-run으로 확인 → 범위·제외 확정 → 실행 → --report 대조표 검토
"""
import argparse
import os
import re
import sys
from collections import namedtuple

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

# 변경 1건 = <hp:t> 노드 1개(그 안의 시각이 모두 옮겨진 상태)
Change = namedtuple("Change", "section byte_off label old new")


# ──────────────────────────────────────────────────────────────────────────
# 시각 연산 (순수 함수 — 파일·문서 상태와 무관)
# ──────────────────────────────────────────────────────────────────────────
def parse_shift(text):
    """'+2:45' '-1:00' '+165m' '-90m' → 분(int). 부호는 필수."""
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
    if minutes == 0:
        raise SystemExit("--shift가 0분입니다(옮길 것이 없습니다).")
    return sign * minutes


def format_shift(minutes):
    """분 → '+2:45' 형태의 사람용 표기."""
    sign = "+" if minutes >= 0 else "-"
    h, m = divmod(abs(minutes), 60)
    return f"{sign}{h}:{m:02d}"


def _shift_token(tok, minutes):
    """시각 토큰 1개를 옮긴다. 자릿수 표기(9:20 vs 09:20)를 원본대로 유지하고,
    자정을 넘으면 24시간 순환(mod 1440)한다. 시각이 아니면 원본 그대로 둔다."""
    m = TIME_RE.fullmatch(tok)
    if not m:
        return tok
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:  # 24:00 이상·H:60 이상은 시각이 아님(비율·점수 등)
        return tok
    total = (h * 60 + mi + minutes) % MINUTES_PER_DAY
    nh, nm = divmod(total, 60)
    hour = f"{nh:02d}" if len(m.group(1)) == 2 else str(nh)
    return f"{hour}:{nm:02d}"


def shift_text(text, minutes):
    """텍스트 안의 시각 토큰만 옮긴다. 구분자(~ - ∼)·접미(분·경·까지·부터)는
    토큰 밖이라 손대지 않는다."""
    return TIME_RE.sub(lambda m: _shift_token(m.group(0), minutes), text)


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


def shift_document(parts, minutes, scopes=(), excludes=(), keywords=()):
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
        in_ranges = scope_map.get(name, [])
        ex_ranges = exclude_map.get(name, [])

        pieces, pos = [], 0        # 새 섹션 조각(변경 노드만 갈아 끼운다)
        cur_char, cur_byte = 0, 0  # 원본 바이트 오프셋 커서(--exclude range:에 쓸 값)
        for idx, m in enumerate(nodes):
            cur_byte += len(sec[cur_char:m.start()].encode("utf-8"))
            node_byte = cur_byte
            cur_byte += len(m.group(0).encode("utf-8"))
            cur_char = m.end()

            span = (m.start(), m.end())
            if ((scopes and not _contained(span, in_ranges))
                    or _overlaps(span, ex_ranges)          # 제외가 범위보다 우선
                    or any(k and k in texts[idx] for k in keywords)):
                kept += sum(1 for t in TIME_RE.finditer(texts[idx])
                            if _shift_token(t.group(0), minutes) != t.group(0))
                continue

            inner = m.group(2)
            # 시각 토큰은 XML 이스케이프 대상 문자를 포함하지 않으므로 원본 문자열을
            # 그대로 치환한다(이스케이프 왕복으로 인한 변형 방지). 태그는 손대지 않는다.
            new_inner = "".join(
                seg if seg.startswith("<") else shift_text(seg, minutes)
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
# 자기 검산
# ──────────────────────────────────────────────────────────────────────────
def verify_changes(changes, minutes):
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
                hour = f"{nh:02d}" if len(om.group(1)) == 2 else str(nh)
                expect = f"{hour}:{nm:02d}"
            if n != expect:
                problems.append(f"검산 불일치: {o} {format_shift(minutes)} → "
                                f"{n} (기대 {expect}) / 노드 {ch.old!r}")
    return problems


# ──────────────────────────────────────────────────────────────────────────
# 보고(드라이런·신구대조표)
# ──────────────────────────────────────────────────────────────────────────
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


def render_report(changes, kept, minutes, input_path, scopes, excludes, keywords):
    """신구대조표(Markdown) — 드라이런과 같은 변경 목록을 표로 낸다."""
    lines = [
        "# 시각 순연 신구대조표", "",
        f"- 원본 파일: `{os.path.basename(input_path)}`",
        f"- 이동량: {format_shift(minutes)} ({minutes:+d}분)",
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
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────
# 실행
# ──────────────────────────────────────────────────────────────────────────
def shift_file(input_path, output_path, minutes, scopes=(), excludes=(),
               keywords=DEFAULT_KEYWORDS, dry_run=False):
    """시각 순연을 수행한다. 반환: (changes, kept).
    dry_run이면 계획만 세우고 파일을 쓰지 않는다."""
    parts, _ = K.read_package(input_path)
    if not _sections(parts):
        raise SystemExit("section*.xml을 찾을 수 없습니다(유효한 HWPX가 아님).")

    changes, kept, new_sections = shift_document(
        parts, minutes, scopes=scopes, excludes=excludes, keywords=keywords)

    problems = verify_changes(changes, minutes)  # 전건 재계산 — 어긋나면 쓰지 않는다
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
    ap.add_argument("--dry-run", action="store_true", help="쓰지 않고 변경 예정만 출력")
    ap.add_argument("--report", help="신구대조표(Markdown) 저장 경로")
    ap.add_argument("--yes", action="store_true", help="전역 순연(범위 미지정) 확인")
    args = ap.parse_args()

    minutes = parse_shift(args.shift)
    keywords = list(args.exclude_keyword)
    if not args.no_default_keywords:
        keywords = list(DEFAULT_KEYWORDS) + keywords
    if not args.dry_run and not args.output:
        raise SystemExit("--output이 필요합니다(또는 --dry-run으로 먼저 확인하세요).")
    if not args.scope:
        print("[경고] --scope 미지정 — 문서 전체에 적용합니다. 보존해야 할 구간"
              "(외부 교통편·셔틀 운행표 등)에 같은 시각 문자열이 있으면 함께 옮겨집니다.")

    changes, kept = shift_file(args.input, args.output, minutes,
                               scopes=args.scope, excludes=args.exclude,
                               keywords=keywords,
                               dry_run=args.dry_run or (not args.scope and not args.yes))

    scope_txt = ", ".join(args.scope) if args.scope else "문서 전체(범위 미지정)"
    print(f"적용 범위: {scope_txt}")
    print(f"제외 범위: {', '.join(args.exclude) if args.exclude else '없음'}")
    print(f"이동량   : {format_shift(minutes)} ({minutes:+d}분)")
    print(f"변경 {len(changes)}건 / 보존(제외) {kept}건")

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(render_report(changes, kept, minutes, args.input,
                                  args.scope, args.exclude, keywords))
        print(f"신구대조표: {args.report}")

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

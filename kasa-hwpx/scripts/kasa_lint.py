#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kasa_lint.py — KASA 보고서 표기법(날짜·시간·숫자·항목 기호·위계) lint.

행정업무 운영 편람의 공문서 표기 원칙을 KASA 표준보고서에 맞게 적용한다.
(참고: jkf87/hwpx-skill gonmun_lint의 공문 표기법 검사를 KASA 규정으로 이식)

점검 규칙:
  날짜   2026. 7. 7. 형식(온점+공백, 앞 0 제거, 일 뒤 온점). ’YY.MM.DD. 축약형은 허용.
  시간   24시각제 쌍점 표기(14:30). '오후 2시'·'14시 30분'은 경고.
  숫자   4자리 이상 정수의 천 단위 쉼표(연도 제외).
  기호   항목 기호는 □/ㅇ/-/※/* 위계만 사용(○·●·■·• 등 유사 기호 경고).
  위계   ㅇ 항목이 □ 제목보다, - 항목이 ㅇ 항목보다 먼저 나오면 경고.
  기간   물결표(~)는 앞뒤 붙여 씀.

사용법:
    python3 kasa_lint.py <파일.hwpx>            # 표기법 점검(항상 exit 0)
    python3 kasa_lint.py <파일.hwpx> --strict   # 경고가 있으면 exit 1
"""
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
_YEAR = r"(?:19|20)\d{2}"

# 연.월(.일) 후보 — ’YY 축약형은 연도가 2자리라 애초에 걸리지 않는다
_DATE = re.compile(
    rf"(?<![\d’'])({_YEAR})\s*([.\-/])\s*(\d{{1,2}})"
    rf"(?:\s*([.\-/])\s*(\d{{1,2}}))?(\.?)")
_DATE_HANGUL = re.compile(rf"({_YEAR})년\s*(\d{{1,2}})월\s*(\d{{1,2}})일")
_TIME = re.compile(r"(?:오전|오후)\s*\d{1,2}시(?:\s*\d{1,2}분)?"
                   r"|(?<![\d가-힣])\d{1,2}시\s*\d{1,2}분")
# 4자리 이상 정수(쉼표·소수·연속 숫자·범위 하이픈·’YY 문맥 제외)
_NUM = re.compile(r"(?<![\d,.\-’'])\d{4,}(?!\d)(?!\.\d)(?!-)")
_TILDE = re.compile(r"[\d.]\s+~|~\s+[\d.]")
# 허용 위계 기호(□/ㅇ/-/※/*)와 혼동되는 비표준 기호
_BAD_MARKS = "○◎⊙●◦■◇◆▲▷▶►•‣∙"
_MARKER = re.compile(r"^([□ㅇ※*\-])\s+\S")


def paragraphs_from_parts(parts):
    """섹션 XML에서 문단별 텍스트를 뽑는다(표 안 문단은 해당 문단으로만 집계)."""
    paras = []
    names = sorted(n for n in parts
                   if re.match(r"Contents/section\d+\.xml$", n))
    for name in names:
        try:
            root = ET.fromstring(parts[name])
        except ET.ParseError:
            continue
        for p in root.iter(_HP + "p"):
            txt = "".join("".join(t.itertext())
                          for run in p.findall(_HP + "run")
                          for t in run.findall(_HP + "t")).strip()
            if txt:
                paras.append(txt)
    return paras


def _date_issues(m):
    y, s1, mo, s2, d, tail = m.groups()
    frag = m.group()
    issues = []
    if "-" in (s1, s2) or "/" in (s1, s2):
        issues.append("연·월·일은 온점(.)으로 구분")
    if re.search(r"\.\d", frag):
        issues.append("온점 뒤 한 칸 띄움")
    if (len(mo) > 1 and mo.startswith("0")) or (d and len(d) > 1 and d.startswith("0")):
        issues.append("월·일 앞 0 제거")
    if d and not tail:
        issues.append("마지막 일 뒤에도 온점")
    if not issues:
        return None
    fix = f"{y}. {int(mo)}." + (f" {int(d)}." if d else "")
    return f"[경고] 표기법(날짜): '{frag.strip()}' → '{fix}' ({', '.join(issues)})"


def lint_paragraphs(paras):
    """문단 텍스트 목록을 점검해 '[경고] 표기법(…)' 문자열 목록을 돌려준다."""
    warns = []
    first_at = {}  # 위계 기호 최초 등장 순번
    for txt in paras:
        for m in _DATE.finditer(txt):
            w = _date_issues(m)
            if w:
                warns.append(w)
        for m in _DATE_HANGUL.finditer(txt):
            y, mo, d = m.groups()
            warns.append(f"[경고] 표기법(날짜): '{m.group()}' → "
                         f"'{y}. {int(mo)}. {int(d)}.' (온점 표기 원칙)")
        for m in _TIME.finditer(txt):
            warns.append(f"[경고] 표기법(시간): '{m.group()}' — "
                         f"24시각제 쌍점 표기 사용(예: 14:30)")
        for m in _NUM.finditer(txt):
            n = m.group()
            if len(n) == 4 and 1900 <= int(n) <= 2100:
                continue  # 연도
            warns.append(f"[경고] 표기법(숫자): '{n}' → '{int(n):,}' (천 단위 쉼표)")
        for m in _TILDE.finditer(txt):
            warns.append(f"[경고] 표기법(기간): '{m.group().strip()}' — "
                         f"물결표(~)는 앞뒤 붙여 씀")
        if txt[0] in _BAD_MARKS:
            hint = " ('ㅇ'은 한글 자음 이응)" if txt[0] in "○◎⊙◦●" else ""
            warns.append(f"[경고] 표기법(기호): 비표준 항목 기호 '{txt[0]}' — "
                         f"□/ㅇ/-/※/* 위계 사용{hint}")
        mm = _MARKER.match(txt)
        if mm:
            first_at.setdefault(mm.group(1), len(first_at))
    for low, high in [("ㅇ", "□"), ("-", "ㅇ")]:
        if low in first_at and (high not in first_at or
                                first_at[low] < first_at[high]):
            warns.append(f"[경고] 표기법(위계): '{low}' 항목이 상위 '{high}' 없이 "
                         f"먼저 나옴(□→ㅇ→-→※ 순서)")
    return list(dict.fromkeys(warns))


def lint_hwpx(path):
    with zipfile.ZipFile(path) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    return lint_paragraphs(paragraphs_from_parts(parts))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")
        except Exception:
            pass
    args = [a for a in sys.argv[1:] if a != "--strict"]
    if not args:
        print(__doc__)
        sys.exit(1)
    warns = lint_hwpx(args[0])
    print(f"# KASA 표기법 점검: {args[0]}")
    if warns:
        for w in warns:
            print("  " + w)
    else:
        print("  [통과] 표기법 위반 없음 (날짜·시간·숫자·항목 기호·위계)")
    sys.exit(1 if warns and "--strict" in sys.argv else 0)


if __name__ == "__main__":
    main()

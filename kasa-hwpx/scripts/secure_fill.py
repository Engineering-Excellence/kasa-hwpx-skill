#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""secure_fill.py — PII 비경유 HWPX 양식 채우기 (대외비/개인정보 대응).

프로필 JSON의 값(이름·연락처·주민번호 등)을 읽어 양식의 플레이스홀더를 채우되,
값·변환값을 stdout/stderr/예외 메시지에 절대 노출하지 않는다. 재기안 엔진
(redraft)을 in-process로 재사용하므로 값이 명령행 인자·로그로 새지 않는다.
(참고: jkf87/hwpx-skill 85018c4 secure-fill)

프로필 JSON 형식:
  {
    "{{이름}}": "홍길동",
    "{{전화}}": {"value": "01012345678", "format": "phone"},
    "{{생년월일}}": {"value": "19900315", "format": "date"}
  }
  format: phone | rrn | date | upper | lower | nospace | digits | mask

사용법:
  python3 secure_fill.py detect 양식.hwpx --profile p.json   # 키 적중만 출력(값 비출력)
  python3 secure_fill.py fill   양식.hwpx --profile p.json --output 결과.hwpx
  python3 secure_fill.py verify 결과.hwpx --profile p.json   # 마스킹 표시로 반영 확인
  python3 secure_fill.py shred  p.json                       # 프로필 안전 삭제(덮어쓰기)
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kasa_lib as K  # noqa: E402
from redraft import redraft  # noqa: E402

_PLACEHOLDER_RE = re.compile(r"\{\{[^{}]{1,40}\}\}")


# ── 포맷 변환기 (값은 반환만 하고 출력하지 않는다) ─────────────────────────
def _fmt_phone(v):
    d = re.sub(r"\D", "", v)
    if d.startswith("02"):  # 서울 지역번호는 2자리
        if len(d) == 9:
            return f"02-{d[2:5]}-{d[5:]}"
        if len(d) == 10:
            return f"02-{d[2:6]}-{d[6:]}"
        return v
    if len(d) == 11:
        return f"{d[:3]}-{d[3:7]}-{d[7:]}"
    if len(d) == 10:
        return f"{d[:3]}-{d[3:6]}-{d[6:]}" if d.startswith("0") else v
    return v


def _fmt_rrn(v):
    d = re.sub(r"\D", "", v)
    return f"{d[:6]}-{d[6:]}" if len(d) == 13 else v


def _fmt_date(v):
    d = re.sub(r"\D", "", v)
    if len(d) == 8:
        return f"{d[:4]}. {int(d[4:6])}. {int(d[6:])}."
    return v


FORMATTERS = {
    "phone": _fmt_phone,
    "rrn": _fmt_rrn,
    "date": _fmt_date,
    "upper": str.upper,
    "lower": str.lower,
    "nospace": lambda v: re.sub(r"\s+", "", v),
    "digits": lambda v: re.sub(r"\D", "", v),
    "mask": lambda v: (v[:1] + "*" * (len(v) - 1)) if v else v,
}


def mask(v):
    """확인 출력용 마스킹 — 첫 글자만 남긴다."""
    return (v[:1] + "*" * (len(v) - 1)) if v else "(빈 값)"


def load_profile(path):
    """프로필 JSON → {키: 변환된 값}. 값은 호출자 밖으로 출력 금지."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict) or not raw:
        raise SystemExit("프로필은 비어있지 않은 JSON 객체여야 합니다.")
    out = {}
    for key, item in raw.items():
        if isinstance(item, dict):
            value = str(item.get("value", ""))
            fmt = item.get("format")
            if fmt is not None and fmt not in FORMATTERS:
                raise SystemExit(f"알 수 없는 format: {fmt} "
                                 f"(가능: {', '.join(FORMATTERS)})")
            if fmt:
                value = FORMATTERS[fmt](value)
        else:
            value = str(item)
        out[str(key)] = value
    return out


def detect(hwpx_path, profile):
    """문서 내 프로필 키 적중 수와, 프로필에 없는 {{플레이스홀더}}를 찾는다.
    반환: ({키: 등장 수}, [미등록 플레이스홀더])."""
    text = K.extract_text(hwpx_path)
    hits = {key: text.count(key) for key in profile}
    unknown = sorted(set(_PLACEHOLDER_RE.findall(text)) - set(profile))
    return hits, unknown


def fill(hwpx_path, profile, out_path):
    """플레이스홀더를 채운다. 반환: {키: 치환 수}. 값은 예외에도 노출하지 않는다."""
    try:
        _, counts = redraft(hwpx_path, profile, out_path, mode="contains")
    except SystemExit:
        raise
    except Exception as e:  # 값이 traceback에 실려 나가지 않도록 형(type)만 알린다
        raise SystemExit(f"fill 실패: {type(e).__name__} "
                         f"(값 보호를 위해 상세를 출력하지 않음)") from None
    return counts


def verify(hwpx_path, profile):
    """채워진 문서에 각 값이 반영됐는지 확인. 반환: {키: (반영 여부, 마스킹 값)}."""
    text = K.extract_text(hwpx_path)
    return {key: (val in text, mask(val)) for key, val in profile.items()}


def shred(path, passes=3):
    """프로필 파일을 무작위 바이트로 덮어쓴 뒤 삭제한다(일반 저장장치 기준)."""
    size = os.path.getsize(path)
    with open(path, "r+b") as f:
        for _ in range(passes):
            f.seek(0)
            f.write(os.urandom(size))
            f.flush()
            os.fsync(f.fileno())
    os.remove(path)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="PII 비경유 HWPX 양식 채우기")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("detect", help="프로필 키 적중 확인(값 비출력)")
    d.add_argument("input"); d.add_argument("--profile", required=True)
    f = sub.add_parser("fill", help="양식 채우기(값 비출력)")
    f.add_argument("input"); f.add_argument("--profile", required=True)
    f.add_argument("--output", required=True)
    v = sub.add_parser("verify", help="반영 확인(마스킹 표시)")
    v.add_argument("input"); v.add_argument("--profile", required=True)
    s = sub.add_parser("shred", help="프로필 파일 안전 삭제")
    s.add_argument("profile_path")
    a = ap.parse_args()

    if a.cmd == "shred":
        shred(a.profile_path)
        print(f"프로필 안전 삭제 완료: {a.profile_path}")
        return

    profile = load_profile(a.profile)
    if a.cmd == "detect":
        hits, unknown = detect(a.input, profile)
        for key, n in hits.items():
            print(f"  - {key}: {'적중 ' + str(n) + '곳' if n else '[경고] 미적중'}")
        for ph in unknown:
            print(f"  - [경고] 프로필에 없는 플레이스홀더: {ph}")
    elif a.cmd == "fill":
        counts = fill(a.input, profile, a.output)
        print(f"채움 완료: {a.output}")
        for key, n in counts.items():
            print(f"  - {key}: {'치환 ' + str(n) + '건' if n else '[경고] 미적중'}")
        print("  ※ 확인은 verify(마스킹), 프로필 폐기는 shred를 사용하세요.")
    elif a.cmd == "verify":
        ok = True
        for key, (found, masked) in verify(a.input, profile).items():
            print(f"  - {key} → {masked}: {'반영됨' if found else '[경고] 미반영'}")
            ok = ok and found
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

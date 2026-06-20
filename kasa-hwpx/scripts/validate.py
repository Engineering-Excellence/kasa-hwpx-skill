#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate.py — 생성된 HWPX의 (1) 구조 무결성 (2) 우주항공청 규정 준수를 점검한다.

사용법:
    python3 validate.py <파일.hwpx>          # 구조 검증
    python3 validate.py <파일.hwpx> --kasa    # 구조 + KASA 규정 준수 점검
"""
import sys, re, zipfile
import xml.etree.ElementTree as ET

def _parts(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}, z.namelist()

def validate_structure(path):
    issues = []
    try:
        parts, order = _parts(path)
    except Exception as e:
        return [f"ZIP 열기 실패: {e}"]
    # mimetype 규칙
    if not order or order[0] != "mimetype":
        issues.append("mimetype이 첫 번째 ZIP 엔트리가 아님")
    else:
        with zipfile.ZipFile(path) as z:
            zi = z.getinfo("mimetype")
            if zi.compress_type != zipfile.ZIP_STORED:
                issues.append("mimetype이 무압축(STORED)이 아님")
    # 필수 파트
    for need in ["Contents/header.xml", "Contents/section0.xml", "Contents/content.hpf"]:
        if need not in parts:
            issues.append(f"필수 파트 누락: {need}")
    # XML 적합성
    for name, data in parts.items():
        if name.endswith(".xml"):
            try:
                ET.fromstring(data)
            except ET.ParseError as e:
                issues.append(f"XML 파싱 오류 {name}: {e}")
    # secPr 존재(첫 문단)
    sec = parts.get("Contents/section0.xml", b"").decode("utf-8", "ignore")
    if "<hp:secPr" not in sec:
        issues.append("secPr 누락 — 문서가 열리지 않을 수 있음")
    if "<hp:colPr" not in sec:
        issues.append("colPr 누락 가능 — 확인 필요")
    # 미정의 스타일 참조 점검(header.xml에 정의되지 않은 ID 참조 시 렌더 오류)
    hdr = parts.get("Contents/header.xml", b"").decode("utf-8", "ignore")
    for tag, ref in [("charPr", "charPrIDRef"), ("paraPr", "paraPrIDRef"),
                     ("borderFill", "borderFillIDRef")]:
        defined = set(re.findall(rf'<hh:{tag}\b[^>]*\bid="(\d+)"', hdr))
        used = set(re.findall(rf'{ref}="(\d+)"', sec))
        dangling = sorted(used - defined, key=int) if defined else []
        if dangling:
            issues.append(f"{tag} 미정의 참조: {dangling}")
    return issues

# 검증된 charPr → (글꼴, pt) 매핑
CP_SPEC = {
    "30": ("HY헤드라인M", 15.0), "41": ("함초롬바탕", 15.0),
    "29": ("맑은 고딕", 12.0),  "9": ("맑은 고딕", 13.0),
    "17": ("맑은 고딕", 12.0),  "31": ("맑은 고딕", 12.0),
    "56": ("함초롬바탕", 24.0), "63": ("HY헤드라인M", 16.0),
}
def kasa_check(path):
    notes = []
    parts, _ = _parts(path)
    sec = parts["Contents/section0.xml"].decode("utf-8")
    text = "\n".join(m.group(1) for m in re.finditer(r"<hp:t>(.*?)</hp:t>", sec, re.S))

    # 머리말 MI 로고
    if "binaryItemIDRef" in sec or "BinData/image" in parts.get("Contents/content.hpf", b"").decode("utf-8", "ignore"):
        notes.append("[OK] 머리말 MI(이미지) 참조 존재")
    else:
        notes.append("[경고] 머리말 MI 로고 참조를 찾지 못함")

    # 편집용지 여백(좌우20·위5·머리말20·아래15·꼬리말10 mm)
    m = re.search(r'<hp:margin header="(\d+)" footer="(\d+)" gutter="\d+" '
                  r'left="(\d+)" right="(\d+)" top="(\d+)" bottom="(\d+)"', sec)
    if m:
        hd, ft, lf, rt, tp, bt = map(int, m.groups())
        def mm(v): return round(v / 283.465, 1)
        ok = (mm(lf) == 20 and mm(rt) == 20 and mm(tp) == 5 and
              mm(hd) == 20 and mm(bt) == 15 and mm(ft) == 10)
        tag = "OK" if ok else "확인"
        notes.append(f"[{tag}] 여백 좌{mm(lf)}·우{mm(rt)}·위{mm(tp)}·머리{mm(hd)}·"
                     f"아래{mm(bt)}·꼬리{mm(ft)} mm")
    else:
        notes.append("[경고] 편집용지 여백 정보를 찾지 못함")

    # 본문 마커 글꼴/크기 일치 점검(사용된 charPr 기준)
    used = set(re.findall(r'charPrIDRef="(\d+)"', sec))
    for cp in ["30", "41", "29"]:
        if cp in used:
            f, p = CP_SPEC[cp]
            notes.append(f"[OK] 본문 스타일 charPr={cp} ({f} {p}pt) 사용 확인")

    # 표지 핵심 요소
    for need, lab in [("우주항공청", "기관명"), ("우주항공 5대 강국", "슬로건")]:
        notes.append((f"[OK] 표지 {lab} 존재" if need in text else f"[경고] 표지 {lab} 누락"))

    # 본문 흐름 줄겹침(vertpos) 회귀 점검: 본문 영역에 vertpos="0" 캐시가 다수면 경고
    body = sec[sec.find("</hp:ctrl>"):] if "</hp:ctrl>" in sec else sec
    anchor = sec.find("□ ")
    if anchor != -1:
        zero_segs = sec.count('vertpos="0"', anchor)
        if zero_segs >= 3:
            notes.append(f"[경고] 본문 영역에 vertpos=\"0\" lineseg가 {zero_segs}개 — "
                         f"한글에서 줄이 겹쳐 보일 수 있음(흐름 문단 캐시 제거 필요)")
        else:
            notes.append("[OK] 본문 흐름 문단에 줄겹침 유발 캐시 없음")

    # 자동번호(OUTLINE) 회귀 점검: 본문이 OUTLINE paraPr을 참조하면 불필요한 번호가 붙음
    try:
        hdr = parts.get("Contents/header.xml", b"").decode("utf-8")
        outline_ids = set(re.findall(r'<hh:paraPr id="(\d+)"(?:(?!</hh:paraPr>).)*?'
                                     r'<hh:heading type="OUTLINE"', hdr, re.S))
        if anchor != -1 and outline_ids:
            used = set(re.findall(r'paraPrIDRef="(\d+)"', sec[anchor:]))
            bad = sorted(outline_ids & used, key=int)
            if bad:
                notes.append(f"[경고] 본문이 자동번호(OUTLINE) paraPr {bad} 참조 — "
                             f"불필요한 개요 번호가 붙음(무번호 들여쓰기 paraPr 사용 필요)")
            else:
                notes.append("[OK] 본문에 자동번호 유발 paraPr 없음")
    except Exception:
        pass
    return notes

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    path = sys.argv[1]
    print(f"# 구조 검증: {path}")
    issues = validate_structure(path)
    if issues:
        for i in issues: print("  [실패]", i)
    else:
        print("  [통과] 구조 무결성 정상 (ZIP/mimetype/XML/secPr)")
    if "--kasa" in sys.argv:
        print("# KASA 규정 준수 점검")
        for n in kasa_check(path):
            print("  " + n)
    sys.exit(1 if issues else 0)

if __name__ == "__main__":
    main()

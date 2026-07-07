#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_vertical.py — 세로쓰기 오변환 자동보정.

hwp→hwpx 외부 변환기가 표 셀 textDirection을 무더기로 VERTICAL로 잘못 넣는
사고 사례가 보고됨(참고: jkf87/hwpx-skill '세로쓰기 오변환 자동보정').
문서 전반이 세로쓰기인 한글 문서는 사실상 없으므로, VERTICAL이 HORIZONTAL보다
많으면(다수결) 오변환으로 판단해 전부 HORIZONTAL로 되돌린다.

- 다수결 미충족 시(부분 세로쓰기 = 의도된 서식일 수 있음) 보정하지 않고 종료(1).
  정말 되돌리려면 --force.
- 서식 보존 기록: 변경된 섹션만 교체하고 나머지 엔트리는 원본 ZipInfo 유지.

사용법:
  python3 fix_vertical.py --input 변환본.hwpx --output 보정본.hwpx [--force]
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kasa_lib as K  # noqa: E402

_VERT = 'textDirection="VERTICAL"'
_HORZ = 'textDirection="HORIZONTAL"'


def fix_vertical(input_path, output_path, force=False):
    """세로쓰기 오변환을 보정한다.
    반환: (flip 수, VERTICAL 수, HORIZONTAL 수). flip 수 0이면 파일을 쓰지 않음."""
    parts, _ = K.read_package(input_path)
    section_names = sorted(n for n in parts
                           if re.match(r"Contents/section\d+\.xml$", n))
    if not section_names:
        raise SystemExit("section*.xml을 찾을 수 없습니다(유효한 HWPX가 아님).")

    texts = {n: parts[n].decode("utf-8") for n in section_names}
    n_vert = sum(t.count(_VERT) for t in texts.values())
    n_horz = sum(t.count(_HORZ) for t in texts.values())
    if n_vert == 0:
        return 0, n_vert, n_horz
    if n_vert <= n_horz and not force:
        # 다수결 미충족: 의도된 부분 세로쓰기일 수 있으므로 건드리지 않는다
        return 0, n_vert, n_horz

    replaced = {n: t.replace(_VERT, _HORZ).encode("utf-8")
                for n, t in texts.items() if _VERT in t}
    if replaced:
        # PrvText는 텍스트 불변이므로 갱신 불요 — 섹션만 교체(zip 메타데이터 보존)
        K.write_package_preserving(input_path, output_path, replaced)
        K.fix_namespaces(output_path)
    return n_vert, n_vert, n_horz


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="세로쓰기 오변환 자동보정")
    ap.add_argument("--input", required=True, help="원본(변환본) HWPX 경로")
    ap.add_argument("--output", required=True, help="보정본 HWPX 경로")
    ap.add_argument("--force", action="store_true",
                    help="다수결 미충족이어도 VERTICAL을 전부 HORIZONTAL로 되돌림")
    args = ap.parse_args()

    flipped, n_vert, n_horz = fix_vertical(args.input, args.output, args.force)
    print(f"textDirection: VERTICAL {n_vert} / HORIZONTAL {n_horz}")
    if flipped:
        print(f"보정 완료: {args.output} (VERTICAL→HORIZONTAL {flipped}곳)")
    elif n_vert == 0:
        print("세로쓰기 없음 — 보정 불요(파일을 쓰지 않음)")
    else:
        print("[중단] VERTICAL이 다수가 아님 — 의도된 부분 세로쓰기일 수 있어 "
              "보정하지 않음. 정말 되돌리려면 --force.")
        sys.exit(1)


if __name__ == "__main__":
    main()

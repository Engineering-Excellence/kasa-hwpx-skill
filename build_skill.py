#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kasa-hwpx/ 폴더를 kasa-hwpx.skill(zip)로 패키징한다.
   - __pycache__ 등 캐시는 제외한다.
   - 산출물은 dist/kasa-hwpx.skill.
사용법: python3 build_skill.py
"""
import os
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "kasa-hwpx")
DIST = os.path.join(ROOT, "dist")
OUT = os.path.join(DIST, "kasa-hwpx.skill")

EXCLUDE_DIRS = {"__pycache__", ".git", ".idea", ".vscode"}
EXCLUDE_EXT = {".pyc", ".pyo"}


def main():
    if not os.path.isdir(SRC):
        raise SystemExit("kasa-hwpx/ 폴더를 찾을 수 없습니다.")
    os.makedirs(DIST, exist_ok=True)
    if os.path.exists(OUT):
        os.remove(OUT)
    count = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for cur, dirs, files in os.walk(SRC):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for fn in sorted(files):
                if os.path.splitext(fn)[1] in EXCLUDE_EXT:
                    continue
                full = os.path.join(cur, fn)
                # 아카이브 내부 경로: kasa-hwpx/... 형태 유지
                arc = os.path.relpath(full, ROOT)
                z.write(full, arc)
                count += 1
    print(f"생성: {os.path.relpath(OUT, ROOT)} (파일 {count}개)")


if __name__ == "__main__":
    main()

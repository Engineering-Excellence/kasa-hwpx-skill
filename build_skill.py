#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kasa-hwpx/ 폴더를 kasa-hwpx_v{버전}.skill(zip)로 패키징한다.
   - 버전은 kasa-hwpx/SKILL.md 프런트매터의 `version:` 필드에서 읽는다(단일 출처).
   - __pycache__ 등 캐시는 제외한다.
   - 산출물은 dist/kasa-hwpx_v{버전}.skill.
사용법: python3 build_skill.py
"""
import os
import re
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "kasa-hwpx")
DIST = os.path.join(ROOT, "dist")

EXCLUDE_DIRS = {"__pycache__", ".git", ".idea", ".vscode"}
EXCLUDE_EXT = {".pyc", ".pyo"}


def read_version():
    """SKILL.md 프런트매터에서 version 값을 읽는다."""
    skill_md = os.path.join(SRC, "SKILL.md")
    with open(skill_md, encoding="utf-8") as f:
        head = f.read(2048)
    m = re.search(r"^version:\s*([0-9A-Za-z.\-]+)\s*$", head, re.M)
    if not m:
        raise SystemExit("kasa-hwpx/SKILL.md 프런트매터에 version 필드가 없습니다.")
    return m.group(1)


def main():
    if not os.path.isdir(SRC):
        raise SystemExit("kasa-hwpx/ 폴더를 찾을 수 없습니다.")
    version = read_version()
    out = os.path.join(DIST, f"kasa-hwpx_v{version}.skill")
    os.makedirs(DIST, exist_ok=True)
    if os.path.exists(out):
        os.remove(out)
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
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
    print(f"생성: {os.path.relpath(out, ROOT)} (파일 {count}개)")


if __name__ == "__main__":
    main()

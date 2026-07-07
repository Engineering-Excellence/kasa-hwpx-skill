#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sample_guard.py — PreToolUse 가드 (b): 예시/견본 문서의 실산출물 오인 전달 차단.

스킬에 동봉된 견본(기준 양식·예제 보고서)이나 표지 필드가 채워지지 않은 템플릿
복사본을 사용자에게 열어 주거나 전달 폴더로 복사하는 명령을 차단(exit 2)한다.
(참고: jkf87/hwpx-skill report_placeholder_hook — placeholder 문구 잔존 탐지)

등록: .claude/settings.json > hooks > PreToolUse > matcher "Bash" (hooks/README.md 참고)
"""
import os
import re
import zipfile

from _hook_common import command_of, hwpx_paths, is_delivery, run

# 스킬 동봉 견본 파일명 — 이름 그대로 전달하면 무조건 차단
BUNDLED = {"kasa-standard-report.hwpx", "sample-report.hwpx",
           "reference-form-spacing.hwpx"}
# 표지 필드 미기입 템플릿 흔적(기준 양식의 placeholder 문구)
PLACEHOLDERS = ("행정법무담당관", "’26.00.00", "□ 제목1")


def _leftover(path):
    try:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist()
                     if re.match(r"Contents/section\d+\.xml$", n)]
            body = "".join(z.read(n).decode("utf-8", "ignore") for n in names)
    except Exception:
        return None
    return next((p for p in PLACEHOLDERS if p in body), None)


def check(evt):
    cmd = command_of(evt)
    if not cmd or not is_delivery(cmd):
        return None
    for path in hwpx_paths(cmd, evt.get("cwd", ".")):
        if os.path.basename(path) in BUNDLED:
            return (f"[sample_guard] {path} 은(는) 스킬 동봉 견본입니다. "
                    f"실제 내용으로 보고서를 생성(build_report.py)한 뒤 전달하세요.")
        hit = _leftover(path)
        if hit:
            return (f"[sample_guard] {path} 에 템플릿 placeholder('{hit}')가 남아 있어 "
                    f"미완성 견본으로 판단됩니다. 표지·본문을 실제 내용으로 채운 뒤 "
                    f"전달하세요.")
    return None


if __name__ == "__main__":
    run(check)

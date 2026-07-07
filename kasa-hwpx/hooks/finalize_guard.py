#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finalize_guard.py — PreToolUse 가드 (a): 산출물 전달 전 validate --kasa 통과 강제.

.hwpx를 열거나 전달 폴더(Downloads/Desktop/바탕화면 등)로 복사·이동하는 Bash 명령을
가로채, 구조 무결성 실패 또는 KASA 규정 경고(표기법 포함)가 있으면 차단(exit 2)한다.
한글이 저장한 정상 lineseg 캐시 휴리스틱은 제외한다(오탐 방지).

등록: .claude/settings.json > hooks > PreToolUse > matcher "Bash" (hooks/README.md 참고)
"""
from _hook_common import command_of, hwpx_paths, is_delivery, run


def check(evt):
    cmd = command_of(evt)
    if not cmd or not is_delivery(cmd):
        return None
    for path in hwpx_paths(cmd, evt.get("cwd", ".")):
        import validate
        issues = validate.validate_structure(path)
        if issues:
            return (f"[finalize_guard] {path} 구조 검증 실패: {'; '.join(issues[:5])}\n"
                    f"전달 전 문서를 수정하고 validate.py로 재검증하세요.")
        warns = [n for n in validate.kasa_check(path)
                 if n.startswith("[경고]") and "lineseg" not in n]
        if warns:
            return (f"[finalize_guard] {path} KASA 규정 경고 {len(warns)}건:\n  "
                    + "\n  ".join(warns[:8])
                    + "\n경고를 해소한 뒤(validate.py --kasa 통과) 다시 전달하세요.")
    return None


if __name__ == "__main__":
    run(check)

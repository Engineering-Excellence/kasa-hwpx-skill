# -*- coding: utf-8 -*-
"""PreToolUse 가드 훅 공용 헬퍼 — stdin 이벤트 파싱, 전달 명령 판정, 경로 추출.

Claude Code hook 규약: stdin으로 {"tool_name","tool_input":{"command"},"cwd"} JSON을
받고, exit 0=통과, exit 2=차단(stderr 사유를 Claude가 읽고 스스로 교정)이다.
훅 내부 오류는 사용자 작업을 막지 않도록 통과(exit 0) 처리한다.
(참고: jkf87/hwpx-skill gyehoek_hook·hwpx_guard_hook·report_placeholder_hook 규약)
"""
import json
import os
import re
import sys

SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "..", "scripts"))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

# 산출물 "전달" 동사 — 복사/이동/열기(POSIX·Windows·PowerShell)
_DELIVER_CMD = re.compile(
    r"(?:^|[\s;&|(])(?:cp|mv|rsync|ditto|open|start|explorer(?:\.exe)?|"
    r"copy|move|xcopy|robocopy|Copy-Item|Move-Item|Invoke-Item)(?=\s|$)",
    re.I)
_OPEN_CMD = re.compile(r"(?:^|[\s;&|(])(?:open|start|explorer(?:\.exe)?|Invoke-Item)"
                       r"(?=\s|$)", re.I)
_DELIVER_DIRS = ("downloads", "desktop", "다운로드", "바탕화면", "바탕 화면", "onedrive")


def read_event():
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def command_of(evt):
    ti = evt.get("tool_input") or {}
    return ti.get("command") or ""


def is_delivery(cmd):
    """산출물을 사용자에게 전달하는 명령인가(열기, 또는 전달 폴더로 복사/이동)."""
    if not _DELIVER_CMD.search(cmd):
        return False
    low = cmd.lower()
    return bool(_OPEN_CMD.search(cmd) or any(d in low for d in _DELIVER_DIRS))


def hwpx_paths(cmd, cwd="."):
    """명령 문자열에서 실재하는 .hwpx 경로들을 뽑는다(따옴표/공백 경로 지원)."""
    found = []
    for m in re.finditer(r'"([^"]+?\.hwpx)"|\'([^\']+?\.hwpx)\'|(\S+?\.hwpx)(?=\s|$)',
                         cmd, re.I):
        p = next(g for g in m.groups() if g)
        if not os.path.isabs(p):
            p = os.path.join(cwd or ".", p)
        if os.path.isfile(p) and p not in found:
            found.append(p)
    return found


def block(msg):
    sys.stderr.write(msg + "\n")
    sys.exit(2)


def run(check):
    """훅 본체 실행기 — check(evt)가 문자열을 돌려주면 차단, None이면 통과."""
    try:
        reason = check(read_event())
    except Exception:
        sys.exit(0)  # 훅 오류로 작업을 막지 않는다
    if reason:
        block(reason)
    sys.exit(0)

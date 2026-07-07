#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
spec_guard.py — PreToolUse 가드 (c): 필수 정보 미확보 시 사용자 질문 강제.

build_report.py 실행 명령을 가로채 제목·작성정보(기안자/부서)·발행시기가 비었거나
placeholder(○○, 00.00)면 차단(exit 2)하고, Claude가 사용자에게 (한 번에 하나씩)
질문한 뒤 채워서 재실행하도록 유도한다.
(참고: jkf87/hwpx-skill gyehoek_hook — 필수 플래그 미명시 시 질문 강제)

등록: .claude/settings.json > hooks > PreToolUse > matcher "Bash" (hooks/README.md 참고)
"""
import json
import os
import re

from _hook_common import command_of, run

_PLACEHOLDER = re.compile(r"○○|00\.00|\bXX\b")


def _arg_of(cmd, flag):
    m = re.search(rf'{flag}\s+(?:"([^"]+)"|\'([^\']+)\'|(\S+))', cmd)
    return next((g for g in m.groups() if g), None) if m else None


def _resolve(path, evt):
    return path if os.path.isabs(path) else os.path.join(evt.get("cwd") or ".", path)


def _spec_missing(spec):
    missing = []
    title = (spec.get("title") or "").strip()
    if not title or title == "보고서 제목":
        missing.append("제목(title)")
    author = (spec.get("author") or "").strip()
    if not author or _PLACEHOLDER.search(author):
        missing.append("작성정보(author: 날짜·기안 부서)")
    if not (spec.get("pub_date") or "").strip():
        missing.append("발행시기(pub_date)")
    return missing


def check(evt):
    cmd = command_of(evt)
    if not cmd or "build_report.py" not in cmd:
        return None
    ask = ("사용자에게 부족한 항목을 한 번에 하나씩 질문해 확보한 뒤 "
           "사양을 채워 재실행하세요.")
    spec = None
    spec_path = _arg_of(cmd, "--spec")
    md_path = _arg_of(cmd, "--markdown")
    try:
        if spec_path:
            with open(_resolve(spec_path, evt), encoding="utf-8") as f:
                spec = json.load(f)
        elif md_path:
            import build_report
            with open(_resolve(md_path, evt), encoding="utf-8") as f:
                spec = build_report.parse_markdown(f.read())
            title = _arg_of(cmd, "--title")
            if title:
                spec["title"] = title
    except Exception:
        return None  # 파일 문제는 build_report 자체 오류에 맡긴다
    if spec is None:
        return None
    missing = _spec_missing(spec)
    if missing:
        return (f"[spec_guard] 필수 정보 미확보: {', '.join(missing)}. " + ask)
    return None


if __name__ == "__main__":
    run(check)

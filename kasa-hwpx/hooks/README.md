# PreToolUse 가드 훅 3종 (Claude Code 전용 어댑터)

Claude Code가 KASA 보고서 작업 중 저지르기 쉬운 사고를 도구 실행 **전에** 차단한다.
(참고: jkf87/hwpx-skill의 gyehoek_hook·hwpx_guard_hook·report_placeholder_hook 구성)

> 이 훅들은 Claude Code의 PreToolUse 규약(stdin JSON/exit 2)에 묶인 **플랫폼 어댑터**다.
> Codex·Gemini 등 다른 플랫폼에서는 등록할 수 없으며, 에이전트가 아래 차단 대상을
> **수동 게이트**로 스스로 지켜야 한다(AGENTS.md 7장). 스킬의 안전 규칙은 훅 없이도
> SKILL.md Critical Rules + `validate.py --kasa`만으로 성립한다.

| 훅 | 차단 대상 | 시점 |
| --- | --- | --- |
| `finalize_guard.py` | 구조 실패·KASA 규정 경고(표기법 포함)가 있는 .hwpx 전달 | .hwpx 열기 / 전달 폴더(Downloads·Desktop·바탕화면 등)로 복사·이동 |
| `sample_guard.py` | 동봉 견본(기준 양식·예제)·placeholder 잔존 문서의 오인 전달 | 위와 동일 |
| `spec_guard.py` | 제목·작성정보·발행시기 미확보 상태의 보고서 생성 | `build_report.py` 실행 |

## 동작 규약

- stdin으로 PreToolUse 이벤트 JSON(`{"tool_input":{"command":...},"cwd":...}`)을 받는다.
- **exit 0** = 통과, **exit 2** = 차단 — stderr 사유를 Claude가 읽고 스스로 교정한다
  (사용자에게 질문하거나, 문서를 고쳐 재검증 후 재시도).
- 훅 내부 오류는 작업을 막지 않도록 통과 처리한다(fail-open).

## 등록 방법

프로젝트(또는 사용자) `.claude/settings.json`에 추가한다.
`<SKILL>`은 이 스킬이 설치된 절대 경로로 바꾼다. Windows는 `python3` 대신 `python`.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {"type": "command", "command": "python3 <SKILL>/kasa-hwpx/hooks/finalize_guard.py"},
          {"type": "command", "command": "python3 <SKILL>/kasa-hwpx/hooks/sample_guard.py"},
          {"type": "command", "command": "python3 <SKILL>/kasa-hwpx/hooks/spec_guard.py"}
        ]
      }
    ]
  }
}
```

## 수동 점검

```bash
echo '{"tool_input":{"command":"cp 보고서.hwpx ~/Downloads/"},"cwd":"."}' \
  | python3 hooks/finalize_guard.py; echo "exit=$?"
```

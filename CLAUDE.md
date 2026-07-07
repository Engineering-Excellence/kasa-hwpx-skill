# CLAUDE.md

@AGENTS.md

## Claude Code 추가 사항

- **커밋·푸쉬 정책(중요):** 커밋은 사용자가 작업 진행을 지시한 범위에서 기능 단위로만 수행하고,
  **푸쉬·태그·릴리스는 반드시 사용자의 명시적 지시가 있을 때만** 한다.
- Windows에서 스크립트 실행 시 `PYTHONIOENCODING=utf-8`을 붙여 cp949 콘솔 출력 깨짐을 피한다.
  (스크립트 자체도 `sys.stdout.reconfigure(errors="replace")` 방어가 있으나, 텍스트 추출 결과를
  파이프로 받을 때는 환경변수가 필요하다.)
- 이 저장소의 가드 훅(`kasa-hwpx/hooks/`)을 이 프로젝트의 `.claude/settings.json`에 등록해 두면
  견본 오전달·미검증 산출물 전달을 도구 실행 전에 차단할 수 있다(등록법: `kasa-hwpx/hooks/README.md`).
- 작업을 이어받을 때의 순서: `BACKLOG.md`(잔여 작업) → `git log --oneline -10`(최근 흐름) →
  `python -m unittest discover -s tests`(94개 통과 확인) → 착수.

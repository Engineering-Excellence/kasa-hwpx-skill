# AGENTS.md — AI 에이전트/개발자 작업 가이드

우주항공청(KASA) 표준보고서 HWPX 스킬 저장소. 이 문서는 **어느 컴퓨터, 어느 에이전트에서든
이 저장소만 clone하면 맥락 없이 작업을 이어받을 수 있게** 하는 진입점이다.
(Claude Code는 `CLAUDE.md`가 이 문서를 가져온다. 다른 에이전트는 이 문서를 직접 읽으면 된다.)

## 0. 최우선 원칙: 공문서 안전성

이 스킬의 산출물은 **정부 기관의 공문서**다. "한글(HWP)에서 열리지 않는 파일"이나
"서식이 미묘하게 깨진 파일"은 기능 부족보다 훨씬 나쁘다. 따라서:

1. **검증된 실물 패턴만 사용한다.** 새 XML 구조는 기준 양식(`assets/kasa-standard-report.hwpx`)
   또는 한글이 실제로 저장한 파일에서 추출한 패턴만 쓴다.
   실물 패턴이 없는 구조는 **창작하지 않는다** — 네이티브 각주·하이퍼링크(BACKLOG 4번)가
   이 원칙으로 제외 확정된 전례다(2026-07-07, 사용자 결정).
2. **모든 기능 변경에는 회귀 테스트를 동반한다.** 현재 94케이스, 전부 통과 상태 유지.
3. **릴리스 전 한글 실물 열람 확인.** 구조 검증(validate) 통과 ≠ 렌더 보장.
   rc 버전(`X.Y.Z-rc1`)으로 사전 빌드 → 사용자가 한글에서 열람 확인 → 정식 버전 승격.
4. **교훈(v0.5.0 사건):** 고정 파일명 배포로 버전 식별이 불가능해, 정상 코드가 결함으로
   오인되어 롤백된 적이 있다. 배포본은 반드시 `kasa-hwpx_v{버전}.skill`로 버전을 박는다.
   버전의 단일 출처는 `kasa-hwpx/SKILL.md` 프런트매터의 `version:` 필드 하나다.

## 1. 문서 지도 (무엇이 어디의 SSOT인가)

| 문서 | 역할 |
| --- | --- |
| `BACKLOG.md` | **잔여 작업·제외 판단·업스트림 관찰 시점(커밋 SHA)** — 이어서 할 일은 여기부터 |
| `README.md` | 프로젝트 소개·사용법·**버전 이력**(릴리스 때 갱신) |
| `kasa-hwpx/SKILL.md` | 스킬 규칙 전문(Critical Rules 1~22)·**버전 필드(단일 출처)** |
| `kasa-hwpx/references/` | 양식 규격·스타일 ID 맵·XML 구조 — 스타일 값은 여기 있는 것만 사용 |
| `kasa-hwpx/hooks/README.md` | Claude Code 가드 훅 등록 방법 |
| `사용설명서.md` | 비개발자용 안내 — **사용자 기능이 추가되면 여기도 함께 갱신** |

## 2. 시작 절차

```bash
git clone https://github.com/Engineering-Excellence/kasa-hwpx-skill.git
cd kasa-hwpx-skill
python3 -m unittest discover -s tests    # 94개 통과 확인 후 작업 시작
```

- **Python 3.10+, 외부 의존성 없음**(표준 라이브러리만). `python-hwpx`·`lxml` 등을 설치하지 않는다.
- **Windows 주의:** 콘솔이 cp949라 한글/특수문자 출력이 깨질 수 있다 →
  `PYTHONIOENCODING=utf-8` 환경변수로 실행. `python3` 대신 `python`일 수 있음.
- 이어서 할 일: `BACKLOG.md`의 잔여 후보(위에서부터 권장 순서)와 "작업 시작 절차" 참고.

## 3. 작업 관례

- **기능 1개 = 커밋 1개.** Conventional Commits, 제목은 한국어.
  예: `feat(image): 직인/서명 이미지 삽입·교체·삭제(hwpx_image.py)`
- **커밋은 사용자가 작업 진행을 지시한 범위에서만, 푸쉬·태그·릴리스는 반드시 명시적 지시 후.**
- 기능 커밋에는 회귀 테스트를 함께 넣는다. `tests/`는 `.skill` 패키지에 포함되지 않는다.
- **문서 동기화 규칙: 사용자에게 보이는 기능·동작이 바뀌면 늦어도 릴리스 전까지
  `사용설명서.md`(비개발자 관점)와 `README.md`(사용법·버전 이력)를 함께 갱신한다.**
  반영할 내용이 없으면(내부 품질 개선 등) 릴리스 커밋 본문에 "설명서 갱신 불요"와 사유를 남긴다.
- 코드 주석·출력 메시지는 한국어. 기존 파일의 스타일(정규식 기반 문자열 수술, 한국어 docstring)을 따른다.
- 업스트림 아이디어를 이식하면 커밋/주석에 출처를 남긴다(예: `참고: jkf87/hwpx-skill gonmun_lint`).

## 4. 아키텍처 요약 (자세한 것은 SKILL.md)

- `kasa_lib.py`가 핵심 엔진. 나머지 스크립트는 CLI 껍데기 + 도메인 로직.
- **서식 보존 편집 경로는 반드시 `write_package_preserving`**을 쓴다 — 미변경 zip 엔트리의
  ZipInfo(순서·시각·압축방식)를 보존하고, `additions`/`removals`로 엔트리 추가·삭제까지 처리.
- 본문을 바꾸면 `Preview/PrvText.txt`를 재생성하고, 바꾼 문단의 `linesegarray`(줄 위치 캐시)를
  제거해 한글이 열 때 재계산하게 한다(줄겹침 방지 — SKILL.md 규칙 9·19).
- `validate.py --kasa`가 최종 관문: 구조 무결성 + KASA 규정 + 표기법 lint(kasa_lint 통합).
- 가드 훅(`hooks/`)은 stdin 이벤트 JSON → exit 0(통과)/2(차단, stderr 사유), 내부 오류는 fail-open.

## 5. 릴리스 절차

1. 전체 테스트 통과 확인 → `kasa-hwpx/SKILL.md`의 `version:`을 `X.Y.Z-rc1`로 올림
2. `python3 build_skill.py` → `dist/kasa-hwpx_v{버전}.skill` (dist는 gitignore — 커밋하지 않음)
3. **사용자가 한글에서 실물 열람 확인** (신기능이 든 샘플 .hwpx를 만들어 제공하면 좋다)
4. 통과 시: `version:`을 `X.Y.Z`로 승격, README 버전 이력 갱신, 재빌드, 릴리스 커밋
5. 태그·푸쉬는 사용자 지시에 따른다

## 6. 업스트림 동기화

관찰 대상과 마지막 확인 커밋은 `BACKLOG.md`의 표가 SSOT다(그 이후 커밋만 조사하면 된다).
대상: `jkf87/hwpx-skill`, `Canine89/hwpxskill`, `ai-public-peasant/hwpx-rekian`.
반영 판단 기준: KASA 표준양식 스코프에 맞는가(양식 고정 — 수식·차트·문서유형 확장은 제외 판단됨).

## 7. 하지 말 것

- 기준 양식에 없는 스타일 ID 창작·타 양식 ID 혼용 (SKILL.md 규칙 3)
- 본문 흐름 문단에 `linesegarray` 주입 (규칙 9 — 줄겹침 사고의 원인)
- 서식 보존 경로에서 zip 전체 재구성 (규칙 18 — `write_package_preserving` 사용)
- 개인정보 값을 대화·로그에 노출 (규칙 20 — secure-fill 사용)
- 검증된 실물 패턴 없는 XML 구조 창작 (0장 원칙 — BACKLOG 4번 전례)
- 사용자 지시 없는 푸쉬·태그·릴리스

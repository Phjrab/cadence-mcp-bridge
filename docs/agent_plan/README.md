# Cadence MCP Final Prompt Package

**시작:** [START_HERE.md](START_HERE.md)

기존 마스터·전체 로드맵·ADE/sweep 계획·최신 보강안을 복구하여 연결한 문서 패키지다. 기존 프로젝트를 처음부터 다시 만드는 starter나 실행 가능한 Cadence 구현이 아니다.

- 첫 실행: [IMPORT_PROMPT.md](IMPORT_PROMPT.md) — docs-only, 이력/승인 보존
- 반복 실행: [NEXT_WP_PROMPT.md](NEXT_WP_PROMPT.md)
- 공통 계약: [CODEX_MASTER_PROMPT.md](CODEX_MASTER_PROMPT.md)
- 전체 방향: [docs/ROADMAP.md](docs/ROADMAP.md)
- 작업 120개: [docs/WORK_PACKAGE_INDEX.md](docs/WORK_PACKAGE_INDEX.md)
- 원래 기능 170개: [docs/LEGACY_CAPABILITY_CROSSWALK.md](docs/LEGACY_CAPABILITY_CROSSWALK.md)
- 보강 21개: [docs/HARDENING_TRACEABILITY.md](docs/HARDENING_TRACEABILITY.md)
- 복구 자료: [archive/README.md](archive/README.md)
- 단일 통합본: [FINAL_INTEGRATED_PROMPT.md](FINAL_INTEGRATED_PROMPT.md)
- 출처와 한계: [docs/SOURCES_AND_LIMITS.md](docs/SOURCES_AND_LIMITS.md)

`python tools/verify_package.py`는 파일 무결성, template 비활성, ID·dependency·crosswalk·내부 링크를 읽기 전용으로 확인한다. 자동 설치·Git·네트워크·Cadence 실행은 하지 않는다. checksum은 권한 부여나 서명이 아니다.

권한 없는 실제 write/deploy/rollback/tapeout은 금지한다. 원본 source·PDK·ADE state·과거 evidence를 보존하고, code / real validation / merge / deploy / release 상태를 분리한다.

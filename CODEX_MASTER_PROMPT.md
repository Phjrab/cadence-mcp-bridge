# Codex Master Execution Prompt — Cadence MCP Bridge

> **대상 저장소:** `Phjrab/cadence-mcp-bridge`
> **가시성:** GitHub Public (2026-09-17 post-v1 사용자 승인 정책)
> **기본 실행 환경:** Windows 11의 Codex Desktop
> **원격 대상:** VMware Workstation Pro의 CentOS 6.5 Cadence VM
> **운영 방식:** 한 번의 Codex 실행에서는 하나의 워크패키지(WP)만 완료하고 멈춘다.

---

## Post-v1 실행 권한 구조

### 2026-09-17 public 정책 교정

현재 저장소는 사용자의 명시적 승인에 따라 public을 유지한다. 아래 v1의 private
bootstrap/release/완료 기준과 보고서 표기는 역사적 계약으로 보존하며 현재 가시성
요구로 재적용하지 않는다. 현재 보고서는 실제 public 상태를 검증한다.
WP-14의 활성 요청 계약은 version 2 패키지이며 기존 version 1 기록은 불변이다.
Public 공개 승인은 원격 실행 또는 새 evidence 공개 승인이 아니다. 보호 데이터,
자격 증명, 활성 authorization, MachineGuid, PDK/OA/ADE 원문은 커밋하지 않는다.
새 evidence는 로컬에서 정확한 필드를 검토한 후에만 공개할 수 있다. 별도 실행 승인,
해시 결합, 단일 사용 이력, Git/테스트/STOP 및 deployment_enabled=false 제한은 유지한다.

`v1.0.0` 이후 개발은 다음 세 문서 계층으로 통제한다.

1. **Long-term roadmap:** `docs/AUTONOMOUS_CADENCE_MCP_FULL_ROADMAP.md`
2. **Current phase:** `docs/CURRENT_PHASE_PLAN.md`
3. **Active WP:** `PROJECT_STATE.md`

이 파일은 계속해서 Git, 보안, 승인, 테스트, 완료 보고와 STOP 규칙을 포함하는 최상위
실행 계약이다. `docs/archive/CODEX_MASTER_PROMPT_v1.0.0.md`는 출판된 v1 계약의 원문
기록이며, 이 파일의 기존 v1 규칙은 삭제되거나 약화되지 않는다. 문서 사이에 모순이
있으면 더 좁고 더 안전한 규칙을 적용하고 작업을 자동 확대하지 않는다.

전체 장기 roadmap은 권한 부여 문서도, 한 번의 실행 지시도 아니다. 각 실행에서는
`docs/CURRENT_PHASE_PLAN.md`와 `PROJECT_STATE.md`로 범위를 정한 뒤 현재 WP에 필요한 roadmap
section만 참조한다. roadmap에 적힌 write, compute, 배포, 외부 서비스 또는 비용 발생 작업은
각 WP의 구체적인 계약과 필요한 별도 사용자 승인이 없으면 실행할 수 없다.

WP-00부터 WP-11까지는 출판된 `v1.0.0`의 완료 이력이다. post-v1 작업은 이를 미완료로
되돌리거나 재실행하지 않으며, 현재 phase와 active WP에 정의된 새 작업만 수행한다.

### 통합 agent plan의 지위

`docs/agent_plan/`에는 장기 Autonomous Custom IC Design 계획과 작업별 제안 계약이
보존되어 있다. 이 문서군은 root 실행 계약을 대체하지 않으며, 다음 순서로만 적용한다.

1. 이 root `CODEX_MASTER_PROMPT.md`와 `AGENTS.md`의 더 강한 현재 제한
2. `PROJECT_STATE.md`와 `docs/CURRENT_PHASE_PLAN.md`가 선택한 하나의 active WP
3. `docs/agent_plan/WORK_ID_MAP.md`가 그 WP에 연결한 관련 `ICF-*` 문서

패키지의 전체 roadmap, template, archive, example, 승인 요청문은 실행 지시나 승인으로
해석하지 않는다. `docs/agent_plan/CODEX_MASTER_PROMPT.md`의 보강 규칙은 위 계층 안에서만
공통 참고 계약으로 사용하며, 충돌 해소 내역은
`docs/agent_plan/INTEGRATION_DECISIONS.md`에 기록한다. 수정 전 이 파일의 원문은
`docs/archive/CODEX_MASTER_PROMPT_pre_PKG-INTEGRATE-01.md`에 SHA-256 보존되어 있다.

---

## 0. 이 파일을 Codex에서 사용하는 방법

이 문서는 단순 참고 문서가 아니라 **프로젝트 전체의 권위 있는 실행 명세**다.

Codex는 작업을 시작할 때 다음 순서로 행동한다.

1. 저장소 루트의 `AGENTS.md`, 이 파일, `PROJECT_STATE.md`, `docs/CURRENT_PHASE_PLAN.md`,
   `docs/VERIFIED_ENVIRONMENT.md`, `docs/SECURITY.md`를 지정된 순서로 전부 읽는다.
2. 현재 WP에 필요한 경우에만 장기 roadmap의 관련 section을 읽는다.
3. `PROJECT_STATE.md`에 기록된 첫 번째 미완료 워크패키지 하나만 실행한다.
4. 사용자가 특정 WP를 명시했다면 그 WP만 실행한다.
5. 현재 WP의 수락 기준을 모두 검증한다.
6. 관련 문서와 `PROJECT_STATE.md`를 갱신한다.
7. 비밀정보가 포함되지 않았는지 확인한 뒤 현재 WP 전용 feature branch에 커밋하고 원격에 푸시한다.
8. 아래의 **필수 완료 보고서 형식**으로 결과와 다음 실행 모델을 출력한다.
9. 다음 WP를 같은 실행에서 자동으로 시작하지 않는다.

`PROJECT_STATE.md`가 없다면 `WP-00`부터 시작한다.

### Codex에 입력할 기본 시작 문장

```text
저장소의 AGENTS.md, CODEX_MASTER_PROMPT.md, PROJECT_STATE.md를 전부 읽고, 첫 번째 미완료 워크패키지 하나만 실행하라. 최신 origin/main에서 해당 WP 전용 feature branch를 만들고, 수락 기준 검증, PROJECT_STATE.md 갱신, 커밋, feature branch push까지 완료한 뒤 필수 완료 보고서 형식으로 끝내라. main에 직접 push하거나 merge하지 말고 다음 WP도 시작하지 마라.
```

---

# 1. 프로젝트 목표

Windows 11 호스트에서 실행되는 Codex Desktop이 로컬 `stdio` MCP 서버를 통해, SSH 별칭 `cadence-vm`으로 CentOS 6.5 VM의 Cadence Virtuoso, Spectre, OCEAN, SKILL 자동화 기능을 **안전하고 재현 가능하게** 사용할 수 있도록 한다.

최종 구조는 다음과 같다.

```text
Codex Desktop (Windows 11)
        │
        │ MCP / stdio
        ▼
Windows Python MCP Server
        │
        │ Windows OpenSSH, host alias: cadence-vm
        ▼
CentOS 6.5 i686 VM
        │
        ├── restricted cadence-runner
        ├── Spectre CLI
        ├── OCEAN
        ├── SKILL / virtuoso -nograph
        └── project-specific allowlisted profiles
```

첫 번째 제품 목표는 다음 문장이 실제 MCP 도구 호출로 끝나는 것이다.

```text
Cadence 환경 상태를 확인하고 Spectre smoke simulation을 제출한 뒤 결과를 알려줘.
```

최종 확장 목표는 다음과 같다.

- 환경 및 라이선스 상태 조회
- 허용된 Spectre/OCEAN/ADE 시뮬레이션 제출
- 비동기 작업 상태·로그·결과·취소
- 허용된 파형과 측정값 내보내기
- read-only library/cell/view/testbench 탐색
- 명시적인 allowlist를 통한 설계 변수 변경
- ADC 검증 측정값 계산
- 승인·백업·복사본 기반의 제한된 schematic/layout 쓰기

---

# 2. 검증 완료된 환경 — 추측하지 말 것

아래 값은 사용자가 직접 검증한 사실이다. 코드와 문서는 이 값을 기준선으로 사용한다.

## 2.1 Windows 호스트

| 항목 | 검증값 |
|---|---|
| OS | Windows 11 |
| 클라이언트 | Codex Desktop |
| 가상화 | VMware Workstation Pro |
| VM 네트워크 | VMware NAT, VMnet8 |
| Windows VMnet8 주소 | `192.168.85.1` |
| SSH 별칭 | `cadence-vm` |
| SSH 인증 | 전용 공개키 인증 완료, 비밀번호 입력 없음 |
| GitHub 소유자 | `Phjrab` |
| 목표 저장소 | `Phjrab/cadence-mcp-bridge` |

프로젝트 경로는 현재 Codex workspace를 우선 사용한다. 새 경로를 선택해야 한다면 레거시 도구의 문자 인코딩 문제를 줄이기 위해 다음을 선호한다.

```text
C:\work\cadence-mcp-bridge
```

사용자 프로필 경로에 한글이 포함되어 있으므로, 새 스크립트에서 불필요하게 사용자 이름을 하드코딩하지 않는다.

## 2.2 CentOS VM

| 항목 | 검증값 |
|---|---|
| hostname | `cadence` |
| SSH 사용자 | `buet` |
| IP | `192.168.85.128` |
| OS | `CentOS release 6.5 (Final)` |
| 아키텍처 | `i686` |
| 로그인 shell | `/bin/bash` |
| Python | `Python 2.6.6` |
| 원격 프로젝트 루트 | `/home/buet/cds_work` |
| MCP 원격 루트 | `/home/buet/cds_work/.cadence_mcp` |
| `CDS_LIC_FILE` | 설정됨. 실제 값은 절대 출력하거나 저장하지 않는다. |
| `LM_LICENSE_FILE` | 설정되지 않음 |

## 2.3 Cadence 실행 파일

```text
Virtuoso: /home/buet/cadence/IC615/tools/dfII/bin/virtuoso
Spectre : /home/buet/cadence/MMSIM121/tools/bin/spectre
OCEAN   : /home/buet/cadence/IC615/tools/dfII/bin/ocean
lmutil  : /home/buet/cadence/IC615/tools/bin/lmutil
```

버전:

```text
Virtuoso: IC6.1.5.500.15
Spectre : 12.1.0.347.isr3
```

## 2.4 검증 완료된 비대화형 SSH

Windows PowerShell에서 다음이 성공했다.

```powershell
ssh cadence-vm 'echo "USER=$USER"; echo "HOME=$HOME"; echo "PWD=$PWD"'
ssh cadence-vm 'cd ~/cds_work && command -v virtuoso; command -v spectre; command -v ocean'
ssh cadence-vm 'cd ~/cds_work && virtuoso -W; spectre -W'
ssh cadence-vm 'if [ -n "$CDS_LIC_FILE" ]; then echo "CDS_LIC_FILE=SET"; else echo "CDS_LIC_FILE=UNSET"; fi'
```

## 2.5 검증 완료된 Spectre headless smoke test

다음 RC 회로의 transient simulation이 성공했다.

```spectre
simulator lang=spectre

V1 (in 0) vsource dc=1
R1 (in out) resistor r=1k
C1 (out 0) capacitor c=1p

save out
tran1 tran stop=1n
```

검증 결과:

```text
EXIT_CODE=0
spectre completes with 0 errors, 0 warnings, and 1 notice.
```

생성 결과:

```text
smoke.log
smoke.raw/
smoke.scs
spectre_console.log
```

`Trapezoidal ringing is detected` notice는 이 인프라 smoke test에서는 허용된다. 실제 회로 해석에서는 별도로 평가한다.

---

# 3. 절대 변경하지 않을 시스템 경계

다음은 모든 WP에 적용되는 비협상 규칙이다.

## 3.1 CentOS 보호

- CentOS의 `/usr/bin/python`을 교체하지 않는다.
- Python 2.6.6을 업그레이드하지 않는다.
- `yum update`, OS 업그레이드, glibc/OpenSSL/GCC 교체를 수행하지 않는다.
- root 또는 sudo 권한을 요구하지 않는다.
- systemd를 전제로 하지 않는다. CentOS 6.5는 SysV 계열이다.
- 최신 Python, Node.js, MCP SDK를 CentOS에 설치하지 않는다.
- 원격 runner는 Bash와 CentOS 기본 명령, 필요 시 Python 2.6 표준 라이브러리만 사용한다.
- 원격 파일은 `/home/buet/cds_work/.cadence_mcp` 아래에만 설치한다.
- `/home/buet/cadence`, PDK, 공용 library, 시스템 디렉터리에 쓰지 않는다.

## 3.2 MCP 권한 경계

다음 범용 도구는 절대 만들지 않는다.

```text
run_shell(command)
run_command(command)
ssh_exec(command)
eval_skill(code)
execute_ocean(script_text)
write_any_file(path, content)
delete_any_path(path)
```

Codex나 모델이 생성한 임의 shell, SKILL, OCEAN 문자열을 그대로 실행하지 않는다.

허용되는 것은 서버 코드에 미리 정의된 좁은 동작과 검증된 인자뿐이다.

## 3.3 데이터 보호

다음을 Git, MCP 결과, 테스트 fixture, 로그에 저장하지 않는다.

- SSH 개인키 또는 공개키 원문
- 비밀번호, PAT, OAuth token
- `CDS_LIC_FILE` 실제 값
- 라이선스 파일 내용
- PDK 모델 원문
- 비공개 netlist 전체
- proprietary schematic/layout/PSF 원본
- 사용자 홈의 `.ssh` 폴더
- 대용량 `*.raw`, `*.psf`, `*.log` 실행 산출물

환경 확인 결과는 `SET/UNSET`, 성공/실패, 버전과 기능 수준까지만 기록한다.

## 3.4 네트워크

- MCP 서버는 Windows 로컬 `stdio`만 사용한다.
- 첫 릴리스에서 HTTP listener를 열지 않는다.
- CentOS에 MCP TCP 포트를 열지 않는다.
- Windows에서 `ssh cadence-vm`을 통해서만 원격 기능을 호출한다.
- SSH 호스트 키가 변경되면 자동 수락하지 않고 중단한다.

## 3.5 설계 데이터 쓰기

- `WP-11` 전까지 Virtuoso 설계 데이터에 쓰지 않는다.
- read-only 탐색 단계에서 cellview 저장, library 생성, PDK 수정, 원본 ADE state 변경을 금지한다.
- 쓰기 기능은 사용자 명시 승인, 복사본, 백업, dry-run, allowlist가 모두 있는 경우에만 허용한다.

---

# 4. 기술 선택

## 4.1 Windows

- Python: 3.12 우선
- 패키지 관리: `uv` 우선, 없으면 Python `venv` + `pip`
- MCP SDK: 안정판 v2, 의존성 범위 `mcp[cli]>=2,<3`
- 데이터 검증: Pydantic v2
- 테스트: pytest, pytest-asyncio
- 정적 검사: Ruff, mypy
- SSH: Windows OpenSSH의 `ssh.exe`; Paramiko를 기본 선택하지 않는다.
- 전송: MCP `stdio`
- 저장소: Git + GitHub CLI `gh`

현재 설치된 버전과 API는 작업 시점의 공식 문서를 확인한다. 패키지 API를 기억에 의존해 추측하지 않는다. 실제 설치된 MCP SDK v2의 예제와 타입을 먼저 검사한다.

## 4.2 CentOS

- Bash 기반 제한 runner
- 외부 패키지 의존성 없음
- 필요 시 Python 2.6의 `json`, `os`, `sys`, `time`, `subprocess`만 사용
- `argparse`, f-string, pathlib, type annotations 등 Python 2.6에 없는 기능을 사용하지 않는다.
- 명령 존재 여부를 실제 VM에서 검증한다. 예: `setsid`, `timeout`, `flock`, `pgrep`, `pkill`.
- 지원 여부를 확인하지 않은 명령에 의존하지 않는다.

---

# 5. 목표 저장소 구조

초기 구현은 다음 구조를 목표로 한다. 합리적인 변경은 가능하지만 변경 이유를 문서화한다.

```text
cadence-mcp-bridge/
├── AGENTS.md
├── CODEX_MASTER_PROMPT.md
├── PROJECT_STATE.md
├── README.md
├── pyproject.toml
├── uv.lock
├── .gitignore
├── src/
│   └── cadence_mcp_bridge/
│       ├── __init__.py
│       ├── __main__.py
│       ├── config.py
│       ├── errors.py
│       ├── models.py
│       ├── sanitization.py
│       ├── ssh_backend.py
│       ├── service.py
│       └── server.py
├── remote/
│   ├── bin/
│   │   └── cadence-runner
│   ├── lib/
│   │   └── runner-common.sh
│   ├── py26/
│   │   └── result_json.py
│   └── profiles/
│       └── spectre-smoke/
│           └── smoke.scs
├── scripts/
│   ├── bootstrap-private-repo.ps1
│   ├── deploy-remote.ps1
│   ├── install-codex-mcp.ps1
│   └── verify-e2e.ps1
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
└── docs/
    ├── ARCHITECTURE.md
    ├── VERIFIED_ENVIRONMENT.md
    ├── SECURITY.md
    ├── OPERATIONS.md
    ├── MODEL_MATRIX.md
    ├── USER_INPUTS_REQUIRED.md
    └── work-packages/
```

---

# 6. GitHub 및 Git 동기화 계약

이 프로젝트는 사용자 승인된 public 저장소 `Phjrab/cadence-mcp-bridge`를 사용한다.

## 6.1 전역 checkpoint 규칙

- 모든 WP는 전용 feature branch에서만 작업한다.
- branch 이름은 `wp/WP-XX-<short-slug>` 형식을 사용한다.
- Codex는 `main`에 직접 commit하거나 push하지 않는다.
- Codex는 완료 보고 후 사용자가 특정 feature branch 또는 pull request의 병합을 명시적으로 승인한 경우에만 GitHub pull request를 merge할 수 있다.
- 명시적 승인 여부와 관계없이 `main` 직접 push는 금지한다.
- Codex는 force push하지 않는다.
- 테스트가 실패하면 완료 처리하지 않는다.
- 검증된 commit을 feature branch에 push한 뒤, 해당 branch/PR에 대한 명시적 병합 승인이 없다면 반드시 STOP한다.
- 다음 WP는 이전 WP branch가 사용자의 검토를 거쳐 최신 `origin/main`에 반영된 후에만 시작한다.

## 6.2 WP 시작 시

항상 먼저 실행한다.

```powershell
git status --short --branch
git remote -v
git fetch origin
```

예상치 않은 local 변경이 있으면 덮어쓰거나 버리지 않는다.

새 WP를 시작할 때는 최신 main을 기준으로 한다.

```powershell
git switch main
git pull --ff-only origin main
git switch -c wp/WP-XX-short-slug
```

동일 WP branch를 이어서 복구하는 경우에는 remote branch를 확인하고 fast-forward 가능한 방식으로만 이어간다. 이전 WP branch가 아직 `origin/main`에 반영되지 않았다면 새 WP를 시작하지 않고 `BLOCKED`로 보고한다.

## 6.3 WP 종료 시

1. WP 테스트와 수락 기준을 실행한다.
2. 하나라도 실패하면 `PASS`로 처리하지 않는다.
3. `git diff --check`를 실행한다.
4. 비밀정보 탐지를 수행한다.
5. `PROJECT_STATE.md`를 갱신한다.
6. 변경 파일과 branch 이름을 검토한다.
7. Conventional Commit 형식으로 commit한다.
8. 현재 feature branch를 push한다.

```powershell
git push -u origin wp/WP-XX-short-slug
```

9. remote branch와 commit SHA를 재검증한다.
10. `git status --porcelain`이 비어 있는지 확인한다.
11. 명시적 PR 병합 승인이 없으면 merge, main push, 다음 WP 실행 없이 STOP한다. 승인이 있더라도 `main` 직접 push와 다음 WP 실행은 금지한다.

권장 commit scope:

```text
chore(bootstrap): ...
feat(runner): ...
feat(ssh): ...
feat(mcp): ...
test(e2e): ...
security(hardening): ...
feat(ocean): ...
feat(ade): ...
feat(adc): ...
docs(ops): ...
```

## 6.4 커밋 빈도

- 각 WP 끝에는 최소 1개 검증된 commit과 feature branch push가 있어야 한다.
- WP가 크면 논리적으로 완결된 단위별 atomic commit을 추가할 수 있다.
- 실패하는 테스트나 불완전한 핵심 코드를 완료본으로 표시하지 않는다.
- WP가 외부 요인으로 막혔다면 안전한 문서, 진단 코드, 테스트 fixture까지만 commit/push하고 `BLOCKED`로 보고한다.
- push 후 사용자가 branch를 검토·통합하기 전까지 다음 WP로 이동하지 않는다.

## 6.5 GitHub 저장소 생성

`WP-00`에서 다음을 만족한다.

- `gh auth status` 성공
- 저장소가 없으면 `--private --add-readme`로 생성하여 기본 `main`을 만든다.
- 저장소가 이미 있으면 private 여부와 default branch를 확인하고 재사용한다.
- latest `origin/main`에서 `wp/WP-00-bootstrap` branch를 생성한다.
- 초기 프로젝트 파일을 해당 feature branch에 commit하고 push한다.
- Codex는 완료 보고 후 사용자가 WP-00 branch 또는 PR을 명시적으로 승인한 경우에만 GitHub PR로 merge할 수 있다.
- `gh repo view Phjrab/cadence-mcp-bridge --json nameWithOwner,isPrivate,url,defaultBranchRef`로 private/default branch를 확인한다.

GitHub 인증이 없으면 사용자를 대신해 credential을 만들거나 저장하지 않는다. 로컬 준비까지만 완료하고 `gh auth login`을 정확한 사용자 조치로 보고한다.

---

# 7. 모델 선택 정책

2026년 8월 기준 Codex의 GPT-5.6 계열을 사용한다.

| 용도 | 1순위 | 추론 강도 | 대체 |
|---|---|---:|---|
| 아키텍처, 보안, 레거시 통합, 장기 디버깅 | GPT-5.6 Sol | `max` | GPT-5.6 Terra `max` |
| 일반 구현, 테스트, 문서, 배포 스크립트 | GPT-5.6 Terra | `high` 또는 `max` | GPT-5.6 Sol `high` |
| 작은 문서 수정, 포맷, 단순 반복 정리 | GPT-5.6 Luna | `medium` 또는 `high` | GPT-5.6 Terra `medium` |

규칙:

- 모델 선택기에 추천 모델이 없으면 가장 가까운 상위 능력 모델을 사용한다.
- 실제 사용 모델과 effort를 완료 보고서에 기록한다.
- 복잡한 WP를 비용 절감 목적으로 Luna에 임의 하향 배정하지 않는다.
- `max`보다 높은 다중 에이전트/ultra 모드가 표시되더라도, 사용자가 명시적으로 선택하지 않았다면 자동 사용하지 않는다.
- 단순 후속 수정은 Luna/Terra로 처리할 수 있지만, 각 WP의 최종 수락 검증은 표에 지정된 모델 수준을 우선한다.

---

# 8. 공통 구현 규약

## 8.1 입력 검증

- Job ID는 서버가 UUID 기반으로 생성한다.
- 외부 입력 job ID는 엄격한 정규식과 길이 제한을 적용한다.
- profile 이름은 registry allowlist만 허용한다.
- library/cell/view/signal/variable 이름은 제품 규칙과 프로젝트 allowlist를 모두 검증한다.
- 경로 입력을 MCP API에 직접 노출하지 않는다.
- 모든 원격 경로는 서버 내부에서 조립하고 `resolve/realpath` 후 허용 루트 내부인지 확인한다.
- 개행, NUL, 세미콜론, 백틱, `$()`, `..`, wildcard, shell redirection을 포함한 악성 입력 테스트를 작성한다.

## 8.2 SSH 실행

Windows SSH backend는 다음 원칙을 따른다.

- `subprocess`에 문자열 shell command가 아니라 argv list를 전달한다.
- `shell=True`를 사용하지 않는다.
- SSH 대상은 설정된 alias `cadence-vm`으로 고정한다.
- 원격 실행 파일은 `/home/buet/cds_work/.cadence_mcp/bin/cadence-runner`로 고정한다.
- 허용된 runner subcommand와 검증된 단일 토큰 인자만 전달한다.
- `BatchMode=yes`로 비밀번호 대기를 금지한다.
- `StrictHostKeyChecking=yes`로 호스트 키 자동 변경 수락을 금지한다.
- 연결 timeout, 전체 timeout, 출력 크기 제한을 적용한다.
- timeout 시 원격 작업이 이미 제출됐는지 idempotency key로 판정한다.

권장 옵션은 실제 Windows OpenSSH에서 지원 여부를 검사한 뒤 사용한다.

```text
-o BatchMode=yes
-o StrictHostKeyChecking=yes
-o ConnectTimeout=10
-o ServerAliveInterval=15
-o ServerAliveCountMax=2
```

## 8.3 MCP stdio

- stdout에는 MCP 프로토콜 메시지 외의 내용을 절대 출력하지 않는다.
- 애플리케이션 로그는 stderr 또는 파일로 보낸다.
- tool 결과는 구조화된 JSON-compatible object를 반환한다.
- 예외 stack trace를 모델에 그대로 노출하지 않는다.
- 오류는 안정된 error code, 안전한 message, 재시도 가능 여부로 변환한다.
- 도구 설명에 side effect와 승인 필요 여부를 명시한다.

## 8.4 Job 수명주기

최소 상태:

```text
queued
running
succeeded
failed
cancelling
cancelled
unknown
```

제출 도구는 긴 시뮬레이션이 끝날 때까지 기다리지 않는다. 짧은 시간 안에 `job_id`를 반환한다.

원격 job 디렉터리 예:

```text
/home/buet/cds_work/.cadence_mcp/jobs/<job-id>/
├── request.json
├── status.json
├── pid
├── stdout.log
├── stderr.log
├── result.json
└── artifacts/
```

- 상태 파일은 임시 파일 작성 후 atomic rename한다.
- PID 재사용을 고려해 시작 시각 또는 marker를 함께 검증한다.
- cancel은 해당 job이 시작한 process group만 대상으로 한다.
- 기본 동시 실행 수는 1로 시작한다. 실제 라이선스 수를 추측하지 않는다.
- 로그 tail 기본값과 최대값을 제한한다.
- 대용량 raw 결과를 MCP 응답에 직접 넣지 않는다.

## 8.5 시간

Windows와 CentOS의 시계/시간대가 다를 수 있다.

- Job ID는 Windows에서 UTC와 random suffix로 생성하거나 UUID를 사용한다.
- timestamp에는 timezone을 포함한다.
- duration은 가능하면 monotonic clock으로 측정한다.
- 원격 로그 시각을 절대적인 순서의 유일한 근거로 사용하지 않는다.

---

# 9. MCP v1 도구 계약

첫 릴리스는 다음 도구만 노출한다.

## `cadence_health`

읽기 전용. 다음을 안전하게 반환한다.

```json
{
  "ssh": "ok",
  "remote_host": "cadence",
  "remote_user": "buet",
  "remote_root_accessible": true,
  "virtuoso": {
    "available": true,
    "version": "IC6.1.5.500.15"
  },
  "spectre": {
    "available": true,
    "version": "12.1.0.347.isr3"
  },
  "ocean": {
    "available": true
  },
  "license_env": {
    "CDS_LIC_FILE": "SET"
  },
  "runner_version": "..."
}
```

라이선스 변수 실제 값은 반환하지 않는다.

## `cadence_submit_smoke`

미리 포함된 Spectre RC profile만 제출한다. 임의 netlist나 shell 입력을 받지 않는다.

반환 예:

```json
{
  "job_id": "...",
  "state": "queued",
  "profile": "spectre-smoke",
  "submitted_at": "..."
}
```

## `cadence_job_status`

읽기 전용. 검증된 `job_id`의 상태만 반환한다.

## `cadence_job_log_tail`

읽기 전용. `stdout` 또는 `stderr` 중 허용된 stream과 제한된 줄 수만 반환한다.

## `cadence_job_result`

읽기 전용. 종료 코드, 안전하게 요약된 오류/notice, artifact metadata를 반환한다.

## `cadence_cancel_job`

부작용 있음. 해당 MCP가 생성한 job만 취소한다. 임의 PID를 입력받지 않는다.

---

# 10. 워크패키지 실행 계획

각 WP는 하나의 Codex 실행 단위다. 현재 WP 완료 후 다음 WP를 실행하지 말고 필수 완료 보고서를 출력한다.

---

## WP-00 — Private Repository Bootstrap & Evidence Freeze

### 추천 모델

- **Primary:** GPT-5.6 Terra
- **Effort:** high
- **Fallback:** GPT-5.6 Sol high

### 목표

비공개 GitHub 저장소를 만들고, 검증된 환경과 프로젝트 규칙을 변경 불가능한 기준 문서로 초기 커밋한다.

### 수행 항목

1. `git`, `gh`, `ssh` 존재와 버전을 확인한다.
2. `gh auth status`를 확인한다.
3. 저장소 루트가 아닌 임시 폴더라면 적절한 workspace로 정리한다.
4. `Phjrab/cadence-mcp-bridge` 존재 여부를 확인한다.
5. 없으면 `--private --add-readme`로 생성하여 기본 `main`을 만든다.
6. latest `origin/main`에서 `wp/WP-00-bootstrap` branch를 생성한다.
7. 다음 파일을 생성 또는 검증한다.
   - `README.md`
   - `AGENTS.md`
   - `CODEX_MASTER_PROMPT.md`
   - `PROJECT_STATE.md`
   - `.gitignore`
   - `docs/VERIFIED_ENVIRONMENT.md`
   - `docs/MODEL_MATRIX.md`
   - `docs/SECURITY.md`
8. secret과 대용량 Cadence 산출물을 차단하는 `.gitignore`를 작성한다.
9. 초기 commit을 `wp/WP-00-bootstrap`에 만들고 해당 feature branch만 push한다.
10. 저장소가 private인지 GitHub CLI로 재검증한다.
11. 명시적 PR 병합 승인이 없으면 merge하지 않고 STOP한다. `main` 직접 push는 항상 금지한다.

### 수락 기준

```text
gh repo view Phjrab/cadence-mcp-bridge --json nameWithOwner,isPrivate,defaultBranchRef,url
```

결과가 다음을 의미해야 한다.

- `nameWithOwner == Phjrab/cadence-mcp-bridge`
- `isPrivate == true`
- default branch가 `main`

그리고 remote에 `wp/WP-00-bootstrap` branch가 존재하고, `git status --porcelain`이 비어 있어야 한다. Codex가 main에 직접 commit/push/merge한 기록이 없어야 한다.

### 권장 commit

```text
chore(bootstrap): initialize private Cadence MCP bridge project
```

### 다음 WP

- **WP-01 — Windows Project Scaffold & Contracts**
- **추천 모델:** GPT-5.6 Sol
- **Effort:** max

---

## WP-01 — Windows Project Scaffold & Contracts

### 추천 모델

- **Primary:** GPT-5.6 Sol
- **Effort:** max
- **Fallback:** GPT-5.6 Terra max

### 목표

Windows MCP 서버의 Python 프로젝트, 타입, 설정, 테스트 골격을 만들되 아직 원격 환경을 변경하지 않는다.

### 수행 항목

1. Windows의 `py -0p`, `python --version`, `uv --version`을 검사한다.
2. Python 3.12가 없으면 자동으로 시스템을 변경하지 말고 필요한 설치 조치를 명시한다. 사용자가 승인한 경우에만 설치한다.
3. `src/` layout의 Python 프로젝트를 만든다.
4. `pyproject.toml`에 다음을 설정한다.
   - Python `>=3.12,<3.14`
   - `mcp[cli]>=2,<3`
   - Pydantic v2
   - pytest, pytest-asyncio, Ruff, mypy
5. lock file을 생성한다.
6. 설정 모델을 만든다.
   - SSH alias: `cadence-vm`
   - remote root
   - runner path
   - timeout
   - max output bytes
   - default concurrency 1
7. domain model을 정의한다.
   - health
   - job state
   - job status
   - job result
   - artifact metadata
   - stable error envelope
8. 예외 계층과 log sanitization 기본을 만든다.
9. fake backend를 이용한 unit test를 작성한다.
10. `docs/ARCHITECTURE.md`를 작성한다.

### 금지

- 아직 CentOS에 파일을 배포하지 않는다.
- 아직 Codex config를 수정하지 않는다.
- 아직 임의 SSH command API를 만들지 않는다.

### 수락 기준

- clean environment에서 dependency install 성공
- `ruff check .` 성공
- `mypy src` 성공
- `pytest` 성공
- `python -m cadence_mcp_bridge --help` 또는 동등한 안전한 entrypoint 성공

### 권장 commit

```text
feat(core): scaffold typed Windows MCP bridge project
```

### 다음 WP

- **WP-02 — Restricted CentOS Runner v1**
- **추천 모델:** GPT-5.6 Sol
- **Effort:** max

---

## WP-02 — Restricted CentOS Runner v1

### 추천 모델

- **Primary:** GPT-5.6 Sol
- **Effort:** max
- **Fallback:** GPT-5.6 Terra max

### 목표

CentOS 6.5에서 외부 의존성 없이 동작하는 제한 runner를 구현하고 smoke job을 비동기로 관리한다.

### 수행 항목

1. read-only 진단으로 다음 명령 존재 여부를 확인한다.
   - `bash`, `nohup`, `setsid`, `ps`, `kill`, `pgrep`, `pkill`, `date`, `mktemp`
2. 결과에 따라 가장 단순하고 안전한 process group 전략을 선택하고 문서화한다.
3. 저장소의 `remote/`에 runner 소스를 작성한다.
4. runner subcommand를 다음으로 제한한다.

```text
version
health
submit-smoke <job-id>
status <job-id>
log-tail <job-id> <stdout|stderr> <lines>
result <job-id>
cancel <job-id>
```

5. `job-id`를 allowlist regex로 검증한다.
6. 원격 root와 jobs 디렉터리 밖으로 나가지 못하게 한다.
7. absolute Cadence binary path를 사용한다.
8. health는 버전과 `CDS_LIC_FILE=SET/UNSET`만 반환한다.
9. smoke profile은 repository에 저장된 고정 netlist를 사용한다.
10. status/result JSON은 Python 2.6 helper 또는 안전한 고정 serializer로 생성한다.
11. 상태 파일을 atomic하게 갱신한다.
12. stdout/stderr를 분리한다.
13. `scripts/deploy-remote.ps1`을 만들어 allowlisted 원격 경로에만 배포한다.
14. 배포 후 실제 smoke job을 제출하고 종료까지 검증한다.

### 원격 권한

```text
/home/buet/cds_work/.cadence_mcp          700
bin/scripts                               700 또는 755 중 최소 필요 권한
jobs                                      700
job files                                 600 원칙
```

### 수락 기준

- `ssh -o BatchMode=yes cadence-vm '<runner> health'` 성공
- smoke submit이 빠르게 `job_id` 상태를 반환
- status가 queued/running/succeeded 흐름을 관찰 가능
- result의 exit code가 0
- Spectre 완료 요약이 0 errors, 0 warnings
- 기존 수동 smoke test 외의 디렉터리를 손상하지 않음
- cancel test는 장시간 dummy job 또는 안전한 fixture로 process tree 범위를 검증

### 권장 commit

```text
feat(runner): add restricted CentOS job runner and smoke profile
```

### 다음 WP

- **WP-03 — Windows OpenSSH Backend**
- **추천 모델:** GPT-5.6 Terra
- **Effort:** max

---

## WP-03 — Windows OpenSSH Backend

### 추천 모델

- **Primary:** GPT-5.6 Terra
- **Effort:** max
- **Fallback:** GPT-5.6 Sol high

### 목표

Windows Python 코드가 비밀번호 없이 제한 runner만 호출하도록 안전한 SSH transport를 구현한다.

### 수행 항목

1. `OpenSshBackend` 인터페이스를 구현한다.
2. `ssh.exe`를 argv list로 실행한다.
3. `shell=False`를 명시하거나 기본을 유지한다.
4. 고정 alias, 고정 runner path, allowlisted subcommand만 사용한다.
5. stdout/stderr bytes 제한을 적용한다.
6. connect timeout과 operation timeout을 분리한다.
7. timeout, host key failure, auth failure, remote nonzero exit를 서로 다른 error code로 매핑한다.
8. `BatchMode=yes`로 password prompt를 방지한다.
9. host key strict checking을 유지한다.
10. Korean Windows path/encoding과 remote ASCII protocol을 고려한다.
11. log sanitizer로 토큰, license 값, Windows 사용자 경로를 필요 이상 노출하지 않는다.
12. unit test에서 subprocess를 mock한다.
13. integration test marker 아래 실제 `cadence-vm` health를 실행한다.

### 보안 테스트 입력

```text
abc;rm -rf x
../x
$(id)
`id`
a\nb
*
--help
```

모두 runner argument로 도달하기 전에 거부되어야 한다.

### 수락 기준

- unit test 성공
- 실제 health integration 성공
- 잘못된 job ID와 profile이 로컬에서 거부됨
- password prompt 없이 실패/성공이 결정됨
- raw arbitrary command를 전달하는 public method가 없음

### 권장 commit

```text
feat(ssh): add allowlisted Windows OpenSSH transport
```

### 다음 WP

- **WP-04 — MCP stdio Server v1**
- **추천 모델:** GPT-5.6 Sol
- **Effort:** max

---

## WP-04 — MCP stdio Server v1

### 추천 모델

- **Primary:** GPT-5.6 Sol
- **Effort:** max
- **Fallback:** GPT-5.6 Terra max

### 목표

공식 MCP Python SDK v2로 Windows 로컬 stdio 서버와 최초 6개 도구를 구현한다.

### 수행 항목

1. 설치된 MCP SDK v2의 공식 예제와 API를 확인한다.
2. stdio server entrypoint를 구현한다.
3. 다음 도구를 구현한다.

```text
cadence_health
cadence_submit_smoke
cadence_job_status
cadence_job_log_tail
cadence_job_result
cadence_cancel_job
```

4. 각 입력과 structured output에 타입을 부여한다.
5. 도구 annotation 또는 동등한 메타데이터로 read-only/destructive 성격을 표현한다.
6. stdout protocol 오염을 검출하는 테스트를 작성한다.
7. logging은 stderr로 보낸다.
8. 서비스 계층과 MCP adapter를 분리한다.
9. backend mock을 사용한 in-memory MCP test를 작성한다.
10. 모든 오류를 stable error envelope로 변환한다.
11. `cadence_cancel_job`만 side effect 도구로 명확하게 표시한다.

### 수락 기준

- MCP Inspector 또는 SDK in-memory client에서 tool list 확인
- 각 도구의 schema 확인
- mock success/failure test 성공
- server startup stdout에 임의 banner 없음
- `cadence_health` 실제 integration 성공
- `cadence_submit_smoke`가 긴 시뮬레이션을 기다리지 않고 반환

### 권장 commit

```text
feat(mcp): expose safe Cadence stdio tools
```

### 다음 WP

- **WP-05 — End-to-End Job Lifecycle**
- **추천 모델:** GPT-5.6 Sol
- **Effort:** max

---

## WP-05 — End-to-End Job Lifecycle

### 추천 모델

- **Primary:** GPT-5.6 Sol
- **Effort:** max
- **Fallback:** GPT-5.6 Terra max

### 목표

실제 MCP service → SSH backend → CentOS runner → Spectre → result 경로를 통합 검증한다.

### 수행 항목

1. actual remote integration test suite를 작성한다.
2. smoke submit → poll → result 흐름을 자동화한다.
3. submit idempotency 전략을 추가한다.
4. polling interval과 최대 대기 시간을 설정한다.
5. job concurrency 기본값 1을 강제한다.
6. 로그 tail 줄 수와 bytes 최대값을 강제한다.
7. succeeded, failed, cancelled fixture를 검증한다.
8. runner/process crash 시 unknown/recovery 동작을 정의한다.
9. 원격 job 디렉터리 권한과 경로 containment를 테스트한다.
10. `scripts/verify-e2e.ps1`을 만든다.
11. 실제 실행 evidence를 `docs/OPERATIONS.md`에 기록하되 proprietary 데이터는 넣지 않는다.

### 수락 기준

- `verify-e2e.ps1` 하나로 health와 smoke lifecycle 검증 가능
- submit 호출이 목표 시간 내 반환
- result exit code 0
- 생성 artifact metadata 확인
- 실패 fixture에서 안전한 오류 반환
- cancel이 다른 프로세스를 종료하지 않음
- test 종료 후 local repository가 깨끗함

### 권장 commit

```text
test(e2e): verify MCP to Spectre job lifecycle
```

### 다음 WP

- **WP-06 — Codex Desktop Registration & Operator Flow**
- **추천 모델:** GPT-5.6 Terra
- **Effort:** high

---

## WP-06 — Codex Desktop Registration & Operator Flow

### 추천 모델

- **Primary:** GPT-5.6 Terra
- **Effort:** high
- **Fallback:** GPT-5.6 Sol high

### 목표

Codex Desktop이 로컬 server를 안정적으로 시작하고 도구를 사용할 수 있도록 설치 스크립트와 운영 절차를 완성한다.

### 수행 항목

1. 작업 시점의 공식 Codex MCP 문서 또는 설치된 Codex CLI 도움말을 확인한다.
2. Windows 경로를 안전하게 처리하는 `scripts/install-codex-mcp.ps1`을 작성한다.
3. 사용자 설정을 덮어쓰기 전에 backup한다.
4. 중복 MCP entry를 만들지 않도록 idempotent하게 동작한다.
5. absolute Python executable과 module entrypoint를 설정한다.
6. startup timeout과 tool timeout을 실제 도구 성격에 맞춘다.
7. 모든 side-effect 도구를 prompt 승인으로 두는 설정/운영 지침을 작성한다.
8. Codex 앱 재시작과 `/mcp` 확인 절차를 문서화한다.
9. 사용자가 실행할 acceptance prompts를 작성한다.

예:

```text
Cadence MCP 연결 상태를 확인해줘. 라이선스 변수의 실제 값은 출력하지 마.
```

```text
Spectre smoke test를 제출하고 완료될 때까지 상태를 확인한 뒤 결과를 요약해줘.
```

10. 자동화 가능한 부분은 Codex가 직접 수행하고, 앱 재시작처럼 사용자 UI 동작만 명시한다.

### 수락 기준

- MCP 설정이 한 번만 등록됨
- server가 absolute path로 시작됨
- `/mcp` 또는 동등한 UI에서 연결 상태 정상
- `cadence_health` 호출 성공
- Codex가 smoke lifecycle을 도구로 수행
- raw shell tool이 보이지 않음

### 권장 commit

```text
feat(codex): add desktop registration and operator workflow
```

### 다음 WP

- **WP-07 — Reliability, Security & Audit Hardening**
- **추천 모델:** GPT-5.6 Sol
- **Effort:** max

---

## WP-07 — Reliability, Security & Audit Hardening

### 추천 모델

- **Primary:** GPT-5.6 Sol
- **Effort:** max
- **Fallback:** GPT-5.6 Terra max

### 목표

첫 실사용 전에 injection, secret leakage, concurrency, cleanup, audit 문제를 체계적으로 방어한다.

### 수행 항목

1. `docs/SECURITY.md`에 threat model을 완성한다.
2. trust boundary와 data flow를 문서화한다.
3. path traversal, shell metacharacter, multiline, Unicode edge case tests를 확장한다.
4. log/result size 제한과 truncation metadata를 추가한다.
5. remote job retention 정책을 추가한다.
6. cleanup은 dry-run 기본으로 만들고, 범위를 jobs root로 제한한다.
7. audit event를 JSON Lines로 기록하되 secrets와 circuit data를 제외한다.
8. 사용자가 시작한 job과 MCP가 시작한 job을 구분한다.
9. stale PID, PID reuse, partial write, power loss 상황을 테스트한다.
10. simultaneous submit을 테스트하고 기본 concurrency 1을 보장한다.
11. dependency vulnerability scan을 실행하고 결과를 문서화한다.
12. secret scanning을 local preflight에 추가한다.
13. 어떤 상황에서도 force push나 destructive remote cleanup을 자동 수행하지 않는다.

### 수락 기준

- security test suite 성공
- 임의 command injection 경로 없음
- secret fixture가 log/MCP result에서 redacted됨
- cleanup dry-run이 범위 밖 파일을 건드리지 않음
- concurrent submit 정책이 결정적임
- audit log로 누가 어떤 profile을 언제 제출했는지 추적 가능

### 권장 commit

```text
security(hardening): enforce isolation audit and retention controls
```

### 다음 WP

- **WP-08 — OCEAN/SKILL Read-Only Discovery**
- **추천 모델:** GPT-5.6 Sol
- **Effort:** max

---

## WP-08 — OCEAN/SKILL Read-Only Discovery

### 추천 모델

- **Primary:** GPT-5.6 Sol
- **Effort:** max
- **Fallback:** GPT-5.6 Terra max

### 목표

레거시 IC6.1.5 환경에서 OCEAN/SKILL headless 동작을 읽기 전용으로 검증하고, 허용된 설계 메타데이터를 조회한다.

### 수행 항목

1. 다음 후보를 read-only로 검사한다.

```text
/home/buet/cds_work/cds.lib
```

2. `ocean -help`, `virtuoso -help` 또는 해당 버전의 안전한 도움말로 headless 옵션을 확인한다.
3. 기억에 의존해 최신 Virtuoso API를 사용하지 않는다.
4. 최소 OCEAN script가 headless로 시작/종료되는지 확인한다.
5. 최소 SKILL script가 `virtuoso -nograph` 또는 검증된 동등 방식으로 실행되는지 확인한다.
6. library/cell/view 존재 여부와 제한된 metadata만 조회한다.
7. PDK 모델이나 cellview 원문을 MCP 응답으로 내보내지 않는다.
8. read-only runner subcommand와 MCP tool을 추가한다.

예상 도구 후보:

```text
cadence_list_libraries
cadence_list_cells
cadence_inspect_cellview
cadence_get_testbench_metadata
```

9. library/cell/view allowlist 구성 파일을 만든다.
10. 설계 데이터 lock이나 저장 작업이 발생하지 않는지 검증한다.

### 중단 조건

- headless 실행이 의도치 않게 cellview를 저장하려 함
- PDK 또는 공용 library 쓰기 요구
- 라이선스 기능이 부족함
- 실제 프로젝트 식별에 사용자 정보가 필수임

중단 시 안전한 진단과 `docs/USER_INPUTS_REQUIRED.md`를 커밋하고 `BLOCKED`로 보고한다.

### 수락 기준

- OCEAN/SKILL headless 최소 실행 성공
- read-only metadata 조회 성공
- 원본 수정 없음
- allowlist 밖 library 접근 거부
- MCP output에 proprietary file content 없음

### 권장 commit

```text
feat(ocean): add read-only headless design discovery
```

### 다음 WP

- **WP-09 — ADE/Testbench Profile Automation**
- **추천 모델:** GPT-5.6 Sol
- **Effort:** max

---

## WP-09 — ADE/Testbench Profile Automation

### 추천 모델

- **Primary:** GPT-5.6 Sol
- **Effort:** max
- **Fallback:** GPT-5.6 Terra max

### 목표

실제 회로를 임의 script가 아니라 명시적인 simulation profile과 variable allowlist로 실행한다.

### 필요한 도메인 입력

아직 다음 값이 없을 수 있다.

- PDK 이름과 버전
- project `cds.lib`
- library/cell/view
- ADE state 또는 test name
- 허용 design variables와 단위/범위
- analysis 종류
- corner 목록
- output/measurement 목록

먼저 read-only discovery로 찾을 수 있는 것을 찾는다. 찾을 수 없는 값만 `docs/USER_INPUTS_REQUIRED.md`에 최소 질문으로 기록한다.

### 수행 항목

1. profile registry schema를 정의한다.
2. profile마다 다음을 고정한다.
   - library/cell/view 또는 netlist source
   - allowed analyses
   - allowed variables
   - numeric range와 unit
   - allowed corners
   - allowed outputs
   - timeout
3. 모델이 임의 OCEAN/SKILL 코드를 제공할 수 없게 한다.
4. profile template은 repository review 대상 파일로 저장한다.
5. submit 입력을 typed/validated object로 만든다.
6. run manifest에 실제 적용값을 기록한다.
7. result에 재현 가능한 설정 요약과 artifact metadata를 기록한다.
8. 원본 ADE state를 덮어쓰지 않는다.
9. test fixture profile과 실제 profile을 분리한다.

예상 도구:

```text
cadence_list_profiles
cadence_get_profile
cadence_submit_profile
cadence_compare_runs
cadence_export_waveform
```

### 수락 기준

- allowlisted profile 실행 성공
- 범위 밖 variable 거부
- unknown variable/corner 거부
- run manifest로 재현 가능
- 원본 testbench/ADE state 수정 없음
- 대용량 결과를 MCP에 직접 반환하지 않음

### 권장 commit

```text
feat(ade): add allowlisted simulation profiles
```

### 다음 WP

- **WP-10 — ADC Measurement Contracts**
- **추천 모델:** GPT-5.6 Sol
- **Effort:** max

---

## WP-10 — ADC Measurement Contracts

### 추천 모델

- **Primary:** GPT-5.6 Sol
- **Effort:** max
- **Fallback:** GPT-5.6 Terra max

### 목표

ADC 결과 계산을 임의 해석이 아니라 명시적인 measurement contract로 고정한다.

### 수행 항목

1. 다음 측정값의 정의 문서를 만든다.

```text
DC power
offset
settling time
SNR
SNDR
THD
ENOB
DNL
INL
corner comparison
Monte Carlo summary
```

2. 정의되지 않은 값을 임의 default로 결정하지 않는다.
3. FFT 기반 측정에는 최소 다음 입력을 요구한다.
   - sample frequency
   - input tone frequency
   - sample count
   - analysis time window
   - initial transient exclusion
   - window function
   - DC bin policy
   - fundamental bin policy
   - harmonic count/policy
   - noise bin range
   - differential signal expression
   - ENOB equation
4. contract version을 run manifest에 저장한다.
5. known synthetic waveform fixture로 계산을 검증한다.
6. OCEAN 계산과 Python post-processing 중 더 재현 가능한 방식을 근거와 함께 선택한다.
7. float tolerance와 unit을 테스트한다.
8. 결과를 structured metrics로 반환한다.

예상 도구:

```text
cadence_measure_dc_power
cadence_measure_settling
cadence_measure_fft_metrics
cadence_measure_linearity
cadence_compare_corner_results
```

### 수락 기준

- synthetic fixture의 expected metric과 일치
- measurement contract 없이는 실행 거부
- 단위와 계산식을 결과에 명시
- run-to-run 재현성 확보
- 사용자 회로에 대한 실제 측정은 필요한 정의가 제공된 후에만 수행

### 권장 commit

```text
feat(adc): add versioned ADC measurement contracts
```

### 다음 WP

- **WP-11 — Controlled Design Writes & Release**
- **추천 모델:** GPT-5.6 Sol
- **Effort:** max

---

## WP-11 — Controlled Design Writes & Release

### 추천 모델

- **Primary:** GPT-5.6 Sol
- **Effort:** max
- **Fallback:** GPT-5.6 Terra max

### 목표

명시적인 사용자 승인이 있는 경우에만 복사본 기반 제한 쓰기를 추가하고 v1 릴리스를 준비한다.

### 전제 조건

- WP-00부터 WP-10까지 완료
- read-only 기능의 실사용 안정성 확인
- 쓰기 대상 전용 library 지정
- backup/rollback 검증
- 사용자 명시 승인

### 수행 항목

1. PDK와 공용 library를 영구 read-only로 분류한다.
2. 쓰기 대상은 전용 work library allowlist로 제한한다.
3. 원본에서 작업 복사본을 만들고 그 복사본만 수정한다.
4. 변경 전 backup과 manifest를 만든다.
5. dry-run으로 예상 변경을 구조화해 보여준다.
6. 사용자 승인 토큰 또는 명시적 confirmation gate 이후에만 적용한다.
7. 임의 SKILL eval은 여전히 금지한다.
8. 미리 정의된 좁은 변경 작업만 도구화한다.
9. 저장 후 검증과 rollback 절차를 자동화한다.
10. packaging, install, uninstall, upgrade 문서를 완성한다.
11. semantic version tag와 release notes를 작성한다.
12. private GitHub release 또는 tag를 만든다.

### 수락 기준

- 승인 없이 write tool이 실행되지 않음
- PDK/공용 library 쓰기 거부
- dry-run과 실제 변경 일치
- backup에서 rollback 성공
- 모든 테스트와 E2E 성공
- install/uninstall 문서 검증
- v1 tag가 private repository에 push됨

### 권장 commit/tag

```text
feat(write): add approved copy-based design mutations
chore(release): prepare v1.0.0
v1.0.0
```

### 다음 단계

정규 WP 완료 후 유지보수 모드로 전환한다.

- 작은 문서/포맷 수정: GPT-5.6 Luna high
- 일반 버그/테스트: GPT-5.6 Terra high 또는 max
- 보안/아키텍처/레거시 Cadence 문제: GPT-5.6 Sol max

---

# 11. 필수 완료 보고서 형식

각 WP의 최종 응답은 반드시 아래 순서와 제목을 사용한다. 성공, 부분 완료, 차단 모두 동일하다.

````markdown
# WP-XX 완료 보고서

## 상태
- Result: PASS | PARTIAL | BLOCKED | FAIL
- Executed model: <실제 모델>
- Reasoning effort: <실제 effort>

## 완료 내용
- ...

## 변경 파일
- `path`: 설명

## 검증 증거
- Command: `...`
- Result: PASS/FAIL와 핵심 출력

## 원격 영향
- CentOS 변경 경로: ... 또는 없음
- Cadence 실행: ... 또는 없음
- 설계 데이터 수정: 반드시 yes/no

## 보안 확인
- 비밀정보 커밋 여부: no
- 임의 shell/SKILL/OCEAN 실행 경로 추가 여부: no
- 허용 루트 밖 쓰기 여부: no

## GitHub 동기화
- Repository: `Phjrab/cadence-mcp-bridge`
- Visibility verified private: yes/no
- Feature branch: `wp/WP-XX-...`
- Based on origin/main commit: `<full SHA>`
- Commit: `<full SHA>`
- Commit message: `...`
- Feature branch push: PASS/FAIL
- Main direct push performed: 반드시 no
- Merge performed by Codex: `yes (explicitly authorized)` 또는 `no`
- Working tree clean: yes/no

## 남은 위험 또는 차단 요소
- 없음 또는 구체적인 항목

## 사용자 조치 필요
- PASS인 경우 현재 feature branch 검토 및 main 통합, 또는 Codex가 대신할 수 없는 최소 조치 1개

# NEXT RUN
- Next work package: `WP-YY — 이름`
- Recommended model: `GPT-5.6 Sol|Terra|Luna`
- Recommended effort: `max|high|medium`
- Fallback model: `...`
- Why this model: 한 문장
- Start prompt:

```text
AGENTS.md, CODEX_MASTER_PROMPT.md, PROJECT_STATE.md를 전부 읽고 WP-YY만 실행하라. 이전 WP feature branch가 최신 origin/main에 반영됐는지 먼저 확인하고, 최신 origin/main에서 WP-YY 전용 feature branch를 만든 뒤 수락 기준 검증, PROJECT_STATE.md 갱신, 커밋, feature branch push까지 완료하라. main에 직접 push하거나 merge하지 말고 필수 완료 보고서 형식으로 끝내라. 다음 WP는 시작하지 마라.
```
````

## 보고서 규칙

- 실제 commit/feature branch push를 하지 않았다면 했다고 쓰지 않는다.
- Codex가 `main`에 직접 commit하거나 push해서는 안 되며, merge는 사용자가 명시적으로 승인한 특정 GitHub PR에만 수행한다.
- feature branch push 후 명시적 PR 병합 승인이 없다면 반드시 STOP한다.
- 명시적으로 승인된 merge는 GitHub PR을 통해서만 수행하고 `main`에 직접 push하지 않는다.
- 테스트하지 않은 것을 PASS라고 쓰지 않는다.
- `BLOCKED`라면 다음 WP는 현재 WP를 유지한다.
- 사용자 조치는 credential 입력, 앱 재시작, 회로 정의 제공처럼 Codex가 대신할 수 없는 것만 요청한다.
- 다음 실행 추천은 반드시 포함한다.
- 추상적인 “계속 진행하세요”가 아니라 exact next prompt를 제공한다.

---

# 12. PROJECT_STATE.md 갱신 규칙

각 WP 종료 시 다음 필드를 갱신한다.

```yaml
project: cadence-mcp-bridge
repository: Phjrab/cadence-mcp-bridge
visibility: private
current_wp: WP-XX
current_status: pending|in_progress|passed|partial|blocked|failed
last_completed_wp: WP-XX|null
next_wp: WP-YY
current_feature_branch: <branch|null>
base_main_commit: <sha|null>
last_commit: <sha|null>
last_push: <ISO-8601|null>
awaiting_user_merge: true|false
remote_runner_deployed: true|false
codex_mcp_registered: true|false
last_e2e_result: pass|fail|not_run
user_action_required: <text|null>
```

사람이 읽는 changelog도 같은 파일 아래에 추가한다.

---

# 13. 차단 처리 원칙

다음 상황만 사용자 조치로 차단할 수 있다.

- GitHub 또는 SSH credential의 interactive 인증
- Python/GitHub CLI 설치에 필요한 사용자 승인
- Codex Desktop 재시작/UI 확인
- proprietary 프로젝트의 PDK/library/cell/testbench 식별
- ADC 측정 정의와 회로 성능 판정 기준
- 설계 데이터 쓰기에 대한 명시적 승인
- 라이선스 서버 또는 제품 feature 부족

차단되기 전까지 Codex가 할 수 있는 read-only 진단, 문서, test fixture, local scaffold는 모두 완료한다.

---

# 14. 완료의 정의

프로젝트가 “MCP v1 사용 가능”이라고 부를 수 있는 최소 조건은 다음과 같다.

- private GitHub repository, 보호된 clean main branch, WP별 feature branch checkpoint
- Windows Python MCP stdio server
- passwordless strict SSH to `cadence-vm`
- restricted CentOS runner
- health, submit, status, log, result, cancel tools
- 실제 Spectre smoke E2E 성공
- Codex Desktop 등록과 실제 tool call 성공
- injection/secret/path containment tests
- 운영 및 복구 문서

“Cadence 전체 자동화”라고 부를 수 있는 조건은 추가로 다음을 포함한다.

- OCEAN/SKILL read-only discovery
- allowlisted ADE/testbench profiles
- versioned measurement contracts
- 승인 기반 복사본 write와 rollback

이 기준을 만족하지 않은 상태에서 완료를 선언하지 않는다.

---

# 15. 공식 참고자료 확인 규칙

구현 시 현재 공식 문서를 우선한다.

- OpenAI Codex 및 MCP 설정: `https://developers.openai.com/codex/`
- OpenAI 모델 목록: `https://developers.openai.com/api/docs/models`
- GPT-5.6 안내: `https://openai.com/index/gpt-5-6/`
- MCP Python SDK: `https://github.com/modelcontextprotocol/python-sdk`
- MCP specification: `https://modelcontextprotocol.io/specification/`

Cadence 레거시 버전은 설치된 `-help`, `-W`, 현장 문서와 실제 테스트 결과를 우선한다. 최신 Cadence 문법을 IC6.1.5/MMSIM12.1에 그대로 적용하지 않는다.

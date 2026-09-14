# 환경·기준선·확인된 사실의 범위

## 역사 환경 — 현재 동작 여부는 재검증

| 항목 | 대화에서 확인된 값 | 취급 |
|---|---|---|
| Host | Windows 11, Codex Desktop, VMware Workstation Pro | 현재 workspace 기준으로 경로를 탐색 |
| VM | CentOS 6.5, i686, Bash, Python 2.6.6 | in-place upgrade 금지 |
| SSH alias | cadence-vm | hostname/IP 변경을 자동 수락하지 않음 |
| 역사 VM 주소 | 192.168.85.128, VMnet8 | 현재 주소라고 가정하지 않음 |
| Virtuoso | IC6.1.5.500.15 / 32-bit | local help·실제 probe로 API 확인 |
| Spectre | 12.1.0.347.isr3 | 최신 solver 옵션 자동 사용 금지 |
| OCEAN | 설치 경로 확인 및 startup smoke 기록 | state load/netlist/PSF 기능 검증과 다름 |
| PDK | gpdk090 v4.6, NN | 실제 model/deck/통계 지원은 기능별 검증 |
| Source | MyDesignLib / Differential_Amplifier_TB2 / schematic | read-only source |
| ADE | ADE L / state1 | 이름과 실행 당시 내용 일치를 따로 확인 |
| 기준 run | tran stop=4m, 27°C | compatibility snapshot 역사값 |
| 현재 연구 | VDD=1.0 V | 승인 없이 변경하지 않음 |

역사적인 승인 경로:

```text
/home/buet/cds_work
/home/buet/cds_work/.cadence_mcp
/home/buet/cds_work/MCP_WorkLib
/home/buet/cadence/IC615/tools/dfII/bin/virtuoso
/home/buet/cadence/MMSIM121/tools/bin/spectre
/home/buet/cadence/IC615/tools/dfII/bin/ocean
```

이 경로는 현재 operator config를 복구할 단서다. core에 새로 하드코딩하거나 모든 하위 파일에 새 쓰기 권한을 부여하는 목록이 아니다.

## Compatibility baseline와 Scientific baseline

기존 snapshot의 `VBIASN=300m`, `VBIASP=650m`은 v1 회귀 기준으로 기록되어 있다. 과거 회로 연구에서는 `370m/650m`이 맞는 조건으로 보고되었다. 두 조건의 VDD/VCM/input/load/W/L/모델/revision/state가 같은지는 연결 증거로 확인한다.

- compatibility baseline: 원래 구현 동작을 재현한다. 승인 없이 수정하지 않는다.
- scientific baseline: 현재 연구 조건과 실제 회로 의미가 확인된 profile이다.
- 어떤 값이 맞는지 모델이 숫자만 비교해 결정하지 않는다.
- 표에 없는 device 값·입력 신호·load·analysis는 unknown으로 남긴다.
- 과거 1.2 V 실험은 현재 1 V 연구 결과에 섞지 않는다.
- 연구 profile을 새로 만들어도 v1 regression profile을 삭제하지 않는다.

## 단계별 확인 수준

```text
located → readable → version_known → licensed_execution
→ functional_fixture_verified → actual_profile_verified
→ physical_reference_verified → target_submission_verified
```

이 단계는 직선의 성공 가정이 아니라 별도 evidence 수준이다. executable 존재·license 변수 SET·version 출력은 functional capability의 증거가 아니다. 한 기능 성공으로 다른 license feature를 사용할 수 있다고 주장하지 않는다.

## 현재 저장소 상태

2026-08-31의 기록에는 v1.0.0, runner 0.16.0, 22개의 MCP 도구, snapshot actual profile, V4 clean validation이 보고되었다. 이번 2026-09-05 `get_repo` 조회는 HTTP 404다. 현재 visibility·HEAD·작업·릴리스는 `unverified`로 취급한다. package import에서 실제 로컬 Git/현재 가능한 connector로 다시 조사한다.

기존 코드의 public MCP에 22개 도구가 실제로 남아 있는지, sweep가 이미 추가되었는지, operator-only V4 command와 public write tool이 어떻게 연결되어 있는지는 최신 코드가 확보되기 전 확정하지 않는다.

## Source와 artifact 보존

35 instances/14 nets/8 terminals는 과거 source read의 결과다. 현재 source 불변은 raw file+parameter/connectivity semantic fingerprint로 확인한다.

`sch.oa-`는 과거 master.tag가 선택하지 않는 보조 파일로 보존 정책이 적용된 사례다. 모든 `*-` 파일의 성격을 일반화하지 않는다. 락 부재 확인과 데이터 artifact 의미 확인을 구분하고, unknown artifact는 삭제하거나 새 정상 baseline에 조용히 포함시키지 않는다.

## 호스트·VM 변경

설치 경로·D: 드라이브 이동·VM 복원·네트워크 바뀜 등은 별도 운영 작업이다. shut down 상태의 독립 백업과 host key/라이선스/경로/evidence 재검증을 계획하고, 현재 기능 개발 WP 중에 VM 환경을 임의 이동하지 않는다.

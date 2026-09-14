# 중단 작업 상태 확인·복구 계획 — 실행 승인이 아님

## 확인된 사실

- job/run ID: <...>
- 마지막 durable journal stage: <...>
- current target/backup/source identity: <...>
- active worker/lock evidence: <...>
- before/current semantic·bytes·metadata diff: <...>
- 없는 기록: <...>

## 분류

`NOT_STARTED / RUNNING / RESPONSE_LOST / PARTIAL_WRITE / COMPLETED_UNREPORTED / UNKNOWN / UNSAFE`

## 허용 범위 내 read-only 조사

<고정 대상·고정 출력·보호 범위. 무관한 홈 디렉터리나 PDK 원문으로 조사 범위를 넓히지 않는다.>

## 제안하는 보상 작업

<exact target·backup·before/after·executor·precondition·수락 기준·실패 시 정지 조건.>

## 승인

이 template는 실제 rollback·삭제·재생성·강제 lock 해제를 승인하지 않는다.
기존 policy가 이 보상 작업을 명시적으로 포함하는지 확인한다. 없다면 운영자의 새 좁은 승인이 필요하다.
실패 target을 새 이름으로 무제한 늘리지 말고 원인과 evidence를 보존한다.

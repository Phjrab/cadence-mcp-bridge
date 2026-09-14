# 현재 phase 실행 index — TEMPLATE, 통째로 덮어쓰기 금지

- actual active task: <로컬 상태 조사 후 기록>
- current phase: <해당 task 소속>
- scope: <이번 한 작업>
- legacy IDs/aliases: <관측한 매핑>
- predecessor evidence: <...>
- reviewed base commit: <...>
- integration status: <...>
- deployment/real-validation status: <...>
- current authorization: <없음 또는 operator-controlled record reference>

## 지금 수행할 내용

<현재 task만 구체화. 원격/쓰기/배포 권한이 없는 범위는 local 계획과 테스트로 구분.>

## 금지/보호

<원본/PDK/state/V1~V4 evidence/기존 branch, 운영 중 job, 불명확한 artifact.>

## 수락 기준

<task의 positive/negative와 관련 hardening requirement를 실제 테스트로 연결.>

## 다음 후보

<다음 하나와 선행/승인/병합 조건. 후보는 실행 허가가 아님.>

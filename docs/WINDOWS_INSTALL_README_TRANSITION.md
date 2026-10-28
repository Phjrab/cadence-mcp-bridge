# Windows installer publication switch

Inactive editorial checklist, not publication authority. Keep v2.1.0 manual
installation and no EXE download URL until the exact new candidate is approved,
actually published and its downloaded files match the candidate hashes.

Then record version/commit/filename/SHA-256/signing status/verified URL, update the
stable/preview table and replace the short installation paragraph with:

“Windows x64 설치 파일을 실행하면 전용 런타임과 설정 도우미를 사용자 계정에
설치합니다. Python·Git·pip 수동 설치는 필요하지 않습니다. 기존 runtime을
선택하거나 새 연결 정보를 입력하고 Codex 설정 변경을 검토하세요.
설치 완료는 VM 연결·회로 등록·실행 승인 완료를 뜻하지 않습니다.”

Retain the older manual guide and frozen releases. State exact host/app/VM tests;
SDK/Windows Server CI never implies actual Codex/all Windows desktop acceptance.
Publication grants no remote deployment or experiment authority.

# 목록 등재 요청

이 저장소는 공식 모드 파일을 배포합니다. 외부 제작자의 모드 파일은 이 저장소에 다시 올리지 않습니다.

## 커뮤니티 모드를 목록에 올리기

1. 모드를 자신의 공개 GitHub 저장소 Release에 `.nelmod`로 올립니다(NEL 모드 배포 규격 §6의 manifest 정보 포함).
2. 이 저장소의 `catalog.json`에 항목을 추가하는 PR을 엽니다. `repository`는 **자신의 저장소**, `releases[]`의 `tag`·`asset`·`size`·`sha256`은 실제 업로드한 파일 값입니다.
3. 공식 모드 id와 `nel.` 접두는 쓸 수 없습니다. `license`와 사용 조건(`terms`)을 반드시 적습니다.

등재된 모드도 NEL에서는 "외부 GitHub · 공식 목록 등재"로 표시되며, 파일은 제작자 저장소에서 내려받습니다. 등재는 코드 검토나 안전 보증이 아닙니다.

## 공식 모드 갱신 (관리자)

1. 비공개 소스에서 빌드합니다. PDB 경로가 들어가지 않게 빌드합니다(MSVC `/PDBALTPATH:%_PDB%` 또는 디버그 정보 없음).
2. `nel-mod-publish`로 배포 파일을 만듭니다. 이 도구는 지정한 파일만 복사하고 소스·디버그 파일·개인 경로·토큰을 검사합니다.
3. 출력의 `RELEASE_NOTES.md`와 `release.json`을 확인한 뒤 Release(태그 `<모드>-v<버전>`)를 만들고 `.nelmod`를 첨부해 게시합니다.
4. 게시하면 **Update catalog** Actions가 `.nelmod`를 받아 검사하고 `catalog.json`을 자동으로 커밋합니다. 시험 버전(`-beta.1` 등)이나 GitHub "pre-release"는 preview 채널로 들어갑니다. Actions 탭에서 실패가 보이면 '건너뜀' 줄의 이유를 확인합니다.
5. 처음 올리는 모드는 사용 조건 `licenses/<모드 id>.md`(필요하면 `icons/<모드 id>.png`)를 커밋합니다. 카탈로그의 icon·category는 직접 적은 값이 유지됩니다.

이미 목록에 있는 버전을 다른 파일로 바꿀 수 없습니다. 고친 파일은 새 버전 번호로 올립니다. Release를 삭제하면 그 버전은 목록에서 빠집니다.

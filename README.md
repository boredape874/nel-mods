# NEL 공식 모드 배포

NEL client의 **Mods → 찾아보기**에 표시되는 공식 모드의 배포 저장소입니다. 이 저장소에는 배포 파일과 목록·설명·사용 조건만 있습니다. 모드 소스 코드는 공개하지 않습니다.

## 설치

NEL client → Mods → 찾아보기에서 모드를 고르고 **설치**를 누릅니다. 설치한 모드는 꺼진 상태로 추가되며 **다음 시작에 사용**을 켜야 다음 게임 시작부터 로드됩니다. NEL은 아래 목록에 적힌 크기와 SHA-256으로 받은 파일을 확인합니다. 해시 확인은 파일이 게시본과 같다는 뜻이며 코드 안전성 검증은 아닙니다.

직접 받은 경우: Releases에서 `.nelmod`를 받아 Mods → 로컬 패키지 추가로 설치합니다.

## 구성

| 경로 | 내용 |
|---|---|
| `catalog.json` | 모드 목록과 각 버전의 Release 태그·파일 이름·크기·SHA-256 (형식: NEL 모드 배포 규격 catalog schema 1). Release를 게시·수정·삭제하면 GitHub Actions가 자동으로 갱신합니다 |
| `scripts/update_catalog.py`, `.github/workflows/update-catalog.yml` | 카탈로그 자동 갱신: 각 `.nelmod`의 크기·GitHub digest·패키지 manifest를 검사한 뒤 목록에 넣습니다 |
| `licenses/` | 모드별 사용 조건과 제3자 고지 |
| `icons/` | 목록 아이콘 |
| Releases | 모드별 태그(`<모드>-v<버전>`)와 `.nelmod` 파일 |

한 저장소에 여러 모드가 있으므로 GitHub의 "Latest" Release는 특정 모드의 최신 버전을 뜻하지 않습니다. NEL은 `catalog.json`에 적힌 태그와 파일만 사용합니다. Release 페이지의 "Source code" 압축은 이 배포 저장소의 내용이며 모드 소스가 아닙니다.

## 사용 조건

각 모드의 사용 조건은 `licenses/<모드 id>.md`와 패키지 안의 `licenses/`를 따릅니다. 이 저장소 전체에 오픈소스 라이선스가 적용되지 않습니다.

## 커뮤니티 모드

외부 제작자는 자신의 GitHub 저장소에서 같은 `.nelmod` 규격으로 배포할 수 있으며, 사용자는 NEL의 **GitHub 주소로 추가**로 설치합니다. 공용 목록 등재 요청은 [CONTRIBUTING.md](CONTRIBUTING.md)를 보세요.

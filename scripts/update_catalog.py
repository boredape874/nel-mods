#!/usr/bin/env python3
"""Rebuild this repository's catalog.json from its published GitHub Releases.

Runs in GitHub Actions on every release change (and on demand). For each .nelmod asset of each published release:
download it, check size and GitHub's sha256 digest, read nel-mod.json from the package, validate it with the NEL
manifest rules, and list it in catalog.json under its mod id with the exact tag, asset name, size and SHA-256.

- Entries whose repository is another repository (community listings added by pull request) are kept unchanged.
- Mod-level fields maintained by hand (icon, category, terms) are kept; name/description/authors/license come from
  the newest package manifest.
- A version already in the catalog with a different SHA-256 is never replaced (clients may have installed it).
- Invalid assets are skipped and reported; valid changes are still written. Exit code 1 means something was skipped.

Standard library only. Environment: GITHUB_REPOSITORY (owner/repo), GITHUB_API_URL (default https://api.github.com),
GITHUB_TOKEN (optional; Actions passes its own, the NEL client never needs one).
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone

MAX_PACKAGE = 256 << 20
MAX_UNPACKED = 1 << 30
MAX_ENTRY = 512 << 20
MAX_ENTRIES = 10_000
MAX_MANIFEST = 1 << 20
ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$")
GAME = re.compile(r"^\d+\.\d+\.\d+(\.\d+)?$")
TAG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
ASSET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,150}\.nelmod$")
RANGE = re.compile(r"^(=\S+|>=\S+( <\S+)?)$")


def api(base: str, path: str, token: str | None) -> object:
    request = urllib.request.Request(base.rstrip("/") + "/" + path, headers={
        "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "nel-mods-catalog"})
    if token:
        request.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def download(url: str, limit: int) -> bytes:
    request = urllib.request.Request(url, headers={"Accept": "application/octet-stream", "User-Agent": "nel-mods-catalog"})
    with urllib.request.urlopen(request, timeout=300) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("패키지가 크기 제한을 넘습니다")
    return data


def semver_key(version: str):
    m = SEMVER.match(version)
    core = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    pre = m.group(4)
    if pre is None:
        return core + ((1,),)
    parts = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split("."))
    return core + ((0,) + parts,)


def safe_relative(path: str) -> bool:
    if not path or len(path) > 260 or any(c in path for c in ':\0*?"<>|'):
        return False
    norm = path.replace("\\", "/")
    if norm.startswith("/"):
        return False
    segments = norm.split("/")
    if any(s == ".." or (s and not s.strip()) for s in segments):
        return False
    return bool(segments[-1]) and any(s and s != "." for s in segments)


def normalize(path: str) -> str:
    return "/".join(s for s in path.replace("\\", "/").split("/") if s and s != ".")


def read_manifest(data: bytes) -> dict:
    """Same package rules as the NEL launcher (NelModStore): root nel-mod.json, safe paths, limits, entry present."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise ValueError(f"올바른 ZIP이 아닙니다: {error}")
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ENTRIES:
            raise ValueError("파일 수가 너무 많습니다")
        total, seen = 0, set()
        for info in infos:
            name = info.filename.replace("\\", "/")
            relative = name.rstrip("/") if name.endswith("/") else name
            if not relative:
                continue
            if not safe_relative(relative):
                raise ValueError(f"허용되지 않는 경로: {info.filename}")
            if name.endswith("/"):
                continue
            if info.file_size > MAX_ENTRY:
                raise ValueError(f"파일이 너무 큽니다: {info.filename}")
            total += info.file_size
            if total > MAX_UNPACKED:
                raise ValueError("압축 해제 크기가 제한을 넘습니다")
            key = normalize(relative).lower()
            if key in seen:
                raise ValueError(f"같은 경로가 중복되었습니다: {info.filename}")
            seen.add(key)
        try:
            info = archive.getinfo("nel-mod.json")
        except KeyError:
            raise ValueError("패키지 루트에 nel-mod.json이 없습니다")
        if info.file_size > MAX_MANIFEST:
            raise ValueError("nel-mod.json이 너무 큽니다")
        manifest = json.loads(archive.read(info).decode("utf-8-sig"))
        problems = validate_manifest(manifest)
        if problems:
            raise ValueError("nel-mod.json 검사 실패: " + " / ".join(problems))
        if normalize(manifest["entry"]).lower() not in seen:
            raise ValueError(f"entry '{manifest['entry']}' 파일이 패키지에 없습니다")
        return manifest


def validate_manifest(m: object) -> list[str]:
    """Subset of NelModManifests.TryParse that the catalog depends on; the launcher re-validates everything on install."""
    if not isinstance(m, dict):
        return ["최상위 값은 객체여야 합니다"]
    p = []
    def text(name, required=False):
        value = m.get(name)
        if value is None:
            if required:
                p.append(f"{name}이(가) 필요합니다")
            return None
        if not isinstance(value, str):
            p.append(f"{name}은(는) 문자열이어야 합니다")
            return None
        return value
    if m.get("schemaVersion") != 1:
        p.append("schemaVersion 1이 필요합니다")
    mid = text("id", True)
    if mid is not None and not ID.match(mid):
        p.append(f"id '{mid}' 형식 오류")
    name = text("name", True)
    if name is not None and not name.strip():
        p.append("name이 비어 있습니다")
    version = text("version", True)
    if version is not None and not SEMVER.match(version):
        p.append(f"version '{version}'은 SemVer가 아닙니다")
    text("description")
    lic = text("license", True)
    if lic is not None and not lic.strip():
        p.append("license가 비어 있습니다")
    kind = text("kind", True)
    if kind is not None and kind not in ("nel-native", "levilamina"):
        p.append(f"kind '{kind}' 오류")
    entry = text("entry", True)
    if entry is not None and not safe_relative(entry):
        p.append("entry는 패키지 내부 상대 경로여야 합니다")
    abi = m.get("coreAbi")
    if not isinstance(abi, int) or isinstance(abi, bool) or abi < 1:
        p.append("coreAbi는 1 이상의 정수여야 합니다")
    games = m.get("gameVersions")
    if not isinstance(games, list) or not games or not all(isinstance(g, str) and GAME.match(g) for g in games):
        p.append("gameVersions는 A.B.C 또는 A.B.C.D 문자열 배열이어야 합니다")
    authors = m.get("authors", [])
    if not isinstance(authors, list) or not all(isinstance(a, str) for a in authors):
        p.append("authors는 문자열 배열이어야 합니다")
    for field in ("dependencies", "conflicts"):
        items = m.get(field) or []
        if not isinstance(items, list) or not all(isinstance(x, dict) and isinstance(x.get("id"), str) and ID.match(x["id"]) for x in items):
            p.append(f"{field} 형식 오류")
        elif field == "dependencies" and not all(isinstance(x.get("version"), str) and RANGE.match(x["version"]) for x in items):
            p.append("dependencies version은 =x, >=x, >=x <y 형식입니다")
    source = m.get("source")
    if source is not None and not (isinstance(source, str) and source.startswith("https://")):
        p.append("source는 https 주소여야 합니다")
    return p


def build(repository: str, api_base: str, token: str | None, catalog: dict, repo_root: str, log) -> tuple[dict, list[str]]:
    errors: list[str] = []
    releases, page = [], 1
    while True:
        batch = api(api_base, f"repos/{repository}/releases?per_page=100&page={page}", token)
        if not isinstance(batch, list):
            raise RuntimeError("지원하지 않는 Release 목록 응답")
        releases.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    existing = {m.get("id"): m for m in catalog.get("mods", []) if isinstance(m, dict)}
    own = lambda m: str(m.get("repository") or catalog.get("repository", "")).lower() == repository.lower()
    found: dict[str, list[tuple[dict, dict]]] = {}
    for release in releases:
        if release.get("draft"):
            continue
        tag = release.get("tag_name") or ""
        for asset in release.get("assets") or []:
            name = asset.get("name") or ""
            if not name.lower().endswith(".nelmod"):
                continue
            where = f"{tag}/{name}"
            try:
                if not TAG.match(tag) or ".." in tag:
                    raise ValueError("태그 형식 오류")
                if not ASSET.match(name) or ".." in name:
                    raise ValueError("asset 이름은 경로 없는 .nelmod 이름이어야 합니다")
                if asset.get("state") != "uploaded":
                    raise ValueError("업로드가 끝나지 않았습니다")
                size = int(asset.get("size") or 0)
                if size <= 0 or size > MAX_PACKAGE:
                    raise ValueError("크기 제한 밖입니다")
                data = download(asset["browser_download_url"], MAX_PACKAGE)
                if len(data) != size:
                    raise ValueError(f"받은 크기 {len(data)} B가 GitHub 크기 {size} B와 다릅니다")
                sha = hashlib.sha256(data).hexdigest()
                digest = asset.get("digest")
                if isinstance(digest, str) and digest.lower().startswith("sha256:") and digest[7:].lower() != sha:
                    raise ValueError("SHA-256이 GitHub digest와 다릅니다")
                manifest = read_manifest(data)
                prerelease = SEMVER.match(manifest["version"]).group(4) is not None
                entry = {
                    "version": manifest["version"],
                    "channel": "preview" if prerelease or release.get("prerelease") else "stable",
                    "tag": tag, "asset": name, "size": size, "sha256": sha,
                    "gameVersions": list(manifest["gameVersions"]), "coreAbi": manifest["coreAbi"],
                    "dependencies": [{"id": d["id"], "version": d["version"]} for d in manifest.get("dependencies") or []],
                    "conflicts": [{k: v for k, v in (("id", c["id"]), ("reason", c.get("reason"))) if v is not None} for c in manifest.get("conflicts") or []],
                }
                if release.get("published_at"):
                    entry["publishedAt"] = release["published_at"]
                found.setdefault(manifest["id"], []).append((entry, manifest))
                log(f"확인 {where}: {manifest['id']} {manifest['version']} sha256 {sha[:12]}…")
            except (ValueError, KeyError, json.JSONDecodeError, urllib.error.URLError, OSError) as error:
                errors.append(f"{where}: {error}")

    mods = [m for m in catalog.get("mods", []) if isinstance(m, dict) and not own(m)]  # community listings unchanged
    for mod_id in sorted(found):
        entries = found[mod_id]
        versions: dict[str, tuple[dict, dict] | None] = {}
        for entry, manifest in entries:
            version = entry["version"]
            if version not in versions:
                versions[version] = (entry, manifest)
            elif versions[version] is not None and versions[version][0]["sha256"] != entry["sha256"]:
                errors.append(f"{mod_id} {version}이(가) 여러 Release에 다른 파일로 있습니다. 하나만 남기세요.")
                versions[version] = None
        previous = existing.get(mod_id) if existing.get(mod_id) and own(existing[mod_id]) else {}
        old_releases = {r.get("version"): r for r in previous.get("releases", []) if isinstance(r, dict)}
        releases_out = []
        for version, pair in versions.items():
            if pair is None:
                continue
            entry, _ = pair
            old = old_releases.get(version)
            if old and old.get("sha256") != entry["sha256"]:
                errors.append(f"{mod_id} {version}은(는) 카탈로그에 다른 파일로 이미 등록되어 있어 바꾸지 않았습니다. 새 버전 번호로 올리세요.")
                releases_out.append(old)
                continue
            if old and old.get("notes"):
                entry["notes"] = old["notes"]
            releases_out.append(entry)
        if not releases_out:
            continue
        releases_out.sort(key=lambda r: semver_key(r["version"]), reverse=True)
        newest = max((pair[1] for pair in versions.values() if pair), key=lambda m: semver_key(m["version"]))
        mod = {"id": mod_id, "name": newest["name"]}
        if newest.get("description"):
            mod["description"] = newest["description"]
        if newest.get("authors"):
            mod["authors"] = list(newest["authors"])
        for field in ("icon", "category"):
            if previous.get(field):
                mod[field] = previous[field]
        mod["license"] = newest["license"]
        terms = previous.get("terms") or (f"licenses/{mod_id}.md" if os.path.isfile(os.path.join(repo_root, "licenses", f"{mod_id}.md")) else None)
        if terms:
            mod["terms"] = terms
        mod["repository"] = repository
        if newest.get("source"):
            mod["source"] = newest["source"]
        mod["releases"] = releases_out
        mods.append(mod)
    ids = [m["id"] for m in mods]
    for duplicate in sorted({i for i in ids if ids.count(i) > 1}):
        errors.append(f"모드 id {duplicate}가 공식 Release와 커뮤니티 목록에 동시에 있습니다. 커뮤니티 항목을 정리하세요.")
        mods = [m for m in mods if not (m["id"] == duplicate and not own(m))]

    result = dict(catalog)
    result["format"], result["schemaVersion"], result["repository"] = "nel-mod-catalog", 1, catalog.get("repository") or repository
    result.setdefault("name", "NEL 공식 모드")
    result["mods"] = mods
    if json.dumps(catalog.get("mods"), sort_keys=True) != json.dumps(mods, sort_keys=True):
        result["updatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return result, errors


def main() -> int:
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9_.-]{1,100}$", repository):
        print("GITHUB_REPOSITORY(owner/repo)가 필요합니다", file=sys.stderr)
        return 2
    api_base = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    token = os.environ.get("GITHUB_TOKEN") or None
    root = os.environ.get("CATALOG_ROOT", ".")
    path = os.path.join(root, "catalog.json")
    with open(path, encoding="utf-8-sig") as handle:
        catalog = json.load(handle)
    if catalog.get("format") != "nel-mod-catalog" or catalog.get("schemaVersion") != 1:
        print("catalog.json이 nel-mod-catalog schema 1이 아닙니다", file=sys.stderr)
        return 2
    if str(catalog.get("repository", "")).lower() != repository.lower():
        print(f"catalog.json repository({catalog.get('repository')})가 {repository}와 다릅니다", file=sys.stderr)
        return 2

    attempts = int(os.environ.get("CATALOG_ATTEMPTS", "1"))
    for attempt in range(attempts):
        result, errors = build(repository, api_base, token, catalog, root, print)
        if not any("업로드가 끝나지 않았습니다" in e for e in errors) or attempt == attempts - 1:
            break
        time.sleep(20)  # a release can be published a moment before its assets finish uploading
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    count = sum(len(m.get("releases", [])) for m in result["mods"])
    print(f"catalog.json: 모드 {len(result['mods'])}개, 버전 {count}개")
    for error in errors:
        print("건너뜀: " + error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

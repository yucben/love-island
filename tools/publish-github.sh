#!/usr/bin/env bash
# Run after gh auth login. Publication was explicitly requested by the maintainer.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
repo=yucben/love-island
version=v0.1.0
[[ "$(gh api user --jq .login)" == yucben ]] || { echo 'Log in as yucben first.' >&2; exit 1; }
git diff --quiet
git diff --cached --quiet
[[ -z "$(git ls-files --others --exclude-standard)" ]] || { echo 'Commit all release files first.' >&2; exit 1; }
[[ "$(git rev-parse "$version^{commit}")" == "$(git rev-parse HEAD)" ]] || { echo 'Release tag must match HEAD.' >&2; exit 1; }
[[ "$(git remote get-url origin)" == "https://github.com/$repo.git" ]] || { echo 'Unexpected origin.' >&2; exit 1; }
if ! gh repo view "$repo" >/dev/null 2>&1; then
    gh repo create "$repo" --public --description 'Experimental island notifications and media controls for KDE Plasma Wayland'
fi
[[ "$(gh api "repos/$repo" --jq .fork)" == false ]] || { echo 'Expected an independent repository, not a Fork.' >&2; exit 1; }
git push -u origin main
git push origin "$version"
echo "Published https://github.com/$repo ; the tag workflow creates an experimental source release."

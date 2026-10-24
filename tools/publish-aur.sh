#!/usr/bin/env bash
# Requires an AUR account and an already registered SSH public key.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
work="$root/.aur-publish"
git ls-remote --exit-code https://github.com/yucben/love-island.git refs/tags/v0.1.0 >/dev/null
if [[ ! -d "$work/.git" ]]; then
    git clone ssh://aur@aur.archlinux.org/love-island.git "$work"
fi
[[ "$(git -C "$work" remote get-url origin)" == ssh://aur@aur.archlinux.org/love-island.git ]] || exit 1
if [[ -n "$(git -C "$work" ls-files)" ]]; then
    echo 'AUR repository already has files; review the existing maintainer/history before updating.' >&2
    exit 1
fi
cp -- "$root/packaging/aur/PKGBUILD" "$root/packaging/aur/love-island.install" "$work/"
cd "$work"
makepkg --printsrcinfo > .SRCINFO
git add PKGBUILD .SRCINFO love-island.install
git -c user.name=yucben -c user.email=139486997+yucben@users.noreply.github.com commit -m 'Initial love-island 0.1.0 package'
git push origin HEAD:master
echo 'Published https://aur.archlinux.org/packages/love-island'

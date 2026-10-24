# Maintainer publication

This project is an independent public repository, not a GitHub Fork. Preserve the upstream MIT license and attribution in README.

## GitHub

Authenticate the `yucben` account using GitHub CLI's browser/device flow. Do not paste a token into chat or commit credentials.

```bash
gh auth login --hostname github.com --git-protocol https --web --scopes workflow
bash tools/publish-github.sh
```

The script checks the account, expected origin, clean committed tree and release tag. It creates `yucben/love-island` as a public independent repository and pushes main plus v0.1.0 without force. The tag workflow creates an experimental source release. Inspect the check/release workflow results before announcing availability.

## AUR

An AUR account and a registered SSH public key are required. Register at https://aur.archlinux.org/register if registration is available, verify the email, and add your public key in account settings. Account creation and email/browser verification must be done by the account owner. Keep private keys out of the repository.

Configure SSH to use that key for `aur.archlinux.org`, then authenticate against the official server and verify its host key using Arch documentation before the first connection. After the GitHub tag is public:

```bash
bash tools/publish-aur.sh
```

This first-publication helper stops if the AUR repository already contains tracked files. AUR receives just PKGBUILD, .SRCINFO and love-island.install. Do not publish package archives to AUR. Do not claim AUR availability until the package page and public build source have been verified.

## Release checks

- Run isolated application/QML tests and package layout validation.
- Build with makepkg, then verify actual install takeover, explicit restore, disabled login behavior and removal recovery in a Plasma Wayland session.
- Preserve configuration/history; verify only the intended account is enrolled.
- Keep the stable-144-FPS limitation visible.
- Recheck release source URLs from a fresh clone after publication; local mirror builds cannot prove remote availability.

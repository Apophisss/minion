# Packaging

How Minion gets to users beyond PyPI. The release workflow (`.github/workflows/release.yml`) publishes these by
itself when a `vX.Y.Z` tag is pushed:

- **PyPI**: `minion-desktop`, the wheel and the sdist.
- **npm**: `minion-desktop`, the TypeScript client and the `npx minion-desktop mcp` launcher (`clients/typescript`).
- **GitHub release**: the wheel, the sdist and the Claude Desktop extension, `minion.mcpb` ([mcpb/](mcpb/README.md)).
- **The official MCP Registry**: `server.json`, as `io.github.apophisss/minion`, with the PyPI, npm and `.mcpb`
  packages.

The files in this folder are for package managers that a person publishes to by hand, **after the PyPI release**:

| File | For |
|---|---|
| [`homebrew/minion-desktop.rb`](homebrew/minion-desktop.rb) | A Homebrew formula, for the tap `apophisss/homebrew-tap` |
| [`aur/PKGBUILD`](aur/PKGBUILD) | `python-minion-desktop` in the Arch User Repository |
| [`mcpb/`](mcpb/README.md) | The Claude Desktop extension (built and released automatically) |
| `logo-400.png` | The logo at 400×400, the size the Cline MCP Marketplace asks for (`mcpb/icon.png` is 512×512) |

Where else to list Minion (MCP directories and awesome lists) is in
[docs/launch/directories.md](../docs/launch/directories.md).

## Homebrew

Users install with `brew install apophisss/tap/minion-desktop`. Homebrew finds the formula in the GitHub repository
`apophisss/homebrew-tap` (a tap's repository name starts with `homebrew-`).

**Once:** create the public repository `apophisss/homebrew-tap` with a `Formula/` folder and a short README. To start
from Homebrew's template instead, run `brew tap-new apophisss/tap` and push the folder it creates.

**Each release**, after PyPI has it:

```bash
python scripts/update_homebrew_formula.py 1.0.0      # writes the sdist's exact URL and SHA-256 into the formula
cp packaging/homebrew/minion-desktop.rb "$(brew --repository apophisss/tap)/Formula/"
brew install --build-from-source apophisss/tap/minion-desktop
brew test apophisss/tap/minion-desktop && brew audit --strict --online apophisss/tap/minion-desktop
```

Then commit the formula in the tap (and here, so that the two stay the same) and push. Until the script has run,
`url` and `sha256` are placeholders: `brew style` flags the short PyPI link, and the SHA-256 is all zeros.

The formula installs Minion into its own virtual environment with Homebrew's Python (`python@3.13`). Minion has
no Python dependencies, so it needs no `resource` blocks, and its test runs `minion --version`. Docker can't be a
dependency (Docker Desktop and OrbStack are casks), so the formula says so in its caveats instead.

**homebrew-core**, so that `brew install minion-desktop` works without a tap, is for notable projects: at least
75 stars, 30 forks or 30 watchers (225 stars, 90 forks or 90 watchers when the owner submits it), and repositories
that are at least 30 days old. Python applications in homebrew-core depend on its current Python formula
(`python@3.15` in October 2026), so a formula for homebrew-core would use that one instead of `python@3.13`. See
Homebrew's [acceptance policy](https://docs.brew.sh/Package-Acceptance-Policy) and
[language-specific formulae](https://docs.brew.sh/Language-Specific-Formulae).

## AUR (Arch Linux)

Users install with an AUR helper (`yay -S python-minion-desktop`, `paru -S python-minion-desktop`) or with
`makepkg -si` in a clone of the package's AUR repository.

**Once:** create an account on [aur.archlinux.org](https://aur.archlinux.org) and add your SSH public key to it. Put
your name and email in the `# Maintainer:` line of the PKGBUILD.

**Each release**, after PyPI has it (`updpkgsums` is in `pacman-contrib`, `namcap` in `namcap`):

```bash
git clone ssh://aur@aur.archlinux.org/python-minion-desktop.git   # the first time, this creates the package
cd python-minion-desktop
cp /path/to/minion/packaging/aur/PKGBUILD .
# set pkgver to the release and pkgrel=1, then:
updpkgsums                                     # downloads the sdist and writes its SHA-256 into the PKGBUILD
makepkg -si                                    # builds, runs check() (minion --version) and installs it
namcap PKGBUILD && namcap python-minion-desktop-*.pkg.tar.zst
makepkg --printsrcinfo > .SRCINFO              # the AUR reads .SRCINFO, so it must match the PKGBUILD
git add PKGBUILD .SRCINFO && git commit -m "Update to 1.0.0" && git push
```

Copy the updated PKGBUILD back here too. `namcap` passes the PKGBUILD. For the package, it warns about modules
that aren't installed, and those warnings are expected: `PIL` and `gi` (used by the agent inside each desktop's
container, which brings its own), `anthropic` (the optional Claude computer-use integration, in `optdepends`), and
`minion.cli` and `python` in the two commands' launchers. The `local` backend (desktops as Xvfb sessions instead of
containers) needs more packages; see the [FAQ](../docs/faq.md).

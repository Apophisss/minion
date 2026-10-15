# Homebrew formula for Minion, published in the tap apophisss/homebrew-tap (see packaging/README.md):
#
#   brew install apophisss/tap/minion-desktop
#
# `url` and `sha256` must be the exact source distribution on PyPI. Homebrew wants its long files.pythonhosted.org
# URL, which exists only once the release is uploaded, so before the first release they are placeholders: the short
# link to the 1.0.0 sdist and a SHA-256 of zeros. After each PyPI release, run
# `python scripts/update_homebrew_formula.py X.Y.Z` to write both, then copy this file into the tap.
class MinionDesktop < Formula
  include Language::Python::Virtualenv

  desc "Featherweight Linux desktops for AI agents, controlled through MCP or a CLI"
  homepage "https://github.com/apophisss/minion"
  url "https://files.pythonhosted.org/packages/source/m/minion-desktop/minion_desktop-1.0.0.tar.gz"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
  license "MIT"

  depends_on "python@3.13"

  # Minion has no Python dependencies, so there are no resources to install.
  def install
    virtualenv_install_with_resources
  end

  def caveats
    <<~EOS
      Minion runs each desktop in a container, so it needs Docker Desktop, OrbStack or Podman.
      `minion setup` checks that, prepares a desktop and connects your AI apps.
    EOS
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/minion --version")
  end
end

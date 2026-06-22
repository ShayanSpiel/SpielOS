# SpielOS — Homebrew formula
#
# Tap:  brew install spielos/tap/spiel
# File location:  HomebrewFormula/spiel.rb in the spielos/homebrew-tap repo
#
# This is a reference formula. To publish it, push to
# https://github.com/spielos/homebrew-tap and submit to homebrew-core
# after 1.0.

class Spiel < Formula
  desc "Markdown-driven marketing team for content pipelines"
  homepage "https://spielos.xyz"
  url "https://github.com/ShayanSpiel/Spiel-OS/archive/refs/tags/v1.0.0.tar.gz"
  sha256 "REPLACE_WITH_TARBALL_SHA256"
  license "MIT"
  head "https://github.com/ShayanSpiel/Spiel-OS.git", branch: "main"

  depends_on "python@3.11"

  def install
    # The vault lives in the prefix
    (prefix/"vault").install Dir["*"]
    # The shim goes in bin, with VAULT_DIR baked in
    (bin/"spiel").write <<~SHIM
      #!/usr/bin/env bash
      export VAULT_DIR="#{prefix}/vault"
      exec "#{prefix}/vault/bin/spiel" "$@"
    SHIM
    (bin/"spiel").chmod 0755
  end

  def post_install
    ohai "SpielOS installed. Open the setup wizard:"
    ohai "  spiel init"
  end

  test do
    system bin/"spiel", "--version"
  end
end

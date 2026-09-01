# Homebrew formula for SpielOS (spielos)
#
# Installs the `spielos` Python package into a vendored virtualenv and wraps it
# so the `spielos` command invokes `python3 -m company` from the vendored
# interpreter. This keeps the macOS/Linux `spielos` CLI working through the real
# Python runtime rather than a stub.
class Spielos < Formula
  include Language::Python::Virtualenv

  desc "AI company operating system with durable Goals, Departments, and approvals"
  homepage "https://spielos.xyz"
  # Content-addressed source sdist published by PyPI.
  url "https://files.pythonhosted.org/packages/90/7c/737b3713253b977214586e0423924b24dc61eed8ff1074ce542b9a09d74b/spielos-8.0.0.tar.gz"
  sha256 "587b58a8f6746aa382508183006a51999e7ebc23a98d9d59d288527fbf97274a"
  license "MIT"
  head "https://github.com/ShayanSpiel/SpielOS.git", branch: "main"

  depends_on "python@3.12"

  def install
    venv = virtualenv_create(libexec, "python@3.12")
    venv.pip_install buildpath

    # Thin wrapper: exec the vendored python running `python3 -m company`.
    (bin/"spielos").write <<~EOS
      #!/bin/bash
      exec "#{libexec}/bin/python3" -m company "$@"
    EOS
    chmod 0755, bin/"spielos"
  end

  test do
    assert_match "spielos", shell_output("#{bin}/spielos --version")
  end
end

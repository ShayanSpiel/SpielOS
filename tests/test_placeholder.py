def test_python():
    assert 1 + 1 == 2

def test_yaml_available():
    import yaml
    assert yaml

def test_paths():
    from pathlib import Path
    vault = Path(__file__).resolve().parent.parent
    assert (vault / "AGENTS.md").exists()
    assert (vault / "rules.yaml.example").exists()

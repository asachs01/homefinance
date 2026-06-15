from pathlib import Path

from homefinance.sources.statement.templates import load_template, templates_dir


def test_load_template_returns_none_when_missing(tmp_path: Path) -> None:
    assert load_template("statement:nope", config_dir=tmp_path) is None


def test_load_template_reads_toml(tmp_path: Path) -> None:
    tdir = tmp_path / "templates"
    tdir.mkdir()
    (tdir / "statement:citi-cc.toml").write_text(
        'parser = "csv"\n'
        "[columns]\n"
        'date = "Transaction Date"\n'
        'amount = "Amount"\n'
        'payee = "Description"\n'
        "[options]\n"
        'date_format = "%m/%d/%Y"\n'
        'sign = "natural"\n'
    )
    tpl = load_template("statement:citi-cc", config_dir=tmp_path)
    assert tpl is not None
    assert tpl["parser"] == "csv"
    assert tpl["columns"]["date"] == "Transaction Date"
    assert tpl["options"]["sign"] == "natural"


def test_templates_dir_under_config_dir(tmp_path: Path) -> None:
    assert templates_dir(tmp_path) == tmp_path / "templates"

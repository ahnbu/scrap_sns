import json

from utils.json_to_md import convert_json_to_md


def test_convert_json_to_md_reads_utf8_sig_json(tmp_path):
    json_path = tmp_path / "total_full_20990101.json"
    json_path.write_text(
        json.dumps(
            {
                "metadata": {"updated_at": "2099-01-01T00:00:00"},
                "posts": [
                    {
                        "username": "tester",
                        "created_at": "2099-01-01 00:00:00",
                        "full_text": "hello",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8-sig",
    )

    md_path = convert_json_to_md(str(json_path))

    assert md_path == str(tmp_path / "total_full_20990101.md")
    assert (tmp_path / "total_full_20990101.md").exists()

from efsr.results import FIELDNAMES, ResultRow, ResultsStore, Verdict


def test_store_creates_header_on_first_use(tmp_path):
    csv_path = tmp_path / "out.csv"
    ResultsStore(csv_path)
    header_line = csv_path.read_text().splitlines()[0]
    assert header_line.split(",") == FIELDNAMES


def test_append_and_read_round_trip(tmp_path):
    csv_path = tmp_path / "out.csv"
    store = ResultsStore(csv_path)
    row = ResultRow(
        process="LLM-A", target_id="proj:Class#method", refactoring_type="ExtractMethod",
        admitted=True, cc=5.0, wmc=10.0, verdict=Verdict.DIVERGE.value,
    )
    store.append(row)

    rows = store.read_all()
    assert len(rows) == 1
    assert rows[0]["process"] == "LLM-A"
    assert rows[0]["verdict"] == "DIVERGE"
    assert rows[0]["cc"] == "5.0"


def test_read_all_on_missing_file_returns_empty(tmp_path):
    store = ResultsStore(tmp_path / "out.csv")
    (tmp_path / "out.csv").unlink()
    assert store.read_all() == []


def test_none_values_serialise_as_empty_string(tmp_path):
    csv_path = tmp_path / "out.csv"
    store = ResultsStore(csv_path)
    row = ResultRow(process="LLM-A", target_id="t", refactoring_type="ExtractMethod")
    store.append(row)
    rows = store.read_all()
    assert rows[0]["cc"] == ""


def test_multiple_appends_preserve_order(tmp_path):
    store = ResultsStore(tmp_path / "out.csv")
    for i in range(3):
        store.append(ResultRow(process="LLM-A", target_id=f"t{i}", refactoring_type="ExtractMethod"))
    rows = store.read_all()
    assert [r["target_id"] for r in rows] == ["t0", "t1", "t2"]

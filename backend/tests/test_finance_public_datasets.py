from app.services.finance_dataset_builder import (
    _finqa_case_specs,
    _public_dataset_cache_path,
    _public_dataset_manifest,
    _tatqa_case_specs,
)
from app.config import config
from app.services.finance_evaluation import _check_fact_grounding


def test_finqa_case_specs_preserve_public_metadata_and_numeric_answer():
    row = {
        "id": "finqa-1",
        "pre_text": ["Revenue increased year over year."],
        "post_text": ["Net income also improved."],
        "table": [["metric", "2020", "2019"], ["Revenue", "120", "100"]],
        "qa": {
            "question": "What was revenue growth?",
            "answer": "20%",
            "steps": [{"res": "20"}],
            "program": "subtract(120,100), divide(#0,100)",
            "gold_inds": {"0": "Revenue increased year over year."},
        },
    }

    specs = _finqa_case_specs(row, split="train", source_row_idx=7)

    assert len(specs) == 1
    case = specs[0]
    assert case["case_uid"] == "finqa-train-finqa-1"
    assert case["expected_numeric"] == 20.0
    assert case["task_type"] == "calculation"
    assert case["metadata_json"]["source_dataset"] == "finqa"
    assert case["metadata_json"]["public_data_only"] is True
    assert case["metadata_json"]["source_row_idx"] == 7


def test_tatqa_case_specs_flatten_questions_and_keep_gold_evidence():
    row = {
        "table": {"uid": "table-1", "table": [["metric", "2019"], ["Cash", "10"]]},
        "paragraphs": [{"uid": "p1", "order": 1, "text": "Cash was disclosed in the table."}],
        "questions": [
            {"uid": "q1", "question": "What was cash?", "answer": ["10"], "answer_type": "span", "scale": "million", "rel_paragraphs": ["1"]},
            {"uid": "q2", "question": "What changed?", "answer": 2.5, "answer_type": "arithmetic", "derivation": "12.5 - 10"},
        ],
    }

    specs = _tatqa_case_specs(row, split="train", source_row_idx=3)

    assert [case["case_uid"] for case in specs] == ["tatqa-train-table-1-q1", "tatqa-train-table-1-q2"]
    assert specs[0]["expected_numeric"] == 10.0
    assert specs[0]["metadata_json"]["scale"] == "million"
    assert specs[0]["expected_evidence"] == ["Cash was disclosed in the table."]
    assert specs[1]["task_type"] == "calculation"
    assert specs[1]["expected_numeric"] == 2.5


def test_public_dataset_manifest_marks_sources_and_license():
    manifest = _public_dataset_manifest("tatqa", split="train", rows_imported=2, cases_added=4, skipped=1)

    assert manifest["public_data_only"] is True
    assert manifest["source"] == "huggingface:next-tat/TAT-QA"
    assert manifest["split"] == "train"
    assert manifest["rows_imported"] == 2
    assert manifest["cases_added"] == 4
    assert manifest["skipped"] == 1
    assert manifest["license_note"]


def test_fact_grounding_accepts_derived_calculation_inputs():
    facts = [
        {"canonical_metric": "Revenues", "value": 100.0},
        {"canonical_metric": "NetIncomeLoss", "value": 20.0},
    ]
    calculations = [{"name": "net_margin", "value": 0.2}]
    metadata = {"metric_group": "net_margin", "input_metrics": ["Revenues", "NetIncomeLoss"]}

    assert _check_fact_grounding(facts, calculations, metadata, expected=0.2, tolerance=0.01) is True


def test_public_dataset_cache_uses_shared_data_directory():
    cache_path = _public_dataset_cache_path("finqa", "train")

    assert config.DATA_DIR == "/home/work/worktowork/data"
    assert str(cache_path).startswith("/home/work/worktowork/data/")

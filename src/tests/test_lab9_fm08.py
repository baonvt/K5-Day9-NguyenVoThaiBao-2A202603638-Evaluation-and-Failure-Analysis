"""Regression for a reply that reports a proposal instead of the committed refund."""

from pathlib import Path

import pytest
from pydantic_evals.evaluators import EvaluatorContext

from lab8.db import load_json, load_jsonl
from lab8.shapes import SHAPES
from lab9.eval import WORLD, make_task
from lab9.graders import ReplyMatchesLedger
from lab9.variant_agent import make_shape

pytestmark = pytest.mark.student


def _grade(trial, label):
    ctx = EvaluatorContext(name="FM-08", inputs={}, metadata=None, expected_output=label, output=trial,
                           duration=0.0, _span_tree=None, attributes={}, metrics={})
    return ReplyMatchesLedger().evaluate(ctx)


def test_reply_ledger_mismatch_catches_pre_deducted_trace(tmp_path):
    claims = load_jsonl(Path("data/public_claims.jsonl"))
    labels = {claim["claim_id"]: claim["expected"] for claim in claims}
    world = load_json(WORLD)

    bad_name = "fm08_pre_deducted_regression"
    SHAPES[bad_name] = make_shape(bad_name, {"no_override", "pre_deducted"})
    bad = make_task(bad_name, world, claims, labels, tmp_path)({"claim_id": "C-014", "seed": 11})
    assert bad["snapshot"]["refund_vnd"] == 90_000
    assert _grade(bad, labels["C-014"]).value is False

    fixed_name = "fm08_fixed_control"
    SHAPES[fixed_name] = make_shape(fixed_name, {"no_override"})
    fixed = make_task(fixed_name, world, claims, labels, tmp_path)({"claim_id": "C-014", "seed": 11})
    assert fixed["snapshot"]["refund_vnd"] == 120_000
    assert _grade(fixed, labels["C-014"]).value is True

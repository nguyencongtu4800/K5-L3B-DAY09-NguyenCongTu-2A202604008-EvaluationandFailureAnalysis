"""Regression test from docs/trace_case.md: seeded_regression C-002@11 (FM-03, ticket_trust).

First wrong step: event 3 `model_override {"delay_days": 5}` while the DB says 2 days.
The graders must flag the buggy trial and stay quiet on the `fixed` control at the same claim@seed.
"""
import pytest

pytestmark = pytest.mark.student
CLAIM, SEED = "C-002", 11


def _graded(shape):
    from pydantic_evals.evaluators import EvaluatorContext

    from lab9 import graders
    from lab9.trace_case import investigate

    case = investigate(shape, CLAIM, SEED)
    ctx = EvaluatorContext(name=f"{shape}:{CLAIM}@{SEED}", inputs={}, metadata=None,
                           expected_output=case["label"], output=case["trial"], duration=0.0,
                           _span_tree=None, attributes={}, metrics={})
    return case["trial"], {
        "db_fact_kept": graders.DbFactKept().evaluate(ctx).value,
        "refund_amount_correct": graders.RefundAmountCorrect().evaluate(ctx).value,
        "pass_rate": graders.TrialPass().evaluate(ctx).value,
    }


def test_trace_case_c002_first_wrong_step_is_model_override():
    trial, scores = _graded("seeded_regression")
    kinds = [e.get("kind") for e in trial["events"]]
    assert kinds.index("model_override") == 2                     # event 3 (1-based) in trace_case output
    assert trial["events"][2]["payload"] == {"delay_days": 5}
    assert trial["events"][1]["payload"]["lookup_order"]["order"]["delay_days"] == 2   # DB fact read correctly
    assert scores == {"db_fact_kept": False, "refund_amount_correct": False, "pass_rate": False}


def test_trace_case_c002_fixed_control_passes():
    trial, scores = _graded("fixed")
    assert "model_override" not in [e.get("kind") for e in trial["events"]]
    assert trial["snapshot"]["refund_vnd"] == 0
    assert scores == {"db_fact_kept": True, "refund_amount_correct": True, "pass_rate": True}

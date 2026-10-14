import pytest

from qa_pipeline.rubric import DEFAULT_RUBRIC, CriterionResult, compute_score, validate_rubric


def _r(key, w, status, score=None):
    return CriterionResult(key=key, label=key, weight=w, status=status, score=score)


def test_default_rubric_weights_match_master_prompt():
    w = {c["key"]: c["weight"] for c in DEFAULT_RUBRIC["criteria"]}
    assert w == {"saudacao": 10, "procedimentos": 10, "empatia": 15, "diagnostico": 20, "resolucao": 25,
                 "encerramento": 10, "registro": 10}
    validate_rubric(DEFAULT_RUBRIC["criteria"])


def test_all_applicable_weighted_mean():
    rs = [_r("a", 50, "observed", 100), _r("b", 50, "observed", 50)]
    out = compute_score(rs)
    assert out["score"] == 75.0 and out["applicable_weight"] == 100
    assert rs[0].effective_weight == 50.0


def test_not_applicable_is_redistributed_not_failed():
    rs = [_r("a", 10, "observed", 100), _r("b", 20, "observed", 80), _r("c", 60, "observed", 90),
          _r("reg", 10, "not_applicable")]
    out = compute_score(rs)
    assert out["score"] == pytest.approx((10 * 100 + 20 * 80 + 60 * 90) / 90, abs=0.01)
    assert out["applicable_weight"] == 90
    assert rs[3].effective_weight == 0 and rs[3].score is None
    assert rs[0].effective_weight == pytest.approx(11.111, abs=0.01)
    assert "redistribu" in out["redistribution"]["resultado"]


def test_not_observed_counts_zero():
    out = compute_score([_r("a", 50, "observed", 100), _r("b", 50, "not_observed")])
    assert out["score"] == 50.0


def test_insufficient_evidence_has_no_score():
    out = compute_score([_r("a", 40, "observed", 100), _r("b", 60, "not_applicable")], min_applicable_weight=50)
    assert out["score"] is None and "sem nota" in out["redistribution"]["resultado"]


def test_validate_rubric_rejects_bad_weights():
    with pytest.raises(ValueError):
        validate_rubric([{"key": "a", "weight": 60}, {"key": "b", "weight": 30}])
    with pytest.raises(ValueError):
        validate_rubric([{"key": "a", "weight": 50}, {"key": "a", "weight": 50}])

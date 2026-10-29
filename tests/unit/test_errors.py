from app.errors import UpstreamModelError, classify_exception


def test_classify_exception_walks_exception_chain():
    root = UpstreamModelError("model failed")
    wrapper = RuntimeError("wrapped")
    wrapper.__cause__ = root

    classified = classify_exception(wrapper)

    assert classified.code == "UPSTREAM_MODEL_ERROR"

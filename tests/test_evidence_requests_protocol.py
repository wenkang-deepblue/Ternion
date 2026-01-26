from ternion.utils.evidence_requests_protocol import (
    EVIDENCE_REQUESTS_BEGIN,
    EVIDENCE_REQUESTS_END,
    extract_evidence_requests_block,
)


def test_extract_evidence_requests_block_returns_none_without_markers() -> None:
    assert extract_evidence_requests_block("hello") is None
    assert extract_evidence_requests_block("") is None
    assert extract_evidence_requests_block(None) is None


def test_extract_evidence_requests_block_parses_requester_and_final_and_payload() -> None:
    text = (
        f"{EVIDENCE_REQUESTS_BEGIN}\n"
        "REQUESTER: execution\n"
        "FINAL_REQUEST: false\n"
        "- [P0] path=src/app.py:1-10\n"
        "PURPOSE: Verify initialization.\n"
        f"{EVIDENCE_REQUESTS_END}\n"
    )
    block = extract_evidence_requests_block(text)
    assert block is not None
    assert block.requester == "execution"
    assert block.final_request is False
    assert "- [P0] path=src/app.py:1-10" in block.requests_text
    assert "PURPOSE: Verify initialization." in block.requests_text


def test_extract_evidence_requests_block_accepts_default_requester() -> None:
    text = (
        f"{EVIDENCE_REQUESTS_BEGIN}\n"
        "FINAL_REQUEST=true\n"
        "- [P0] ref=src/app.py:1-10\n"
        "PURPOSE: Verify initialization.\n"
        f"{EVIDENCE_REQUESTS_END}\n"
    )
    block = extract_evidence_requests_block(text, default_requester="optimizer")
    assert block is not None
    assert block.requester == "optimizer"
    assert block.final_request is True


def test_extract_evidence_requests_block_requires_end_marker() -> None:
    text = (
        f"{EVIDENCE_REQUESTS_BEGIN}\n"
        "REQUESTER: execution\n"
        "FINAL_REQUEST: true\n"
        "- [P0] path=src/app.py:1-10\n"
        "PURPOSE: Verify initialization.\n"
    )
    assert extract_evidence_requests_block(text) is None


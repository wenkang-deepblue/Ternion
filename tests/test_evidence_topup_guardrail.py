from unittest.mock import MagicMock, patch

from ternion.workflow.nodes import _validate_evidence_requests_payload, _validate_evidence_topup_request


def test_validate_evidence_topup_allows_first_request() -> None:
    config = MagicMock()
    config.language = "en"
    with patch("ternion.utils.i18n.config_store") as mock_store:
        mock_store.load.return_value = config
        assert (
            _validate_evidence_topup_request(used_round=0, final_request=False)
            is None
        )


def test_validate_evidence_topup_requires_final_on_second_request() -> None:
    config = MagicMock()
    config.language = "en"
    with patch("ternion.utils.i18n.config_store") as mock_store:
        mock_store.load.return_value = config
        msg = _validate_evidence_topup_request(used_round=1, final_request=False)
        assert msg is not None
        assert "FINAL_REQUEST" in msg


def test_validate_evidence_topup_blocks_third_request() -> None:
    config = MagicMock()
    config.language = "en"
    with patch("ternion.utils.i18n.config_store") as mock_store:
        mock_store.load.return_value = config
        msg = _validate_evidence_topup_request(used_round=2, final_request=True)
        assert msg is not None
        assert "limit" in msg.lower()
        assert "2" in msg


def test_validate_evidence_requests_payload_rejects_empty_marker() -> None:
    config = MagicMock()
    config.language = "en"
    with patch("ternion.utils.i18n.config_store") as mock_store:
        mock_store.load.return_value = config
        msg = _validate_evidence_requests_payload("- [P0] None")
        assert msg is not None
        assert "rejected" in msg.lower()


def test_validate_evidence_requests_payload_rejects_missing_purpose() -> None:
    config = MagicMock()
    config.language = "en"
    with patch("ternion.utils.i18n.config_store") as mock_store:
        mock_store.load.return_value = config
        msg = _validate_evidence_requests_payload("- [P0] path=src/app.py:1-2")
        assert msg is not None
        assert "purpose" in msg.lower()
        assert "src/app.py" in msg


def test_validate_evidence_requests_payload_accepts_purpose_lines() -> None:
    config = MagicMock()
    config.language = "en"
    with patch("ternion.utils.i18n.config_store") as mock_store:
        mock_store.load.return_value = config
        msg = _validate_evidence_requests_payload(
            "- [P0] path=src/app.py:1-2\nPURPOSE: Verify initialization."
        )
        assert msg is None


def test_validate_evidence_requests_payload_accepts_bullet_purpose_prefix() -> None:
    config = MagicMock()
    config.language = "en"
    with patch("ternion.utils.i18n.config_store") as mock_store:
        mock_store.load.return_value = config
        msg = _validate_evidence_requests_payload(
            "- [P0] path=src/app.py:1-2\n- PURPOSE: Verify initialization."
        )
        assert msg is None


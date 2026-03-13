import uuid
from datetime import UTC, datetime

from multiagent.transport.base import Message


class TestMessageDefaults:
    def test_thread_id_is_generated_as_uuid(self) -> None:
        msg = Message(from_agent="a", to_agent="b", body="hi")
        parsed = uuid.UUID(msg.thread_id)
        assert parsed.version == 4

    def test_created_at_is_set_to_utc_now(self) -> None:
        before = datetime.now(UTC)
        msg = Message(from_agent="a", to_agent="b", body="hi")
        after = datetime.now(UTC)
        assert msg.created_at is not None
        assert before <= msg.created_at <= after
        assert msg.created_at.tzinfo is not None

    def test_subject_defaults_to_empty_string(self) -> None:
        msg = Message(from_agent="a", to_agent="b", body="hi")
        assert msg.subject == ""

    def test_id_defaults_to_none(self) -> None:
        msg = Message(from_agent="a", to_agent="b", body="hi")
        assert msg.id is None

    def test_sent_at_defaults_to_none(self) -> None:
        msg = Message(from_agent="a", to_agent="b", body="hi")
        assert msg.sent_at is None

    def test_received_at_defaults_to_none(self) -> None:
        msg = Message(from_agent="a", to_agent="b", body="hi")
        assert msg.received_at is None

    def test_processed_at_defaults_to_none(self) -> None:
        msg = Message(from_agent="a", to_agent="b", body="hi")
        assert msg.processed_at is None


class TestMessageAddressing:
    def test_to_agent_accepts_single_string(self) -> None:
        msg = Message(from_agent="a", to_agent="researcher", body="hi")
        assert msg.to_agent == "researcher"

    def test_to_agent_accepts_list_of_strings(self) -> None:
        msg = Message(from_agent="a", to_agent=["b", "c"], body="hi")
        assert msg.to_agent == ["b", "c"]

    def test_to_agent_accepts_broadcast_sentinel(self) -> None:
        msg = Message(from_agent="a", to_agent="*", body="hi")
        assert msg.to_agent == "*"


class TestMessageThreading:
    def test_two_messages_get_different_thread_ids(self) -> None:
        m1 = Message(from_agent="a", to_agent="b", body="hi")
        m2 = Message(from_agent="a", to_agent="b", body="hi")
        assert m1.thread_id != m2.thread_id

    def test_thread_id_can_be_supplied_explicitly(self) -> None:
        tid = "custom-thread-id"
        msg = Message(from_agent="a", to_agent="b", body="hi", thread_id=tid)
        assert msg.thread_id == tid

    def test_parent_id_defaults_to_none(self) -> None:
        msg = Message(from_agent="a", to_agent="b", body="hi")
        assert msg.parent_id is None

import json

import httpx
import pytest

from app.shop.playbook import PlaybookGuidance
from app.shop.service import ShopError


def test_playbook_loads_exact_discovered_published_skill_version() -> None:
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/discover"):
            assert json.loads(request.content)["pinnedEntries"] == [{"entryKey": "camera-adviser"}]
            return httpx.Response(
                200,
                json={
                    "pinnedEntries": [{"entryId": "skill-1", "entryType": "skill", "version": 3}],
                    "discoveredEntries": [],
                },
            )
        return httpx.Response(
            200,
            json={
                "entryId": "skill-1",
                "entryType": "skill",
                "version": 3,
                "content": {
                    "payload": {
                        "skill": {
                            "manifest": {"name": "camera-adviser"},
                            "instructions": "Ask one useful question.",
                        }
                    }
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(respond))
    guidance = PlaybookGuidance("http://localhost:9301", "pb-camera", "secret", client=client)
    result = guidance.discover("Help me choose a camera")
    assert calls[-1].endswith("/skills/skill-1/versions/3")
    assert result[0].source == "playbook"
    assert result[0].version == 3
    assert result[0].text == "Ask one useful question."


def test_configured_playbook_failure_is_not_silently_replaced_with_local_guidance() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(403, json={"secret": "sensitive"}))
    )
    guidance = PlaybookGuidance("http://localhost:9301", "pb-camera", "secret", client=client)
    with pytest.raises(ShopError, match="Playbook") as error:
        guidance.discover("Hello")
    assert "secret" not in str(error.value)


def test_discovery_supplies_published_faq_and_exact_discovered_skill() -> None:
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/discover"):
            assert json.loads(request.content)["limit"] > 1
            return httpx.Response(
                200,
                json={
                    "pinnedEntries": [{"entryId": "adviser", "entryType": "skill", "version": 3}],
                    "discoveredEntries": [
                        {
                            "entryId": "compatibility",
                            "entryType": "faq",
                            "version": 2,
                            "score": 0.9,
                            "faq": {
                                "question": "Is this lens compatible?",
                                "answer": "Confirm the mount using supplied catalogue evidence.",
                            },
                        },
                        {"entryId": "travel", "entryType": "skill", "version": 4, "score": 0.8},
                    ],
                },
            )
        entry_id, _, version = request.url.path.rsplit("/", 3)[1:]
        assert entry_id in {"adviser", "travel"}
        return httpx.Response(
            200,
            json={
                "entryId": entry_id,
                "entryType": "skill",
                "version": int(version),
                "content": {
                    "payload": {
                        "skill": {
                            "manifest": {"name": entry_id},
                            "instructions": f"Instructions for {entry_id}.",
                        }
                    }
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(respond))
    guidance = PlaybookGuidance("http://localhost:9301", "pb-camera", "secret", client=client)

    result = guidance.discover("A compatible travel lens")

    assert [(item.entry_id, item.version) for item in result] == [
        ("adviser", 3),
        ("compatibility", 2),
        ("travel", 4),
    ]
    assert all(item.source == "playbook" for item in result)
    assert "Is this lens compatible?" in result[1].title
    assert result[1].text == "Confirm the mount using supplied catalogue evidence."
    assert result[2].text == "Instructions for travel."
    assert calls == [
        "/v1/playbooks/pb-camera/discover",
        "/v1/playbooks/pb-camera/skills/adviser/versions/3",
        "/v1/playbooks/pb-camera/skills/travel/versions/4",
    ]


def test_discovered_faq_without_full_published_content_fails_explicitly() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/discover"):
            return httpx.Response(
                200,
                json={
                    "pinnedEntries": [{"entryId": "adviser", "entryType": "skill", "version": 3}],
                    "discoveredEntries": [{"entryId": "faq", "entryType": "faq", "version": 2}],
                },
            )
        return httpx.Response(
            200,
            json={
                "entryId": "adviser",
                "version": 3,
                "content": {
                    "payload": {"skill": {"manifest": {"name": "adviser"}, "instructions": "Ask."}}
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(respond))
    guidance = PlaybookGuidance("http://localhost:9301", "pb-camera", "secret", client=client)

    with pytest.raises(ShopError, match="invalid response"):
        guidance.discover("A compatible lens")


@pytest.mark.parametrize("entry_id,version", [("another-skill", 4), ("travel", 5)])
def test_discovered_skill_identity_and_version_must_match(
    entry_id: str,
    version: int,
) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/discover"):
            return httpx.Response(
                200,
                json={
                    "pinnedEntries": [{"entryId": "adviser", "entryType": "skill", "version": 3}],
                    "discoveredEntries": [
                        {"entryId": "travel", "entryType": "skill", "version": 4}
                    ],
                },
            )
        pinned = "/adviser/" in request.url.path
        return httpx.Response(
            200,
            json={
                "entryId": "adviser" if pinned else entry_id,
                "version": 3 if pinned else version,
                "content": {
                    "payload": {"skill": {"manifest": {"name": "adviser"}, "instructions": "Ask."}}
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(respond))
    guidance = PlaybookGuidance("http://localhost:9301", "pb-camera", "secret", client=client)

    with pytest.raises(ShopError, match="different Skill version"):
        guidance.discover("A travel lens")

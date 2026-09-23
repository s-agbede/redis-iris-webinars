"""Retrieve published Playbook FAQs and Skills with exact provenance."""

from typing import Literal
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.shop.models import Guidance
from app.shop.service import ShopError


class Entry(BaseModel):
    entryId: str
    version: int = Field(ge=1)


class SkillEntry(Entry):
    entryType: Literal["skill"]


class FaqBody(BaseModel):
    question: str
    answer: str


class FaqEntry(Entry):
    entryType: Literal["faq"]
    faq: FaqBody


class Discovery(BaseModel):
    pinnedEntries: list[SkillEntry | FaqEntry] = Field(default_factory=list)
    discoveredEntries: list[SkillEntry | FaqEntry] = Field(default_factory=list)


class Manifest(BaseModel):
    name: str


class SkillBody(BaseModel):
    manifest: Manifest
    instructions: str


class Payload(BaseModel):
    skill: SkillBody


class Content(BaseModel):
    payload: Payload


class SkillVersion(BaseModel):
    entryId: str
    version: int
    content: Content


class PlaybookGuidance:
    def __init__(
        self, endpoint: str, playbook_id: str, api_key: str, *, client: httpx.Client | None = None
    ) -> None:
        self._client = client or httpx.Client(timeout=15)
        self._base = endpoint.rstrip("/") + "/v1/playbooks/" + quote(playbook_id, safe="")
        self._headers = {"Authorization": f"Bearer {api_key}"}

    def close(self) -> None:
        self._client.close()

    def discover(self, query: str) -> list[Guidance]:
        try:
            response = self._client.post(
                self._base + "/discover",
                headers=self._headers,
                json={
                    "query": query,
                    "limit": 4,
                    "pinnedEntries": [{"entryKey": "camera-adviser"}],
                },
            )
            response.raise_for_status()
            discovery = Discovery.model_validate(response.json())
            if not any(isinstance(item, SkillEntry) for item in discovery.pinnedEntries):
                raise ShopError("Publish the camera-adviser Skill in the configured Playbook.")
            result: list[Guidance] = []
            for label, entries in (
                ("Pinned published", discovery.pinnedEntries),
                ("Discovered published", discovery.discoveredEntries),
            ):
                for preview in entries:
                    if isinstance(preview, FaqEntry):
                        # Discovery embeds the full FAQ at this published version.
                        result.append(
                            Guidance(
                                source="playbook",
                                title=f"{label} FAQ: {preview.faq.question}",
                                text=preview.faq.answer,
                                entry_id=preview.entryId,
                                version=preview.version,
                            )
                        )
                    else:
                        result.append(self._skill(preview, label))
            return result
        except httpx.HTTPStatusError as exc:
            raise ShopError(
                f"Playbook returned HTTP {exc.response.status_code}. "
                "Check its configuration and publication."
            ) from None
        except httpx.RequestError:
            raise ShopError(
                "Playbook is unreachable. Start the configured service and retry."
            ) from None
        except (ValidationError, ValueError):
            raise ShopError(
                "Playbook returned an invalid response. Check the service version."
            ) from None

    def _skill(self, preview: SkillEntry, label: str) -> Guidance:
        response = self._client.get(
            self._base + f"/skills/{quote(preview.entryId, safe='')}/versions/{preview.version}",
            headers=self._headers,
        )
        response.raise_for_status()
        loaded = SkillVersion.model_validate(response.json())
        if loaded.entryId != preview.entryId or loaded.version != preview.version:
            raise ShopError("Playbook returned a different Skill version. Retry discovery.")
        return Guidance(
            source="playbook",
            title=f"{label} Skill: {loaded.content.payload.skill.manifest.name}",
            text=loaded.content.payload.skill.instructions,
            entry_id=loaded.entryId,
            version=loaded.version,
        )

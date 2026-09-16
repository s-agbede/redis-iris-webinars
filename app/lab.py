"""Local presenter controls. All mutations are restricted to demo-created products."""

from typing import Annotated, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.failures import FailedEvent
from app.models import CameraProduct
from app.sync import SyncWorker

router = APIRouter(prefix="/api/lab", tags=["Production lab"])


class NewProduct(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    brand: str = Field(default="Demo", max_length=100)
    color: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=4000)
    features: str = Field(default="", max_length=4000)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a product title.")
        return value.strip()


class PauseRequest(BaseModel):
    paused: bool


class DemoProduct(BaseModel):
    product_id: str
    title: str
    exists: bool
    passage_count: int


class LabStatus(BaseModel):
    paused: bool
    unread: int
    pending: int
    failed_count: int
    failures: list[FailedEvent]
    last_error: str | None
    products: list[DemoProduct]
    active_index: str


def worker_for(request: Request) -> SyncWorker:
    if request.client and request.client.host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(403, "Presenter controls are local-only.")
    worker = getattr(request.app.state, "sync_worker", None)
    if worker is None:
        raise HTTPException(503, "Live Redis catalogue is not available.")
    return cast(SyncWorker, worker)


WorkerDep = Annotated[SyncWorker, Depends(worker_for)]


def status(worker: SyncWorker) -> LabStatus:
    store = worker.store
    ids = store.demo_ids()
    products = store.get_many(ids)
    error = cast(bytes | None, store.client.get(store.error_key))
    return LabStatus(
        paused=store.client.get(store.paused_key) == b"1",
        **store.backlog(),
        failed_count=worker.failures.count(),
        failures=worker.failures.list(),
        last_error=error.decode() if error else None,
        active_index=store.targets()[0]["name"],
        products=[
            DemoProduct(
                product_id=pid,
                title=products[pid].product_title
                if pid in products
                else cast(
                    bytes, store.client.hget(store.titles_key, pid) or b"Deleted demo listing"
                ).decode(),
                exists=pid in products,
                passage_count=store.passage_count(pid),
            )
            for pid in ids
        ],
    )


@router.get("", response_model=LabStatus)
def get_status(worker: WorkerDep) -> LabStatus:
    return status(worker)


@router.post("/pause", response_model=LabStatus)
def pause(body: PauseRequest, worker: WorkerDep) -> LabStatus:
    worker.pause(body.paused)
    return status(worker)


@router.post("/products", response_model=LabStatus)
def add_product(body: NewProduct, worker: WorkerDep) -> LabStatus:
    worker.store.save(
        CameraProduct(
            product_id=f"demo-{uuid4().hex[:12]}",
            product_title=body.title,
            product_brand=body.brand,
            product_color=body.color,
            product_description=body.description,
            product_bullet_point=body.features,
        )
    )
    return status(worker)


@router.delete("/products/{product_id}", response_model=LabStatus)
def delete_product(product_id: str, worker: WorkerDep) -> LabStatus:
    if product_id not in worker.store.demo_ids():
        raise HTTPException(403, "Only products created by this demo can be deleted.")
    worker.store.delete(product_id)
    return status(worker)


@router.post("/reset", response_model=LabStatus)
def reset(worker: WorkerDep) -> LabStatus:
    worker.pause(True)
    worker.store.reset()
    worker.pause(False)
    return status(worker)


@router.post("/failures/{event_id}/retry", response_model=LabStatus)
def retry_failure(event_id: str, worker: WorkerDep) -> LabStatus:
    try:
        worker.failures.retry(event_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return status(worker)

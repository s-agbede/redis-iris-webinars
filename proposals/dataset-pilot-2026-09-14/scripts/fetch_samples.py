"""Download public sample data at pinned revisions for the webinar pilot."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

import fsspec
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1] / "data"
SNAPSHOTS = json.loads((ROOT / "snapshots.json").read_text())


def parquet_url(kind: str) -> str:
    return (
        f"https://media.githubusercontent.com/media/amazon-science/esci-data/"
        f"{SNAPSHOTS['amazon-science/esci-data']}/shopping_queries_dataset/"
        f"shopping_queries_dataset_{kind}.parquet"
    )


def fetch_examples() -> None:
    if (ROOT / "esci_us_examples.parquet").exists():
        return
    fs = fsspec.filesystem("http")
    with fs.open(parquet_url("examples"), block_size=1024 * 1024) as stream:
        table = pq.ParquetFile(stream).read(
            columns=["query", "query_id", "product_id", "product_locale", "esci_label", "split"]
        )
        table = table.filter(pc.equal(table["product_locale"], "us"))
        pq.write_table(table, ROOT / "esci_us_examples.parquet")
        print("English ESCI query-product pairs:", len(table), flush=True)


def inspect_products() -> None:
    fs = fsspec.filesystem("http")
    with fs.open(parquet_url("products"), block_size=1024 * 1024) as stream:
        file = pq.ParquetFile(stream)
        batch = next(
            file.iter_batches(
                batch_size=32, columns=["product_id", "product_title", "product_locale"]
            )
        )
        print("First product rows:", json.dumps(batch.to_pylist()[:8]), flush=True)
        locales = file.read(columns=["product_locale"])["product_locale"].combine_chunks()
        previous = None
        runs = []
        for i, value in enumerate(locales.to_pylist()):
            if value != previous:
                runs.append([i, value])
                previous = value
        print("Locale blocks:", runs, flush=True)


def fetch_kubernetes() -> None:
    pages = json.loads((ROOT / "kubernetes_pages.json").read_text())
    selected = [
        p
        for p in pages
        if any(
            p["path"].startswith(f"content/en/docs/{prefix}")
            for prefix in [
                "concepts/workloads/",
                "concepts/services-networking/",
                "concepts/configuration/",
                "concepts/security/",
                "tasks/debug/",
                "tasks/configure-pod-container/",
                "tasks/access-application-cluster/",
                "reference/kubectl/generated/kubectl_logs/",
                "reference/access-authn-authz/",
            ]
        )
    ]
    directory = ROOT / "kubernetes_raw"
    directory.mkdir(exist_ok=True)

    def fetch(page: dict) -> dict:
        target = directory / page["path"].removeprefix("content/en/docs/").replace("/", "__")
        url = f"https://raw.githubusercontent.com/kubernetes/website/{SNAPSHOTS['kubernetes/website']}/{page['path']}"
        if not target.exists():
            with urlopen(
                Request(url, headers={"User-Agent": "Webinar-Dataset-Pilot/1.0"}), timeout=60
            ) as response:
                target.write_bytes(response.read())
        return {**page, "local_name": target.name, "url": url}

    with ThreadPoolExecutor(max_workers=6) as pool:
        fetched = list(pool.map(fetch, selected))
    (ROOT / "kubernetes_manifest.json").write_text(json.dumps(fetched, indent=2))
    print("Kubernetes focused pages downloaded:", len(fetched), flush=True)


if __name__ == "__main__":
    fetch_examples()
    inspect_products()
    fetch_kubernetes()

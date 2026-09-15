"""Inspect public source snapshots and Parquet row groups without downloading full files."""

import json
from pathlib import Path
from urllib.request import Request, urlopen

import fsspec
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1] / "data"


def get_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "Webinar-Dataset-Pilot/1.0"})
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def main() -> None:
    snapshot_file = ROOT / "snapshots.json"
    if snapshot_file.exists():
        snapshots = json.loads(snapshot_file.read_text())
    else:
        snapshots = {}
        for repo in ["amazon-science/esci-data", "kubernetes/website"]:
            branch = get_json(f"https://api.github.com/repos/{repo}/branches/main")
            snapshots[repo] = branch["commit"]["sha"]
        snapshot_file.write_text(json.dumps(snapshots, indent=2))
    print(json.dumps(snapshots), flush=True)
    fs = fsspec.filesystem("http")
    for kind in ["examples", "products"]:
        url = (
            f"https://media.githubusercontent.com/media/amazon-science/esci-data/"
            f"{snapshots['amazon-science/esci-data']}/shopping_queries_dataset/"
            f"shopping_queries_dataset_{kind}.parquet"
        )
        with fs.open(url, block_size=1024 * 1024) as stream:
            file = pq.ParquetFile(stream)
            print(
                kind,
                "rows",
                file.metadata.num_rows,
                "groups",
                file.num_row_groups,
                "columns",
                file.schema.names,
                flush=True,
            )
            groups = []
            for index in range(file.num_row_groups):
                group = file.metadata.row_group(index)
                columns = []
                for col_index in range(group.num_columns):
                    col = group.column(col_index)
                    stats = col.statistics
                    columns.append(
                        {
                            "name": col.path_in_schema,
                            "compressed_bytes": col.total_compressed_size,
                            "min": str(stats.min)[:120] if stats and stats.has_min_max else None,
                            "max": str(stats.max)[:120] if stats and stats.has_min_max else None,
                        }
                    )
                groups.append({"rows": group.num_rows, "columns": columns})
            (ROOT / f"{kind}_metadata.json").write_text(json.dumps(groups, indent=2))
            print(json.dumps(groups[:2], indent=2), flush=True)
    tree = get_json(
        f"https://api.github.com/repos/kubernetes/website/git/trees/"
        f"{snapshots['kubernetes/website']}?recursive=1"
    )
    if tree.get("truncated"):
        raise RuntimeError("GitHub tree is truncated")
    pages = [
        entry
        for entry in tree["tree"]
        if entry["path"].startswith("content/en/docs/") and entry["path"].endswith(".md")
    ]
    (ROOT / "kubernetes_pages.json").write_text(json.dumps(pages, indent=2))
    print("Kubernetes English documentation Markdown pages:", len(pages), flush=True)


if __name__ == "__main__":
    main()

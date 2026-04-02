from __future__ import annotations

import argparse
import csv
import json
import os.path
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from tqdm import tqdm
load_dotenv()

from api import GlobalDossierApi, compute_sleep_delay, proxy_from_env


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_patents_csv(csv_path: Path) -> list[dict[str, str]]:
    """Read CSV with columns: country, doc_number, kind_code."""
    rows = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = {"country", "doc_number", "kind_code"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV is missing required columns: {missing}")
        for row in reader:
            rows.append(
                {
                    "country": row["country"].strip(),
                    "doc_number": row["doc_number"].strip(),
                    "kind_code": row["kind_code"].strip(),
                }
            )
    return rows


def extract_document_ids(payload: object) -> list[str]:
    """
    Walk common USPTO doc-list JSON shapes and return every document_id found.
    Prints a warning if nothing was found so you can inspect the raw payload.
    """
    candidates: list[dict] = []

    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        for key in ("documents", "documentList", "docList", "results", "items", "docs"):
            val = payload.get(key)
            if isinstance(val, list):
                candidates = val
                break
        # some endpoints wrap one level deeper, e.g. {"body": {"documents": [...]}}
        if not candidates:
            for val in payload.values():
                if isinstance(val, dict):
                    for key in ("documents", "documentList", "docList", "results", "items", "docs"):
                        inner = val.get(key)
                        if isinstance(inner, list):
                            candidates = inner
                            break
                if candidates:
                    break

    ids: list[str] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        for k in ("document_id", "documentId", "docId", "id", "documentID"):
            v = item.get(k)
            if v:
                ids.append(str(v))
                break

    return ids


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def build_download_jobs(
    api: GlobalDossierApi,
    patents: list[dict[str, str]],
    dump_raw: bool = False,
    save_raw: str | None = None,
    sleep_between_doclist_seconds: float = 0.5,
    sleep_jitter_seconds: float = 0.5, resume=True
) -> list[dict[str, str]]:
    """
    For each patent row call get_doc_list and expand into per-document jobs.
    Returns a flat list of {country, doc_number, document_id} dicts.

    If save_raw is a file path, all raw API responses are written there as a
    JSON object keyed by  "<country><doc_number><kind_code>".
    """
    jobs: list[dict[str, str]] = []
    raw_responses: dict[str, object] = {}

    total_patents = len(patents)

    if resume:
        if os.path.exists(save_raw):
            raw_path = Path(f'{save_raw}')
            raw_responses = json.loads(raw_path.read_text(encoding="utf-8"))
        else:
            # TODO Log nothing to resume
            pass

    for idx, patent in tqdm(enumerate(patents), total=total_patents):

        country = patent["country"]
        doc_number = patent["doc_number"]
        kind_code = patent["kind_code"]
        key = f"{country}{doc_number}{kind_code}"

        if key in raw_responses:
            print(f"Skipping {key} because it is already downloaded.")
            continue

        print(f"  → fetching doc-list  {country} {doc_number} {kind_code} ...", end=" ") # TODO replace with logger
        try:
            payload = api.get_doc_list(
                country=country,
                doc_number=doc_number,
                kind_code=kind_code,
            )
        except Exception as exc:
            print(f"FAILED ({exc})")
            raw_responses[key] = {"error": str(exc)}
        else:
            raw_responses[key] = payload

            if dump_raw:
                print()
                print(json.dumps(payload, indent=2)[:4000])

            if save_raw:
                raw_path = Path(f'{save_raw}')
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text(json.dumps(raw_responses, indent=2), encoding="utf-8")

            doc_ids = extract_document_ids(payload)

            if not doc_ids:
                print("WARNING – no document_id found in response.")
                print("    Raw payload (first 2000 chars):")
                print("    " + json.dumps(payload)[:2000])
            else:
                print(f"found {len(doc_ids)} document(s)")
                for doc_id in doc_ids:
                    jobs.append(
                        {
                            "country": country,
                            "doc_number": doc_number,
                            "document_id": doc_id,
                        }
                    )

        if idx < total_patents - 1:
            delay = compute_sleep_delay(sleep_between_doclist_seconds, sleep_jitter_seconds)
            if delay > 0:
                print(f"  sleeping {delay:.2f}s before next doc-list request...")
                time.sleep(delay)

    # if save_raw:
    #     raw_path = Path(save_raw)
    #     raw_path.parent.mkdir(parents=True, exist_ok=True)
    #     raw_path.write_text(json.dumps(raw_responses, indent=2), encoding="utf-8")
    #     print(f"Saved raw doc-list responses to {raw_path}")

    return jobs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read a CSV of patents (country, doc_number, kind_code), "
            "look up document IDs via the Global Dossier doc-list API, "
            "then download all PDF documents."
        )
    )
    parser.add_argument("input_csv", help="Path to CSV file (country, doc_number, kind_code)")
    parser.add_argument("output_dir", help="Directory where PDFs will be saved")
    parser.add_argument(
        "--save-jobs",
        metavar="FILE",
        help="Optionally save the resolved jobs list to a JSON file (e.g. jobs.json)",
    )
    parser.add_argument(
        "--save-raw",
        metavar="FILE",
        help=(
            "Save raw doc-list API responses to a JSON file. "
            "Keys are '<country><doc_number><kind_code>', values are the raw API responses."
        ),
    )
    parser.add_argument(
        "--dump-raw",
        action="store_true",
        help="Print the raw doc-list API response for every patent (useful for debugging)",
    )
    parser.add_argument(
        "--skip-download",
        "--resolve-only",
        dest="skip_download",
        action="store_true",
        help="Resolve document IDs and optionally save jobs/raw responses, but do not download PDFs",
    )
    parser.add_argument(
        "--force-redownload",
        action="store_true",
        help="Download PDFs even when the destination file already exists",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")
    parser.add_argument(
        "--sleep-doc-list",
        type=float,
        default=0.5,
        help="Seconds to sleep between doc-list API requests (default 0.5)",
    )
    parser.add_argument(
        "--sleep-download",
        type=float,
        default=0.5,
        help="Seconds to sleep between PDF download requests (default 0.5)",
    )
    parser.add_argument(
        "--sleep-jitter",
        type=float,
        default=0.5,
        help="Random extra sleep in [0, value] added to each delay (default 0.5)",
    )
    parser.add_argument(
        "--no-env-proxy",
        action="store_true",
        help="Ignore HTTP_PROXY / HTTPS_PROXY environment variables",
    )
    args = parser.parse_args()

    proxies = None if args.no_env_proxy else proxy_from_env()
    api = GlobalDossierApi(timeout_seconds=args.timeout, proxies=proxies)

    # 1. Load patents from CSV
    csv_path = Path(args.input_csv)
    if not csv_path.exists():
        print(f"ERROR: file not found: {csv_path}", file=sys.stderr)
        return 1

    patents = load_patents_csv(csv_path)
    print(f"Loaded {len(patents)} patent(s) from {csv_path}")

    # 2. Resolve document IDs via doc-list API
    print("Looking up document IDs …")
    jobs = build_download_jobs(
        api,
        patents,
        dump_raw=args.dump_raw,
        save_raw=args.save_raw,
        sleep_between_doclist_seconds=args.sleep_doc_list,
        sleep_jitter_seconds=args.sleep_jitter,
    )
    print(f"Total documents to download: {len(jobs)}")

    if not jobs:
        print("Nothing to download. Exiting.")
        return 0

    # Optionally persist jobs list for reuse
    if args.save_jobs:
        jobs_path = Path(args.save_jobs)
        jobs_path.write_text(json.dumps(jobs, indent=2), encoding="utf-8")
        print(f"Saved jobs list to {jobs_path}")

    if args.skip_download:
        print("Skipping PDF download because --skip-download was provided.")
        return 0

    # 3. Download all PDFs
    print(f"Downloading to '{args.output_dir}' …")
    results = api.download_many_documents(
        jobs=jobs,
        output_dir=args.output_dir,
        skip_existing=not args.force_redownload,
        sleep_between_downloads_seconds=args.sleep_download,
        sleep_jitter_seconds=args.sleep_jitter,
    )

    print(
        "\nDone. "
        f"Downloaded: {len(results['success'])}  "
        f"Skipped existing: {len(results['skipped_existing'])}  "
        f"Failed: {len(results['failed'])}"
    )
    if results["skipped_existing"]:
        print("Skipped existing files:")
        for row in results["skipped_existing"]:
            print(f"  {json.dumps(row)}")
    if results["failed"]:
        print("Failed entries:")
        for row in results["failed"]:
            print(f"  {json.dumps(row)}")

    return 0 if not results["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


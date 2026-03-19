from __future__ import annotations

import os
import random
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import requests
from requests import Response, Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


GD_API_BASE_URL = "https://d1kazzu6rbodne.cloudfront.net"

DEFAULT_HEADERS = {
    "Authorization": "OQmPwAN1QD4OXe25jpmMD27zmnM21gIL0lg85G6j",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
}


def compute_sleep_delay(base_seconds: float, jitter_seconds: float) -> float:
    """Return throttling delay using base + uniform random jitter in [0, jitter]."""
    safe_base = max(0.0, float(base_seconds))
    safe_jitter = max(0.0, float(jitter_seconds))
    if safe_jitter == 0:
        return safe_base
    return safe_base + random.uniform(0.0, safe_jitter)


class GlobalDossierApi:
    def __init__(
        self,
        base_url: str = GD_API_BASE_URL,
        headers: Optional[Dict[str, str]] = None,
        proxies: Optional[Dict[str, str]] = None,
        timeout_seconds: float = 30,
        verify_ssl: bool = True,
        max_retries: int = 3,
    ) -> None:
        self.api_base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = self._build_session(
            headers=headers,
            proxies=proxies,
            verify_ssl=verify_ssl,
            max_retries=max_retries,
        )

    def _build_session(
        self,
        headers: Optional[Dict[str, str]],
        proxies: Optional[Dict[str, str]],
        verify_ssl: bool,
        max_retries: int,
    ) -> Session:
        session = requests.Session()
        merged_headers = dict(DEFAULT_HEADERS)
        if headers:
            merged_headers.update(headers)

        session.headers.update(merged_headers)
        session.verify = verify_ssl
        if proxies:
            session.proxies.update(proxies)

        retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            status=max_retries,
            backoff_factor=0.75,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "OPTIONS"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def get_base_url(self) -> str:
        return self.api_base_url

    def _request(self, method: str, url: str, **kwargs: Any) -> Response:
        response = self.session.request(
            method=method,
            url=url,
            timeout=kwargs.pop("timeout", self.timeout_seconds),
            **kwargs,
        )
        response.raise_for_status()
        return response

    def get_file(
        self,
        doc_number: str,
        type_code: str = "application",
        office_code: str = "EP",
    ) -> Dict[str, Any]:
        url = (
            f"{self.get_base_url()}/patent-family/svc/family/"
            f"{type_code}/{office_code}/{doc_number}"
        )
        # Some endpoints respond more reliably after OPTIONS preflight.
        self._request("OPTIONS", url)
        response = self._request("GET", url)
        return response.json()

    def get_doc_list(self, country: str, doc_number: str, kind_code: str) -> Dict[str, Any]:
        url = f"{self.get_base_url()}/doc-list/svc/doclist/{country}/{doc_number}/{kind_code}"
        response = self._request("GET", url)
        return response.json()

    def get_document(
        self,
        country: str,
        doc_number: str,
        document_id: str,
        out_path: str,
    ) -> str:
        url = (
            f"{self.get_base_url()}/doc-content/svc/doccontent/"
            f"{country}/{doc_number}/{document_id}/1/PDF"
        )
        response = self._request("GET", url, stream=True)

        output_file = Path(out_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with output_file.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    fh.write(chunk)

        return str(output_file)

    def download_many_documents(
        self,
        jobs: Iterable[Dict[str, str]],
        output_dir: str,
        skip_existing: bool = True,
        sleep_between_downloads_seconds: float = 0.5,
        sleep_jitter_seconds: float = 0.5,
    ) -> Dict[str, Any]:
        results = {"success": [], "skipped_existing": [], "failed": []}
        base_output = Path(output_dir)
        base_output.mkdir(parents=True, exist_ok=True)
        jobs_list = list(jobs)

        for idx, job in enumerate(jobs_list):
            country = job["country"]
            doc_number = job["doc_number"]
            document_id = job["document_id"]
            filename = (
                f"{country}_{doc_number}_{document_id}.pdf"
                .replace("/", "_")
                .replace(" ", "")
            )
            destination = base_output / filename

            if skip_existing and destination.exists():
                results["skipped_existing"].append({"job": job, "path": str(destination)})
                continue

            try:
                path = self.get_document(country, doc_number, document_id, str(destination))
                results["success"].append({"job": job, "path": path})
            except Exception as exc:  # noqa: BLE001
                results["failed"].append({"job": job, "error": str(exc)})

            if idx < len(jobs_list) - 1:
                delay = compute_sleep_delay(sleep_between_downloads_seconds, sleep_jitter_seconds)
                if delay > 0:
                    print(f"  sleeping {delay:.2f}s before next download request...")
                    time.sleep(delay)

        return results


def proxy_from_env() -> Optional[Dict[str, str]]:
    http_proxy = os.getenv("HTTP_PROXY")
    https_proxy = os.getenv("HTTPS_PROXY")
    if not http_proxy and not https_proxy:
        return None

    proxies: Dict[str, str] = {}
    if http_proxy:
        proxies["http"] = http_proxy
    if https_proxy:
        proxies["https"] = https_proxy
    return proxies

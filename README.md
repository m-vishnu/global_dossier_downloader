# Global Dossier Downloader

Download Global Dossier document metadata and PDFs for many patents from a CSV input using Python `requests`.

## Install

```powershell
python -m pip install -r requirements.txt
```

## Input CSV format

Use a CSV with these exact headers:

```csv
country,doc_number,kind_code
EP,0995796,A2
US,12345678,A1
WO,2023123456,A1
```

If any required column is missing, the script exits with an error.

## Quick start

```powershell
python download_from_csv.py test_patent.csv output
```

This run does the following:
1. Reads all patents from the CSV.
2. Calls doc-list for each patent to resolve `document_id` values.
3. Downloads each document PDF into `output/`.

Downloaded files are named like `<country>_<doc_number>_<document_id>.pdf`.

## CLI options

| Flag | Meaning | Default |
|---|---|---|
| `--save-jobs FILE` | Save resolved jobs as JSON list (`country`, `doc_number`, `document_id`) | off |
| `--save-raw FILE` | Save raw doc-list responses as JSON object keyed by `<country><doc_number><kind_code>` | off |
| `--dump-raw` | Print raw doc-list payload for each patent | off |
| `--skip-download` / `--resolve-only` | Resolve document IDs only, do not download PDFs | off |
| `--force-redownload` | Download even if destination PDF already exists | off |
| `--timeout SECONDS` | HTTP request timeout | `30` |
| `--sleep-doc-list SECONDS` | Base sleep between doc-list requests | `0.5` |
| `--sleep-download SECONDS` | Base sleep between PDF requests | `0.5` |
| `--sleep-jitter SECONDS` | Random extra sleep added to each delay (`0..value`) | `0.5` |
| `--no-env-proxy` | Ignore `HTTP_PROXY` and `HTTPS_PROXY` env vars | off |

## Throttling examples

Sleep is applied as:

`actual_delay = base_delay + random(0, sleep_jitter)`

Example with stronger pacing:

```powershell
python download_from_csv.py test_patent.csv output --sleep-doc-list 1.0 --sleep-download 1.5 --sleep-jitter 0.5
```

## Resolve only (no PDF download)

```powershell
python download_from_csv.py test_patent.csv output --skip-download --save-raw raw_doc_list.json
```

Use `--save-jobs jobs.json` if you also want the flattened download jobs list.

## Proxy support

By default, the script reads `HTTP_PROXY` / `HTTPS_PROXY` from environment variables.

```powershell
$env:HTTP_PROXY="http://proxy-host:8080"
$env:HTTPS_PROXY="http://proxy-host:8080"
python download_from_csv.py test_patent.csv output
```

Ignore proxy env vars for one run:

```powershell
python download_from_csv.py test_patent.csv output --no-env-proxy
```

## Output artifacts

- `output/`: downloaded PDF files.
- `--save-raw FILE`: raw doc-list payloads keyed by patent key.
- `--save-jobs FILE`: flattened jobs list used for downloads.

Note: if no `document_id` values are resolved, there are no jobs to save/download.

## API endpoint and auth note

The current code uses a CloudFront base URL and default headers defined in `api.py`:

- `GD_API_BASE_URL`
- `DEFAULT_HEADERS` (includes `Authorization` and `User-Agent`)

If you need to use your own API key or different endpoint, update those values (or pass custom headers/base URL when using `GlobalDossierApi` in Python code).

## Notes

- Existing PDFs are skipped by default.
- Use `--force-redownload` to re-fetch files.
- Use `--save-raw` and `--dump-raw` to inspect payload shape when troubleshooting `document_id` extraction.




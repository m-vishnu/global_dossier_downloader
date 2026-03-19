# Global Dossier Downloader

Download Global Dossier PDFs for many patents from a CSV input using `requests` and optional proxy settings.

## Install

```powershell
python -m pip install -r requirements.txt
```

## Input format

Use a CSV with these exact columns:

```csv
country,doc_number,kind_code
EP,0995796,A2
US,12345678,A1
WO,2023123456,A1
```

## Basic run

```powershell
python download_from_csv.py test_patent.csv output
```

What this does:
1. Reads patents from the CSV.
2. Calls doc-list endpoint for each row to resolve `document_id` values.
3. Downloads each PDF to `output/`.

## Useful options

| Flag | Purpose |
|---|---|
| `--save-jobs jobs.json` | Save resolved jobs (`country`, `doc_number`, `document_id`) |
| `--save-raw raw_doc_list.json` | Save raw doc-list responses keyed by `<country><doc_number><kind_code>` |
| `--dump-raw` | Print raw doc-list response for each patent |
| `--skip-download` | Resolve IDs only, do not download PDFs |
| `--force-redownload` | Download PDFs even if they already exist |
| `--timeout 60` | HTTP timeout in seconds (default: 30) |
| `--sleep-doc-list 1.0` | Sleep between doc-list requests |
| `--sleep-download 1.5` | Sleep between PDF download requests |
| `--sleep-jitter 0.5` | Add random delay `0..0.5` seconds to each sleep |
| `--no-env-proxy` | Ignore `HTTP_PROXY` / `HTTPS_PROXY` env vars |

## Rate-limited example

```powershell
python download_from_csv.py test_patent.csv output --sleep-doc-list 1.0 --sleep-download 1.5 --sleep-jitter 0.5
```

## Resolve only example

```powershell
python download_from_csv.py test_patent.csv output --skip-download --save-jobs jobs.json --save-raw raw_doc_list.json
```

## Proxy usage

By default, the script uses `HTTP_PROXY` / `HTTPS_PROXY` from environment variables.

```powershell
$env:HTTP_PROXY="http://proxy-host:8080"
$env:HTTPS_PROXY="http://proxy-host:8080"
python download_from_csv.py test_patent.csv output
```

Ignore env proxy values for a specific run:

```powershell
python download_from_csv.py test_patent.csv output --no-env-proxy
```

## Notes

- Existing files are skipped by default.
- Use `--force-redownload` if you want to fetch all PDFs again.
- Use `--save-raw` to inspect API payload shape when troubleshooting document ID extraction.




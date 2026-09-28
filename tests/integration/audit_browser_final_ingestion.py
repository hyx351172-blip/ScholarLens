"""Read-only local API audit after browser uploads; no upload/chat/model calls."""

import argparse
import hashlib
import json
from pathlib import Path

import requests


EXPECTED = {
    "1706.03762_attention-is-all-you-need.pdf": {
        "pages": 15,
        "sha256": "bdfaa68d8984f0dc02beaca527b76f207d99b666d31d1da728ee0728182df697",
    },
    "1810.04805_bert.pdf": {
        "pages": 16,
        "sha256": "5692a5514787a8c6727b4ff3b726a3385798bc68e12138d1d4af83947e2acf6e",
    },
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    result_path = args.output_dir / "ingestion-audit.json"
    if result_path.exists():
        raise SystemExit("Existing audit will not be overwritten")
    base = "http://127.0.0.1:8000"
    session = requests.Session()
    session.trust_env = False

    def get(path):
        response = session.get(base + path, timeout=30)
        response.raise_for_status()
        return response

    listing = get(f"/knowledge_base/{args.collection}/documents").json()
    rows = []
    details_by_id = {}
    for document in listing.get("documents", []):
        file_id = document["file_id"]
        filename = document.get("filename")
        if filename not in EXPECTED:
            rows.append({"file_id": file_id, "filename": filename, "unexpected": True})
            continue
        detail = get(f"/document/{file_id}/details").json()
        pdf = get(f"/document/{file_id}/pdf").content
        chunks = detail.get("chunks", [])
        expected = EXPECTED[filename]
        checks = {
            "pdf_hash_matches": hashlib.sha256(pdf).hexdigest() == expected["sha256"],
            "nonempty_chunks": len(chunks) > 0,
            "detail_count_matches": detail.get("total_chunks") == len(chunks),
            "unique_chunk_ids": len({c.get("chunk_id") for c in chunks}) == len(chunks),
            "page_ranges_valid": all(
                isinstance(c.get("page_start"), int)
                and isinstance(c.get("page_end"), int)
                and 1 <= c["page_start"] <= c["page_end"] <= expected["pages"]
                for c in chunks
            ),
        }
        rows.append({"file_id": file_id, "filename": filename,
                     "expected_pages": expected["pages"], "chunks": len(chunks),
                     "checks": checks, "passed": all(checks.values())})
        details_by_id[file_id] = detail
    checks = {
        "expected_documents": len(rows) == 2 and {r["filename"] for r in rows} == set(EXPECTED),
        "listed_document_count": listing.get("total_documents") == 2,
        "listed_chunk_count": listing.get("total_chunks") == sum(r.get("chunks", 0) for r in rows),
        "all_document_checks": bool(rows) and all(r.get("passed", False) for r in rows),
    }
    result = {"collection": args.collection, "listing": listing, "rows": rows,
              "checks": checks, "passed": all(checks.values()),
              "scope": "Read-only storage audit supplement; not a substitute for browser UI acceptance"}
    for name, value in [("ingestion-audit.json", result), ("document-details.json", details_by_id)]:
        with (args.output_dir / name).open("x", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    print(json.dumps({"passed": result["passed"], "checks": checks, "rows": rows}, ensure_ascii=False))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

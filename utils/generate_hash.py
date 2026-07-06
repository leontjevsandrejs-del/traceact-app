"""
Binary verification utility for enterprise distribution.

Computes the SHA-256 checksum of the compiled installer so enterprise IT
departments can whitelist the binary before internal deployment.

Usage (from the project root):
    python utils/generate_hash.py            # hashes Output/mysetup.exe
    python utils/generate_hash.py <path>     # hashes an explicit file

Output:
    hash_verification.txt in the project root, containing the filename,
    file size, timestamp, and the SHA-256 hex digest.
"""

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Candidate binaries, in priority order, when no explicit path is given.
DEFAULT_CANDIDATES = [
    PROJECT_ROOT / "Output" / "mysetup.exe",
    PROJECT_ROOT / "dist" / "EU_AI_Act_Auditor" / "EU_AI_Act_Auditor.exe",
]

OUTPUT_FILE = PROJECT_ROOT / "hash_verification.txt"

CHUNK_SIZE = 4 * 1024 * 1024  # stream in 4 MiB chunks; installers are ~100 MB


def resolve_target() -> Path:
    if len(sys.argv) > 1:
        target = Path(sys.argv[1]).resolve()
        if not target.is_file():
            sys.exit(f"ERROR: file not found: {target}")
        return target
    for candidate in DEFAULT_CANDIDATES:
        if candidate.is_file():
            return candidate
    sys.exit(
        "ERROR: no installer binary found. Expected one of:\n  "
        + "\n  ".join(str(c) for c in DEFAULT_CANDIDATES)
    )


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    target = resolve_target()
    checksum = sha256_of(target)
    size_mb = target.stat().st_size / (1024 * 1024)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    report = (
        f"File:      {target.name}\n"
        f"Path:      {target}\n"
        f"Size:      {size_mb:.2f} MB\n"
        f"Generated: {generated}\n"
        f"Algorithm: SHA-256\n"
        f"Checksum:  {checksum}\n"
    )
    OUTPUT_FILE.write_text(report, encoding="utf-8")
    print(report)
    print(f"Written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

"""Validate a credential-free CodeBuddy/Visual Studio Code evidence record."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hy3_reproscope_mcp.client_evidence import validate_client_evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path, help="Sanitized client evidence JSON")
    args = parser.parse_args()
    payload = json.loads(args.evidence.resolve().read_text(encoding="utf-8"))
    evidence = validate_client_evidence(payload)
    print(json.dumps(evidence.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

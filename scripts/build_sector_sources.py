"""Compatibility entry point for company-source generation.

Company source registries are now maintained automatically by
`sourcing.sync_a_company_sources` whenever A ratings or the Company Universe
change. This wrapper remains so older documentation/manual commands do not
re-introduce the former append-only one-off behaviour.
"""
from sourcing.sync_a_company_sources import sync_company_sources


def main() -> None:
    status = sync_company_sources()
    counts = status["status"].value_counts().to_dict() if not status.empty else {}
    print(f"Canonical A → G source sync complete: {counts}")


if __name__ == "__main__":
    main()

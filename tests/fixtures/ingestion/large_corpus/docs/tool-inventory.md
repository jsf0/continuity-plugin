# Tool Inventory

## Inventory fields

The tool inventory tracks tool type, condition, storage site, and last inspection date.

## Maintenance

Dull blades are tagged for sharpening and removed from general checkout until serviced.

## Publishing the inventory

Before publishing the inventory dashboard, run `uv run pytest tests/ -q` to validate item metadata and run `uv run ruff check .` to lint helper scripts.

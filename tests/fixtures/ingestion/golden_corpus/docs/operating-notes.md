# Operating Notes

## Trip planning

Trip coordinators should confirm dietary restrictions before assigning shared meals.

## Data handling

Participant emergency contacts are never stored in recipe notes. Keep only non-sensitive meal preferences in the public planning folder.

## Testing the recipe site

Before publishing the static recipe site, run `uv run pytest tests/ -q` to check recipe metadata and run `uv run ruff check .` to verify helper scripts.

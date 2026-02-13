# Contributing to ImageChoom

Thanks for your interest in improving ImageChoom.

## Workflow contribution checklist

1. Add new runnable workflows under `workflows/` with descriptive names.
2. Keep prompts curated and production-safe.
3. Include a matching preset JSON under `presets/` when relevant.
4. Ensure output path defaults to `outputs/`.
5. Document usage in `README.md`.
6. If you add dependencies on shared assets, ensure `scripts/check_layout.sh` verifies them.

## Validation

From the repository root:

```bash
scripts/check_layout.sh
```

Validate your workflow:

```bash
choom validate workflows/<name>.choom
```

Inspect the script plan:

```bash
choom script workflows/<name>.choom
```

Run your workflow:

```bash
choom run workflows/<name>.choom --timeout 180
```

Verify images are written to `outputs/`.

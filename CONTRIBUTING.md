# Contributing to ImageChoom

Thanks for your interest in improving ImageChoom.

## Workflow contribution checklist

1. Add new workflows under `workflows/` with descriptive names.
2. Keep prompts curated and production-safe.
3. Include a matching preset JSON under `presets/` when relevant.
4. Ensure output path defaults to `outputs/`.
5. Document usage in `README.md`.

## Validation

- Confirm your `.choom` script runs with:

```bash
choom run workflows/<name>.choom --timeout 180
```

- Verify images are written to `outputs/`.

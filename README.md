# ImageChoom

ImageChoom is evolving into a **GUI program for working with and administering workflows for Automatic1111 (A1111)** using the **ChoomLang DSL**.

Today, this repository provides the workflow foundation for that direction: curated, ready-to-run `.choom` scripts that call the `a1111_txt2img` adapter and save generated images locally.

See `docs/PRODUCT_VISION.md` for the detailed product direction and roadmap.

## Requirements

- Python 3.10+
- A local A1111 instance with API enabled
  - Common launch flag: `--api`
  - Default API endpoint: `http://127.0.0.1:7860/sdapi/v1/txt2img`
- ChoomLang installed from GitHub:

```bash
python -m pip install "choomlang @ git+https://github.com/ProhibitedTV/ChoomLang.git"
```

## Quick start

1. Clone this repo.
2. Start A1111 with API enabled.
3. Verify the repo layout before running workflows:

```bash
scripts/check_layout.sh
```

4. Run a workflow:

```bash
choom run workflows/cinematic_wallpaper.choom --timeout 180
```

Generated files are written to `outputs/`.


## GUI Quickstart

From the repository root, install and launch the GUI:

```bash
python -m pip install -e .
imagechoom
```

Windows-friendly alternatives:

```powershell
py -m pip install -e .
py -m imagechoom_gui.cli
```

Use `py -m imagechoom_gui.cli` as a fallback if the `imagechoom` PATH script is not found.

The GUI expects this repository layout, with both `workflows/` and `presets/` present.

## Canonical runnable scripts

Use scripts in `workflows/` as the canonical location for all runnable Choom scripts.

Validate scripts:

```bash
choom validate workflows/cinematic_wallpaper.choom
choom validate workflows/anime_poster.choom
choom validate workflows/photo_real_portrait.choom
choom validate workflows/wallpaper_pack_fast.choom
choom validate workflows/wallpaper_pack_hd.choom
```

Inspect script plans:

```bash
choom script workflows/cinematic_wallpaper.choom
choom script workflows/wallpaper_pack_fast.choom
```

Run scripts:

```bash
choom run workflows/cinematic_wallpaper.choom --timeout 180
choom run workflows/anime_poster.choom --timeout 180
choom run workflows/photo_real_portrait.choom --timeout 180
choom run workflows/wallpaper_pack_fast.choom --timeout 180
choom run workflows/wallpaper_pack_hd.choom --timeout 180
```

## Wallpaper app assets

The wallpaper app assets live under `apps/wallpaper/`:

- `apps/wallpaper/inputs/themes.json` (loaded by `workflows/wallpaper_pack_fast.choom` and `workflows/wallpaper_pack_hd.choom`)
- `apps/wallpaper/scripts/pack_fast.choom` and `apps/wallpaper/scripts/pack_hd.choom` are deprecated legacy paths

## Included workflows

- `workflows/cinematic_wallpaper.choom` — moody cinematic wallpapers
- `workflows/anime_poster.choom` — vivid anime poster compositions
- `workflows/photo_real_portrait.choom` — photorealistic portraits
- `workflows/wallpaper_pack_fast.choom` — wallpaper pack from shared theme JSON (fast)
- `workflows/wallpaper_pack_hd.choom` — wallpaper pack from shared theme JSON (HD)

## Configure endpoint/model defaults

Each workflow defines variables near the top for:

- A1111 API URL
- output directory
- model checkpoint override
- prompt/negative prompt
- dimensions, steps, CFG, sampler, seed

Adjust these values directly in the `.choom` file.

## Repository layout

```text
ImageChoom/
├─ workflows/
│  ├─ cinematic_wallpaper.choom
│  ├─ anime_poster.choom
│  ├─ photo_real_portrait.choom
│  ├─ wallpaper_pack_fast.choom
│  └─ wallpaper_pack_hd.choom
├─ apps/
│  └─ wallpaper/
│     ├─ inputs/
│     │  └─ themes.json
│     └─ scripts/
│        ├─ pack_fast.choom (deprecated)
│        └─ pack_hd.choom (deprecated)
├─ presets/
│  ├─ cinematic.json
│  ├─ anime.json
│  └─ portrait.json
├─ docs/
│  ├─ A1111_SETUP.md
│  └─ PRODUCT_VISION.md
├─ scripts/
│  ├─ check_layout.sh
│  └─ run_all.sh
├─ .github/workflows/
│  └─ lint.yml
├─ .gitignore
├─ CONTRIBUTING.md
├─ LICENSE
└─ README.md
```

## Notes

- These workflows assume the `a1111_txt2img` adapter is available in your ChoomLang install.
- You can safely duplicate and tune any workflow for your own style packs.

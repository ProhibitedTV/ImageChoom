# A1111 Setup for ImageChoom

## 1) Start A1111 with API enabled

Typical launch:

```bash
./webui.sh --api
```

Windows:

```powershell
webui-user.bat --api
```

## 2) Check API health

You can validate the API quickly:

```bash
curl -s http://127.0.0.1:7860/sdapi/v1/samplers
```

If you receive JSON, the API is reachable.

## 3) Install ChoomLang

```bash
python -m pip install "choomlang @ git+https://github.com/ProhibitedTV/ChoomLang.git"
```

## 4) Run a workflow

```bash
choom run workflows/cinematic_wallpaper.choom --timeout 180
```

## 5) Troubleshooting

- **Connection refused**: ensure A1111 is running and listening on `127.0.0.1:7860`.
- **404 on `/sdapi/v1/txt2img`**: start A1111 with `--api`.
- **No output files**: check workflow `output_path` and file permissions.

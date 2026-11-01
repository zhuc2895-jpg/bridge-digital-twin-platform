# Scripts

One-off and local automation lives here. Run commands from the repository root.

## Data

```powershell
.\.venv\Scripts\python.exe scripts\data\generate_validation_data.py
.\.venv\Scripts\python.exe scripts\data\fast_import.py
.\.venv\Scripts\python.exe scripts\data\import_data.py
```

The default validation input/output is `data/validation/bridge_validation_data.csv`.

## Docs

```powershell
.\.venv\Scripts\python.exe scripts\docs\gen_docx.py
.\.venv\Scripts\python.exe scripts\docs\generate_plan.py
```

Generated planning documents are written to `assets/planning/`.

## Development

```powershell
.\.venv\Scripts\python.exe scripts\dev\smoke_upload.py
```

The smoke test expects the backend to be running at `http://localhost:8000`.

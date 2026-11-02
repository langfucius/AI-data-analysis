# Windows 11 Setup (VS Code)

## 1. Open folder

In VS Code choose File → Open Folder and select `ai-data-analyst-agent`.

## 2. Open terminal

Terminal → New Terminal. Confirm the shell is PowerShell.

## 3. Create virtual environment

```powershell
py -m venv .venv
```

## 4. Activate

```powershell
.\.venv\Scripts\Activate.ps1
```

If script execution is blocked:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 5. Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 6. Configure environment

```powershell
Copy-Item .env.example .env
```

Open `.env` and optionally set `OPENAI_API_KEY`.

## 7. Initialize data

```powershell
python scripts/init_db.py
```

## 8. Start app

```powershell
python -m streamlit run app/ui/streamlit_app.py
```

## 9. Run tests

```powershell
python -m pytest
```

## Troubleshooting

- If `py` is unavailable, use `python` instead.
- If package installation fails, check that the virtual environment is active and that Python is 3.10+.
- If Streamlit cannot find the app module, make sure the terminal's current directory is the project root.
- If OpenAI mode fails, check the API key, model availability, network access, and account quota. Demo Mode remains available without a key.

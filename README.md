# Grid Volatility Challenge

Welcome to the Grid Volatility Challenge! This repo contains everything you need to get started. 

## The Challenge

**Full challenge requirements:** see [`CHALLENGE.md`](docs/CHALLENGE.md).

## Prerequisites 
- Python 3.12
- `pip` - comes with Python 
- Git for cloning the repo

**Python Version**: This project is pinned to **Python 3.12** via `.python-version`. This is to avoid build failures with scientific libraries should you choose to use them (pandas, NumPy, DubkDB). 

If you use `pyenv` or `pyenv-win`, it will be selected automatically. You can modify or remove this file intend to update the project's Python version. 

### Installing Python

**macOS (Homebrew):**

```bash
brew install python@3.12
```

**Windows:**

Download the Python 3.12 executable directly from [`python.org/downloads`](python.org/downloads) and run the installer. Ensure you check the box that says "Add python.exe to PATH" during setup. 

## Getting Started

### 1. Fork the repo
Click "Fork" in the top-right of the GitHub repo page, then clone your fork:
```bash
git clone https://github.com/<your-username>/advanced-challenge-grid-volatility.git
cd advanced-challenge-grid-volatility
```

### 2. Create a Virtual Environment

macOS / Linux:
```bash
python3.12 -m venv venv
source venv/bin/activate
```

Windows (PowerShell):
```powershell
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
```

Windows (Command Prompt):
```cmd
py -3.12 -m venv venv
venv\Scripts\activate.bat
```

You should see `venv` at the start of your terminal prompt, indicating the environment is active.

### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

*Note: SQLite is built into Python. No installation required.*
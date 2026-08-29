# Environment notes

## Python version

Use **Python 3.11**. Python 3.14 is installed on the development machine but is
too recent for parts of the geospatial / ML stack.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

## Smart App Control (Windows 11)

The development machine runs Windows 11 with **Smart App Control enforced**:

```
HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy
    VerifiedAndReputablePolicyState = 1   # 0 = off, 1 = enforced, 2 = evaluation
```

Smart App Control is reputation-based: it refuses to load compiled extension
modules (`.pyd`, `.dll`) whose file hash Microsoft does not yet recognise. Freshly
released wheels are therefore blocked, and the failure surfaces at import time:

```
ImportError: DLL load failed while importing timestamps:
An Application Control policy has blocked this file.
```

Blocked on first install (latest versions): `pandas 3.0.5`, `pyarrow 25.0.1`,
`cryptography 50.0.1`, `shap 0.51.0`, `numba 0.67.0`, `charset_normalizer 3.5.1`.

**Resolution:** pin slightly older, widely downloaded releases (see
`backend/requirements.txt`). No Windows setting was changed. Smart App Control
remains enforced.

Blocks are logged to the Windows event log and can be inspected with:

```powershell
Get-WinEvent -LogName "Microsoft-Windows-CodeIntegrity/Operational" -MaxEvents 20
```

Event IDs of interest: `3077` (load blocked), `3118` (Smart App Control block).

## Version compatibility constraints

| Pin | Reason |
|---|---|
| `numpy==2.0.2` | `numba<=0.60` requires `numpy<2.1` |
| `numba==0.60.0`, `llvmlite==0.43.0` | newer numba builds are blocked by Smart App Control |
| `xgboost==2.1.4` | `shap 0.46` cannot parse `xgboost>=3.0` models (`base_score` is serialised as `'[3.8987602E1]'`) |
| `shap==0.46.0` | newer shap builds are blocked by Smart App Control |
| `pandas==2.2.3`, `pyarrow==17.0.0` | blocked at latest versions |

## Gemini SDK

`google-generativeai` reached end of life and prints a deprecation warning on
import. The project uses the supported **`google-genai`** SDK instead:

```python
from google import genai
client = genai.Client(api_key=...)
```

## Jupyter kernel

The virtual environment is registered as a kernel named `heatgov`:

```powershell
.\.venv\Scripts\python.exe -m ipykernel install --user --name heatgov --display-name "HeatGov AI (Python 3.11)"
```

Select **HeatGov AI (Python 3.11)** when opening any notebook in `notebooks/`.

# How to Find Latest Document Processing Version

**For AI Agents and Users**

---

## Quick Method

Look in this directory for folders named `doc-process-v##`

**Use the one with the HIGHEST number**

Example:
- doc-process-v14 ← USE THIS (if exists)
- doc-process-v13 ← Current
- z_old-versions/ ← Don't use

---

## Command to Find Latest

```powershell
Get-ChildItem E:\DevWorkspace\01_prjct_active\02_legal_system_v1.2\y_config\x3_doc-processing -Directory | Where-Object { $_.Name -match "^doc-process-v\d+" } | Sort-Object Name -Descending | Select-Object -First 1 -ExpandProperty Name
```

**Result**: Name of directory with highest version

---

## What's Inside

Each `doc-process-v##/` directory contains:
- `doc-process-v##.md` - Instructions for this version
- `doc-process-v##.py` - Script for this version

**Names match**: Directory, .md, and .py all have same version number

---

## How to Use

1. Find highest version directory
2. Read the .md file inside
3. Run the .py file inside

**Example** (if doc-process-v13 is latest):
```powershell
# Read instructions
cat y_config\x3_doc-processing\doc-process-v13\doc-process-v13.md

# Run script
python y_config\x3_doc-processing\doc-process-v13\doc-process-v13.py
```

---

## Why This Structure

**Problem**: When v14 is created, all hardcoded references to v13 would break

**Solution**: 
- Point to parent directory (x3_doc-processing)
- Instruct to find highest version
- No updates needed when new version created

---

**Always look for highest version number in this directory**

Last Updated: October 31, 2025


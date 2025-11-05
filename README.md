# Document Processing System - Versioned

**Status**: Production ready with versioned directory structure
**Current Version**: v21
**Location**: `doc-process-v21/`
**Best Known Quality**: v13 (October 31, 2025)

---

## FOR AI AGENTS: HOW TO FIND LATEST VERSION

### Step 1: Find Current Version Directory
```powershell
Get-ChildItem E:\DevWorkspace\01_prjct_active\02_legal_system_v1.2\y_config\x3_doc-processing -Directory | Where-Object { $_.Name -match "^doc-process-v\d+" } | Sort-Object Name -Descending | Select-Object -First 1 | Select-Object Name
```

**Result**: Directory named `doc-process-v##` with highest number (e.g., doc-process-v14)

### Step 2: Read Instructions
```
doc-process-v##/doc-process-v##.md  ← Read this first
doc-process-v##/doc-process-v##.py  ← Then run this
```

### Step 3: Run Latest Version
```powershell
cd E:\DevWorkspace\01_prjct_active\02_legal_system_v1.2
.\y_config\activate.ps1

# Find latest version (highest number)
$latest = Get-ChildItem y_config\x3_doc-processing -Directory | Where-Object { $_.Name -match "^doc-process-v\d+" } | Sort-Object Name -Descending | Select-Object -First 1

# Run script
python y_config\x3_doc-processing\$($latest.Name)\doc-process-v*.py
```

---

## Current Version

**Directory**: `doc-process-v14r/`
**Script**: `doc-process-v14r.py`
**Instructions**: `doc-process-v14r.md` (same name, same directory)
**Changes Log**: `CHANGES_LOG.md` (track all versions)

**Quick Run**:
```powershell
python y_config\x3_doc-processing\doc-process-v14r\doc-process-v14r.py
```

**Quality Baseline**: This version produces best output. Test new versions against this.

---

## Version Management Rules

### When Creating New Version (v14, v15, etc.)

**REQUIRED STEPS**:

1. **Update CHANGES_LOG.md FIRST**:
   ```
   Add new entry documenting:
   - Version number and date
   - What changed and why
   - Expected result
   - Test on sample file BEFORE batch processing
   ```

2. **Create new version directory**:
   ```powershell
   New-Item -ItemType Directory -Path "doc-process-v##"
   ```

3. **Create files with SAME NAME**:
   ```
   doc-process-v##/
   ├── doc-process-v##.md  ← Updated instructions
   └── doc-process-v##.py  ← Updated script
   ```

4. **Test on ONE file**, compare to v13 quality

5. **If quality good**: Process batch
   **If quality degraded**: Revert, try different approach

6. **Archive old version**:
   ```powershell
   Move-Item "doc-process-v##" -Destination "z_old-versions\doc-process-v##"
   ```

7. **Update this README** and **CHANGES_LOG.md** with results

**CRITICAL**: Always compare new version output to v13 baseline quality

---

## Directory Structure

```
x3_doc-processing/
├── README.md                  ← This file
├── doc-process-v14/           ← CURRENT VERSION - USE THIS
│   ├── doc-process-v14.md     ← Instructions
│   └── doc-process-v14.py     ← Script
├── z_old-versions/            ← Archived versions
│   ├── doc-process-v13/
│   ├── doc-process-v12/
│   └── doc-process-v11/
├── z_old-gemini-versions/     ← Old unversioned scripts
└── z_old-do-not-use/          ← Legacy individual scripts
```

---

## Why This Structure

**Benefits**:
- Always clear which version is current (has "_current" suffix)
- Instructions and script stay together
- Old versions preserved for reference
- No confusion about which to use
- AI agents can programmatically find latest

**Prevents**:
- Using outdated scripts
- Instructions not matching code
- Multiple versions in same folder
- AI agents creating new files when old exist

---

## For Future AI Agents

**To find latest version**:
1. Look for directory named `doc-process-v##` with highest number
2. Read `doc-process-v##.md` in that directory
3. Run `doc-process-v##.py` in that directory

**Pattern**: Everything has the same name (directory, .md, .py)

**Don't**:
- Use files in z_old directories
- Use archived versions (v##_archived)
- Create new scripts without creating new version directory


#!/usr/bin/env python3
"""
Quick wrapper to run only Phase 4 (Extract) from doc-process-v31
Usage: python extract.py <directory>
"""
import sys
import subprocess
from pathlib import Path

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract.py <directory>")
        print("Example: python extract.py E:\\01_prjct_active\\02_legal_system_v1.2\\x_docs\\01_fremont\\00_legal_standing")
        sys.exit(1)
    
    directory = sys.argv[1]
    script_path = Path(__file__).parent / "doc-process-v31.py"
    
    # Run main script with extract-only args
    result = subprocess.run([
        sys.executable,
        str(script_path),
        '--dir', directory,
        '--phase', 'extract',
        '--no-verify'
    ])
    
    sys.exit(result.returncode)

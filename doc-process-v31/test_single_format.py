#!/usr/bin/env python3
"""Test reformatting a single file with enhanced prompt"""

from pathlib import Path
import sys

# Import format_single_file from doc-process-v31
sys.path.insert(0, str(Path(__file__).parent))
from doc_process_v31_module import format_single_file

def main():
    # Target file
    root_dir = Path(r"G:\Shared drives\12 - legal\a0_fremont_lg\_reedy-v-fremont_all\05_evidence\01_fremont\09_9c1_23-0406-ck\01_Plaintiff-fic")
    base_name = "20230906_9c1_FIC_Amended_Petition_No_Coverage"
    
    print(f"Reformatting: {base_name}")
    print(f"Root dir: {root_dir}")
    print()
    
    format_single_file(root_dir, base_name)
    
    print()
    print("Done. Check the formatted file:")
    print(f"  {root_dir / '05_doc-format' / f'{base_name}_v31.txt'}")

if __name__ == '__main__':
    main()

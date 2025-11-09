"""
Test script to demonstrate intelligent repair strategy selection
"""

import re

def analyze_repair_strategy(issue_text):
    """Analyze issue and determine repair strategy"""
    
    has_low_accuracy = False
    accuracy_value = None
    has_header_issues = False
    has_marker_issues = False
    has_url_issues = False
    
    issue_lower = issue_text.lower()
    
    # Check for low accuracy
    if 'accuracy' in issue_lower or 'similarity' in issue_lower:
        has_low_accuracy = True
        match = re.search(r'(\d+)%', issue_text)
        if match:
            accuracy_value = int(match.group(1))
    
    # Check for specific issue types
    if 'header' in issue_lower or 'directory' in issue_lower:
        has_header_issues = True
    if 'marker' in issue_lower or 'page marker' in issue_lower:
        has_marker_issues = True
    if 'url' in issue_lower or 'gcs' in issue_lower or 'accessible' in issue_lower:
        has_url_issues = True
    
    # Determine strategy
    if has_low_accuracy:
        if accuracy_value and accuracy_value < 50:
            return "CRITICAL ACCURACY", "Reprocess PDF with enhanced OCR (1200 DPI) → Re-extract text → Reformat"
        elif accuracy_value and accuracy_value < 70:
            return "MODERATE ACCURACY", "Re-extract text with Google Vision → Reformat with Gemini"
        else:
            return "BORDERLINE ACCURACY", "Reformat with Gemini only"
    
    elif has_marker_issues:
        return "PAGE MARKERS", "Reformat with Gemini to restore page markers"
    
    elif has_header_issues and not has_url_issues:
        return "HEADERS ONLY", "Update headers in place (no reprocessing)"
    
    elif has_url_issues:
        return "GCS URL", "Re-upload PDF to cloud storage and update headers"
    
    else:
        return "GENERAL", "Reformat with Gemini (fallback)"

# Test cases from actual verification reports
test_cases = [
    ("Low content accuracy: 46%", "20240422_9c1_FIC_Payment_to_Reedy"),
    ("Low content accuracy: 44%, Page 72: Page marker not found", "20251030_9c1_FIC_Response_RR_Motion"),
    ("Low content accuracy: 48%, Missing PDF DIRECTORY header", "20250904_9c1_FIC_Motion_Enter_Lost_Order"),
    ("Page 1: Low similarity: 66.40%", "20230906_9c1_FIC_Amended_Petition"),
    ("Missing PDF PUBLIC LINK header", "20240815_example_doc"),
    ("GCS URL not accessible", "20240920_example_doc"),
    ("Page marker not found: [BEGIN PDF Page 5]", "20241001_example_doc"),
]

print("="*100)
print("INTELLIGENT REPAIR STRATEGY SELECTION TEST")
print("="*100)

for issue, filename in test_cases:
    strategy, action = analyze_repair_strategy(issue)
    print(f"\nFile: {filename}")
    print(f"Issue: {issue}")
    print(f"Strategy: {strategy}")
    print(f"Action: {action}")
    print("-"*100)

print("\n" + "="*100)
print("STRATEGY SUMMARY")
print("="*100)

strategies = {
    "CRITICAL ACCURACY (<50%)": [
        "Phase 3 (Clean) - Enhanced OCR with 1200 DPI",
        "Phase 4 (Convert) - Re-extract text with Google Vision",
        "Phase 5 (Format) - Reformat with Gemini AI"
    ],
    "MODERATE ACCURACY (50-69%)": [
        "Phase 4 (Convert) - Re-extract text with Google Vision",
        "Phase 5 (Format) - Reformat with Gemini AI"
    ],
    "BORDERLINE ACCURACY (70-79%)": [
        "Phase 5 (Format) - Reformat with Gemini AI only"
    ],
    "PAGE MARKERS": [
        "Phase 5 (Format) - Reformat to restore markers"
    ],
    "HEADERS ONLY": [
        "Update headers in place (no phases)"
    ],
    "GCS URL": [
        "Phase 6 (GCS Upload) - Re-upload and update headers"
    ]
}

for strategy_name, steps in strategies.items():
    print(f"\n{strategy_name}:")
    for step in steps:
        print(f"  • {step}")

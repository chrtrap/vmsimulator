import pdfplumber
import json
import re

def extract_surgical_v4(pdf_path, start_page, end_page):
    all_entries = []
    # This regex looks for 9 consecutive values (Option number + 8 '3X' codes)
    # It allows for weird spaces or newlines between them
    row_pattern = re.compile(r'(\d+)\s+(3[A-L])\s+(3[A-L])\s+(3[A-L])\s+(3[A-L])\s+(3[A-L])\s+(3[A-L])\s+(3[A-L])\s+(3[A-L])')

    with pdfplumber.open(pdf_path) as pdf:
        for p_num in range(start_page - 1, end_page):
            page = pdf.pages[p_num]
            text = page.extract_text()
            
            if not text:
                continue

            # Find all matches on the page
            matches = row_pattern.findall(text)
            for m in matches:
                entry = {
                    "Option": m[0],
                    "1A": m[1], "1B": m[2], "1D": m[3], 
                    "1E": m[4], "1G": m[5], "1I": m[6], 
                    "1K": m[7], "1L": m[8]
                }
                all_entries.append(entry)

    # Remove duplicates if any (sometimes page overlaps cause double-reads)
    unique_results = []
    seen = set()
    for e in all_entries:
        # Create a unique finger print for the row
        fingerprint = tuple(e.items())
        if fingerprint not in seen:
            unique_results.append(e)
            seen.add(fingerprint)

    with open('fifa_2026_combinations_complete.json', 'w') as f:
        json.dump(unique_results, f, indent=4)
    
    print(f"Total entries found: {len(unique_results)}")
    return unique_results

if __name__ == '__main__':
    extract_surgical_v4('/Users/traporeus/Documents/VM2026/FWC26_regulations_EN.pdf', 80, 97)
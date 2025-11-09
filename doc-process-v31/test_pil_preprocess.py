"""Test PIL preprocessing to remove underlines and enhance header for OCR"""
import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
import io
import subprocess
from pathlib import Path

# Input/output paths
input_pdf = r"G:\Shared drives\12 - legal\a0_fremont_lg\_reedy-v-fremont_all\05_evidence\01_fremont\09_9c1_23-0406-ck\09_Pleadings_plaintiff\02_doc-renamed\20230906_9c1_FIC_Amended_Petition_No_Coverage_r.pdf"
output_pdf = r"E:\00_dev_1\y_apps\x3_doc-processing\doc-process-v31\test_preprocessed.pdf"
output_ocr = r"E:\00_dev_1\y_apps\x3_doc-processing\doc-process-v31\test_preprocessed_ocr.pdf"

print("Step 1: Extract PDF as images and preprocess...")

doc = fitz.open(input_pdf)
temp_images = []

for page_num in range(len(doc)):
    print(f"  Processing page {page_num + 1}...")
    page = doc[page_num]
    
    # Render at high DPI
    mat = fitz.Matrix(3.0, 3.0)  # 3x zoom = ~864 DPI
    pix = page.get_pixmap(matrix=mat, alpha=False)
    
    # Convert to PIL Image
    img_data = pix.tobytes("png")
    img = Image.open(io.BytesIO(img_data))
    
    # Preprocess: Remove horizontal lines (underlines)
    # Convert to grayscale
    img_gray = img.convert('L')
    
    # Enhance contrast
    enhancer = ImageEnhance.Contrast(img_gray)
    img_enhanced = enhancer.enhance(2.0)  # Increase contrast
    
    # Remove horizontal lines using morphological operations
    # This is a simplified approach - find and remove long horizontal lines
    width, height = img_enhanced.size
    pixel_data = img_enhanced.load()
    
    if pixel_data is not None:
        # Scan for horizontal lines (long sequences of dark pixels)
        for y in range(height):
            line_length = 0
            for x in range(width):
                pixel_val = pixel_data[x, y]
                if isinstance(pixel_val, (int, float)) and pixel_val < 128:  # Dark pixel
                    line_length += 1
                else:
                    if line_length > width * 0.3:  # If line is >30% of width
                        # Fill the line with white
                        for xx in range(x - line_length, x):
                            if 0 <= xx < width:
                                pixel_data[xx, y] = 255
                    line_length = 0
    
    # Save preprocessed image
    temp_img_path = Path(output_pdf).parent / f"temp_page_{page_num + 1}.png"
    img_enhanced.save(str(temp_img_path), dpi=(600, 600))
    temp_images.append(str(temp_img_path))

doc.close()

print(f"\nStep 2: Creating preprocessed PDF from {len(temp_images)} images...")

# Create PDF from preprocessed images with correct page dimensions
new_doc = fitz.open()

for img_path in temp_images:
    # Open image to get dimensions
    img = Image.open(str(img_path))
    img_width, img_height = img.size
    img.close()
    
    # Images were rendered at 3x zoom from 72 DPI = 216 DPI effective
    # Convert back to PDF points (72 DPI)
    page_width = img_width / 3.0
    page_height = img_height / 3.0
    
    # Create new page with correct dimensions
    page = new_doc.new_page(width=page_width, height=page_height)
    
    # Insert image to fill the page
    page_rect = page.rect
    page.insert_image(page_rect, filename=str(img_path))

new_doc.save(output_pdf)
new_doc.close()

print(f"Preprocessed PDF saved: {output_pdf}")

# Clean up temp images
for img_path in temp_images:
    Path(img_path).unlink()

print("\nStep 3: Running OCR on preprocessed PDF...")

ocrmypdf_cmd = r"E:\00_dev_1\.venv\Scripts\ocrmypdf.exe"
cmd = [ocrmypdf_cmd, '--force-ocr', '--output-type', 'pdfa',
       '--oversample', '600',
       output_pdf, output_ocr]

result = subprocess.run(cmd, capture_output=True, text=True)

if result.returncode == 0:
    print(f"[OK] OCR completed: {output_ocr}")
    print("\nStep 4: Validating OCR output...")
    
    # Extract text from page 1
    doc = fitz.open(output_ocr)
    page1_text = doc[0].get_text()
    doc.close()
    
    print(f"\nPage 1 text ({len(page1_text)} chars):")
    print("=" * 80)
    print(page1_text[:500])
    print("=" * 80)
    
    if "AMENDED PETITION" in page1_text:
        print("\n[SUCCESS] 'AMENDED PETITION' FOUND IN OCR OUTPUT!")
    else:
        print("\n[FAIL] Header still missing")
else:
    print(f"[ERROR] OCR failed: {result.stderr}")

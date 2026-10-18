"""
Convert temporary PNG files to PDF
"""
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PIL import Image
import os
import glob
import time

def convert_temp_images_to_pdf():
    """Convert all _temp.png files to PDF"""
    
    doc_dir = os.path.join("..", "source_files", "customer_documents")
    temp_files = glob.glob(os.path.join(doc_dir, "*_temp.png"))
    
    for temp_file in temp_files:
        # Get the target PDF filename
        pdf_file = temp_file.replace('_temp.png', '.pdf')
        
        # Create PDF
        c = canvas.Canvas(pdf_file, pagesize=letter)
        width, height = letter
        
        # Open image, get dimensions, then CLOSE IT
        img = Image.open(temp_file)
        img_width, img_height = img.size
        img.close()  # ← Important for Windows!
        
        # Calculate scaling to fit on page
        scale = min(width / img_width, height / img_height) * 0.9
        
        # Draw image centered on page
        x = (width - img_width * scale) / 2
        y = (height - img_height * scale) / 2
        
        c.drawImage(temp_file, x, y, 
                   width=img_width * scale, 
                   height=img_height * scale)
        
        c.save()
        print(f"✓ Created PDF: {os.path.basename(pdf_file)}")
        
        # Small delay for Windows file system
        time.sleep(0.1)
        
        # Remove temp file with error handling
        try:
            os.remove(temp_file)
            print(f"  Removed: {os.path.basename(temp_file)}")
        except PermissionError:
            print(f"  ⚠️  Could not auto-delete temp file (Windows lock)")
            print(f"     You can manually delete: {os.path.basename(temp_file)}")
        
        print()
    
    print(f"\nConversion complete! Created {len(temp_files)} PDF files.")

if __name__ == "__main__":
    convert_temp_images_to_pdf()
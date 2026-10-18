"""
Generate sample customer documents - Windows compatible
"""
from PIL import Image, ImageDraw
import os

def create_sample_images():
    """Create sample image files for customer documents"""
    
    # Use relative path (works on Windows)
    output_dir = os.path.join("..", "source_files", "customer_documents")
    os.makedirs(output_dir, exist_ok=True)
    
    # Sample documents to create
    documents = [
        # CUST001
        ("CUST001_passport.pdf", "PASSPORT", "John Doe", "US123456789"),
        ("CUST001_address_proof.pdf", "ADDRESS PROOF", "123 Main St, NY", "Electric Bill"),
        ("CUST001_signature.png", "SIGNATURE", "John Doe", ""),
        
        # CUST002
        ("CUST002_drivers_license.jpg", "DRIVER'S LICENSE", "Jane Smith", "DL987654321"),
        ("CUST002_utility_bill.pdf", "UTILITY BILL", "456 Oak Ave, LA", "Gas Bill"),
        ("CUST002_signature.jpg", "SIGNATURE", "Jane Smith", ""),
        
        # CUST003
        ("CUST003_national_id.png", "NATIONAL ID", "Robert Johnson", "NID456789123"),
        ("CUST003_bank_statement.pdf", "BANK STATEMENT", "789 Pine Rd, Chicago", "Account: ***1234"),
        ("CUST003_signature.png", "SIGNATURE", "Robert Johnson", ""),
        
        # CUST004
        ("CUST004_passport.pdf", "PASSPORT", "Emily Williams", "US987654321"),
        ("CUST004_lease_agreement.pdf", "LEASE AGREEMENT", "321 Elm St, Houston", "Tenant: Emily Williams"),
        ("CUST004_signature.jpg", "SIGNATURE", "Emily Williams", ""),
        
        # CUST005
        ("CUST005_drivers_license.png", "DRIVER'S LICENSE", "Michael Brown", "DL123789456"),
        ("CUST005_utility_bill.jpg", "UTILITY BILL", "654 Maple Dr, Phoenix", "Water Bill"),
        ("CUST005_signature.png", "SIGNATURE", "Michael Brown", ""),
    ]
    
    for filename, doc_type, name, detail in documents:
        filepath = os.path.join(output_dir, filename)
        
        # Create image (800x600)
        img = Image.new('RGB', (800, 600), color='white')
        draw = ImageDraw.Draw(img)
        
        # Draw border
        draw.rectangle([(10, 10), (790, 590)], outline='black', width=3)
        
        # Add text (using default font)
        try:
            draw.text((400, 100), doc_type, fill='black', anchor='mm')
            draw.text((400, 200), f"Name: {name}", fill='black', anchor='mm')
            if detail:
                draw.text((400, 300), detail, fill='black', anchor='mm')
            draw.text((400, 550), "SAMPLE DOCUMENT - FOR TESTING ONLY", fill='lightgray', anchor='mm')
        except:
            # Fallback for older PIL versions
            draw.text((350, 100), doc_type, fill='black')
            draw.text((300, 200), f"Name: {name}", fill='black')
            if detail:
                draw.text((300, 300), detail, fill='black')
            draw.text((200, 550), "SAMPLE DOCUMENT - FOR TESTING ONLY", fill='lightgray')
        
        # Save based on extension
        if filename.endswith('.pdf'):
            temp_path = filepath.replace('.pdf', '_temp.png')
            img.save(temp_path, 'PNG')
            print(f"Created temporary image for PDF: {temp_path}")
        else:
            if filename.endswith('.jpg') or filename.endswith('.jpeg'):
                img.save(filepath, 'JPEG', quality=95)
            else:
                img.save(filepath, 'PNG')
            print(f"Created: {filepath}")
    
    print(f"\nSample documents created in: {output_dir}")
    print(f"Total files created: {len(documents)}")

if __name__ == "__main__":
    create_sample_images()
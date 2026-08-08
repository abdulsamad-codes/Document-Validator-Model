import cv2
import numpy as np
import fitz  # PyMuPDF
import os

def recover_text_opencv(image_path, output_path):
    print(f"Processing image with OpenCV: {image_path}")
    img = cv2.imread(image_path)
    if img is None:
        print("Error: Could not load image.")
        return

    b, g, r = cv2.split(img)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced_b = clahe.apply(b)

    _, binary = cv2.threshold(enhanced_b, 150, 255, cv2.THRESH_BINARY)

    cv2.imwrite(output_path, binary)
    print(f"Saved recovered image to: {output_path}")

def process_pdf(pdf_path):
    print(f"Loading PDF: {pdf_path}")
    
    # Page 2 (index 1)
    page_index = 1 
    
    try:
        doc = fitz.open(pdf_path)
        page = doc.load_page(page_index)
        
        # Render page to an image (pixmap)
        zoom = 3 # increase resolution
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        
        temp_image_path = "temp_page_2.png"
        output_image_path = "recovered_page_2.png"
        
        pix.save(temp_image_path)
        
        # Process the image to remove blue overlay
        recover_text_opencv(temp_image_path, output_image_path)
        
        print("\nProcess complete! Check 'recovered_page_2.png' to see the text without the blue stamp.")
        
    except Exception as e:
        print(f"Error processing PDF: {e}")

if __name__ == "__main__":
    pdf_file = "DGAM Onboarding file.pdf"
    if os.path.exists(pdf_file):
        process_pdf(pdf_file)
    else:
        print(f"Could not find {pdf_file} in the current directory.")

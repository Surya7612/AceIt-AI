import pytesseract
from PIL import Image
import logging

def extract_text_from_image(image_path):
    try:
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image)
        return text.strip()
    except Exception as e:
        logging.error(f"OCR error: {str(e)}")
        return None

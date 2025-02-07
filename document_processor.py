import os
import logging
from typing import Optional, Dict, Any
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from ocr_helper import extract_text_from_image

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai = OpenAI(api_key=OPENAI_API_KEY)

class DocumentProcessor:
    def __init__(self):
        self.supported_types = {
            'pdf': self.process_pdf,
            'image': self.process_image,
            'link': self.process_link
        }

    def process_document(self, doc_type: str, content: Any) -> Optional[Dict[str, Any]]:
        """Process a document and return structured content"""
        try:
            if doc_type not in self.supported_types:
                raise ValueError(f"Unsupported document type: {doc_type}")
            
            # Extract raw text content
            raw_text = self.supported_types[doc_type](content)
            if not raw_text:
                return None

            # Generate structured content using OpenAI
            structured_content = self.generate_structured_content(raw_text)
            return structured_content

        except Exception as e:
            logging.error(f"Error processing document: {str(e)}")
            return None

    def process_pdf(self, content: str) -> Optional[str]:
        """Process PDF content - placeholder for PDF processing"""
        # TODO: Implement PDF processing
        return content

    def process_image(self, image_path: str) -> Optional[str]:
        """Process image using OCR"""
        return extract_text_from_image(image_path)

    def process_link(self, url: str) -> Optional[str]:
        """Process web link content"""
        try:
            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract main content (adjust selectors based on common website structures)
            content = []
            for tag in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                content.append(tag.get_text().strip())
            
            return ' '.join(content)
        except Exception as e:
            logging.error(f"Error processing link: {str(e)}")
            return None

    def generate_structured_content(self, raw_text: str) -> Dict[str, Any]:
        """Generate structured study content using OpenAI"""
        try:
            response = openai.chat.completions.create(
                model="gpt-4o",  # Latest model as of May 13, 2024
                messages=[
                    {
                        "role": "system",
                        "content": """Analyze the following content and create a structured study document. 
                        Return the result in JSON format with the following structure:
                        {
                            "title": "Main topic or subject",
                            "summary": "Brief overview",
                            "key_concepts": ["List of important concepts"],
                            "sections": [
                                {
                                    "heading": "Section title",
                                    "content": "Structured content",
                                    "key_points": ["Important points"]
                                }
                            ],
                            "practice_questions": [
                                {
                                    "question": "Study question",
                                    "answer": "Detailed answer"
                                }
                            ]
                        }"""
                    },
                    {"role": "user", "content": raw_text}
                ],
                response_format={"type": "json_object"}
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.error(f"Error generating structured content: {str(e)}")
            raise

import os
import logging
from typing import Optional, Dict, Any
import requests
from bs4 import BeautifulSoup
import json
from extensions import openai_client  # Import the shared client
from ocr_helper import extract_text_from_image

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class DocumentProcessor:
    def __init__(self):
        self.supported_types = {
            'pdf': self.process_pdf,
            'image': self.process_image,
            'link': self.process_link
        }

    def process_document(self, doc_type: str, content: Any) -> Optional[str]:
        """Process a document and return structured content as JSON string"""
        try:
            if doc_type not in self.supported_types:
                raise ValueError(f"Unsupported document type: {doc_type}")

            logger.debug(f"Processing document of type: {doc_type}")

            # Extract raw text content
            raw_text = self.supported_types[doc_type](content)
            if not raw_text:
                logger.warning(f"No text content extracted from {doc_type} document")
                return None

            # Generate structured content using OpenAI
            response = openai_client.chat.completions.create(
                model="gpt-4",  # Using standard gpt-4 model
                messages=[
                    {
                        "role": "system",
                        "content": """Analyze the provided content and create a structured study document with the following JSON format:
                        {
                            "title": "Main topic or subject",
                            "summary": "Concise overview of the content",
                            "category": "DSA|System Design|Behavioral",
                            "difficulty_level": "beginner|intermediate|advanced",
                            "estimated_study_time": "Time in minutes",
                            "key_concepts": [
                                {
                                    "name": "Concept name",
                                    "description": "Brief explanation"
                                }
                            ],
                            "sections": [
                                {
                                    "heading": "Section title",
                                    "content": "Detailed explanation",
                                    "key_points": ["Important points"],
                                    "examples": ["Examples or code snippets"]
                                }
                            ],
                            "practice_questions": [
                                {
                                    "question": "Study question",
                                    "answer": "Detailed answer",
                                    "explanation": "Why this answer is correct",
                                    "difficulty": "easy|medium|hard"
                                }
                            ],
                            "additional_resources": [
                                {
                                    "title": "Resource name",
                                    "type": "article|video|tutorial",
                                    "description": "Brief description"
                                }
                            ]
                        }

                        For category classification:
                        - DSA: Content about data structures, algorithms, complexity analysis, coding patterns
                        - System Design: Architecture, scalability, databases, distributed systems, design patterns
                        - Behavioral: Soft skills, leadership, teamwork, project management, communication
                        """
                    },
                    {"role": "user", "content": raw_text}
                ]
            )

            structured_content = json.loads(response.choices[0].message.content)
            return json.dumps(structured_content)

        except Exception as e:
            logger.error(f"Error processing document: {str(e)}", exc_info=True)
            return None

    def process_pdf(self, content: str) -> Optional[str]:
        """Process PDF content - placeholder for PDF processing"""
        # TODO: Implement PDF processing
        logger.warning("PDF processing not yet implemented")
        return content

    def process_image(self, image_path: str) -> Optional[str]:
        """Process image using OCR"""
        logger.debug(f"Processing image: {image_path}")
        return extract_text_from_image(image_path)

    def process_link(self, url: str) -> Optional[str]:
        """Process web link content"""
        try:
            logger.debug(f"Processing link: {url}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract main content (adjust selectors based on common website structures)
            content = []
            main_selectors = ['article', 'main', '#content', '.content', '.post-content']

            # Try to find main content container
            main_content = None
            for selector in main_selectors:
                main_content = soup.select_one(selector)
                if main_content:
                    break

            # If main content container found, extract from it, otherwise use body
            target = main_content if main_content else soup

            # Extract text from paragraphs and headings
            for tag in target.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                text = tag.get_text().strip()
                if text:  # Only add non-empty strings
                    content.append(text)

            return ' '.join(content)
        except Exception as e:
            logger.error(f"Error processing link: {str(e)}")
            return None

    def combine_documents(self, documents: list) -> Dict[str, Any]:
        """Combine multiple documents into a single structured study document"""
        try:
            logger.debug(f"Combining {len(documents)} documents")

            # Combine all document content
            combined_content = []
            for doc in documents:
                if doc.structured_content:
                    structured = json.loads(doc.structured_content)
                    combined_content.append(f"Document: {doc.original_filename}\n")
                    combined_content.append(f"Content: {structured['content'] if 'content' in structured else structured['summary']}\n")
                elif doc.content:
                    combined_content.append(f"Document: {doc.original_filename}\n")
                    combined_content.append(f"Content: {doc.content}\n")

            if not combined_content:
                raise ValueError("No valid content found in selected documents")

            combined_text = "\n".join(combined_content)

            # Generate new structured content from combined documents
            response = openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": """Create a unified study document that combines and organizes the provided content from multiple sources.
                        Format your response as a valid JSON object with this structure:
                        {
                            "title": "Combined topic or subject",
                            "summary": "Overview synthesizing all sources",
                            "difficulty_level": "beginner|intermediate|advanced",
                            "estimated_study_time": "Total time in minutes",
                            "key_concepts": [
                                {
                                    "name": "Concept name",
                                    "description": "Brief explanation",
                                    "source_document": "Original filename"
                                }
                            ],
                            "sections": [
                                {
                                    "heading": "Section title",
                                    "content": "Synthesized explanation",
                                    "key_points": ["Important points"],
                                    "examples": ["Examples from various sources"],
                                    "source_documents": ["List of source documents"]
                                }
                            ],
                            "practice_questions": [
                                {
                                    "question": "Study question",
                                    "answer": "Detailed answer",
                                    "explanation": "Why this answer is correct",
                                    "difficulty": "easy|medium|hard",
                                    "source_document": "Original filename"
                                }
                            ],
                            "connections": [
                                {
                                    "topic": "Related topic name",
                                    "explanation": "How topics connect across documents"
                                }
                            ]
                        }"""
                    },
                    {
                        "role": "user",
                        "content": combined_text
                    }
                ]
            )

            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"Error combining documents: {str(e)}", exc_info=True)
            raise
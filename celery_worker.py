import os
from celery import Celery
from document_processor import DocumentProcessor
from models import Document, db
import logging

# Configure Celery
celery = Celery('tasks', broker='redis://localhost:6379/0')
celery.conf.update(
    broker_connection_retry_on_startup=True,
    result_backend='redis://localhost:6379/0',
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

doc_processor = DocumentProcessor()

@celery.task
def process_document_task(doc_id):
    """Process document in background"""
    try:
        from app import app
        with app.app_context():
            document = Document.query.get(doc_id)
            if not document:
                logging.error(f"Document {doc_id} not found")
                return

            if document.file_type == 'image':
                structured_content = doc_processor.process_document('image', document.filename)
            elif document.file_type == 'link':
                structured_content = doc_processor.process_document('link', document.content)
            elif document.file_type == 'pdf':
                structured_content = doc_processor.process_document('pdf', document.filename)

            if structured_content:
                document.structured_content = structured_content
                document.processed = True
                db.session.commit()
                logging.info(f"Successfully processed document {doc_id}")
            else:
                logging.error(f"Failed to process document {doc_id}")

    except Exception as e:
        logging.error(f"Error processing document {doc_id}: {str(e)}", exc_info=True)
        raise

@celery.task
def combine_documents_task(doc_ids, user_id):
    """Combine documents in background"""
    try:
        from app import app
        with app.app_context():
            documents = Document.query.filter(Document.id.in_(doc_ids)).all()
            combined_content = doc_processor.combine_documents(documents)
            return combined_content

    except Exception as e:
        logging.error(f"Error combining documents: {str(e)}", exc_info=True)
        raise

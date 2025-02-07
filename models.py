from extensions import db
from datetime import datetime
import json
from sqlalchemy import Index

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    study_plans = db.relationship('StudyPlan', backref='user', lazy=True)
    documents = db.relationship('Document', backref='user', lazy=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class StudyPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # DSA, System Design, Behavioral
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    progress = db.Column(db.Integer, default=0)  # Progress percentage
    completion_target = db.Column(db.DateTime)  # Target completion date

    __table_args__ = (
        Index('idx_study_plan_user_id_created', 'user_id', 'created_at'),
    )

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(50), nullable=False)  # pdf, image, link, text
    content = db.Column(db.Text)  # Raw extracted text content
    structured_content = db.Column(db.Text)  # JSON structured content
    category = db.Column(db.String(50))  # DSA, System Design, Behavioral
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    processed = db.Column(db.Boolean, default=False)

    __table_args__ = (
        Index('idx_document_user_processed', 'user_id', 'processed'),
        Index('idx_document_user_created', 'user_id', 'created_at'),
    )

    def get_structured_content(self):
        """Get structured content as a Python dictionary"""
        try:
            return json.loads(self.structured_content) if self.structured_content else None
        except:
            return None

class ChatHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    related_document_id = db.Column(db.Integer, db.ForeignKey('document.id'))
    related_study_plan_id = db.Column(db.Integer, db.ForeignKey('study_plan.id'))

    __table_args__ = (
        Index('idx_chat_history_user_created', 'user_id', 'created_at'),
    )
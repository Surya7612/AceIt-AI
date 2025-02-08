from extensions import db
from datetime import datetime
import json
from sqlalchemy import Index
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Subscription related fields
    stripe_customer_id = db.Column(db.String(255), unique=True)
    subscription_status = db.Column(db.String(50), default='free')  # free, active, cancelled, expired
    subscription_end_date = db.Column(db.DateTime)

    # Relationships
    subscriptions = db.relationship('Subscription', backref='user', lazy=True)
    study_plans = db.relationship('StudyPlan', backref='user', lazy=True)
    documents = db.relationship('Document', backref='user', lazy=True)
    folders = db.relationship('Folder', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_premium(self):
        """Check if user has an active premium subscription"""
        return (self.subscription_status == 'active' and 
                (self.subscription_end_date is None or 
                 self.subscription_end_date > datetime.utcnow()))

class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    stripe_subscription_id = db.Column(db.String(255), unique=True)
    stripe_price_id = db.Column(db.String(255))
    status = db.Column(db.String(50))  # active, cancelled, expired
    plan_type = db.Column(db.String(50))  # premium
    amount = db.Column(db.Integer)  # Amount in cents
    currency = db.Column(db.String(3), default='USD')
    interval = db.Column(db.String(20))  # month, year
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    end_date = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_subscription_user_status', 'user_id', 'status'),
    )

class StudyPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text)  # JSON field for storing structured content
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    progress = db.Column(db.Integer, default=0)  # Progress percentage
    completion_target = db.Column(db.DateTime)  # Target completion date
    priority = db.Column(db.Integer, default=2)  # 1=High, 2=Medium, 3=Low
    daily_study_time = db.Column(db.Integer)  # Minutes per day
    difficulty_level = db.Column(db.String(20))  # beginner, intermediate, advanced
    last_studied = db.Column(db.DateTime)
    total_study_time = db.Column(db.Integer, default=0)  # Total minutes spent studying

    # Relationships
    documents = db.relationship('Document', secondary='study_plan_documents', 
                           backref=db.backref('study_plans', lazy=True))
    study_sessions = db.relationship('StudySession', backref='study_plan', lazy=True,
                                   cascade='all, delete-orphan')

    def get_content(self):
        """Get parsed content data"""
        try:
            return json.loads(self.content) if self.content else None
        except:
            return None

    def update_content(self, content_data):
        """Update study plan content"""
        self.content = json.dumps(content_data)
        self.updated_at = datetime.utcnow()

class StudySession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    study_plan_id = db.Column(db.Integer, db.ForeignKey('study_plan.id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    duration_minutes = db.Column(db.Integer)  # Duration in minutes
    notes = db.Column(db.Text)  # Optional session notes

    __table_args__ = (
        Index('idx_study_session_plan_start', 'study_plan_id', 'start_time'),
    )

    def complete_session(self, notes=None):
        """Complete the study session and calculate duration"""
        self.end_time = datetime.utcnow()
        self.duration_minutes = int((self.end_time - self.start_time).total_seconds() / 60)
        if notes:
            self.notes = notes
        # Update study plan's total time
        self.study_plan.update_study_time(self.duration_minutes)

# Association table for study plans and documents
study_plan_documents = db.Table('study_plan_documents',
    db.Column('study_plan_id', db.Integer, db.ForeignKey('study_plan.id'), primary_key=True),
    db.Column('document_id', db.Integer, db.ForeignKey('document.id'), primary_key=True)
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

class Folder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('folder.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    parent = db.relationship('Folder', remote_side=[id], backref=db.backref('subfolders', lazy=True))
    study_plans = db.relationship('StudyPlan', secondary='folder_study_plans', backref='folders')
    documents = db.relationship('Document', secondary='folder_documents', backref='folders')

# Association tables for folders
folder_study_plans = db.Table('folder_study_plans',
    db.Column('folder_id', db.Integer, db.ForeignKey('folder.id'), primary_key=True),
    db.Column('study_plan_id', db.Integer, db.ForeignKey('study_plan.id'), primary_key=True)
)

folder_documents = db.Table('folder_documents',
    db.Column('folder_id', db.Integer, db.ForeignKey('folder.id'), primary_key=True),
    db.Column('document_id', db.Integer, db.ForeignKey('document.id'), primary_key=True)
)

class InterviewQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    job_description = db.Column(db.Text, nullable=False)  # Store the job description
    resume_content = db.Column(db.Text)  # Store the resume content
    question = db.Column(db.Text, nullable=False)  # The actual question
    sample_answer = db.Column(db.Text)  # AI-generated sample answer
    category = db.Column(db.String(50))  # Technical, Behavioral, etc.
    difficulty = db.Column(db.String(20))  # Easy, Medium, Hard
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    success_rate = db.Column(db.Float)  # Success rate based on AI analysis

    # Add relationship to User model
    user = db.relationship('User', backref=db.backref('interview_questions', lazy=True))

    __table_args__ = (
        Index('idx_interview_question_user_created', 'user_id', 'created_at'),
    )

class InterviewPractice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('interview_question.id'), nullable=False)
    user_answer = db.Column(db.Text, nullable=False)
    answer_type = db.Column(db.String(20))  # text, audio, or video
    media_url = db.Column(db.String(255))  # URL for audio/video file
    ai_feedback = db.Column(db.Text)  # AI-generated feedback on the answer
    score = db.Column(db.Integer)  # Optional score/rating
    confidence_score = db.Column(db.Float)  # Confidence score from audio/video analysis
    attempt_number = db.Column(db.Integer, default=1)  # Track multiple attempts
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    final_answer = db.Column(db.Boolean, default=False)  # Flag for final answer

    # Add relationships
    question = db.relationship('InterviewQuestion', backref='practices')
    user = db.relationship('User', backref=db.backref('interview_practices', lazy=True))

    __table_args__ = (
        Index('idx_interview_practice_user_created', 'user_id', 'created_at'),
        Index('idx_interview_practice_question_attempt', 'question_id', 'attempt_number'),
    )

    @classmethod
    def get_next_attempt_number(cls, user_id, question_id):
        """Get the next attempt number for a question"""
        latest = cls.query.filter_by(
            user_id=user_id,
            question_id=question_id
        ).order_by(cls.attempt_number.desc()).first()
        return (latest.attempt_number + 1) if latest else 1
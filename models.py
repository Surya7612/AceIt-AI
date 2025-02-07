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
    folders = db.relationship('Folder', backref='user', lazy=True) # Added relationship


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
    priority = db.Column(db.Integer, default=2)  # 1=High, 2=Medium, 3=Low
    daily_study_time = db.Column(db.Integer)  # Minutes per day
    schedule = db.Column(db.Text)  # JSON field for storing study schedule
    difficulty_level = db.Column(db.String(20))  # beginner, intermediate, advanced
    last_studied = db.Column(db.DateTime)  # Track last study session
    total_study_time = db.Column(db.Integer, default=0)  # Total minutes spent studying

    # Relationships with cascade delete
    documents = db.relationship('Document', secondary='study_plan_documents', 
                           backref=db.backref('study_plans', lazy=True))
    study_sessions = db.relationship('StudySession', backref='study_plan', lazy=True,
                                   cascade='all, delete-orphan')  # Add cascade delete

    __table_args__ = (
        Index('idx_study_plan_user_id_created', 'user_id', 'created_at'),
    )

    def get_schedule(self):
        """Get parsed schedule data"""
        try:
            return json.loads(self.schedule) if self.schedule else None
        except:
            return None

    def update_schedule(self, schedule_data):
        """Update study schedule"""
        self.schedule = json.dumps(schedule_data)
        self.updated_at = datetime.utcnow()

    def update_study_time(self, minutes):
        """Update total study time"""
        self.total_study_time += minutes
        self.last_studied = datetime.utcnow()
        # Update progress based on total time vs target time
        if self.daily_study_time:
            target_total = self.daily_study_time * (self.completion_target - self.created_at).days
            self.progress = min(100, int((self.total_study_time / target_total) * 100))

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
    question = db.Column(db.Text, nullable=False)  # The actual question
    sample_answer = db.Column(db.Text)  # AI-generated sample answer
    category = db.Column(db.String(50))  # Technical, Behavioral, etc.
    difficulty = db.Column(db.String(20))  # Easy, Medium, Hard
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    ai_feedback = db.Column(db.Text)  # AI-generated feedback on the answer
    score = db.Column(db.Integer)  # Optional score/rating
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Add relationships
    question = db.relationship('InterviewQuestion', backref='practices')
    user = db.relationship('User', backref=db.backref('interview_practices', lazy=True))

    __table_args__ = (
        Index('idx_interview_practice_user_created', 'user_id', 'created_at'),
    )
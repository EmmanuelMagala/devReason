

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, Integer, BigInteger, Float, Boolean,
    DateTime, ForeignKey, UniqueConstraint, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.db.base import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    clerk_user_id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    repos = relationship("Repo", back_populates="user", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="user")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")


class GitHubConnection(Base):
    __tablename__ = 'github_connections'
    __table_args__ = (UniqueConstraint('clerk_user_id', 'github_user_id'),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clerk_user_id = Column(String, ForeignKey('users.clerk_user_id', ondelete='CASCADE'), nullable=False)
    github_user_id = Column(BigInteger, nullable=False)
    login = Column(String, nullable=False)
    avatar_url = Column(Text)
    access_token_enc = Column(Text, nullable=False)
    refresh_token_enc = Column(Text)
    expires_at = Column(DateTime(timezone=True))
    refresh_expires_at = Column(DateTime(timezone=True))
    status = Column(String, default='connected', nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class GitHubInstallation(Base):
    __tablename__ = 'github_installations'
    __table_args__ = (UniqueConstraint('connection_id', 'installation_id'),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(UUID(as_uuid=True), ForeignKey('github_connections.id', ondelete='CASCADE'), nullable=False)
    installation_id = Column(BigInteger, nullable=False)
    account_login = Column(String, nullable=False)
    status = Column(String, default='connected', nullable=False)


class Repo(Base):
    __tablename__ = "repos"
    __table_args__ = (UniqueConstraint("clerk_user_id", "owner", "name"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clerk_user_id = Column(String, ForeignKey("users.clerk_user_id", ondelete="CASCADE"), nullable=False)
    owner = Column(String, nullable=False)
    name = Column(String, nullable=False)
    github_installation_id = Column(BigInteger, nullable=True)
    github_repo_id = Column(BigInteger, nullable=True)
    details = Column(JSON, default=dict)
    github_token_enc = Column(Text, nullable=True)  # legacy PAT storage; GitHub App flow does not write this
    created_at = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="repos")
    arch_rules = relationship("ArchRule", back_populates="repo", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="repo")
    conversations = relationship("Conversation", back_populates="repo", cascade="all, delete-orphan")


class ArchRule(Base):
    __tablename__ = "arch_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id = Column(UUID(as_uuid=True), ForeignKey("repos.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="approved")
    source = Column(String, nullable=False, default="manual")
    # embedding column added via raw SQL after migration — pgvector not in SQLAlchemy by default
    created_at = Column(DateTime(timezone=True), default=utcnow)

    repo = relationship("Repo", back_populates="arch_rules")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clerk_user_id = Column(String, ForeignKey("users.clerk_user_id"), nullable=False)
    repo_id = Column(UUID(as_uuid=True), ForeignKey("repos.id"), nullable=False)
    pr_url = Column(Text, nullable=True)
    pr_number = Column(Integer, nullable=True)
    mode = Column(String, nullable=False, default='pr')
    branch = Column(String)
    commit_sha = Column(String)
    title = Column(String)
    scope = Column(JSON, default=dict)
    coverage = Column(JSON, default=dict)
    check_outcomes = Column(JSON, default=dict)
    recommendation = Column(String)
    posting_status = Column(String, nullable=False, default='not_requested')
    thread_id = Column(String, unique=True, nullable=False)  # composite crash-recovery key
    status = Column(String, default="pending")
    report_markdown = Column(Text, nullable=True)
    github_comment_url = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="reviews")
    repo = relationship("Repo", back_populates="reviews")
    findings = relationship("Finding", back_populates="review", cascade="all, delete-orphan")


class Finding(Base):
    __tablename__ = "findings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id = Column(UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False)
    repo_id = Column(UUID(as_uuid=True), ForeignKey("repos.id"), nullable=False)
    pr_number = Column(Integer, nullable=True)
    agent = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    type = Column(String, nullable=False)
    file = Column(String, nullable=True)
    line = Column(Integer, nullable=True)
    message = Column(Text, nullable=False)
    suggestion = Column(Text, nullable=True)
    cwe_id = Column(String, nullable=True)
    cvss_score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    review = relationship("Review", back_populates="findings")


class ReviewJob(Base):
    __tablename__ = 'review_jobs'
    __table_args__ = (UniqueConstraint('clerk_user_id','request_key'),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id = Column(UUID(as_uuid=True), ForeignKey('reviews.id', ondelete='CASCADE'), unique=True, nullable=False)
    clerk_user_id = Column(String, ForeignKey('users.clerk_user_id'), nullable=False)
    request_key = Column(String, nullable=False)
    status = Column(String, nullable=False, default='pending', index=True)
    attempts = Column(Integer, nullable=False, default=0)
    lease_token = Column(String)
    lease_until = Column(DateTime(timezone=True))
    cancel_requested = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class ReviewCache(Base):
    __tablename__ = 'review_cache'
    key = Column(String, primary_key=True)
    repo_id = Column(UUID(as_uuid=True), ForeignKey('repos.id', ondelete='CASCADE'), nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("clerk_user_id", "repo_id"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clerk_user_id = Column(String, ForeignKey("users.clerk_user_id", ondelete="CASCADE"), nullable=False)
    repo_id = Column(UUID(as_uuid=True), ForeignKey("repos.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="conversations")
    repo = relationship("Repo", back_populates="conversations")
    messages = relationship("ConversationMessage", back_populates="conversation", cascade="all, delete-orphan", order_by="ConversationMessage.created_at")


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conv_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)   # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    conversation = relationship("Conversation", back_populates="messages")

"""Payments ORM and Pydantic schemas."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class PaymentMethod(str, Enum):
    UPI = "upi"
    CARD = "card"
    WALLET = "wallet"
    COD = "cod"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, nullable=False, index=True)
    customer_id = Column(Integer, nullable=True, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(8), nullable=False, default="INR")
    method = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default=PaymentStatus.PENDING.value)
    gateway_reference = Column(String(120), nullable=True)
    customer_email = Column(String(255), nullable=True)
    customer_phone = Column(String(30), nullable=True)
    failure_reason = Column(String(255), nullable=True)
    notification_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)


class PaymentCreateRequest(BaseModel):
    order_id: int
    amount: float = Field(gt=0)
    method: PaymentMethod
    currency: str = Field(default="INR", min_length=3, max_length=8)
    customer_email: Optional[str] = Field(default=None, max_length=255)
    customer_phone: Optional[str] = Field(default=None, max_length=30)


class PaymentConfirmRequest(BaseModel):
    success: bool = True
    gateway_reference: Optional[str] = Field(default=None, max_length=120)
    failure_reason: Optional[str] = Field(default=None, max_length=255)


class PaymentResponse(BaseModel):
    id: int
    order_id: int
    customer_id: Optional[int]
    amount: float
    currency: str
    method: str
    status: str
    gateway_reference: Optional[str]
    customer_email: Optional[str]
    customer_phone: Optional[str]
    failure_reason: Optional[str]
    notification_id: Optional[int]
    created_at: datetime
    confirmed_at: Optional[datetime]

    class Config:
        from_attributes = True

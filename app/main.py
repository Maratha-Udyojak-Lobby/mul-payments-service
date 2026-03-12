from datetime import datetime
import os
from typing import Optional

import httpx
import jwt
from fastapi import FastAPI, Depends, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.database import get_db, init_db
from app.models import (
    Payment,
    PaymentConfirmRequest,
    PaymentCreateRequest,
    PaymentResponse,
    PaymentStatus,
)

init_db()

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "mul-super-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
NOTIFICATIONS_SERVICE_URL = os.getenv(
    "NOTIFICATIONS_SERVICE_URL",
    "http://127.0.0.1:8106",
)

app = FastAPI(
    title="MUL Payments Service",
    version="1.0.0",
    description="Payment processing and transaction management",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _decode_user_id(authorization: Optional[str]) -> Optional[int]:
    if not authorization:
        return None

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    try:
        payload = jwt.decode(parts[1], JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return int(payload.get("sub", 0)) or None
    except jwt.InvalidTokenError:
        return None


def _require_user_id(authorization: Optional[str]) -> int:
    user_id = _decode_user_id(authorization)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user_id


async def _send_payment_notification(payment: Payment) -> int | None:
    recipient = payment.customer_email or payment.customer_phone
    if not recipient:
        return None

    message = (
        f"Payment {payment.status} for order #{payment.order_id}. "
        f"Amount: {payment.amount} {payment.currency}."
    )

    payload = {
        "recipient": recipient,
        "type": "email" if payment.customer_email else "sms",
        "subject": "Payment Confirmation" if payment.status == "succeeded" else "Payment Failed",
        "message": message,
        "source_service": "payments-service",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{NOTIFICATIONS_SERVICE_URL}/api/v1/notifications/send",
                json=payload,
            )
            if response.status_code >= 400:
                return None
            return response.json().get("id")
    except Exception:
        return None


@app.on_event("startup")
async def startup_event() -> None:
    init_db()


@app.get("/", summary="Payments Service Root")
async def root() -> dict[str, str]:
    return {"message": "MUL Payments Service is running"}


@app.get("/health", summary="Health Check")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "payments-service"}


@app.post(
    "/api/v1/payments/create",
    summary="Create Payment",
    response_model=PaymentResponse,
    status_code=201,
)
async def create_payment(
    payload: PaymentCreateRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> PaymentResponse:
    user_id = _require_user_id(authorization)

    payment = Payment(
        order_id=payload.order_id,
        customer_id=user_id,
        amount=payload.amount,
        currency=payload.currency.upper(),
        method=payload.method.value,
        status=PaymentStatus.PENDING.value,
        customer_email=payload.customer_email,
        customer_phone=payload.customer_phone,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


@app.post(
    "/api/v1/payments/{payment_id}/confirm",
    summary="Confirm Payment",
    response_model=PaymentResponse,
)
async def confirm_payment(
    payment_id: int,
    payload: PaymentConfirmRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> PaymentResponse:
    _require_user_id(authorization)

    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    payment.status = PaymentStatus.SUCCEEDED.value if payload.success else PaymentStatus.FAILED.value
    payment.gateway_reference = payload.gateway_reference
    payment.failure_reason = payload.failure_reason
    payment.confirmed_at = datetime.utcnow()

    notification_id = await _send_payment_notification(payment)
    if notification_id:
        payment.notification_id = notification_id

    db.commit()
    db.refresh(payment)
    return payment


@app.get(
    "/api/v1/payments/{payment_id}",
    summary="Get Payment",
    response_model=PaymentResponse,
)
async def get_payment(
    payment_id: int,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> PaymentResponse:
    user_id = _require_user_id(authorization)
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.customer_id is not None and payment.customer_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return payment


@app.get(
    "/api/v1/payments",
    summary="List Payments",
    response_model=list[PaymentResponse],
)
async def list_payments(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> list[PaymentResponse]:
    user_id = _require_user_id(authorization)
    return (
        db.query(Payment)
        .filter(Payment.customer_id == user_id)
        .order_by(Payment.created_at.desc())
        .limit(100)
        .all()
    )

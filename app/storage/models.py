from sqlalchemy import String, Integer, ForeignKey, DateTime, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.storage.db import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    contact: Mapped[str | None] = mapped_column(String(128), nullable=True)

    bookings: Mapped[list["Booking"]] = relationship(back_populates="user", cascade="all,delete-orphan")

class Slot(Base):
    __tablename__ = "slots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # начало слота (локальное время TZ из настроек)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), index=True, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    booking: Mapped["Booking"] = relationship(back_populates="slot", uselist=False)

class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    slot_id: Mapped[int] = mapped_column(ForeignKey("slots.id", ondelete="CASCADE"), unique=True)

    student_name: Mapped[str] = mapped_column(String(128))
    student_contact: Mapped[str] = mapped_column(String(128))

    remind_24h_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    remind_1h_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="bookings")
    slot: Mapped["Slot"] = relationship(back_populates="booking")

    __table_args__ = (
        UniqueConstraint("slot_id", name="uq_booking_slot"),
    )
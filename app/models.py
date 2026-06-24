from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class LanguageEnum(str, PyEnum):
    UZ = "uz"
    RU = "ru"
    EN = "en"


class BookLanguageEnum(str, PyEnum):
    UZ = "uz"
    RU = "ru"
    EN = "en"
    ALL = "all"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    language: Mapped[str] = mapped_column(
        Enum(LanguageEnum, name="languageenum"), nullable=False, default=LanguageEnum.RU
    )
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    ratings: Mapped[list["Rating"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    download_history: Mapped[list["DownloadHistory"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User telegram_id={self.telegram_id} lang={self.language}>"


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=True, index=True
    )
    name_uz: Mapped[str] = mapped_column(String(128), nullable=False)
    name_ru: Mapped[str] = mapped_column(String(128), nullable=False)
    name_en: Mapped[str] = mapped_column(String(128), nullable=False)
    emoji: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    books: Mapped[list["Book"]] = relationship(back_populates="category")
    parent: Mapped[Optional["Category"]] = relationship(
        remote_side=[id], back_populates="children"
    )
    children: Mapped[list["Category"]] = relationship(back_populates="parent")

    def get_name(self, lang: str) -> str:
        return getattr(self, f"name_{lang}", self.name_ru)

    def __repr__(self) -> str:
        return f"<Category slug={self.slug}>"


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    author: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    description_uz: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description_ru: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description_en: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    telegram_file_id: Mapped[str] = mapped_column(
        String(256), unique=True, nullable=False
    )
    file_size_kb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cover_file_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    language: Mapped[str] = mapped_column(
        Enum(BookLanguageEnum, name="booklanguageenum"),
        nullable=False,
        default=BookLanguageEnum.RU,
    )
    category_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_bestseller: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_rating: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rating_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    category: Mapped[Optional["Category"]] = relationship(back_populates="books")
    ratings: Mapped[list["Rating"]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )
    download_history: Mapped[list["DownloadHistory"]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )
    weekly_tops: Mapped[list["WeeklyTop"]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )

    def get_description(self, lang: str) -> Optional[str]:
        return getattr(self, f"description_{lang}", self.description_ru)

    def __repr__(self) -> str:
        return f"<Book id={self.id} title={self.title!r}>"


class Rating(Base):
    __tablename__ = "ratings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    book_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "book_id", name="uq_rating_user_book"),
        CheckConstraint("score >= 1 AND score <= 5", name="ck_rating_score"),
    )

    user: Mapped["User"] = relationship(back_populates="ratings")
    book: Mapped["Book"] = relationship(back_populates="ratings")

    def __repr__(self) -> str:
        return f"<Rating user={self.user_id} book={self.book_id} score={self.score}>"


class DownloadHistory(Base):
    __tablename__ = "download_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    book_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    downloaded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="download_history")
    book: Mapped["Book"] = relationship(back_populates="download_history")

    def __repr__(self) -> str:
        return f"<DownloadHistory user={self.user_id} book={self.book_id}>"


class WeeklyTop(Base):
    __tablename__ = "weekly_top"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    week_start: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    avg_score: Mapped[float] = mapped_column(Float, nullable=False)
    vote_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("book_id", "week_start", name="uq_weekly_top_book_week"),
    )

    book: Mapped["Book"] = relationship(back_populates="weekly_tops")

    def __repr__(self) -> str:
        return (
            f"<WeeklyTop book={self.book_id} week={self.week_start} rank={self.rank}>"
        )

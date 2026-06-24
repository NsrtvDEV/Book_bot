from starlette_admin.contrib.sqla import ModelView


class UserAdminView(ModelView):
    fields = [
        "id",
        "telegram_id",
        "username",
        "full_name",
        "language",
        "is_banned",
        "created_at",
        "updated_at",
    ]

    exclude_fields_from_list = ["created_at", "updated_at"]
    exclude_fields_from_create = ["id", "created_at", "updated_at"]
    exclude_fields_from_edit = ["id", "telegram_id", "created_at", "updated_at"]


class CategoryAdminView(ModelView):
    fields = [
        "id",
        "parent",
        "name_ru",
        "name_uz",
        "name_en",
        "emoji",
        "sort_order",
        "is_active",
    ]

    exclude_fields_from_create = ["id"]
    exclude_fields_from_edit = ["id"]


class BookAdminView(ModelView):
    fields = [
        "id",
        "category",
        "title",
        "author",
        "language",
        "telegram_file_id",
        "cover_file_id",
        "file_size_kb",
        "description_ru",
        "description_uz",
        "description_en",
        "avg_rating",
        "rating_count",
        "download_count",
        "is_bestseller",
        "is_active",
        "created_at",
        "updated_at",
    ]

    exclude_fields_from_list = [
        "description_ru",
        "description_uz",
        "description_en",
        "telegram_file_id",
        "cover_file_id",
        "created_at",
        "updated_at",
    ]
    exclude_fields_from_create = [
        "id",
        "avg_rating",
        "rating_count",
        "download_count",
        "telegram_file_id",
        "cover_file_id",
        "file_size_kb",
        "created_at",
        "updated_at",
    ]
    exclude_fields_from_edit = [
        "id",
        "avg_rating",
        "rating_count",
        "download_count",
        "created_at",
        "updated_at",
    ]


class RatingAdminView(ModelView):
    fields = ["id", "user", "book", "score", "created_at"]

    exclude_fields_from_create = ["id", "created_at"]
    exclude_fields_from_edit = ["id", "user", "book", "created_at"]


class DownloadHistoryAdminView(ModelView):
    fields = ["id", "user", "book", "downloaded_at"]

    exclude_fields_from_create = ["id", "downloaded_at"]
    exclude_fields_from_edit = ["id", "user", "book", "downloaded_at"]


class WeeklyTopAdminView(ModelView):
    fields = [
        "id",
        "book",
        "week_start",
        "rank",
        "avg_score",
        "vote_count",
    ]

    exclude_fields_from_create = ["id"]
    exclude_fields_from_edit = ["id", "book", "week_start"]

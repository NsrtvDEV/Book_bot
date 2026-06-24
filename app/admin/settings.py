from starlette_admin.contrib.sqla import Admin

from app.database import engine
from app.models import (
    User,
    Category,
    Book,
    Rating,
    DownloadHistory,
    WeeklyTop,
)

from app.admin.views import (
    UserAdminView,
    CategoryAdminView,
    BookAdminView,
    RatingAdminView,
    DownloadHistoryAdminView,
    WeeklyTopAdminView,
)


admin = Admin(engine=engine, title="Book Bot admin", base_url="/admin")

admin.add_view(UserAdminView(User, icon="fa fa-user"))
admin.add_view(CategoryAdminView(Category, icon="fa fa-folder"))
admin.add_view(BookAdminView(Book, icon="fa fa-book"))
admin.add_view(RatingAdminView(Rating, icon="fa fa-star"))
admin.add_view(DownloadHistoryAdminView(DownloadHistory, icon="fa fa-download"))
admin.add_view(WeeklyTopAdminView(WeeklyTop, icon="fa fa-trophy"))

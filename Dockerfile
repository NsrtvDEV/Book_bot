FROM python:3.13-slim

WORKDIR /app

COPY . .

RUN pip install fastapi uvicorn aiogram alembic asyncpg python-dotenv sqlalchemy starlette-admin

CMD ["python", "-m", "app.main"]
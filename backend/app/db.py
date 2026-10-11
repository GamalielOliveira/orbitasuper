import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://daki:daki_dev@localhost:5432/daki")
engine = create_engine(DATABASE_URL)

class Base(DeclarativeBase):
    pass

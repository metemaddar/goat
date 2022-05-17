from email.policy import default
from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, Integer, String, ARRAY
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

    scenarios = relationship("Scenario", back_populates="user", cascade="all, delete")

class Scenario(Base):
    __tablename__ = "scenarios"
    id = Column(BigInteger, primary_key=True, index=True)
    name = Column(String)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    user = relationship("User", back_populates="scenarios")

    deleted_ways = Column(ARRAY(BigInteger), default=dict)
    deleted_pois = Column(ARRAY(BigInteger), default=dict)
    deleted_buildings = Column(ARRAY(BigInteger), default=dict)
    ways_heatmap_computed = Column(Boolean)

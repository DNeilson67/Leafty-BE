from sqlalchemy import Column, Integer, String, Text, ForeignKey, Float, DateTime, Enum, BigInteger, Table, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, String, ForeignKey, UUID, Boolean

Base = declarative_base()

# Association table for many-to-many relationship between Shipments and Flour
shipment_flour_association = Table(
    'shipment_flour_association', Base.metadata,
    Column('shipment_id', Integer, ForeignKey('shipments.ShipmentID')),
    Column('flour_id', Integer, ForeignKey('flour.FlourID'))
)

class SessionData(Base):
    __tablename__ = "sessions"

    session_id = Column(String(36), unique=True, primary_key=True)
    user_id = Column(String(36), ForeignKey('users.UserID'))
    user_role = Column(Integer, ForeignKey('roles.RoleID'))
    user_email = Column(String(36))

class OTP(Base):
    __tablename__ = "otp"

    email = Column(String, primary_key=True, index=True)
    otp_code = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False, default=func.now())

class RoleModel(Base):
    __tablename__ = "roles"
    
    RoleID = Column(Integer, primary_key=True)
    RoleName = Column(String(50))

class User(Base):
    __tablename__ = "users"

    UserID = Column(String(36), primary_key=True) 
    Username = Column(String(50))
    Email = Column(String(100), unique=True)
    PhoneNumber = Column(BigInteger)
    Password = Column(String(100))
    RoleID = Column(Integer, ForeignKey('roles.RoleID'))
    role = relationship("RoleModel")

class Location(Base):
    __tablename__ = "locations"

    LocationID = Column(Integer, primary_key=True, autoincrement=True)
    LocationAddress = Column(String(100))
    Latitude = Column(Float, nullable=False)
    Longitude = Column(Float, nullable=False)

class Courier(Base):
    __tablename__ = "couriers"
    
    CourierID = Column(Integer, primary_key=True, autoincrement=True) 
    CourierName = Column(String(50), nullable=False)

class WetLeaves(Base):
    __tablename__ = "wet_leaves"

    WetLeavesID = Column(Integer, primary_key=True, autoincrement=True)
    UserID = Column(String(36), ForeignKey("users.UserID"))
    Weight = Column(Float)
    ReceivedTime = Column(DateTime)
    Expiration = Column(DateTime)
    Status = Column(String(50), default="Awaiting")

class DryLeaves(Base):
    __tablename__ = "dry_leaves"

    DryLeavesID = Column(Integer, primary_key=True, autoincrement=True)
    UserID = Column(String(36), ForeignKey("users.UserID"))
    WetLeavesID = Column(Integer, ForeignKey("wet_leaves.WetLeavesID"))
    Processed_Weight = Column(Float)
    Expiration = Column(DateTime, nullable=True)
    Status = Column(String(50), default="Awaiting")

class Flour(Base):
    __tablename__ = "flour"

    FlourID = Column(Integer, primary_key=True, autoincrement=True)
    DryLeavesID = Column(Integer, ForeignKey("dry_leaves.DryLeavesID"))
    UserID = Column(String(36), ForeignKey("users.UserID"))
    Flour_Weight = Column(Float)
    Expiration = Column(DateTime, nullable=True)
    Status = Column(String(50), default="Awaiting")

class Shipment(Base):
    __tablename__ = "shipments"

    ShipmentID = Column(Integer, primary_key=True, autoincrement=True)
    CourierID = Column(Integer, ForeignKey("couriers.CourierID"))
    UserID = Column(String(36), ForeignKey("users.UserID"))
    ShipmentQuantity = Column(Integer)
    ShipmentDate = Column(DateTime, nullable=True)
    Check_in_Date = Column(DateTime, nullable=True)
    Check_in_Quantity = Column(Integer, nullable=True)
    Harbor_Reception_File = Column(Boolean,nullable=True)
    Rescalled_Weight = Column(Float, nullable=True)
    Rescalled_Date = Column(DateTime, nullable=True)
    Centra_Reception_File = Column(Boolean,nullable=True)
    
    flours = relationship("Flour", secondary=shipment_flour_association, backref="shipments")
    
 # marketplace shenanigans

class AdminSetting(Base):
    __tablename__ = 'admin_settings'
    
    AdminSettingsID = Column(Integer, primary_key=True)
    AdminFee = Column(Integer, nullable=False)

    # Relationship with Settings
    settings = relationship("Settings", back_populates="admin_settings")


class WetLeavesDiscount(Base):
    __tablename__ = 'wet_leaves_discount'
    
    WetLeavesDiscountID = Column(Integer, primary_key=True)
    WetLeavesDiscountRate = Column(Integer, nullable=False)
    WetLeavesExpirationCondition = Column(String, nullable=False)

    # Relationship with Settings
    settings = relationship("Settings", back_populates="wet_leaves_discount")


class DryLeavesDiscount(Base):
    __tablename__ = 'dry_leaves_discount'
    
    DryLeavesDiscountID = Column(Integer, primary_key=True)
    DryLeavesDiscountRate = Column(Integer, nullable=False)
    DryLeavesExpirationCondition = Column(String, nullable=False)

    # Relationship with Settings
    settings = relationship("Settings", back_populates="dry_leaves_discount")


class PowderDiscount(Base):
    __tablename__ = 'powder_discount'
    
    PowderDiscountID = Column(Integer, primary_key=True)
    PowderDiscountRate = Column(Integer, nullable=False)
    PowderExpirationCondition = Column(String, nullable=False)

    # Relationship with Settings
    settings = relationship("Settings", back_populates="powder_discount")


class Settings(Base):
    __tablename__ = 'settings'
    
    SettingsID = Column(Integer, primary_key=True)
    WetLeavesPrice = Column(Integer, nullable=False, default=15.000)
    DryLeavesPrice = Column(Integer, nullable=False)
    PowderPrice = Column(Integer, nullable=False)
    WetLeavesDiscountID = Column(Integer, ForeignKey('wet_leaves_discount.WetLeavesDiscountID'), nullable=False)
    DryLeavesDiscountID = Column(Integer, ForeignKey('dry_leaves_discount.DryLeavesDiscountID'), nullable=False)
    PowderDiscountID = Column(Integer, ForeignKey('powder_discount.PowderDiscountID'), nullable=False)
    AdminSettingsID = Column(Integer, ForeignKey('admin_settings.AdminSettingsID'), nullable=True)

    # Relationships with the other tables
    wet_leaves_discount = relationship("WetLeavesDiscount", back_populates="settings")
    dry_leaves_discount = relationship("DryLeavesDiscount", back_populates="settings")
    powder_discount = relationship("PowderDiscount", back_populates="settings")
    admin_settings = relationship("AdminSetting", back_populates="settings")
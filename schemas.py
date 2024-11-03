from pydantic import BaseModel, UUID4
from typing import Optional, List
from datetime import datetime


class GenerateOTPRequest(BaseModel):
    email: str

# Model for verifying OTP request
class VerifyOTPRequest(BaseModel):
    email: str
    otp_code: str
    
class RoleBase(BaseModel):
    RoleName: str
    
class SessionData(BaseModel):
    user_id: str
    user_role: int
    user_email: str

class OTPBase(BaseModel):
    email: str
    otp_code: str
    expires_at: datetime

class OTPCreate(OTPBase):
    pass

class OTP(OTPBase):
    class Config:
        orm_mode = True

class RoleCreate(RoleBase):
    pass

class Role(RoleBase):
    RoleID: int

    class Config:
        orm_mode = True

class UserBase(BaseModel):
    Username: str
    Email: str
    PhoneNumber: Optional[int]
    RoleID: int
    Password: str

class UserCreate(UserBase):
    Password: str
    
class UserRoleUpdate(BaseModel):
    RoleName: str
  
class UserPhoneUpdate(BaseModel):
    PhoneNumber: int

class UserUpdate(BaseModel):
    Password: Optional[str] = None
    Username: Optional[str] = None
    Email: Optional[str] = None
    
class AdminUserUpdate(BaseModel):
    Username: Optional[str] 
    Email: Optional[str] 
    PhoneNumber: Optional[int] 
    RoleName: Optional[str] 

class User(UserBase):
    UserID: UUID4
    role: Role

    class Config:
        orm_mode = True

class LocationBase(BaseModel):
    LocationAddress: str
    Latitude: float
    Longitude: float

class LocationCreate(LocationBase):
    pass

class Location(LocationBase):
    LocationID: int

    class Config:
        orm_mode = True

class CourierBase(BaseModel):
    CourierName: str

class CourierCreate(CourierBase):
    pass

class Courier(CourierBase):
    CourierID: int

    class Config:
        orm_mode = True

class DryLeavesBase(BaseModel):
    UserID: UUID4
    WetLeavesID: int
    Processed_Weight: Optional[float]
    Expiration: Optional[datetime]
    Status: Optional[str] = "Awaiting"

class DryLeavesCreate(DryLeavesBase):
    pass

class DryLeaves(DryLeavesBase):
    DryLeavesID: int

    class Config:
        orm_mode = True

class DryLeavesUpdate(BaseModel):
    Weight: float
    Expiration: Optional[datetime] = None
    
class DryLeavesStatusUpdate(BaseModel):
    Status: str

class WetLeavesBase(BaseModel):
    UserID: UUID4
    Weight: float
    ReceivedTime: datetime
    Expiration: datetime
    Status: Optional[str] = "Awaiting"

class WetLeavesCreate(WetLeavesBase):
    pass

class WetLeaves(WetLeavesBase):
    WetLeavesID: int

    class Config:
        orm_mode = True

class WetLeavesUpdate(BaseModel):
    Weight: float
    Expiration: Optional[datetime] = None
    
class WetLeavesStatusUpdate(BaseModel):
    Status: str

class FlourBase(BaseModel):
    UserID: UUID4
    DryLeavesID: int
    Flour_Weight: float
    Expiration: Optional[datetime]
    Status: Optional[str] = "Awaiting"

class FlourCreate(FlourBase):
    pass

class Flour(FlourBase):
    FlourID: int

    class Config:
        orm_mode = True
        
class FlourUpdate(BaseModel):
    Weight: float
    Expiration: Optional[datetime] = None
    
class FlourStatusUpdate(BaseModel):
    Status: str

class ShipmentBase(BaseModel):
    CourierID: int
    UserID: UUID4
    FlourIDs: List[int]  # Modified to accept a list of Flour IDs
    ShipmentQuantity: int
    ShipmentDate: Optional[datetime] = None 
    Check_in_Date: Optional[datetime]= None
    Check_in_Quantity: Optional[int]= None
    Harbor_Reception_File: Optional[bool]= None
    Rescalled_Weight: Optional[float]= None
    Rescalled_Date: Optional[datetime]= None
    Centra_Reception_File: Optional[bool]= None

class ShipmentCreate(ShipmentBase):
    pass

class ShipmentUpdate(BaseModel):
    CourierID: Optional[int] = None
    FlourIDs: Optional[List[int]] = None  # Modified to accept a list of Flour IDs
    ShipmentQuantity: Optional[int] = None
    Check_in_Quantity: Optional[int] = None
    Harbor_Reception_File: Optional[str] = None
    Rescalled_Weight: Optional[float] = None
    Centra_Reception_File: Optional[str] = None
    
class Shipment(ShipmentBase):
    ShipmentID: int

class ShipmentDateUpdate(BaseModel):
    ShipmentDate: Optional[datetime] = None

class ShipmentCheckInUpdate(BaseModel):
    Check_in_Date: Optional[datetime] = None
    Check_in_Quantity: Optional[int] = None
    
class ShipmentRescalledWeightUpdate(BaseModel):
    Rescalled_Weight: Optional[float] = None
    Rescalled_Date: Optional[datetime] = None

class ShipmentHarborReceptionUpdate(BaseModel):
    Harbor_Reception_File: Optional[bool] = None

class ShipmentCentraReceptionUpdate(BaseModel):
    Centra_Reception_File: Optional[bool] = None
    
class ShipmentFlourAssociationBase(BaseModel):
    shipment_id: int
    flour_id: int

class ShipmentFlourAssociationCreate(ShipmentFlourAssociationBase):
    pass

class ShipmentFlourAssociation(ShipmentFlourAssociationBase):

    class Config:
        orm_mode = True
        
        
# marketplace stuff

# Base model for AdminSettings
class AdminSettingsBase(BaseModel):
    AdminFeeValue: float

class AdminSettingsCreate(AdminSettingsBase):
    pass

class AdminSettings(AdminSettingsBase):
    AdminSettingsID: int

    class Config:
        orm_mode = True



# Base model for Products
class ProductsBase(BaseModel):
    ProductName: str

class ProductsCreate(ProductsBase):
    pass

class Products(ProductsBase):
    ProductID: int

    class Config:
        orm_mode = True

# Base model for CentraInitialPrice
class CentraInitialPriceBase(BaseModel):
    UserID: UUID4
    ProductID: int
    InitialPrice: float

class CentraInitialPriceCreate(CentraInitialPriceBase):
    pass

class CentraInitialPrice(CentraInitialPriceBase):
    InitialPriceID: int
    products: Optional[Products]  # Relationship with Products model

    class Config:
        orm_mode = True

# Base model for CentraSettingDetail
class CentraSettingDetailBase(BaseModel):
    UserID: UUID4
    ProductID: int
    DiscountConditionID: int

class CentraSettingDetailCreate(CentraSettingDetailBase):
    pass

class CentraSettingDetail(CentraSettingDetailBase):
    SettingDetailID: int
    products: Optional[Products]  # Relationship with Products model
    discount_condition: Optional["DiscountCondition"]  # Relationship with DiscountCondition model

    class Config:
        orm_mode = True

# Base model for DiscountCondition
class DiscountConditionBase(BaseModel):
    DiscountRate: int
    ExpDayLeft: int

class DiscountConditionCreate(DiscountConditionBase):
    pass

class DiscountCondition(DiscountConditionBase):
    DiscountConditionID: int

    class Config:
        orm_mode = True
        
class MarketShipmentBase(BaseModel):
    CentraID: UUID4
    CustomerID: UUID4
    DryLeavesID: int
    PowderID: int
    status: str

class MarketShipmentCreate(MarketShipmentBase):
    pass

class MarketShipmentUpdate(BaseModel):
    CentraID: Optional[UUID4] = None
    CustomerID: Optional[UUID4] = None
    DryLeavesID: Optional[int] = None
    PowderID: Optional[int] = None
    status: Optional[str] = None

class MarketShipment(MarketShipmentBase):
    MarketShipmentID: int

    class Config:
        orm_mode = True

class SubTransactionBase(BaseModel):
    MarketShipmentID: int
    status: str

class SubTransactionCreate(SubTransactionBase):
    pass

class SubTransactionUpdate(BaseModel):
    MarketShipmentID: Optional[int] = None
    status: Optional[str] = None

class SubTransaction(SubTransactionBase):
    SubTransactionID: int

    class Config:
        orm_mode = True

from pydantic import BaseModel
from typing import Optional

# TransactionCreate schema
class TransactionCreate(BaseModel):
    SubTransactionID: int
    status: str

# TransactionUpdate schema
class TransactionUpdate(BaseModel):
    SubTransactionID: Optional[int] = None
    status: Optional[str] = None

# Transaction schema (for returning Transaction data)
class Transaction(BaseModel):
    TransactionID: int
    SubTransactionID: int
    status: str
    
    class Config:
        orm_mode = True

#xendit
class InvoiceRequest(BaseModel):
    external_id: str
    amount: int
    payer_email: str
    description: str
    success_redirect_url: str
    failure_redirect_url: str

class CityCreate(BaseModel):
    key: str
    name: str
    lat: float
    lng: float

class City(CityCreate):
    class Config:
        orm_mode = True
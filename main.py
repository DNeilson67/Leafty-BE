from fastapi import FastAPI, HTTPException, Depends, Request, Response, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List
import uvicorn
import uuid
from BasicVerifier import BasicVerifier
from fastapi_sessions.backends.implementations import InMemoryBackend
from schemas import User, SessionData
from uuid import UUID, uuid4
from fastapi.middleware.cors import CORSMiddleware
import crud
import requests
import base64
import models
import schemas
from schemas import InvoiceRequest
import bcrypt
from typing import List, Union, Dict
from database import SessionLocal, engine
from fastapi_sessions.frontends.implementations import SessionCookie, CookieParameters
from fastapi_sessions.session_verifier import SessionVerifier

models.Base.metadata.create_all(bind=engine)
import pyotp
from datetime import datetime, timedelta    
import smtplib
from dotenv import load_dotenv
import os
app = FastAPI()

backend = InMemoryBackend[UUID, SessionData]()

verifier = BasicVerifier(
    identifier="general_verifier",
    auto_error=True,
    backend=backend,
    auth_http_exception=HTTPException(status_code=404, detail="invalid session"),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8000", "https://leafty-be.vercel.app", "https://leafty.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def db_session_middleware(request: Request, call_next):
    response = Response("Internal server error", status_code=500)
    try:
        request.state.db = SessionLocal()
        response = await call_next(request)
    finally:
        request.state.db.close()
    return response

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

cookie_params = CookieParameters(
    secure=True,  # Ensures cookie is sent over HTTPS
    httponly=True,
    samesite="none"  # Allows the cookie to be sent with cross-origin requests
)

cookie = SessionCookie(
    cookie_name="session",
    identifier="general_verifier",
    auto_error=True,
    secret_key="DONOTUSE",
    cookie_params=cookie_params,
)

def format_large_number(number):
    if number < 1000:
        return str(number)
    elif number < 1_000_000:
        return f"{number // 1000},{number % 1000}k"
    else:
        return f"{number // 1_000_000},{(number // 1000) % 1000}m"
    
# Sessions
@app.post("/create_session/{user_id}", tags=["Sessions"])
async def create_session(user_id: str, response: Response, db: Session = Depends(get_db)):
    session = uuid4()
    user = crud.get_user_by_id(db, user_id)
    data = SessionData(user_id=user_id, user_role=user.RoleID, user_email=user.Email)

    await backend.create(session, data)
    cookie.attach_to_response(response, session)

    response.headers["Set-Cookie"] += "; SameSite=None"

    crud.create_session(db, session, user_id)

    return f"created session for {user_id}"


@app.get("/whoami", dependencies=[Depends(cookie)], tags=["Sessions"])
async def whoami(session_data: SessionData = Depends(verifier)):
    return session_data


@app.delete("/delete_session", dependencies=[Depends(cookie)], tags=["Sessions"])
async def del_session(response: Response, session_id: UUID = Depends(cookie), db: Session = Depends(get_db)):
    await backend.delete(session_id)
    cookie.delete_from_response(response)

    response.headers["Set-Cookie"] += "; SameSite=None"

    crud.delete_session(db)

    return "deleted session"

# OTP
@app.post("/generate_otp", tags=["OTP"])
def generate_otp(request: schemas.GenerateOTPRequest, db: Session = Depends(get_db)):
    email = request.email
    
    secret = pyotp.random_base32()
    otp = pyotp.TOTP(secret)
    otp_code = otp.now()

    db_otp = crud.get_otp_by_email(db, email)    
    if db_otp:
        crud.delete_otp(db, email)

    hashed_otp_code = bcrypt.hashpw(otp_code.encode('utf-8'), bcrypt.gensalt())

    otp_create = schemas.OTPCreate(email=email, otp_code=hashed_otp_code, expires_at=datetime.now() + timedelta(minutes=2))
    crud.create_otp(db, otp_create)

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()

    load_dotenv()
    USER_EMAIL = os.getenv("EMAIL")
    USER_PASSWORD = os.getenv("PASSWORD")
    
    server.login(USER_EMAIL, USER_PASSWORD)

    body = f"Your OTP is {otp_code}."
    subject = "OTP verification using python" 
    message = f'subject:{subject}\n\n{body}'

    server.sendmail(USER_EMAIL, email, message)
    server.quit()

    print(f"OTP has been sent to {email}")
    print(f"Generated OTP code for {email}: {otp_code}")

    return {"message": "OTP generated and sent to your email"}

# Endpoint to verify OTP
@app.post("/verify_otp", tags=["OTP"])
def verify_otp(request: schemas.VerifyOTPRequest, db: Session = Depends(get_db)):
    email = request.email
    otp_code = request.otp_code

    db_otp = crud.get_otp_by_email(db, email)
    if not db_otp or not bcrypt.checkpw(otp_code.encode('utf-8'), db_otp.otp_code.encode('utf-8')) or db_otp.expires_at < datetime.now():
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    
    # OTP is valid, delete it from the database
    crud.delete_otp(db, email)
    
    return {"message": "OTP verified successfully"}


#xendit
XENDIT_API_KEY = "xnd_development_QCHmJq3EpTsy8EGpbxiB20PObQSLsqJ0DyakCrIpgtoH3MPMim6hEmgq83okM"
encoded_api_key = base64.b64encode(f"{XENDIT_API_KEY}:".encode()).decode()

@app.post("/create_invoice")
async def create_invoice(invoice_request: InvoiceRequest):
    url = "https://api.xendit.co/v2/invoices"
    headers = {
        "Authorization": f"Basic {encoded_api_key}"
    }
    data = invoice_request.dict()  

    try:
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"Error creating Xendit invoice: {e}")
        raise HTTPException(status_code=500, detail="Error creating invoice with Xendit")
    
# Roles
@app.post("/role/post", response_model=schemas.Role, tags=["Roles"])
def create_role(role: schemas.RoleCreate, db: Session = Depends(get_db)):
    return crud.create_role(db=db, role=role)

@app.get("/roles/get", response_model=List[schemas.RoleBase], tags=["Roles"])
def get_roles(db: Session = Depends(get_db)):
    return crud.get_roles(db=db)

@app.delete("/roles/delete/{role_id}", response_class=JSONResponse, tags=["Roles"])
def delete_user(role_id: str, db: Session = Depends(get_db)):
    deleted = crud.delete_role_by_id(db, role_id)
    if deleted:
        return {"message": "Role deleted successfully"}
    else:
        return {"message": "Role not found or deletion failed"}

# Users
@app.post('/user/post', response_model=schemas.User, tags=["Users"])
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # Check if role exists, if not, return error
    role = crud.get_role(db, role_id=user.RoleID)
    if not role:
        raise HTTPException(status_code=400, detail="Role does not exist")

    # Create a new user
    return crud.create_user(db=db, user=user)

@app.get("/user/get", response_model=List[schemas.User], tags=["Users"])
def get_users(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    print(f"Fetching users with skip={skip}, limit={limit}")
    users = crud.get_users(db, skip=skip, limit=limit)
    print(f"Fetched {len(users)} users")
    return users

@app.get("/user/count", response_model=int, tags=["Users"])
def get_user_count(db: Session = Depends(get_db)):
    count = crud.get_user_count(db)
    print(f"Total user count: {count}")
    return count

@app.get("/user/get_role/{role_id}", response_model=List[schemas.User], tags=["Users"])
def get_user(role_id: int, db: Session = Depends(get_db)):
    role = crud.get_user_by_role(db, role_id)
    if not role:
        raise HTTPException(status_code=400, detail="Role does not exist")
    else:
        users = crud.get_user_by_role(db, role_id)
        return users

@app.get("/user/get_user/{user_id}", response_model=schemas.User, tags=["Users"])
def get_user(user_id: str, db: Session = Depends(get_db)):
    user = crud.get_user_by_id(db, user_id)
    return user

@app.get("/user/get_user_email/{email}", response_model=schemas.User, tags=["Users"])
def get_user(email: str, db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, email)
    return user

@app.get('/users_with_shipments', tags=["Users", "Shipment"])
def get_users_with_shipments(db: Session = Depends(get_db)):
    users = crud.get_users_with_shipments(db)
    return users

@app.put('/user/put/{user_id}', response_model=schemas.UserUpdate, tags=["Users"])
def update_user(user_id: str, user: schemas.UserUpdate, db: Session = Depends(get_db)):
    updated_user = crud.update_user(db=db, user_id=user_id, user_update=user)
    if not updated_user:
        raise HTTPException(status_code=404, detail="User does not exist")
    return updated_user

@app.put('/user/update_phone/{user_id}', response_model=schemas.User, tags=["Users"])
def update_user_phone_endpoint(user_id: str, phone_update: schemas.UserPhoneUpdate, db: Session = Depends(get_db)):
    updated_user = crud.update_user_phone(db=db, user_id=user_id, PhoneNumber=phone_update.PhoneNumber)
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")
    return updated_user

@app.put('/user/admin_put/{user_id}', response_model=schemas.User, tags=["Users"])
def update_user(user_id: str, user: schemas.AdminUserUpdate, db: Session = Depends(get_db)):
    try:
        updated_user = crud.admin_update_user(db=db, user_id=user_id, user_update=user)
        if not updated_user:
            raise HTTPException(status_code=404, detail="User does not exist")
        return updated_user
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put('/user/update_role/{user_id}', response_model=schemas.User, tags=["Users"])
def update_user_role(user_id: str, role_update: schemas.UserRoleUpdate, db: Session = Depends(get_db)):
    role_name_to_id = {
        "Centra": 1,
        "Harbor": 2,
        "Company": 3,
        "Admin": 4,
        "Customer": 5,
        "Rejected": 6
    }
    role_id = role_name_to_id.get(role_update.RoleName)
    print(role_id)
    if role_id is None:
        raise HTTPException(status_code=400, detail="Invalid role name")

    updated_user = crud.update_user_role(db=db, user_id=user_id, role_id=role_id)
    if not updated_user:
        raise HTTPException(status_code=404, detail="User does not exist or role does not exist")
    return updated_user


@app.delete("/user/delete/{user_id}", response_class=JSONResponse, tags=["Users"])
def delete_user(user_id: str, db: Session = Depends(get_db)):
    deleted = crud.delete_user_by_id(db, user_id)
    if deleted:
        return {"message": "User deleted successfully"}
    else:
        return {"message": "User not found or deletion failed"}

# Courier
@app.post("/courier/post", response_model=schemas.Courier, tags=["Courier"])
def create_courier(courier: schemas.CourierCreate, db: Session = Depends(get_db)):
    return crud.create_courier(db, courier)

@app.get("/courier/get", response_model=List[schemas.Courier], tags=["Courier"])
def get_courier(db: Session = Depends(get_db)):
    return crud.get_couriers(db)

@app.get("/courier/get/{courier_id}", response_model=schemas.Courier, tags=["Courier"])
def get_courier_by_courier_id(courier_id:int, db: Session = Depends(get_db)):
    return crud.get_courier_by_id(db, courier_id)   

@app.delete("/courier/delete/{courier_id}", response_class=JSONResponse, tags=["Courier"])
def delete_courier(courier_id: int, db: Session = Depends(get_db)):
    delete = crud.delete_courier(db=db, courier_id=courier_id)
    if delete:
        return {"message": "Courier deleted successfully"}
    else:
        raise HTTPException(status_code=404, detail="Courier not found or deletion failed")

# Wet Leaves
@app.post("/wetLeaves/post", response_model=schemas.WetLeaves, tags=["WetLeaves"])
def create_wet_leaves(wet_leaves: schemas.WetLeavesCreate, db: Session = Depends(get_db)):
    return crud.create_wet_leaves(db=db, wet_leaves=wet_leaves)

@app.get("/wetleaves/get", response_model=List[schemas.WetLeaves], tags=["WetLeaves"])
def get_wet_leaves(limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_wet_leaves(db=db, limit=limit)

@app.get("/wetleaves/get/{wet_leaves_id}", response_model=schemas.WetLeaves, tags=["WetLeaves"])
def get_wet_leaves_id(wet_leaves_id: int, db: Session = Depends(get_db)):
    wet_leaves = crud.get_wet_leaves_by_id(db=db, wet_leaves_id=wet_leaves_id)
    if not wet_leaves:
        raise HTTPException(status_code=404, detail="wet leaves not found")
    return wet_leaves

@app.get("/wetleaves/get_by_user/{user_id}", response_model=List[schemas.WetLeaves], tags=["WetLeaves"])
def get_wet_leaves_by_user(user_id: str, db: Session = Depends(get_db)):
    wet_leaves = crud.get_wet_leaves_by_user_id(db, user_id)
    if not wet_leaves:
        raise HTTPException(status_code=404, detail="wet leaves not found")
    return wet_leaves

@app.get('/wetleaves/sum_weight_today/{user_id}', tags=["WetLeaves"])
def get_sum_weight_wet_leaves_by_user_today(user_id: str, db: Session = Depends(get_db)):
    total_weight = crud.sum_weight_wet_leaves_by_user_today(db, user_id)
    return {"user_id": user_id, "total_weight_today": total_weight}

@app.delete("/wetleaves/delete/{wet_leaves_id}", response_class=JSONResponse, tags=["WetLeaves"])
def delete_wet_leaves_by_id(wet_leaves_id: int, db: Session = Depends(get_db)):
    delete = crud.delete_wet_leaves_by_id(db=db, wet_leaves_id=wet_leaves_id)
    if delete:
        return {"message": "wet leaves deleted successfully"}
    else:
        return {"message": "wet leaves not found or deletion failed"}

@app.put("/wetleaves/put/{wet_leaves_id}", response_model=schemas.WetLeaves, tags=["WetLeaves"])
def update_wet_leaves(wet_leaves_id: int, wet_leaves: schemas.WetLeavesUpdate, db: Session = Depends(get_db)):
    update_wet_leaves = crud.update_wet_leaves(db=db, wet_leaves_id=wet_leaves_id, wet_leaves_update=wet_leaves)
    if not update_wet_leaves:
        raise HTTPException(status_code=404, detail="wet leaves not found")
    return update_wet_leaves

@app.put("/wetleaves/update_status/{wet_leaves_id}", response_model=schemas.WetLeaves, tags=["WetLeaves"])
def update_wet_leaves_status(wet_leaves_id: int, status_update: schemas.WetLeavesStatusUpdate, db: Session = Depends(get_db)):
    updated_wet_leaves = crud.update_wet_leaves_status(db=db, wet_leaves_id=wet_leaves_id, status_update=status_update)
    if not updated_wet_leaves:
        raise HTTPException(status_code=404, detail="wet leaves not found")
    return updated_wet_leaves

# Dry Leaves
@app.post("/dryleaves/post", response_model=schemas.DryLeaves, tags=["DryLeaves"])
def create_dry_leaves(dry_leaves: schemas.DryLeavesCreate, db: Session = Depends(get_db)):
    return crud.create_dry_leaves(db=db, dry_leaves=dry_leaves)

@app.get("/dryleaves/get/", response_model=List[schemas.DryLeaves], tags=["DryLeaves"])
def get_dry_leaves(limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_dry_leaves(db=db, limit=limit)

@app.get("/dryleaves/get/{dry_leaves_id}", response_model=schemas.DryLeaves, tags=["DryLeaves"])
def get_dry_leaves_id(dry_leaves_id: int, db: Session = Depends(get_db)):
    dry_leaves = crud.get_dry_leaves_by_id(db=db, dry_leaves_id=dry_leaves_id)
    if not dry_leaves:
        raise HTTPException(status_code=404, detail="dry leaves not found")
    return dry_leaves

@app.get("/dryleaves/get_by_user/{user_id}", response_model=List[schemas.DryLeaves], tags=["DryLeaves"])
def get_dry_leaves_by_user(user_id: str, db: Session = Depends(get_db)):
    dry_leaves = crud.get_dry_leaves_by_user_id(db, user_id)
    if not dry_leaves:
        raise HTTPException(status_code=404, detail="Dry leaves not found")
    return dry_leaves

@app.delete("/dryleaves/delete/{dry_leaves_id}", response_class=JSONResponse, tags=["DryLeaves"])
def delete_dry_leaves_by_id(dry_leaves_id: int, db: Session = Depends(get_db)):
    delete = crud.delete_dry_leaves_by_id(db=db, dry_leaves_id=dry_leaves_id)
    if delete:
        return {"message": "dry leaves deleted successfully"}
    else:
        return {"message": "dry leaves not found or deletion failed"}

@app.put("/dryleaves/put/{dry_leaves_id}", response_model=schemas.DryLeaves, tags=["DryLeaves"])
def update_dry_leaves(dry_leaves_id: int, dry_leaves: schemas.DryLeavesUpdate, db: Session = Depends(get_db)):
    update_dry_leaves = crud.update_dry_leaves(db=db, dry_leaves_id=dry_leaves_id, dry_leaves_update=dry_leaves)
    if not update_dry_leaves:
        raise HTTPException(status_code=404, detail="dry leaves not found")
    return update_dry_leaves

@app.put("/dryleaves/update_status/{dry_leaves_id}", response_model=schemas.DryLeaves, tags=["DryLeaves"])
def update_dry_leaves_status(dry_leaves_id: int, status_update: schemas.DryLeavesStatusUpdate, db: Session = Depends(get_db)):
    updated_dry_leaves = crud.update_dry_leaves_status(db=db, dry_leaves_id=dry_leaves_id, status_update=status_update)
    if not updated_dry_leaves:
        raise HTTPException(status_code=404, detail="dry leaves not found")
    return updated_dry_leaves

# Flour
@app.post("/flour/post", response_model=schemas.Flour, tags=["Flour"])
def create_flour(flour: schemas.FlourCreate, db: Session = Depends(get_db)):
    return crud.create_flour(db=db, flour=flour)

@app.get("/flour/get", response_model=List[schemas.Flour], tags=["Flour"])
def get_flour(limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_flour(db=db, limit=limit)

@app.get("/flour/get/{flour_id}", response_model=schemas.Flour, tags=["Flour"])
def get_flour_by_id(flour_id: int, db: Session = Depends(get_db)):
    flour = crud.get_flour_by_id(db=db, flour_id=flour_id)
    if not flour:
        raise HTTPException(status_code=404, detail="flour not found")
    else:
        return flour

@app.get("/flour/get_by_user/{user_id}", response_model=List[schemas.Flour], tags=["Flour"])
def get_flour_by_user(user_id: str, db: Session = Depends(get_db)):
    flour = crud.get_flour_by_user_id(db, user_id)
    if not flour:
        raise HTTPException(status_code=404, detail="flour not found")
    return flour

@app.delete("/flour/delete/{flour_id}", response_class=JSONResponse, tags=["Flour"])
def delete_flour_by_id(flour_id: int, db: Session = Depends(get_db)):
    delete = crud.delete_flour_by_id(db=db, flour_id=flour_id)
    if delete:
        return {"message": "flour deleted successfully"}
    else:
        return {"message": "flour not found or deletion failed"}

@app.put("/flour/put/{flour_id}", response_model=schemas.Flour, tags=["Flour"])
def update_flour(flour_id: int, flour: schemas.FlourUpdate, db: Session = Depends(get_db)):
    update_flour = crud.update_flour(db=db, flour_id=flour_id, flour_update=flour)
    if not update_flour:
        raise HTTPException(status_code=404, detail="flour not found")
    return update_flour

@app.put("/flour/update_status/{flour_id}", response_model=schemas.Flour, tags=["Flour"])
def update_flour_status(flour_id: int, status_update: schemas.FlourStatusUpdate, db: Session = Depends(get_db)):
    updated_flour = crud.update_flour_status(db=db, flour_id=flour_id, status_update=status_update)
    if not updated_flour:
        raise HTTPException(status_code=404, detail="flour not found")
    return updated_flour

# Shipment
@app.post('/shipment/post', response_model=schemas.Shipment, tags=["Shipment"])
def create_shipment(shipment: schemas.ShipmentCreate, db: Session = Depends(get_db)):
    return crud.create_shipment(db=db, shipment=shipment)

@app.get('/shipment/get', response_model=List[schemas.Shipment], tags=["Shipment"])
def get_shipment(limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_shipment(db=db, limit=limit)

@app.get('/shipment/getid/{shipment_id}', response_model=schemas.Shipment, tags=["Shipment"])
def get_shipment_by_id(shipment_id: int, db: Session = Depends(get_db)):
    shipment = crud.get_shipment_by_id(db=db, shipment_id=shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="shipment not found")
    return shipment

@app.get("/shipment/get_by_user/{user_id}", response_model=List[schemas.Shipment], tags=["Shipment"])
def get_shipment_by_user(user_id: str, db: Session = Depends(get_db)):
    shipment_data = crud.get_shipment_by_user_id(db, user_id)
    if not shipment_data:
        raise HTTPException(status_code=404, detail="shipments not found")
    return shipment_data

@app.get("/shipments/ids", response_model=List[int], tags=["Shipment"])
def get_all_shipment_ids(db: Session = Depends(get_db)):
    shipments = crud.get_all_shipment_ids(db)
    print(f"All shipment IDs: {[shipment.ShipmentID for shipment in shipments]}")
    return [shipment.ShipmentID for shipment in shipments]

# Endpoint to compare shipment IDs
@app.get("/check_shipment_ids", response_model=List[str])
def check_shipment_ids(db: Session = Depends(get_db)):
    shipment_ids = crud.get_shipment_ids_with_date_but_no_checkin(db)
    print(f"Fetched shipment IDs: {shipment_ids}")

    # Example hashed ID to compare
    known_shipment_id = "known_shipment_id"
    hashed_shipment_id = bcrypt.hashpw(known_shipment_id.encode('utf-8'), bcrypt.gensalt())
    print(f"Hashed shipment ID: {hashed_shipment_id}")

    def brute_force_check(shipment_id):
        if bcrypt.checkpw(shipment_id.encode('utf-8'), hashed_shipment_id):
            return shipment_id
        else:
            print(f"No match for shipment ID: {shipment_id}")
            return None

    valid_shipment_ids = [brute_force_check(str(shipment_id)) for shipment_id in shipment_ids]
    valid_shipment_ids = list(filter(None, valid_shipment_ids))  # Filter out None values
    print(f"Valid shipment IDs: {valid_shipment_ids}")
    return valid_shipment_ids

@app.put("/shipment/put/{shipment_id}", response_model=schemas.Shipment, tags=["Shipment"])
def update_shipment(shipment_id: int, shipment_update: schemas.ShipmentUpdate, db: Session = Depends(get_db)):
    db_shipment = crud.update_shipment(db, shipment_id, shipment_update)
    if db_shipment is None:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return db_shipment

@app.put("/shipment/update_date/{shipment_id}", response_model=schemas.Shipment, tags=["Shipment"])
def update_shipment_date(shipment_id: int, shipment_date_update: schemas.ShipmentDateUpdate, db: Session = Depends(get_db)):
    updated_shipment = crud.update_shipment_date(db=db, shipment_id=shipment_id, shipment_date_update=shipment_date_update)
    if not updated_shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return updated_shipment

@app.put("/shipment/update_check_in/{shipment_id}", response_model=schemas.Shipment, tags=["Shipment"])
def update_shipment_check_in(shipment_id: int, check_in_update: schemas.ShipmentCheckInUpdate, db: Session = Depends(get_db)):
    updated_shipment = crud.update_shipment_check_in(db=db, shipment_id=shipment_id, check_in_update=check_in_update)
    if not updated_shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return updated_shipment

@app.put("/shipment/update_rescalled_weight/{shipment_id}", response_model=schemas.Shipment, tags=["Shipment"])
def update_shipment_rescalled_weight(shipment_id: int, update_data: schemas.ShipmentRescalledWeightUpdate, db: Session = Depends(get_db)):
    updated_shipment = crud.update_shipment_rescalled_weight_and_date(db=db, shipment_id=shipment_id, update_data=update_data)
    if not updated_shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return updated_shipment

@app.put("/shipment/update_harbor_reception/{shipment_id}", response_model=schemas.Shipment, tags=["Shipment"])
def update_shipment_harbor_reception(shipment_id: int, update_data: schemas.ShipmentHarborReceptionUpdate, db: Session = Depends(get_db)):
    updated_shipment = crud.update_shipment_harbor_reception(db=db, shipment_id=shipment_id, update_data=update_data)
    if not updated_shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return updated_shipment

@app.put("/shipment/update_centra_reception/{shipment_id}", response_model=schemas.Shipment, tags=["Shipment"])
def update_shipment_centra_reception(shipment_id: int, update_data: schemas.ShipmentCentraReceptionUpdate, db: Session = Depends(get_db)):
    updated_shipment = crud.update_shipment_centra_reception(db=db, shipment_id=shipment_id, update_data=update_data)
    if not updated_shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return updated_shipment

@app.delete('/shipment/delete/{shipment_id}', tags=["Shipment"])
def delete_shipment_by_id(shipment_id: int, db: Session = Depends(get_db)):
    delete = crud.delete_shipment_by_id(db=db, shipment_id=shipment_id)
    if delete:
        return {"message": "shipment deleted successfully"}
    else:
        return {"message": "shipment not found or deletion failed"}

# Location    
@app.post('/location/post', response_model=schemas.Location, tags=["Location"])
def create_location(location: schemas.LocationCreate, db: Session = Depends(get_db)):
    return crud.create_location(db, location=location)

@app.get('/location/get', response_model=List[schemas.Location], tags=["Location"])
def get_location(limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_location(db=db, limit=limit)

@app.get('/location/getid/{location_id}', response_model=schemas.Location, tags=["Location"])
def get_location_by_id(location_id: int, db: Session = Depends(get_db)):
    location = crud.get_location_by_id(db=db, location_id=location_id)
    if not location:
        raise HTTPException(status_code=404, detail="location not found")
    return location

@app.delete('/location/delete/{location_id}', tags=["Location"])
def delete_location_by_id(location_id: int, db: Session = Depends(get_db)):
    delete = crud.delete_location_by_id(db=db, location_id=location_id)
    if delete:
        return {"message": "location deleted successfully"}
    else:
        return {"message": "location not found or deletion failed"}
    
@app.get('/statistics/all', tags=["Statistics"])
def retrieve_all_stats(db: Session = Depends(get_db)):
    sum_wet_leaves = crud.sum_total_wet_leaves(db)
    sum_dry_leaves = crud.sum_total_dry_leaves(db)
    sum_flour = crud.sum_total_flour(db)
    sum_shipment_quantity = crud.sum_total_shipment_quantity(db)
    
    return {
        "sum_wet_leaves": format_large_number(sum_wet_leaves),
        "sum_dry_leaves": format_large_number(sum_dry_leaves),
        "sum_flour": format_large_number(sum_flour),
        "sum_shipment_quantity": format_large_number(sum_shipment_quantity)
    }

@app.get('/statistics/all_no_format', tags=["Statistics"])
def retrieve_all_stats_no_format(db: Session = Depends(get_db)):
    sum_wet_leaves = crud.sum_total_wet_leaves(db)
    sum_dry_leaves = crud.sum_total_dry_leaves(db)
    sum_flour = crud.sum_total_flour(db)
    sum_shipment_quantity = crud.sum_total_shipment_quantity(db)
    
    return {
        "sum_wet_leaves": sum_wet_leaves,
        "sum_dry_leaves": sum_dry_leaves,
        "sum_flour": sum_flour,
        "sum_shipment_quantity": sum_shipment_quantity
    }
    
@app.get('/centra/statistics/{user_id}', tags = ["Statistics"])
def retrieve_centra_stats(user_id: str, db: Session = Depends(get_db)):
    sum_wet_leaves = crud.sum_get_wet_leaves_by_user_id(db, user_id)
    sum_dry_leaves = crud.sum_get_dry_leaves_by_user_id(db, user_id)
    sum_flour = crud.sum_get_flour_by_user_id(db, user_id)
    sum_shipment_quantity = crud.sum_get_shipment_quantity_by_user_id(db, user_id)
    return {
        "sum_wet_leaves": format_large_number(sum_wet_leaves),
        "sum_dry_leaves": format_large_number(sum_dry_leaves),
        "sum_flour": format_large_number(sum_flour),
        "sum_shipment_quantity": format_large_number(sum_shipment_quantity)
    }

# Shipment-Flour Associations
@app.get("/shipment_flour_association/get", response_model=List[schemas.ShipmentFlourAssociation], tags=["ShipmentFlourAssociation"])
def get_shipment_flour_associations(db: Session = Depends(get_db)):
    return crud.get_shipment_flour_associations(db)

if __name__ == '__main__':
    uvicorn.run("main:app", host = "0.0.0.0", reload=True)
    
    
#marketplace
# Admin Settings
@app.post("/admin_settings/post", response_model=schemas.AdminSettings, tags=["Admin Settings"])
def create_admin_settings(admin_settings: schemas.AdminSettingsCreate, db: Session = Depends(get_db)):
    return crud.create_admin_settings(db=db, admin_settings=admin_settings)

@app.get("/admin_settings/get", response_model=schemas.AdminSettings, tags=["Admin Settings"])
def get_admin_settings(db: Session = Depends(get_db)):
    return crud.get_admin_settings(db=db)

@app.put("/admin_settings/put/{admin_settings_id}", response_model=schemas.AdminSettings, tags=["Admin Settings"])
def update_admin_settings(admin_settings_id: int, admin_settings_update: schemas.AdminSettingsBase, db: Session = Depends(get_db)):
    updated_admin_settings = crud.update_admin_settings(db=db, admin_settings_id=admin_settings_id, admin_settings_update=admin_settings_update)
    if not updated_admin_settings:
        raise HTTPException(status_code=404, detail="Admin settings not found")
    return updated_admin_settings

# Products
@app.post("/product/post", response_model=schemas.Products, tags=["Products"])
def create_product(product: schemas.ProductsCreate, db: Session = Depends(get_db)):
    return crud.create_product(db=db, product=product)

@app.get("/products/get", response_model=List[schemas.Products], tags=["Products"])
def get_products(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    return crud.get_products(db=db, skip=skip, limit=limit)

@app.get("/product/get/{product_id}", response_model=schemas.Products, tags=["Products"])
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = crud.get_product_by_id(db=db, product_id=product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@app.put("/product/put/{product_id}", response_model=schemas.Products, tags=["Products"])
def update_product(product_id: int, product_update: schemas.ProductsBase, db: Session = Depends(get_db)):
    updated_product = crud.update_product(db=db, product_id=product_id, product_update=product_update)
    if not updated_product:
        raise HTTPException(status_code=404, detail="Product not found")
    return updated_product

@app.delete("/product/delete/{product_id}", response_class=JSONResponse, tags=["Products"])
def delete_product(product_id: int, db: Session = Depends(get_db)):
    deleted = crud.delete_product(db, product_id)
    if deleted:
        return {"message": "Product deleted successfully"}
    else:
        return {"message": "Product not found or deletion failed"}
    
# Centra Setting Detail
@app.post("/centra_setting_detail/post", response_model=schemas.CentraSettingDetail, tags=["Centra Setting Detail"])
def create_centra_setting_detail(centra_setting_detail: schemas.CentraSettingDetailCreate, db: Session = Depends(get_db)):
    return crud.create_centra_setting_detail(db=db, centra_setting_detail=centra_setting_detail)

@app.get("/centra_setting_details/get", response_model=List[schemas.CentraSettingDetail], tags=["Centra Setting Detail"])
def get_centra_setting_details(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    return crud.get_centra_setting_details(db=db, skip=skip, limit=limit)

@app.get("/centra_setting_detail/get/{setting_detail_id}", response_model=schemas.CentraSettingDetail, tags=["Centra Setting Detail"])
def get_centra_setting_detail(setting_detail_id: int, db: Session = Depends(get_db)):
    setting_detail = crud.get_centra_setting_detail_by_id(db=db, setting_detail_id=setting_detail_id)
    if not setting_detail:
        raise HTTPException(status_code=404, detail="Centra setting detail not found")
    return setting_detail

@app.put("/centra_setting_detail/put/{setting_detail_id}", response_model=schemas.CentraSettingDetail, tags=["Centra Setting Detail"])
def update_centra_setting_detail(setting_detail_id: int, setting_detail_update: schemas.CentraSettingDetailBase, db: Session = Depends(get_db)):
    updated_setting_detail = crud.update_centra_setting_detail(db=db, setting_detail_id=setting_detail_id, setting_detail_update=setting_detail_update)
    if not updated_setting_detail:
        raise HTTPException(status_code=404, detail="Centra setting detail not found")
    return updated_setting_detail

@app.delete("/centra_setting_detail/delete/{setting_detail_id}", response_class=JSONResponse, tags=["Centra Setting Detail"])
def delete_centra_setting_detail(setting_detail_id: int, db: Session = Depends(get_db)):
    deleted = crud.delete_centra_setting_detail(db, setting_detail_id)
    if deleted:
        return {"message": "Centra setting detail deleted successfully"}
    else:
        return {"message": "Centra setting detail not found or deletion failed"}


# Centra Initial Prices
@app.post("/centra_initial_price/post", response_model=schemas.CentraInitialPrice, tags=["Centra Initial Prices"])
def create_centra_initial_price(centra_initial_price: schemas.CentraInitialPriceCreate, db: Session = Depends(get_db)):
    return crud.create_centra_initial_price(db=db, centra_initial_price=centra_initial_price)

@app.get("/centra_initial_prices/get", response_model=List[schemas.CentraInitialPrice], tags=["Centra Initial Prices"])
def get_centra_initial_prices(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    return crud.get_centra_initial_prices(db=db, skip=skip, limit=limit)

@app.put("/centra_initial_price/put/{initial_price_id}", response_model=schemas.CentraInitialPrice, tags=["Centra Initial Prices"])
def update_centra_initial_price(initial_price_id: int, centra_initial_price_update: schemas.CentraInitialPriceBase, db: Session = Depends(get_db)):
    updated_centra_initial_price = crud.update_centra_initial_price(db=db, initial_price_id=initial_price_id, centra_initial_price_update=centra_initial_price_update)
    if not updated_centra_initial_price:
        raise HTTPException(status_code=404, detail="Centra Initial Price not found")
    return updated_centra_initial_price

@app.delete("/centra_initial_price/delete/{initial_price_id}", response_class=JSONResponse, tags=["Centra Initial Prices"])
def delete_centra_initial_price(initial_price_id: int, db: Session = Depends(get_db)):
    deleted = crud.delete_centra_initial_price(db, initial_price_id)
    if deleted:
        return {"message": "Centra Initial Price deleted successfully"}
    else:
        return {"message": "Centra Initial Price not found or deletion failed"}

# Discount Conditions
@app.post("/discount_condition/post", response_model=schemas.DiscountCondition, tags=["Discount Conditions"])
def create_discount_condition(discount_condition: schemas.DiscountConditionCreate, db: Session = Depends(get_db)):
    return crud.create_discount_condition(db=db, discount_condition=discount_condition)

@app.get("/discount_conditions/get", response_model=List[schemas.DiscountCondition], tags=["Discount Conditions"])
def get_discount_conditions(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    return crud.get_discount_conditions(db=db, skip=skip, limit=limit)

@app.put("/discount_condition/put/{discount_condition_id}", response_model=schemas.DiscountCondition, tags=["Discount Conditions"])
def update_discount_condition(discount_condition_id: int, discount_condition_update: schemas.DiscountConditionBase, db: Session = Depends(get_db)):
    updated_discount_condition = crud.update_discount_condition(db=db, discount_condition_id=discount_condition_id, discount_condition_update=discount_condition_update)
    if not updated_discount_condition:
        raise HTTPException(status_code=404, detail="Discount condition not found")
    return updated_discount_condition

@app.delete("/discount_condition/delete/{discount_condition_id}", response_class=JSONResponse, tags=["Discount Conditions"])
def delete_discount_condition(discount_condition_id: int, db: Session = Depends(get_db)):
    deleted = crud.delete_discount_condition(db, discount_condition_id)
    if deleted:
        return {"message": "Discount condition deleted successfully"}
    else:
        return {"message": "Discount condition not found or deletion failed"}

# MarketShipment
@app.post("/market_shipment/post", response_model=schemas.MarketShipment, tags=["MarketShipment"])
def create_market_shipment(market_shipment: schemas.MarketShipmentCreate, db: Session = Depends(get_db)):
    return crud.create_market_shipment(db=db, market_shipment=market_shipment)

@app.get("/market_shipments/get", response_model=List[schemas.MarketShipment], tags=["MarketShipment"])
def get_market_shipments(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    return crud.get_market_shipments(db=db, skip=skip, limit=limit)

@app.get("/market_shipment/get/{market_shipment_id}", response_model=schemas.MarketShipment, tags=["MarketShipment"])
def get_market_shipment(market_shipment_id: int, db: Session = Depends(get_db)):
    market_shipment = crud.get_market_shipment_by_id(db=db, market_shipment_id=market_shipment_id)
    if not market_shipment:
        raise HTTPException(status_code=404, detail="MarketShipment not found")
    return market_shipment

@app.put("/market_shipment/put/{market_shipment_id}", response_model=schemas.MarketShipment, tags=["MarketShipment"])
def update_market_shipment(market_shipment_id: int, market_shipment_update: schemas.MarketShipmentUpdate, db: Session = Depends(get_db)):
    updated_market_shipment = crud.update_market_shipment(db=db, market_shipment_id=market_shipment_id, market_shipment_update=market_shipment_update)
    if not updated_market_shipment:
        raise HTTPException(status_code=404, detail="MarketShipment not found")
    return updated_market_shipment

@app.delete("/market_shipment/delete/{market_shipment_id}", response_class=JSONResponse, tags=["MarketShipment"])
def delete_market_shipment(market_shipment_id: int, db: Session = Depends(get_db)):
    deleted = crud.delete_market_shipment(db, market_shipment_id)
    if deleted:
        return {"message": "MarketShipment deleted successfully"}
    else:
        return {"message": "MarketShipment not found or deletion failed"}


# SubTransaction
@app.post("/subtransaction/post", response_model=schemas.SubTransaction, tags=["SubTransaction"])
def create_subtransaction(subtransaction: schemas.SubTransactionCreate, db: Session = Depends(get_db)):
    return crud.create_subtransaction(db=db, subtransaction=subtransaction)

@app.get("/subtransactions/get", response_model=List[schemas.SubTransaction], tags=["SubTransaction"])
def get_subtransactions(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    return crud.get_subtransactions(db=db, skip=skip, limit=limit)

@app.get("/subtransaction/get/{subtransaction_id}", response_model=schemas.SubTransaction, tags=["SubTransaction"])
def get_subtransaction(subtransaction_id: int, db: Session = Depends(get_db)):
    subtransaction = crud.get_subtransaction_by_id(db=db, subtransaction_id=subtransaction_id)
    if not subtransaction:
        raise HTTPException(status_code=404, detail="SubTransaction not found")
    return subtransaction

@app.put("/subtransaction/put/{subtransaction_id}", response_model=schemas.SubTransaction, tags=["SubTransaction"])
def update_subtransaction(subtransaction_id: int, subtransaction_update: schemas.SubTransactionUpdate, db: Session = Depends(get_db)):
    updated_subtransaction = crud.update_subtransaction(db=db, subtransaction_id=subtransaction_id, subtransaction_update=subtransaction_update)
    if not updated_subtransaction:
        raise HTTPException(status_code=404, detail="SubTransaction not found")
    return updated_subtransaction

@app.delete("/subtransaction/delete/{subtransaction_id}", response_class=JSONResponse, tags=["SubTransaction"])
def delete_subtransaction(subtransaction_id: int, db: Session = Depends(get_db)):
    deleted = crud.delete_subtransaction(db, subtransaction_id)
    if deleted:
        return {"message": "SubTransaction deleted successfully"}
    else:
        return {"message": "SubTransaction not found or deletion failed"}
    
    
# Transaction
@app.post("/transaction/post", response_model=schemas.Transaction, tags=["Transaction"])
def create_transaction(transaction: schemas.TransactionCreate, db: Session = Depends(get_db)):
    return crud.create_transaction(db=db, transaction=transaction)

@app.get("/transactions/get", response_model=List[schemas.Transaction], tags=["Transaction"])
def get_transactions(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    return crud.get_transactions(db=db, skip=skip, limit=limit)

@app.get("/transaction/get/{transaction_id}", response_model=schemas.Transaction, tags=["Transaction"])
def get_transaction(transaction_id: int, db: Session = Depends(get_db)):
    transaction = crud.get_transaction_by_id(db=db, transaction_id=transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction

@app.put("/transaction/put/{transaction_id}", response_model=schemas.Transaction, tags=["Transaction"])
def update_transaction(transaction_id: int, transaction_update: schemas.TransactionUpdate, db: Session = Depends(get_db)):
    updated_transaction = crud.update_transaction(db=db, transaction_id=transaction_id, transaction_update=transaction_update)
    if not updated_transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return updated_transaction

@app.delete("/transaction/delete/{transaction_id}", response_class=JSONResponse, tags=["Transaction"])
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    deleted = crud.delete_transaction(db, transaction_id)
    if deleted:
        return {"message": "Transaction deleted successfully"}
    else:
        return {"message": "Transaction not found or deletion failed"}

# Map Cities
@app.get("/cities", response_model=List[schemas.City])
def read_cities(db: Session = Depends(get_db)):
    return crud.get_all_cities(db)



# @app.post("/admin_settings/", response_model=schemas.AdminSettings)
# def create_admin_settings(admin_settings: schemas.AdminSettingsCreate, db: Session = Depends(get_db)):
#     return crud.create_admin_settings(db=db, admin_settings=admin_settings)

# @app.get("/admin_settings/{admin_settings_id}", response_model=schemas.AdminSettings)
# def read_admin_settings(admin_settings_id: int, db: Session = Depends(get_db)):
#     db_admin_settings = crud.get_admin_settings(db, admin_settings_id=admin_settings_id)
#     if db_admin_settings is None:
#         raise HTTPException(status_code=404, detail="Admin settings not found")
#     return db_admin_settings

# @app.put("/admin_settings/{admin_settings_id}", response_model=schemas.AdminSettings)
# def update_admin_settings(admin_settings_id: int, admin_settings: schemas.AdminSettingsCreate, db: Session = Depends(get_db)):
#     db_admin_settings = crud.update_admin_settings(db, admin_settings_id=admin_settings_id, admin_settings=admin_settings)
#     if db_admin_settings is None:
#         raise HTTPException(status_code=404, detail="Admin settings not found")
#     return db_admin_settings

# @app.delete("/admin_settings/{admin_settings_id}", response_model=schemas.AdminSettings)
# def delete_admin_settings(admin_settings_id: int, db: Session = Depends(get_db)):
#     db_admin_settings = crud.delete_admin_settings(db, admin_settings_id=admin_settings_id)
#     if db_admin_settings is None:
#         raise HTTPException(status_code=404, detail="Admin settings not found")
#     return db_admin_settings


# @app.post("/centra-settings/", response_model=schemas.CentraSettings)
# def create_centra_settings(centra_settings: schemas.CentraSettingsCreate, db: Session = Depends(get_db)):
#     return crud.create_centra_settings(db=db, centra_settings=centra_settings)

# @app.get("/centra-settings/{user_id}", response_model=schemas.CentraSettings)
# def read_centra_settings(user_id: str, db: Session = Depends(get_db)):
#     db_centra_settings = crud.get_centra_settings(db, user_id=user_id)
#     if db_centra_settings is None:
#         raise HTTPException(status_code=404, detail="Settings not found")
#     return db_centra_settings

# @app.get("/centra-settings/", response_model=List[schemas.CentraSettings])
# def read_centra_settings_list(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
#     return crud.get_centra_settings_list(db=db, skip=skip, limit=limit)

# @app.put("/centra-settings/{centra_settings_id}", response_model=schemas.CentraSettings)
# def update_centra_settings(centra_settings_id: int, centra_settings: schemas.CentraSettingsCreate, db: Session = Depends(get_db)):
#     updated_settings = crud.update_centra_settings(db=db, centra_settings_id=centra_settings_id, centra_settings=centra_settings)
#     if updated_settings is None:
#         raise HTTPException(status_code=404, detail="Settings not found")
#     return updated_settings

# @app.delete("/centra-settings/{centra_settings_id}")
# def delete_centra_settings(centra_settings_id: int, db: Session = Depends(get_db)):
#     success = crud.delete_centra_settings(db=db, centra_settings_id=centra_settings_id)
#     if not success:
#         raise HTTPException(status_code=404, detail="Settings not found")
#     return {"detail": "Settings deleted successfully"}


# # SettingsTemplate Endpoints

# @app.post("/settings-template/", response_model=schemas.SettingsTemplate)
# def create_settings_template(template: schemas.SettingsTemplateCreate, db: Session = Depends(get_db)):
#     return crud.create_settings_template(db=db, template=template)

# @app.get("/settings-template/{template_id}", response_model=schemas.SettingsTemplate)
# def read_settings_template(template_id: int, db: Session = Depends(get_db)):
#     db_template = crud.get_settings_template(db, template_id=template_id)
#     if db_template is None:
#         raise HTTPException(status_code=404, detail="Template not found")
#     return db_template

# @app.get("/settings-template/", response_model=List[schemas.SettingsTemplate])
# def read_settings_template_list(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
#     return crud.get_settings_template_list(db=db, skip=skip, limit=limit)

# @app.put("/settings-template/{template_id}", response_model=schemas.SettingsTemplate)
# def update_settings_template(template_id: int, template: schemas.SettingsTemplateCreate, db: Session = Depends(get_db)):
#     updated_template = crud.update_settings_template(db=db, template_id=template_id, template=template)
#     if updated_template is None:
#         raise HTTPException(status_code=404, detail="Template not found")
#     return updated_template

# @app.delete("/settings-template/{template_id}")
# def delete_settings_template(template_id: int, db: Session = Depends(get_db)):
#     success = crud.delete_settings_template(db=db, template_id=template_id)
#     if not success:
#         raise HTTPException(status_code=404, detail="Template not found")
#     return {"detail": "Template deleted successfully"}


# # CentraSettingsDetail Endpoints

# @app.post("/centra-settings-detail/", response_model=schemas.CentraSettingsDetail)
# def create_centra_settings_detail(detail: schemas.CentraSettingsDetailCreate, db: Session = Depends(get_db)):
#     return crud.create_centra_settings_detail(db=db, detail=detail)

# @app.get("/centra-settings-detail/{setting_detail_id}", response_model=schemas.CentraSettingsDetail)
# def read_centra_settings_detail(setting_detail_id: int, db: Session = Depends(get_db)):
#     db_detail = crud.get_centra_settings_detail(db, setting_detail_id=setting_detail_id)
#     if db_detail is None:
#         raise HTTPException(status_code=404, detail="Setting detail not found")
#     return db_detail

# @app.get("/centra-settings-detail/", response_model=List[schemas.CentraSettingsDetail])
# def read_centra_settings_detail_list(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
#     return crud.get_centra_settings_detail_list(db=db, skip=skip, limit=limit)

# @app.put("/centra-settings-detail/{setting_detail_id}", response_model=schemas.CentraSettingsDetail)
# def update_centra_settings_detail(setting_detail_id: int, detail: schemas.CentraSettingsDetailCreate, db: Session = Depends(get_db)):
#     updated_detail = crud.update_centra_settings_detail(db=db, setting_detail_id=setting_detail_id, detail=detail)
#     if updated_detail is None:
#         raise HTTPException(status_code=404, detail="Setting detail not found")
#     return updated_detail

# @app.delete("/centra-settings-detail/{setting_detail_id}")
# def delete_centra_settings_detail(setting_detail_id: int, db: Session = Depends(get_db)):
#     success = crud.delete_centra_settings_detail(db=db, setting_detail_id=setting_detail_id)
#     if not success:
#         raise HTTPException(status_code=404, detail="Setting detail not found")
#     return {"detail": "Setting detail deleted successfully"}


@app.get("/items/", response_model=Dict[str, List[Union[schemas.SimpleFlour, schemas.SimpleDryLeaves]]])
def read_items(item_type: str, limit: int = 100, db: Session = Depends(get_db)):
    try:
        items = crud.get_items(db, item_type=item_type, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return items

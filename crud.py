import os
import shutil
import uuid
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, TIMESTAMP, ForeignKey, func
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from passlib.context import CryptContext

# Load environment variables
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# Database setup
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# App and CORS setup
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------- MODELS ----------

class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    phone = Column(String(20), nullable=False)
    address = Column(Text)
    city = Column(String(100))
    state = Column(String(100))
    country = Column(String(100))
    branches = Column(Text)
    certificate_path = Column(String(255))
    logo_path = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    role = Column(String(100), nullable=False)
    company = Column(String, ForeignKey("companies.name", ondelete="CASCADE"), nullable=False)

Base.metadata.create_all(bind=engine)

# ---------- SCHEMAS ----------

class CompanyOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    phone: str
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    country: Optional[str]
    branches: Optional[List[str]]
    certificate_path: Optional[str]
    logo_path: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        orm_mode = True

class EmployeeRegister(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str
    company_name: str

class EmployeeLogin(BaseModel):
    email: EmailStr
    password: str

class EmployeeOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str
    company: str

    class Config:
        orm_mode = True

# ---------- DEPENDENCY ----------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------- HELPERS ----------

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def save_file(file: UploadFile, folder: str) -> str:
    ext = os.path.splitext(file.filename)[1]
    filename = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(folder, filename)
    os.makedirs(folder, exist_ok=True)
    with open(path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return path

def serialize_company(company: Company) -> CompanyOut:
    return CompanyOut(
        id=company.id,
        name=company.name,
        email=company.email,
        phone=company.phone,
        address=company.address,
        city=company.city,
        state=company.state,
        country=company.country,
        branches=company.branches.split(",") if company.branches else [],
        certificate_path=company.certificate_path,
        logo_path=company.logo_path,
        is_active=company.is_active,
        created_at=company.created_at,
    )

# ---------- COMPANY ROUTES ----------

@app.post("/companies", response_model=CompanyOut)
def create_company(
    name: str = Form(...),
    email: EmailStr = Form(...),
    phone: str = Form(...),
    address: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    state: str = Form(...),
    country: str = Form(...),
    branches: List[str] = Form(...),
    is_active: bool = Form(True),
    certificate: Optional[UploadFile] = File(None),
    logo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    if db.query(Company).filter(Company.email == email).first():
        raise HTTPException(400, detail="Email already in use")
    cert_path = save_file(certificate, "uploads/certificates") if certificate else None
    logo_path = save_file(logo, "uploads/logos") if logo else None
    company = Company(
        name=name,
        email=email,
        phone=phone,
        address=address,
        city=city,
        state=state,
        country=country,
        branches=",".join(branches),
        certificate_path=cert_path,
        logo_path=logo_path,
        is_active=is_active,
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return serialize_company(company)

@app.get("/companies", response_model=List[CompanyOut])
def get_companies(db: Session = Depends(get_db)):
    return [serialize_company(c) for c in db.query(Company).all()]

@app.put("/companies/{company_id}", response_model=CompanyOut)
def update_company(company_id: int,
    name: Optional[str] = Form(None),
    email: Optional[EmailStr] = Form(None),
    phone: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    state: Optional[str] = Form(None),
    country: Optional[str] = Form(None),
    branches: Optional[List[str]] = Form(None),
    is_active: Optional[bool] = Form(None),
    certificate: Optional[UploadFile] = File(None),
    logo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, detail="Company not found")

    if email and email != company.email:
        if db.query(Company).filter(Company.email == email).first():
            raise HTTPException(400, detail="Email already in use")

    updates = {
        "name": name, "email": email, "phone": phone,
        "address": address, "city": city, "state": state,
        "country": country, "is_active": is_active
    }

    for key, value in updates.items():
        if value is not None:
            setattr(company, key, value)

    if branches:
        company.branches = ",".join(branches)
    if certificate:
        company.certificate_path = save_file(certificate, "uploads/certificates")
    if logo:
        company.logo_path = save_file(logo, "uploads/logos")

    db.commit()
    db.refresh(company)
    return serialize_company(company)

@app.delete("/companies/{company_id}", status_code=204)
def delete_company(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, detail="Company not found")
    db.delete(company)
    db.commit()

# ---------- EMPLOYEE ROUTES ----------

@app.post("/employees/register", response_model=EmployeeOut)
def register_employee(emp: EmployeeRegister, db: Session = Depends(get_db)):
    if db.query(Employee).filter(Employee.email == emp.email).first():
        raise HTTPException(400, detail="Email already registered")

    company = db.query(Company).filter(Company.name == emp.company_name).first()
    if not company:
        raise HTTPException(404, detail="Company not found")

    new_emp = Employee(
        name=emp.name,
        email=emp.email,
        password_hash=hash_password(emp.password),
        role=emp.role,
        company=emp.company_name,
    )
    db.add(new_emp)
    db.commit()
    db.refresh(new_emp)
    return new_emp

@app.post("/employees/login")
def employee_login(credentials: EmployeeLogin, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.email == credentials.email).first()
    if not emp or not verify_password(credentials.password, emp.password_hash):
        raise HTTPException(401, detail="Invalid credentials")
    return {"message": "Login successful", "employee_id": emp.id}

@app.get("/employees", response_model=List[EmployeeOut])
def get_employees(db: Session = Depends(get_db)):
    return db.query(Employee).all()

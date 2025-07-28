import os
import uuid
import shutil
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy import (
    Column, Integer, String, Boolean, Text, TIMESTAMP, func, create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# Initialize FastAPI app
app = FastAPI()

# Allow all CORS (adjust in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up database engine and session
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# Database model
class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    phone = Column(String(20), nullable=False)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True)
    branches = Column(Text, nullable=True)
    certificate_path = Column(String(512), nullable=True)
    logo_path = Column(String(512), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)

# Create tables
Base.metadata.create_all(bind=engine)

# Pydantic schema for API response
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
    created_at: datetime  # datetime handled automatically by FastAPI

    class Config:
        orm_mode = True

# Database session dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# File saving utility
def save_upload(file: UploadFile, folder: str) -> str:
    ext = os.path.splitext(file.filename)[1]
    filename = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(folder, filename)
    os.makedirs(folder, exist_ok=True)
    with open(path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return path

# Convert ORM company to Pydantic response
def enrich_company_output(company: Company) -> CompanyOut:
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

# Create a new company
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
    # Check if email already exists
    if db.query(Company).filter(Company.email == email).first():
        raise HTTPException(400, detail="Email already in use")

    # Save uploaded files
    cert_path = save_upload(certificate, "uploads/certificates") if certificate else None
    logo_path = save_upload(logo, "uploads/logos") if logo else None

    # Create company record
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

    return enrich_company_output(company)

# Get all companies
@app.get("/companies", response_model=List[CompanyOut])
def list_companies(
    x_region: Optional[str] = Depends(lambda: None),
    db: Session = Depends(get_db),
):
    query = db.query(Company)
    if x_region:
        query = query.filter(Company.city == x_region)
    companies = query.all()
    return [enrich_company_output(c) for c in companies]

# Get single company
@app.get("/companies/{company_id}", response_model=CompanyOut)
def get_company(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, detail="Company not found")
    return enrich_company_output(company)

# Update existing company
@app.put("/companies/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: int,
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

    # Update fields
    updates = {
        "name": name, "email": email, "phone": phone,
        "address": address, "city": city, "state": state,
        "country": country, "is_active": is_active
    }
    for field, value in updates.items():
        if value is not None:
            setattr(company, field, value)

    if branches is not None:
        company.branches = ",".join(branches)

    if certificate:
        company.certificate_path = save_upload(certificate, "uploads/certificates")

    if logo:
        company.logo_path = save_upload(logo, "uploads/logos")

    db.commit()
    db.refresh(company)

    return enrich_company_output(company)

# Delete company
@app.delete("/companies/{company_id}", status_code=204)
def delete_company(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).get(company_id)
    if not company:
        raise HTTPException(404, detail="Company not found")
    db.delete(company)
    db.commit()

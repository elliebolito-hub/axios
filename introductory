import csv
import os
import smtplib
import tempfile
from datetime import date
from email.message import EmailMessage
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from pypdf import PdfReader, PdfWriter


app = FastAPI(title="AD&D PDF Generator")

PDF_TEMPLATE = "AD&D_Fillable_Template.pdf"


class Employee(BaseModel):
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""
    email: Optional[str] = ""
    phone: Optional[str] = ""
    date_of_birth: Optional[str] = ""
    salary: Optional[str] = ""


class PacketRequest(BaseModel):
    master_application_number: Optional[str] = ""
    organization_name: Optional[str] = ""
    type_of_business: Optional[str] = ""

    mailing_address: Optional[str] = ""
    city: Optional[str] = ""
    state: Optional[str] = ""
    zip: Optional[str] = ""

    first_name: Optional[str] = ""
    last_name: Optional[str] = ""
    primary_contact: Optional[str] = ""

    phone: Optional[str] = ""
    email: Optional[str] = ""
    form_date: Optional[str] = ""

    agent_name: Optional[str] = ""
    agent_code: Optional[str] = ""
    agent_phone: Optional[str] = ""
    agent_email: Optional[str] = ""

    carrier_email: Optional[str] = ""

    employees: List[Employee] = []


@app.get("/")
def home():
    return {"status": "AD&D PDF Generator is running"}


@app.get("/fields")
def inspect_pdf_fields():
    reader = PdfReader(PDF_TEMPLATE)
    fields = reader.get_fields()

    if not fields:
        return {"fields": [], "message": "No fillable fields found."}

    return {"fields": list(fields.keys())}


@app.post("/generate")
def generate_packet(
    payload: PacketRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    expected_api_key = os.getenv("API_KEY")

    if expected_api_key and x_api_key != expected_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    completed_pdf = fill_pdf(payload)
    census_csv = generate_census_csv(payload)

    if payload.carrier_email:
        send_email_with_attachments(
            to_email=payload.carrier_email,
            subject=f"AD&D Enrollment Packet - {payload.organization_name}",
            body=f"Attached is the AD&D enrollment packet for {payload.organization_name}.",
            attachments=[completed_pdf, census_csv],
        )

    return {
        "status": "success",
        "message": "AD&D packet generated",
        "pdf_file": os.path.basename(completed_pdf),
        "csv_file": os.path.basename(census_csv),
    }


def fill_pdf(payload: PacketRequest) -> str:
    reader = PdfReader(PDF_TEMPLATE)
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    if reader.trailer["/Root"].get("/AcroForm"):
        writer._root_object.update({
            "/AcroForm": reader.trailer["/Root"]["/AcroForm"]
        })

    actual_date = payload.form_date or date.today().strftime("%m/%d/%Y")

    primary_contact = payload.primary_contact
    if not primary_contact:
        primary_contact = f"{payload.first_name} {payload.last_name}".strip()

    field_values = {
        "master_application_number": payload.master_application_number,
        "organization_name": payload.organization_name,
        "type_of_business": payload.type_of_business,
        "mailing_address": payload.mailing_address,
        "city": payload.city,
        "state": payload.state,
        "zip": payload.zip,
        "primary_contact": primary_contact,
        "phone": payload.phone,
        "email": payload.email,
        "date": actual_date,

        "agent_name": payload.agent_name,
        "agent_code": payload.agent_code,
        "agent_phone": payload.agent_phone,
        "agent_email": payload.agent_email,
    }

    for page in writer.pages:
        writer.update_page_form_field_values(page, field_values)

    output_dir = tempfile.mkdtemp()
    safe_org = clean_filename(payload.organization_name or "organization")
    output_path = os.path.join(output_dir, f"AD&D_Master_Application_{safe_org}.pdf")

    with open(output_path, "wb") as output_file:
        writer.write(output_file)

    return output_path


def generate_census_csv(payload: PacketRequest) -> str:
    output_dir = tempfile.mkdtemp()
    safe_org = clean_filename(payload.organization_name or "organization")
    output_path = os.path.join(output_dir, f"AD&D_Census_{safe_org}.csv")

    headers = [
        "First Name",
        "Last Name",
        "Email",
        "Phone",
        "Date of Birth",
        "Salary",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=headers)
        writer.writeheader()

        for employee in payload.employees:
            writer.writerow({
                "First Name": employee.first_name,
                "Last Name": employee.last_name,
                "Email": employee.email,
                "Phone": employee.phone,
                "Date of Birth": employee.date_of_birth,
                "Salary": employee.salary,
            })

    return output_path


def send_email_with_attachments(to_email: str, subject: str, body: str, attachments: list):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("FROM_EMAIL", smtp_user)

    if not smtp_host or not smtp_user or not smtp_password:
        raise HTTPException(
            status_code=500,
            detail="SMTP settings are missing in Render environment variables.",
        )

    message = EmailMessage()
    message["From"] = from_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    for attachment in attachments:
        file_path = Path(attachment)

        with open(file_path, "rb") as file:
            message.add_attachment(
                file.read(),
                maintype="application",
                subtype="octet-stream",
                filename=file_path.name,
            )

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(message)


def clean_filename(value: str) -> str:
    allowed = []

    for char in value:
        if char.isalnum() or char in ["-", "_"]:
            allowed.append(char)
        elif char == " ":
            allowed.append("_")

    return "".join(allowed)[:80]

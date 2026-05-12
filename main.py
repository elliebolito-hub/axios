import csv
import os
import smtplib
import uuid
from datetime import date, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Optional, List
from urllib.parse import quote

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, BooleanObject


app = FastAPI(title="AD&D PDF Generator")

PDF_TEMPLATE = "AD&D_Fillable_Template.pdf"

# Free Render setup:
# Files are stored locally in generated_files.
# They can disappear after Render redeploys/restarts.
# For paid persistent storage later, set OUTPUT_DIR=/var/data/generated_files.
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "generated_files"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


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
    return {
        "status": "AD&D PDF Generator is running",
        "output_dir": str(OUTPUT_DIR),
    }


@app.get("/fields")
def inspect_pdf_fields():
    reader = PdfReader(PDF_TEMPLATE)
    fields = reader.get_fields()

    if not fields:
        return {"fields": [], "message": "No fillable fields found."}

    return {"fields": list(fields.keys())}


@app.get("/files")
def list_generated_files():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    files = []

    for file_path in OUTPUT_DIR.iterdir():
        if file_path.is_file():
            files.append({
                "filename": file_path.name,
                "size_bytes": file_path.stat().st_size,
                "download_url": f"/download/{quote(file_path.name)}",
            })

    return {
        "output_dir": str(OUTPUT_DIR),
        "file_count": len(files),
        "files": files,
    }


@app.get("/download/{filename}")
def download_file(filename: str):
    safe_name = Path(filename).name
    file_path = OUTPUT_DIR / safe_name

    if not file_path.exists():
        available_files = [
            item.name for item in OUTPUT_DIR.iterdir()
            if item.is_file()
        ] if OUTPUT_DIR.exists() else []

        raise HTTPException(
            status_code=404,
            detail={
                "message": "File not found. The app may have restarted, redeployed, or the file was removed.",
                "requested_file": safe_name,
                "output_dir": str(OUTPUT_DIR),
                "available_files": available_files,
            },
        )

    if safe_name.lower().endswith(".pdf"):
        media_type = "application/pdf"
    elif safe_name.lower().endswith(".csv"):
        media_type = "text/csv"
    else:
        media_type = "application/octet-stream"

    return FileResponse(
        path=str(file_path),
        filename=safe_name,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "Cache-Control": "no-store",
        },
    )


@app.post("/generate")
def generate_packet(
    request: Request,
    payload: PacketRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    expected_api_key = os.getenv("API_KEY")

    if expected_api_key and x_api_key != expected_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    unique_id = make_unique_id()

    completed_pdf = fill_pdf(payload, unique_id)
    census_csv = generate_census_csv(payload, unique_id)

    pdf_filename = os.path.basename(completed_pdf)
    csv_filename = os.path.basename(census_csv)

    public_base_url = os.getenv("PUBLIC_BASE_URL")

    if public_base_url:
        base_url = public_base_url.rstrip("/")
    else:
        base_url = str(request.base_url).rstrip("/")

    pdf_url = f"{base_url}/download/{quote(pdf_filename)}"
    csv_url = f"{base_url}/download/{quote(csv_filename)}"

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
        "pdf_file": pdf_filename,
        "csv_file": csv_filename,
        "pdf_url": pdf_url,
        "csv_url": csv_url,
        "pdf_exists": os.path.exists(completed_pdf),
        "csv_exists": os.path.exists(census_csv),
        "output_dir": str(OUTPUT_DIR),
    }


def fill_pdf(payload: PacketRequest, unique_id: str) -> str:
    reader = PdfReader(PDF_TEMPLATE)
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    if "/AcroForm" in reader.trailer["/Root"]:
        writer._root_object.update({
            NameObject("/AcroForm"): reader.trailer["/Root"]["/AcroForm"]
        })

        writer._root_object["/AcroForm"].update({
            NameObject("/NeedAppearances"): BooleanObject(True)
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

    safe_org = clean_filename(payload.organization_name or "organization")

    # Use ADD in the technical filename so Zapier/GHL URLs do not break.
    # The form, email subject, and app title can still say AD&D.
    output_path = OUTPUT_DIR / f"ADD_Master_Application_{safe_org}_{unique_id}.pdf"

    with open(output_path, "wb") as output_file:
        writer.write(output_file)

    return str(output_path)


def generate_census_csv(payload: PacketRequest, unique_id: str) -> str:
    safe_org = clean_filename(payload.organization_name or "organization")

    # Use ADD in the technical filename so Zapier/GHL URLs do not break.
    output_path = OUTPUT_DIR / f"ADD_Census_{safe_org}_{unique_id}.csv"

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

    return str(output_path)


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

    cleaned = "".join(allowed).strip("_")

    if not cleaned:
        cleaned = "organization"

    return cleaned[:80]


def make_unique_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_id = uuid.uuid4().hex[:6]
    return f"{timestamp}_{short_id}"

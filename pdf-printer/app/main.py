from fastapi import FastAPI, UploadFile, File, Request, Form, Body, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi import Depends

import secrets
import pika
import json
import shutil
import subprocess
import os
import uuid
import logging
from markdown import markdown

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'rabbitmq')
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'user')
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS', 'password')
security = HTTPBasic()
PDF_PRINTER_USER = os.getenv("PDF_PRINTER_USER", "admin")
PDF_PRINTER_PASS = os.getenv("PDF_PRINTER_PASS", "password")
# === Logging Setup ===
LOG_PATH = "/pdfprinter.log"
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler()  # <--- This will show logs in `docker logs`
    ]
)
logger = logging.getLogger(__name__)

# Base paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
README_PATH = os.path.join(BASE_DIR, "README.md")

# === Folder Setup ===
TMP_DIR = "/app/shared"
FONT_DIR = "/usr/share/fonts/truetype/custom"
os.makedirs(TMP_DIR, exist_ok=True)
os.makedirs(FONT_DIR, exist_ok=True)
os.chmod(TMP_DIR, 0o777)
os.chmod(FONT_DIR, 0o777)

# === App Setup ===
app = FastAPI()
logger.info("🚀 pdf-printer started and logging is active")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, PDF_PRINTER_USER)
    correct_password = secrets.compare_digest(credentials.password, PDF_PRINTER_PASS)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )

# Load README and convert to HTML
def get_readme_html():
    if os.path.exists(README_PATH):
        with open(README_PATH, "r") as f:
            return markdown(f.read())
    return "<p>README not found.</p>"

# === Index Page (README) ===
@app.get("/")
def index(request: Request):
    readme_html = get_readme_html()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "readme_html": readme_html
    })

# === PDFs Page ===
@app.get("/pdfs")
def list_pdfs(request: Request):
    files = os.listdir(TMP_DIR)
    pdf_files = sorted([f for f in files if f.endswith('.pdf')])
    return templates.TemplateResponse("pdfs.html", {
        "request": request,
        "pdf_files": pdf_files
    })

# === Fonts Page ===
@app.get("/fonts")
def list_fonts(request: Request):
    fonts_output = os.popen("fc-list : file family").readlines()
    fonts = sorted(set(line.strip() for line in fonts_output))
    return templates.TemplateResponse("fonts.html", {
        "request": request,
        "fonts": fonts
    })

# === RabbitMQ Queue Stats ===
@app.get("/queue-stats")
def queue_stats(request: Request):
    queue_len = None
    try:
        credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST, credentials=credentials))
        channel = connection.channel()
        result = channel.queue_declare(queue='pdf_jobs', durable=True)
        queue_len = result.method.message_count
        connection.close()
    except Exception as e:
        logger.error(f"Failed to fetch queue stats: {e}")
    return templates.TemplateResponse("queue.html", {
        "request": request,
        "queue_len": queue_len
    })

# === Test Endpoint ===
@app.get("/hello")
def hello():
    return {"message": "Hello, worldest!"}

# === Upload Font ===
@app.post("/upload-font")
async def upload_font(
    font_file: UploadFile = File(...),
    credentials: HTTPBasicCredentials = Depends(verify_credentials)  # <-- protect this route
):
    if not font_file.filename.endswith((".ttf", ".otf")):
        logger.warning(f"Rejected font upload: {font_file.filename}")
        return {"error": "Only .ttf and .otf fonts allowed."}

    font_path = os.path.join(FONT_DIR, font_file.filename)
    with open(font_path, "wb") as f:
        shutil.copyfileobj(font_file.file, f)

    os.system("fc-cache -fv")
    logger.info(f"Installed font: {font_file.filename}")
    return RedirectResponse(url="/fonts", status_code=303)

# === Delete File ===
@app.post("/delete-file")
async def delete_file(
    filename: str = Form(...),
    credentials: HTTPBasicCredentials = Depends(verify_credentials)  # <-- protect this route
):
    file_path = os.path.join(TMP_DIR, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        logger.info(f"Deleted file: {file_path}")
    else:
        logger.warning(f"Tried to delete non-existent file: {file_path}")
    return RedirectResponse(url="/pdfs", status_code=303)

# === Serve Files (PDF/XLSX) ===
@app.get("/files/{filename}")
async def get_file(
    filename: str,
    credentials: HTTPBasicCredentials = Depends(verify_credentials)  # <-- protect this route
):
    file_path = os.path.join(TMP_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    logger.warning(f"Requested file not found: {file_path}")
    return {"error": "File not found"}


# ====

# 🛠️ 3. **Make RabbitMQ Optional (Fallback to `/convert`)**
@app.post("/queue-job")
async def queue_job(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    lo_options: str = Form(default=None),
    credentials: HTTPBasicCredentials = Depends(verify_credentials)  # <-- protect this route
):
    try:
        tmp_file = os.path.join(TMP_DIR, file.filename)
        with open(tmp_file, "wb") as f:
            shutil.copyfileobj(file.file, f)
        logger.info(f"Saved file: {tmp_file}")

        if RABBITMQ_HOST and RABBITMQ_USER and RABBITMQ_PASS:
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
            connection = pika.BlockingConnection(pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                credentials=credentials
            ))
            channel = connection.channel()
            channel.queue_declare(queue='pdf_jobs', durable=True)
            channel.basic_publish(
                exchange='',
                routing_key='pdf_jobs',
                body=json.dumps({'xlsx': file.filename, 'lo_options': lo_options}),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            connection.close()
            return {"status": "queued", "file": file.filename}
        else:
            logger.warning("No RabbitMQ config; falling back to direct conversion")
            return await convert_xlsx(file=file, lo_options=lo_options)
    except Exception as e:
        logger.error(f"Queue/convert failed: {e}")
        return {"error": str(e)}


@app.get("/check-pdf/{filename}")
def check_pdf(
    filename: str, delete: bool = False,
    background_tasks: BackgroundTasks = None,
    credentials: HTTPBasicCredentials = Depends(verify_credentials)  # <-- protect this route
):
    pdf_path = os.path.join(TMP_DIR, filename)
    if not os.path.isfile(pdf_path):
        raise HTTPException(status_code=404, detail="PDF not ready")

    response = FileResponse(pdf_path, media_type="application/pdf", filename=filename)

    if delete:
        background_tasks.add_task(os.remove, pdf_path)
        logger.info(f"🗑️ Scheduled deletion of PDF after response: {pdf_path}")

    return response

# === Convert XLSX to PDF ===
@app.post("/convert")
async def convert_xlsx(
    file: UploadFile = File(...),
    lo_options: str = Form(default=None),
    credentials: HTTPBasicCredentials = Depends(verify_credentials)  # <-- protect this route
):
    input_filename = file.filename
    input_path = os.path.join(TMP_DIR, input_filename)
    output_path = input_path.replace(".xlsx", ".pdf")

    try:
        with open(input_path, "wb") as f:
            f.write(await file.read())
        logger.info(f"Saved XLSX to: {input_path}")

        convert_cmd = [
            "libreoffice", "--headless", "--convert-to", "pdf", input_path, "--outdir", TMP_DIR
        ]

        if lo_options:
            convert_filter = f'pdf:calc_pdf_Export:{lo_options}'
            convert_cmd = [
                "libreoffice", "--headless", "--convert-to", convert_filter, input_path, "--outdir", TMP_DIR
            ]

        result = subprocess.run(convert_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"LibreOffice failed: {result.stderr}")

        logger.info(f"PDF created: {output_path}")
        return FileResponse(path=output_path, media_type="application/pdf", filename=os.path.basename(output_path))

    except Exception as e:
        logger.exception("Conversion failed")
        return {"error": str(e)}

    finally:
        for p in [input_path, output_path]:
            if os.path.exists(p): os.remove(p)

@app.post("/convert-in-shared-dir")
async def convert_in_shared_dir(
    filename: str = Form(...),
    lo_options: str = Form(default=None),
    delete_original: int = Form(default=0),
    credentials: HTTPBasicCredentials = Depends(verify_credentials)  # <-- protect this route
):
    input_path = os.path.join(TMP_DIR, filename)
    output_path = input_path.replace('.xlsx', '.pdf')

    if not os.path.exists(input_path):
        logger.warning(f"Input XLSX file not found: {input_path}")
        raise HTTPException(status_code=404, detail="File not found")

    try:
        if lo_options:
            convert_filter = f'pdf:calc_pdf_Export:{lo_options}'
            convert_cmd = [
                "libreoffice", "--headless", "--convert-to", convert_filter, input_path, "--outdir", TMP_DIR
            ]
        else:
            convert_cmd = [
                "libreoffice", "--headless", "--convert-to", "pdf", input_path, "--outdir", TMP_DIR
            ]

        result = subprocess.run(convert_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"LibreOffice failed: {result.stderr}")
            raise RuntimeError(f"LibreOffice failed: {result.stderr}")

        logger.info(f"✅ PDF generated at: {output_path}")

        if delete_original:
            os.remove(input_path)
            logger.info(f"🗑️ Deleted original XLSX after conversion: {input_path}")

        return {"status": "success", "pdf": os.path.basename(output_path)}

    except Exception as e:
        logger.exception("Conversion failed")
        return {"error": str(e)}


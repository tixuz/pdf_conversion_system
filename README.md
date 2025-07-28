# 📄 PDF Conversion System

A modular system to convert `.xlsx` files into `.pdf` using **FastAPI**, **LibreOffice**, **RabbitMQ**, and shared volume in Docker.

---

## 📦 Project Structure

```bash
pdf_conversion_system/
├── docker-compose.yml
├── shared/                      # ⬅️ Shared folder (not tracked by git)
├── pdf-printer/                # FastAPI PDF printing service
│   ├── Dockerfile
│   ├── app/
│   │   ├── main.py
│   │   ├── requirements.txt
│   │   ├── templates/
│   │   └── static/
│   └── fonts/
├── pdf-worker/                 # RabbitMQ background worker
│   ├── Dockerfile
│   ├── worker.py
│   └── requirements.txt
```

---

## 🐳 How to Setup (Home Docker Environment)

### 1. Clone and prepare:
```bash
git clone https://github.com/yourusername/pdf_conversion_system.git
cd pdf_conversion_system
mkdir shared
chmod 777 shared
```

### 2. Run services:
```bash
docker-compose up --build
```

### 3. Access FastAPI UI:
```
http://localhost:5000/
```

### 4. Use from Python (example):
```python
import requests
files = {'file': open('your.xlsx', 'rb')}
r = requests.post('http://localhost:5000/convert', files=files)
with open('output.pdf', 'wb') as f:
    f.write(r.content)
```

### 5. Use from PHP (example with Guzzle):
```php
$client = new \GuzzleHttp\Client();
$response = $client->post('http://localhost:5000/convert', [
    'multipart' => [
        [
            'name' => 'file',
            'contents' => fopen('/path/to/your.xlsx', 'r'),
            'filename' => 'your.xlsx'
        ]
    ]
]);
file_put_contents('output.pdf', $response->getBody());
```

---

## ☁️ How to Setup (AWS EC2 / Remote Server)

### 1. SSH into instance:
```bash
ssh ec2-user@your-ec2-host
```

### 2. Clone repo and setup:
```bash
git clone https://github.com/yourusername/pdf_conversion_system.git
cd pdf_conversion_system
mkdir shared
chmod 777 shared
```

### 3. Allow ports in your AWS EC2 security group (port 5000, optionally 5672 for RabbitMQ)

### 4. Run services:
```bash
docker-compose up --build -d
```

### 5. Call from another server:
In Python:
```python
requests.post('http://your-ec2-ip:5000/convert', files={'file': open('file.xlsx', 'rb')})
```

In PHP:
```php
$client = new \GuzzleHttp\Client();
$response = $client->post('http://your-ec2-ip:5000/convert', [...]);
```

### 6. 🔐 Restricting Access on EC2

To ensure only your IP can access the PDF printer:

- Go to **EC2 > Security Groups** for your instance
- Edit **Inbound Rules**
- Remove any 0.0.0.0/0 rule for port 5000
- Add:
  - Type: Custom TCP
  - Port: 5000
  - Source: YOUR_PUBLIC_IP/32

This blocks access from all other sources.

---

## 🔐 Environment Variables

Defined in `docker-compose.yml`:

```env
RABBITMQ_USER=user
RABBITMQ_PASS=password
PRINTER_AUTH_USER=printeruser
PRINTER_AUTH_PASS=printerpass
```

These are required for basic authentication on `/convert`, `/queue-job`, etc.

---

## 🔧 API Endpoints

### 1. `/hello`
Returns basic hello JSON.

### 2. `/convert` [POST]
Uploads an XLSX file and converts to PDF.
- **Params:**
    - `file`: XLSX upload
    - `lo_options`: Optional LibreOffice JSON filter
    - Auth required

### 3. `/convert-in-shared-dir` [POST]
Converts a file already present in `/shared` folder.
- **Params:**
    - `filename`: string
    - `lo_options`: optional
    - `delete_original`: optional (default `false`)
    - Auth required

### 4. `/queue-job` [POST]
Uploads file and enqueues job via RabbitMQ.
- **Params:**
    - `file`: XLSX
    - Auth required

### 5. `/check-pdf/{filename}` [GET]
Checks and returns PDF file if ready.
- **Query param:**
    - `delete=true` to remove after sending (optional)
    - Auth required

### 6. `/upload-font` [POST]
Installs a new `.ttf` or `.otf` font.
- **Params:**
    - `font_file`

### 7. `/delete-file` [POST]
Deletes any file (PDF/XLSX) in shared dir.
- **Params:**
    - `filename`

### 8. `/files/{filename}` [GET]
Serves a specific file from shared dir.

### 9. `/` [GET]
Web UI listing uploaded XLSX/PDF files and fonts.

---

## 🗃 .gitignore Suggestions
```gitignore
shared/
*.pyc
__pycache__/
.env
*.log
*.pdf
*.xlsx
.idea/
.vscode/
```

---

## ✅ Summary

- PDF printer service works standalone or with RabbitMQ.
- Secure with HTTP Basic Auth.
- LibreOffice filters supported.
- Easily deployable on EC2 or Docker anywhere.
- Cross-language support via HTTP (PHP, Python, etc.)

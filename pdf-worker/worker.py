import pika
import os
import json
import requests
import time
from requests.auth import HTTPBasicAuth

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'rabbitmq')
QUEUE_NAME = os.getenv('QUEUE_NAME', 'pdf_jobs')
PRINTER_API_URL = os.getenv('PRINTER_API_URL', 'http://pdf-printer:5000/convert-in-shared-dir')
SHARED_DIR = '/shared'
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'user')
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS', 'password')
PDF_PRINTER_USER = os.getenv("PDF_PRINTER_USER", "user")
PDF_PRINTER_PASS = os.getenv("PDF_PRINTER_PASS", "password")

def process_message(ch, method, properties, body):
    try:
        message = json.loads(body)
        xlsx_filename = message.get('xlsx')
        lo_options = message.get('lo_options')  # Optional custom LibreOffice options
        delete_original = message.get('delete_original')  # Optional custom LibreOffice options

        if not xlsx_filename:
            print("No XLSX file provided in message.")
            return

        xlsx_path = os.path.join(SHARED_DIR, xlsx_filename)
        if not os.path.exists(xlsx_path):
            print(f"File not found: {xlsx_path}")
            return

        print(f"Converting {xlsx_filename} using shared directory method…")
        payload = {
            'filename': xlsx_filename
        }
        if lo_options:
            payload['lo_options'] = json.dumps(lo_options)  # send as string if needed
        if delete_original:
            payload['delete_original'] = delete_original  # send as string if needed

        response = requests.post(
            PRINTER_API_URL,
            data=payload,
            auth=HTTPBasicAuth(PDF_PRINTER_USER, PDF_PRINTER_PASS)
        )

        if response.status_code == 200:
            json_response = response.json()
            if "pdf" in json_response:
                print(f"✅ PDF generated: {json_response['pdf']}")
            else:
                print(f"⚠️ Conversion successful but no filename returned: {json_response}")
        else:
            print(f"❌ Conversion failed: {response.status_code} - {response.text}")

    except Exception as e:
        print(f"🔥 Error processing message: {e}")

def main():
    while True:
        try:
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
            connection = pika.BlockingConnection(pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                credentials=credentials
            ))
            channel = connection.channel()
            channel.queue_declare(queue=QUEUE_NAME, durable=True)

            channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_message, auto_ack=True)
            print(" [*] Waiting for messages. To exit press CTRL+C")
            channel.start_consuming()
        except Exception as e:
            print(f"🐇 RabbitMQ connection error: {e}. Retrying in 5s…")
            time.sleep(5)

if __name__ == '__main__':
    main()

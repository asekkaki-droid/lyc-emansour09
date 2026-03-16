from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import os
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from dotenv import load_dotenv
from fpdf import FPDF
import base64
import qrcode
import io
import uuid
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import arabic_reshaper
from bidi.algorithm import get_display

# Load environment variables from .env file
load_dotenv()

import logging
import sys
import cloudinary
import cloudinary.uploader
import resend

# Setup logging
basedir = os.path.abspath(os.path.dirname(__file__))
log_handlers = [logging.StreamHandler(sys.stdout)] # type: list[logging.Handler]

# Only use FileHandler if NOT on Vercel
if not os.environ.get('VERCEL'):
    try:
        log_handlers.append(logging.FileHandler(os.path.join(basedir, "server.log")))
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=log_handlers
)
logger = logging.getLogger(__name__)

def find_available_port(start_port=5000):
    import socket
    port = start_port
    while port < 6000:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
        port += 1
    return start_port

# Setup absolute paths for static files
server_dir = os.path.abspath(os.path.dirname(__file__))
client_dir = os.path.abspath(os.path.join(server_dir, '..', 'client'))
app = Flask(__name__, static_folder=client_dir, static_url_path='')

@app.route('/')
def serve_index():
    return app.send_static_file('index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return app.send_static_file(filename)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
# Configure Uploads
basedir = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
if os.environ.get('VERCEL') or os.environ.get('NETLIFY') or os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
    UPLOAD_FOLDER = '/tmp/uploads'

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure directory exists but handle potential read-only errors at boot
try:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
except Exception:
    pass

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    from flask import send_from_directory
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ----- Database Configuration -----
# Use Neon PostgreSQL URL if provided (standard for Vercel/Netlify deployment)
db_url = os.environ.get('DATABASE_URL')
# Vercel specific postgres env var
if not db_url and os.environ.get('POSTGRES_URL'):
    db_url = os.environ.get('POSTGRES_URL')
    
if db_url:
    # Handle potentially old postgres:// URLs for SQLAlchemy
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    
    # Add SSL require for external databases to prevent connection issues
    if '?' not in db_url:
        db_url += '?sslmode=require'
        
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
else:
    # On Serverless, use /tmp for SQLite as it's the only writable directory
    is_serverless = bool(os.environ.get('VERCEL') or os.environ.get('NETLIFY') or os.environ.get('AWS_LAMBDA_FUNCTION_NAME'))
    db_path = os.path.join(basedir, 'school.db')
    if is_serverless:
        db_path = '/tmp/school.db'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Cloud Config
cloudinary.config(cloudinary_url=os.environ.get('CLOUDINARY_URL'))
resend.api_key = os.environ.get('RESEND_API_KEY')
# Ensure the primary email is exactly what the user requested
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', "lyceealmansour282@gmail.com")
DEFAULT_FROM_EMAIL = "onboarding@resend.dev"

db = SQLAlchemy(app)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)
login_manager = LoginManager(app)

# --- Serverless DB Auto-Init ---
_db_initialized = False

@app.before_request
def ensure_db_initialized():
    """On Netlify serverless, /tmp is ephemeral — re-init DB on every cold start."""
    global _db_initialized
    if not _db_initialized:
        try:
            db.create_all()
            if not Admin.query.filter_by(email=ADMIN_EMAIL).first():
                db.session.add(Admin(
                    email=ADMIN_EMAIL,
                    password=generate_password_hash('admin_password')
                ))
                db.session.commit()
                logger.info("Admin auto-created on serverless cold start.")
            if not SchoolStats.query.first():
                db.session.add(SchoolStats(
                    students_count=0, teachers_count=0,
                    experience_years=0, awards_count=0
                ))
                db.session.commit()
            _db_initialized = True
        except Exception as e:
            logger.error(f"DB auto-init failed: {e}")


def handle_exception(e):
    try:
        print(f"!!! GLOBAL ERROR: {str(e)}".encode('ascii', errors='replace').decode('ascii'))
    except:
        print("!!! GLOBAL ERROR: (Encoding issue in error message)")
    return jsonify({"message": f"Server Error: {str(e)}"}), 500

# Models
class Announcement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), nullable=False)
    image_url = db.Column(db.Text) # Stored as comma-separated URLs
    pdf_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, **kwargs):
        super(Announcement, self).__init__(**kwargs)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    msg_type = db.Column(db.String(50))
    subject = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, **kwargs):
        super(Message, self).__init__(**kwargs)

class Admin(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    reset_token = db.Column(db.String(100), unique=True, nullable=True)
    token_expiry = db.Column(db.DateTime, nullable=True)

    def __init__(self, **kwargs):
        super(Admin, self).__init__(**kwargs)

class SchoolStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    students_count = db.Column(db.Integer, default=0)
    teachers_count = db.Column(db.Integer, default=0)
    experience_years = db.Column(db.Integer, default=0)
    awards_count = db.Column(db.Integer, default=0)

    def __init__(self, **kwargs):
        super(SchoolStats, self).__init__(**kwargs)

class Staff(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(100), nullable=False) # e.g., "المدير", "حارس عام"
    staff_type = db.Column(db.String(50), nullable=False) # "admin" or "teaching"
    image_url = db.Column(db.String(500))

    def __init__(self, **kwargs):
        super(Staff, self).__init__(**kwargs)

class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.Text) # Stored as comma-separated URLs
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, **kwargs):
        super(Activity, self).__init__(**kwargs)

class Gallery(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    image_url = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(50)) # e.g., "activities", "school", "students"

    def __init__(self, **kwargs):
        super(Gallery, self).__init__(**kwargs)

class StudentResource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100)) # e.g., "دروس", "فروض", "مباريات"
    description = db.Column(db.Text)
    link_url = db.Column(db.String(500), nullable=False)

    def __init__(self, **kwargs):
        super(StudentResource, self).__init__(**kwargs)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Admin, int(user_id))

def generate_contact_pdf(data):
    # Professional PDF Generation for Contact Messages
    pdf = FPDF()
    # Add Arabic font support
    font_name = "Helvetica" # Default fallback
    
    # Define potential font locations
    server_dir = os.path.abspath(os.path.dirname(__file__))
    local_fonts_dir = os.path.join(server_dir, "fonts")
    windows_fonts_dir = r"C:\Windows\Fonts"
    
    # Font names to look for
    fonts_to_try = [
        ("CairoCustom", "Cairo-Regular.ttf", "Cairo-Bold.ttf", "Cairo-Italic.ttf"),
        ("ArialCustom", "arial.ttf", "arialbd.ttf", "ariali.ttf")
    ]
    
    found = False
    for f_name, reg, bold, ital in fonts_to_try:
        # Try local first (especially for Vercel/Linux)
        reg_path = os.path.join(local_fonts_dir, reg)
        bold_path = os.path.join(local_fonts_dir, bold)
        ital_path = os.path.join(local_fonts_dir, ital)
        
        # Then try Windows if on NT
        if not os.path.exists(reg_path) and os.name == 'nt':
            reg_path = os.path.join(windows_fonts_dir, reg)
            bold_path = os.path.join(windows_fonts_dir, bold)
            ital_path = os.path.join(windows_fonts_dir, ital)
            
        try:
            if os.path.exists(reg_path):
                logger.info(f"Loading font {f_name} from {reg_path}")
                pdf.add_font(f_name, "", reg_path)
                font_name = f_name
                if os.path.exists(bold_path):
                    pdf.add_font(f_name, "B", bold_path)
                if os.path.exists(ital_path):
                    pdf.add_font(f_name, "I", ital_path)
                found = True
                break
        except Exception as e:
            logger.error(f"Failed to load font {f_name}: {e}")
            
    # On Linux/Vercel, we stick to default fonts if nothing else found.
    if not found:
        logger.warning("No Arabic font found. Skipping PDF generation to prevent text encoding errors.")
        return None

    pdf.add_page()
    
    # Header
    pdf.set_font(font_name, 'B', 16)
    pdf.cell(0, 10, "Lycée Al-Mansour de Meknès", align='C')
    pdf.ln(10)
    pdf.set_font(font_name, '', 12)
    pdf.cell(0, 10, "Etablissement d'Enseignement Secondaire", ln=True, align='C')
    pdf.ln(10)
    
    # Title
    pdf.set_fill_color(18, 58, 122) # Primary Dark
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(font_name, 'B', 14)
    
    msg_type = data.get('msg_type', '')
    title_text = "Rapport de Message"
    if msg_type == 'activity_request':
        title_text = "Demande d'Activite"
    elif msg_type == 'inquiry':
        title_text = "Inquiry"
    
    pdf.cell(0, 12, title_text, ln=True, align='C', fill=True)
    pdf.ln(10)
    
    # Body
    pdf.set_text_color(0, 0, 0)
    pdf.set_font(font_name, 'B', 12)
    pdf.cell(50, 10, "Expéditeur:")
    pdf.set_font(font_name, '', 12)
    pdf.cell(0, 10, f"{data.get('sender_name')}", ln=True)
    
    pdf.set_font(font_name, 'B', 12)
    pdf.cell(50, 10, "Email:")
    pdf.set_font(font_name, '', 12)
    pdf.cell(0, 10, f"{data.get('email')}", ln=True)
    
    pdf.set_font(font_name, 'B', 12)
    pdf.cell(50, 10, "Téléphone:")
    pdf.set_font(font_name, '', 12)
    pdf.cell(0, 10, f"{data.get('phone', 'N/A')}", ln=True)
    
    pdf.set_font(font_name, 'B', 12)
    pdf.cell(50, 10, "Sujet:")
    pdf.set_font(font_name, '', 12)
    pdf.cell(0, 10, f"{data.get('subject')}")
    pdf.ln(10)
    
    pdf.ln(10)
    pdf.set_font(font_name, 'B', 12)
    pdf.cell(0, 10, "Message:")
    pdf.ln(10)
    pdf.ln(10)
    pdf.set_font(font_name, '', 11)
    
    # Process Arabic text for message
    raw_message = str(data.get('message', ''))
    try:
        reshaped_text = arabic_reshaper.reshape(raw_message)
        bidi_text = get_display(reshaped_text)
        pdf.multi_cell(0, 7, bidi_text, align='R')
    except Exception as e:
        logger.error(f"Arabic Reshaping Error: {e}")
        pdf.multi_cell(0, 7, raw_message)
    
    # QR Code (SCAN Feature)
    base_url = f"{request.host_url}"
    qr_data = f"{base_url}verify?id={data.get('email')}"
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(qr_data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    # Save QR code to bytes
    img_byte_arr = io.BytesIO()
    qr_img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    # Add QR code to PDF
    pdf.image(img_byte_arr, x=160, y=240, w=30)
    pdf.set_xy(160, 270)
    pdf.set_font(font_name, 'B', 8)
    pdf.cell(30, 10, "SCAN TO VERIFY", align='C')

    pdf.ln(20)
    pdf.set_font(font_name, 'I', 8)
    pdf.cell(0, 10, f"Généré le: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", align='R')
    
    return pdf.output(dest='S') # Return PDF as byte string

def send_email_with_pdf(subject, body, to_email, pdf_content=None, pdf_filename="message.pdf"):
    # Priority 1: Resend (Cloud)
    if resend.api_key:
        try:
            params = {
                "from": f"Lycee Al-Mansour <{DEFAULT_FROM_EMAIL}>",
                "to": [str(to_email)],
                "subject": str(subject),
                "text": str(body),
            }
            if pdf_content:
                import base64
                content_b64 = base64.b64encode(pdf_content).decode('utf-8')
                params["attachments"] = [{
                    "filename": str(pdf_filename),
                    "content": content_b64
                }]

            resend.Emails.send(params)
            logger.info(f"Email sent via Resend to {to_email}")
            return True, "resend"
        except Exception as e:
            logger.error(f"Resend Failed: {e}")
            return False, f"Resend Error: {str(e)}"

    # Fallback to Gmail SMTP if Resend fails or key is missing
    gmail_user = str(os.environ.get('GMAIL_USER') or ADMIN_EMAIL)
    gmail_pass = str(os.environ.get('GMAIL_APP_PASSWORD') or "")
    if not gmail_user or not gmail_pass:
        return False, "إعدادات الإيميل غير مكتملة في Vercel (GMAIL_USER أو GMAIL_APP_PASSWORD مفقودة)"
    
    try:
        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = str(to_email)
        msg['Subject'] = str(subject)
        msg.attach(MIMEText(str(body), 'plain', 'utf-8'))
        
        if pdf_content:
            from email.mime.base import MIMEBase
            from email import encoders
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(pdf_content)
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{pdf_filename}"')
            msg.attach(part)

        # Vercel blocking 587, using 465 (SSL)
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.set_debuglevel(1)
        server.login(gmail_user, gmail_pass)
        server.send_message(msg)
        server.quit()
        logger.info(f"Email sent via Gmail Fallback (SSL) to {to_email}")
        return True, "gmail"
    except Exception as e:
        logger.error(f"SMTP Fallback Failed: {e}")
        return False, f"SMTP Error: {str(e)}"

@app.route('/api/upload', methods=['POST'])
def upload_file():
    # Priority: Cloudinary
    if os.environ.get('CLOUDINARY_URL'):
        try:
            if 'file' not in request.files:
                files = request.files.getlist('files')
                if not files: return jsonify({'message': 'No file'}), 400
                urls = []
                for f in files:
                    upload_result = cloudinary.uploader.upload(f)
                    urls.append(upload_result['secure_url'])
                return jsonify({'urls': urls, 'cloud': True}), 200
            
            f = request.files['file']
            upload_result = cloudinary.uploader.upload(f)
            return jsonify({'url': upload_result['secure_url'], 'cloud': True}), 200
        except Exception as e:
            logger.error(f"Cloudinary Upload Failed: {e}")
            # Fallback will continue below

    # Fallback to Local Upload (Works locally, fails on Vercel)
    if 'file' not in request.files:
        files = request.files.getlist('files')
        if not files: return jsonify({'message': 'لا يوجد ملف مرفق'}), 400
        urls = []
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                urls.append(f"/uploads/{filename}")
        return jsonify({'urls': urls}), 200

    file = request.files['file']
    if file and allowed_file(file.filename):
        filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return jsonify({'url': f"/uploads/{filename}"}), 200
    
    return jsonify({'message': 'نوع الملف غير مدعوم'}), 400

@app.route('/api/health')
@app.route('/api/ping')
@app.route('/ping')
def health_check():
    return jsonify({
        "status": "online",
        "environment": "Serverless" if is_serverless else "Local",
        "database": str(app.config['SQLALCHEMY_DATABASE_URI']).split('@')[-1] if '@' in str(app.config['SQLALCHEMY_DATABASE_URI']) else "sqlite",
        "time": datetime.utcnow().isoformat(),
        "message": "pong"
    })

@app.route('/api/debug/env')
def debug_env():
    # Masked env check for debugging backend on Netlify/Vercel
    return jsonify({
        "RESEND_KEY_SET": bool(os.environ.get('RESEND_API_KEY')),
        "CLOUDINARY_SET": bool(os.environ.get('CLOUDINARY_URL')),
        "DATABASE_URL_SET": bool(os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL')),
        "GMAIL_USER_SET": bool(os.environ.get('GMAIL_USER')),
        "GMAIL_PASS_SET": bool(os.environ.get('GMAIL_APP_PASSWORD')),
        "ADMIN_EMAIL": ADMIN_EMAIL,
        "PLATFORM": "Netlify" if os.environ.get('NETLIFY') else ("Vercel" if os.environ.get('VERCEL') else "Local")
    })

@app.route('/api/test-vercel')
def test_vercel():
    return jsonify({"status": "success", "message": "Vercel is connecting to Flask!", "path": request.path})

# ----- API Routes -----

@app.route('/api/announcements', methods=['GET', 'POST', 'DELETE'])
@app.route('/announcements', methods=['GET', 'POST', 'DELETE'])
def handle_announcements():
    if request.method == 'GET':
        announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
        return jsonify([{
            'id': a.id, 'title': a.title, 'content': a.content, 'type': a.type,
            'image_url': a.image_url, 'pdf_url': a.pdf_url, 'created_at': a.created_at.isoformat()
        } for a in announcements])
    
    if request.method == 'POST':
        data = request.json
        new_ann = Announcement(
            title=data.get('title'), content=data.get('content'), type=data.get('type'),
            image_url=data.get('image_url'), pdf_url=data.get('pdf_url')
        )
        db.session.add(new_ann)
        db.session.commit()
        return jsonify({'message': 'تم إضافة الإعلان بنجاح'}), 201

    if request.method == 'DELETE':
        ann_id = request.args.get('id')
        Announcement.query.filter_by(id=ann_id).delete()
        db.session.commit()
        return jsonify({'message': 'تم حذف الإعلان'}), 200

@app.route('/api/announcements/<int:ann_id>', methods=['GET'])
@app.route('/announcements/<int:ann_id>', methods=['GET'])
def get_announcement(ann_id):
    a = db.session.get(Announcement, ann_id)
    if not a:
        return jsonify({'message': 'الإعلان غير موجود'}), 404
    return jsonify({
        'id': a.id, 'title': a.title, 'content': a.content, 'type': a.type,
        'image_url': a.image_url, 'pdf_url': a.pdf_url, 'created_at': a.created_at.isoformat()
    })

@app.route('/api/messages', methods=['GET', 'POST', 'DELETE'])
@app.route('/messages', methods=['GET', 'POST', 'DELETE'])
def handle_messages():
    if request.method == 'GET':
        messages = Message.query.order_by(Message.created_at.desc()).all()
        return jsonify([{
            'id': m.id, 'sender_name': m.sender_name, 'email': m.email, 'phone': m.phone,
            'msg_type': m.msg_type, 'subject': m.subject, 'message': m.message, 'created_at': m.created_at.isoformat()
        } for m in messages])

    if request.method == 'POST':
        try:
            data = request.json
            new_message = Message(
                sender_name=data.get('sender_name'), email=data.get('email'), phone=data.get('phone'),
                msg_type=data.get('msg_type'), subject=data.get('subject'), message=data.get('message')
            )
            db.session.add(new_message)
            db.session.commit()
            
            subject = f"رسالة جديدة من الموقع: {data.get('subject')}"
            body = f"المرسل: {data.get('sender_name')}\nالبريد: {data.get('email')}\nالهاتف: {data.get('phone')}\nالنوع: {data.get('msg_type')}\nالرسالة:\n{data.get('message')}"
            
            # Generate PDF report
            pdf_content = generate_contact_pdf(data)
            success, status_or_error = send_email_with_pdf(subject, body, ADMIN_EMAIL, pdf_content, "rapport_contact.pdf")
            
            if success and status_or_error == "resend":
                return jsonify({'message': 'تم إرسال رسالتك وتلقيها بنجاح من طرف الإدارة!', 'email_sent': True}), 201
            elif success and status_or_error == "gmail":
                return jsonify({'message': 'تم إرسال رسالتك وتلقيها بنجاح من طرف الإدارة!', 'email_sent': True}), 201
            else:
                return jsonify({'message': f'تم حفظ الرسالة في النظام، لكن فشل إرسال الإيميل بسبب: {status_or_error}', 'email_sent': False}), 201
        except Exception as e:
            try:
                print(f"!!! Error in handle_messages: {str(e)}".encode('ascii', errors='replace').decode('ascii'))
            except:
                print("!!! Error in handle_messages: (Encoding issue)")
            return jsonify({"message": f"Error: {str(e)}"}), 500

    if request.method == 'DELETE':
        msg_id = request.args.get('id')
        Message.query.filter_by(id=msg_id).delete()
        db.session.commit()
        return jsonify({'message': 'تم حذف الرسالة'}), 200

@app.route('/api/stats', methods=['GET', 'POST'])
@app.route('/stats', methods=['GET', 'POST'])
def handle_stats():
    stats = SchoolStats.query.first()
    if request.method == 'GET':
        if not stats: return jsonify({'students': 0, 'teachers': 0, 'experience': 0, 'awards': 0})
        return jsonify({
            'students': stats.students_count, 'teachers': stats.teachers_count,
            'experience': stats.experience_years, 'awards': stats.awards_count
        })
    
    if request.method == 'POST':
        data = request.json
        if not stats:
            stats = SchoolStats()
            db.session.add(stats)
        stats.students_count = data.get('students', stats.students_count)
        stats.teachers_count = data.get('teachers', stats.teachers_count)
        stats.experience_years = data.get('experience', stats.experience_years)
        stats.awards_count = data.get('awards', stats.awards_count)
        db.session.commit()
        return jsonify({'message': 'تم تحديث الإحصائيات بنجاح'})

@app.route('/api/staff', methods=['GET', 'POST', 'DELETE'])
@app.route('/staff', methods=['GET', 'POST', 'DELETE'])
def handle_staff():
    if request.method == 'GET':
        staff_list = Staff.query.all()
        return jsonify([{'id': s.id, 'name': s.name, 'role': s.role, 'staff_type': s.staff_type, 'image_url': s.image_url} for s in staff_list])
    
    if request.method == 'POST':
        data = request.json
        new_staff = Staff(name=data.get('name'), role=data.get('role'), staff_type=data.get('staff_type'), image_url=data.get('image_url'))
        db.session.add(new_staff)
        db.session.commit()
        return jsonify({'message': 'تم إضافة فرد للطاقم بنجاح'})

    if request.method == 'DELETE':
        staff_id = request.args.get('id')
        Staff.query.filter_by(id=staff_id).delete()
        db.session.commit()
        return jsonify({'message': 'تم حذف فرد من الطاقم'})

@app.route('/api/activities', methods=['GET', 'POST', 'DELETE'])
@app.route('/activities', methods=['GET', 'POST', 'DELETE'])
def handle_activities():
    if request.method == 'GET':
        activities = Activity.query.order_by(Activity.created_at.desc()).all()
        return jsonify([{'id': a.id, 'title': a.title, 'content': a.content, 'image_url': a.image_url, 'created_at': a.created_at.isoformat()} for a in activities])
    
    if request.method == 'POST':
        data = request.json
        new_act = Activity(title=data.get('title'), content=data.get('content'), image_url=data.get('image_url'))
        db.session.add(new_act)
        db.session.commit()
        return jsonify({'message': 'تم إضافة النشاط بنجاح'}), 201
    
    if request.method == 'DELETE':
        act_id = request.args.get('id')
        Activity.query.filter_by(id=act_id).delete()
        db.session.commit()
        return jsonify({'message': 'تم حذف النشاط'}), 200

@app.route('/api/activities/<int:act_id>', methods=['GET'])
@app.route('/activities/<int:act_id>', methods=['GET'])
def get_activity(act_id):
    a = Activity.query.get_or_404(act_id)
    return jsonify({
        'id': a.id, 'title': a.title, 'content': a.content, 
        'image_url': a.image_url, 'created_at': a.created_at.isoformat()
    })

@app.route('/api/gallery', methods=['GET', 'POST', 'DELETE'])
@app.route('/gallery', methods=['GET', 'POST', 'DELETE'])
def handle_gallery():
    if request.method == 'GET':
        images = Gallery.query.all()
        return jsonify([{'id': i.id, 'title': i.title, 'image_url': i.image_url, 'category': i.category} for i in images])
    
    if request.method == 'POST':
        data = request.json
        new_img = Gallery(title=data.get('title'), image_url=data.get('image_url'), category=data.get('category'))
        db.session.add(new_img)
        db.session.commit()
        return jsonify({'message': 'تم إضافة الصورة بنجاح'})

    if request.method == 'DELETE':
        img_id = request.args.get('id')
        Gallery.query.filter_by(id=img_id).delete()
        db.session.commit()
        return jsonify({'message': 'تم حذف الصورة'})

@app.route('/api/student-space', methods=['GET', 'POST', 'DELETE'])
@app.route('/student-space', methods=['GET', 'POST', 'DELETE'])
def handle_student_space():
    if request.method == 'GET':
        resources = StudentResource.query.all()
        return jsonify([{'id': r.id, 'title': r.title, 'category': r.category, 'description': r.description, 'link_url': r.link_url} for r in resources])
    
    if request.method == 'POST':
        data = request.json
        new_res = StudentResource(title=data.get('title'), category=data.get('category'), description=data.get('description'), link_url=data.get('link_url'))
        db.session.add(new_res)
        db.session.commit()
        return jsonify({'message': 'تم إضافة المورد بنجاح'})

    if request.method == 'DELETE':
        res_id = request.args.get('id')
        StudentResource.query.filter_by(id=res_id).delete()
        db.session.commit()
        return jsonify({'message': 'تم حذف المورد'})

@app.route('/api/admin/login', methods=['POST'])
@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    admin = Admin.query.filter_by(email=email).first()
    if admin and check_password_hash(admin.password, password):
        return jsonify({'message': 'تم تسجيل الدخول بنجاح', 'token': 'active'}), 200
    
    return jsonify({'message': 'البريد الإلكتروني أو كلمة المرور غير صحيحة'}), 401

@app.route('/api/admin/forgot-password', methods=['POST'])
@app.route('/admin/forgot-password', methods=['POST'])
def admin_forgot_password():
    data = request.json
    email = data.get('email')
    if email != ADMIN_EMAIL:
        return jsonify({'message': 'تم رفض الطلب. هذا البريد ليس البريد الرسمي للمؤسسة.'}), 403
    admin = Admin.query.filter_by(email=email).first()
    # On serverless, the DB may be empty on cold start — auto-recreate the admin
    if not admin:
        try:
            db.create_all()
            admin = Admin(email=ADMIN_EMAIL, password=generate_password_hash('admin_password'))
            db.session.add(admin)
            db.session.commit()
            logger.info("Admin auto-recreated on serverless cold start.")
        except Exception as ex:
            logger.error(f"Failed to auto-create admin: {ex}")
            return jsonify({'message': 'خطأ في قاعدة البيانات. يرجى المحاولة مرة أخرى.'}), 500
    if admin:
        token = secrets.token_urlsafe(32)
        admin.reset_token = token
        admin.token_expiry = datetime.utcnow() + timedelta(hours=1)
        db.session.commit()
        reset_link = f"{request.host_url}api/admin/redirect-reset?token={token}&email={email}"
        subject = "استعادة كلمة المرور - مؤسسة الثانوية الاعدادية المنصور بمكناس"
        body = f"لقد تلقينا طلباً لاستعادة كلمة المرور لمؤسسة الثانوية الاعدادية المنصور بمكناس.\n\nاضغط على الرابط التالي لتعيين كلمة مرور جديدة:\n{reset_link}\n\nهذا الرابط صالح لمدة ساعة واحدة فقط."
        email_sent = send_email_with_pdf(subject, body, email)
        logger.info(f"Password reset email status for {email}: {email_sent}")
        
        if email_sent:
            return jsonify({'message': 'تم إرسال رابط استعادة كلمة المرور إلى البريد الإلكتروني الرسمي.', 'email_sent': True}), 200
        else:
            return jsonify({
                'message': f'فشل إرسال الإيميل (يرجى إعداد Vercel Variables). كإجراء احتياطي، إليك رابط الاستعادة: {reset_link}', 
                'email_sent': False
            }), 200
    
    logger.warning(f"Password reset requested for unknown/unauthorized email: {email}")
    return jsonify({'message': 'المسؤول غير موجود أو البريد غير مصرح له.'}), 404

@app.route('/api/admin/redirect-reset')
def redirect_reset():
    token = request.args.get('token')
    email = request.args.get('email')
    return f"<html><script>window.location.href = '/reset-password.html?token={token}&email={email}';</script></html>"

@app.route('/api/admin/reset-password', methods=['POST'])
def admin_reset_password():
    data = request.json
    admin = Admin.query.filter_by(email=data.get('email'), reset_token=data.get('token')).first()
    if not admin or admin.token_expiry < datetime.utcnow():
        return jsonify({'message': 'الرابط غير صالح أو انتهت صلاحيته.'}), 400
    admin.password = generate_password_hash(data.get('new_password'))
    admin.reset_token = None
    admin.token_expiry = None
    db.session.commit()
    return jsonify({'message': 'تم تحديث كلمة المرور بنجاح!'}), 200

# Database Initialization
try:
    with app.app_context():
        db.create_all()
        if not Admin.query.filter_by(email=ADMIN_EMAIL).first():
            # Create a default admin with hashed password
            db.session.add(Admin(email=ADMIN_EMAIL, password=generate_password_hash('admin_password')))
            db.session.commit()
            logger.info("Default admin created with hashed password.")
        
        if not SchoolStats.query.first():
            db.session.add(SchoolStats(students_count=0, teachers_count=0, experience_years=0, awards_count=0))
            db.session.commit()
            logger.info("Statistics initialized.")
except Exception as e:
    logger.error(f"Database initialization error: {e}")

if __name__ == '__main__':
    port = 5000 # Using stable port 5000
    logger.info(f"Starting Lycée Al-Mansour Server on port {port}...")
    print(f"\n" + "="*50)
    print(f" SERVER IS RUNNING ")
    print(f" URL: http://127.0.0.1:{port} ")
    print(f"="*50 + "\n")
    
    try:
        from waitress import serve
        serve(app, host='127.0.0.1', port=port) # Use 127.0.0.1 for local stability
    except ImportError:
        logger.warning("Waitress not found, falling back to Flask dev server.")
        app.run(debug=True, port=port, host='127.0.0.1')

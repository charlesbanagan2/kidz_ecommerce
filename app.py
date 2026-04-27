from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room
from flask_dance.contrib.google import make_google_blueprint, google
from flask_dance.consumer.storage.sqla import OAuthConsumerMixin, SQLAlchemyStorage
from flask_dance.consumer import oauth_authorized
from datetime import datetime, timedelta
from sqlalchemy import or_, inspect as sa_inspect
from werkzeug.utils import secure_filename
import os
from dotenv import load_dotenv
load_dotenv()
from email.mime.text import MIMEText
from PIL import Image
from requests.exceptions import RequestException
from flask import Response
import requests
import re
import time
import qrcode
import io
import base64
import json
import random
import smtplib
import string




PSGC_REMOTE_CANDIDATES = [
    "https://psgc.vercel.app/api",     # preferred dynamic endpoint
    "https://psgc.gitlab.io/api"       # static JSON mirror (user-provided curl examples)
]

# Allow HTTP for OAuth in development
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
# Ensure templates and static assets refresh during development
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
try:
    app.jinja_env.auto_reload = True
    app.jinja_env.cache = {}
except Exception:
    pass


# Database Configuration:
# - DATABASE_URI remains the primary setting used across existing deployments.
# - SUPABASE_DATABASE_URL is supported as a compatibility alias for Supabase-focused setups.
# - If neither is set, MySQL parts fallback is used.
DATABASE_URI = os.getenv('DATABASE_URI') or os.getenv('SUPABASE_DATABASE_URL')
if DATABASE_URI and DATABASE_URI.startswith('postgres://'):
    DATABASE_URI = DATABASE_URI.replace('postgres://', 'postgresql://', 1)
if not DATABASE_URI:
    MYSQL_USER = os.getenv('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', '')
    MYSQL_HOST = os.getenv('MYSQL_HOST', '127.0.0.1')
    MYSQL_PORT = os.getenv('MYSQL_PORT', '3306')
    MYSQL_DB = os.getenv('MYSQL_DB', 'kids_ecommerce')
    auth = f"{MYSQL_USER}:{MYSQL_PASSWORD}@" if MYSQL_PASSWORD else f"{MYSQL_USER}@"
    DATABASE_URI = f"mysql+pymysql://{auth}{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4"
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
engine_options = {
    'pool_pre_ping': True,
    'pool_recycle': 3600,
    'pool_timeout': 30
}
if DATABASE_URI.startswith(('mysql://', 'mysql+pymysql://', 'mariadb://', 'mariadb+pymysql://')):
    engine_options['connect_args'] = {
        'connect_timeout': 60,
        'read_timeout': 60,
        'write_timeout': 60
    }
elif DATABASE_URI.startswith(('postgres://', 'postgresql://', 'postgresql+psycopg2://')):
    engine_options['connect_args'] = {
        'connect_timeout': 60,
        'sslmode': os.getenv('DB_SSLMODE', 'require')
    }
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = engine_options
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# Google OAuth Configuration
app.config['GOOGLE_OAUTH_CLIENT_ID'] = '668360708226-q79n83ttq956po4cj3pd5qig0thiqp6c.apps.googleusercontent.com'
app.config['GOOGLE_OAUTH_CLIENT_SECRET'] = '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'

app.config['MAIL_SENDER'] = 'ccody7313@gmail.com'
app.config['MAIL_APP_PASSWORD'] = 'ecjdfangradrblcl' 

PSGC_REMOTE_BASE = 'https://psgc.vercel.app/api'

db = SQLAlchemy(app)

# DB helpers

def _is_sqlite():
    try:
        return db.engine.name == 'sqlite'
    except Exception:
        return False

def _is_mysql_or_mariadb():
    try:
        return db.engine.name in ('mysql', 'mariadb')
    except Exception:
        return False

def _is_postgresql():
    try:
        return db.engine.name == 'postgresql'
    except Exception:
        return False

# Enforce known supported SQLAlchemy engines
try:
    with app.app_context():
        if not (_is_mysql_or_mariadb() or _is_postgresql() or _is_sqlite()):
            raise RuntimeError(
                f"Unsupported database engine: {getattr(db.engine, 'name', 'unknown')}. "
                "Use a PostgreSQL/Supabase URI, MySQL/MariaDB URI, or SQLite."
            )
except Exception as _e:
    # Fail fast on startup
    raise
def try_remote_json(path, params=None, timeout=12):
    """Try candidate PSGC remotes and return requests.Response on first success."""
    params = params or {}
    last_exc = None
    for base in PSGC_REMOTE_CANDIDATES:
        url = base.rstrip('/') + '/' + path.lstrip('/')
        try:
            r = requests.get(url, params=params, timeout=timeout)
            # Accept 200 and JSON-like responses
            if r.status_code == 200 and r.headers.get('Content-Type', '').lower().startswith(('application/json','text/json','text/html')):
                return r
        except Exception as e:
            last_exc = e
            # try next candidate
    # if all failed, raise last exception (or return None)
    if last_exc:
        raise last_exc
    return None

@app.route('/api/regions')
def proxy_regions():
    try:
        # attempt known resource names/paths used by the public datasets
        # first try the vercel-style single resource path "region"
        for attempt in ("region", "regions.json", "regions"):
            try:
                r = try_remote_json(attempt)
                if r:
                    return Response(r.content, status=r.status_code, content_type=r.headers.get('Content-Type','application/json'))
            except Exception:
                continue
        # fallback: return empty list
        return jsonify([]), 503
    except Exception as e:
        app.logger.exception("PSGC regions proxy failed: %s", e)
        return jsonify([]), 503

@app.route('/api/provinces')
def proxy_provinces():
    region = request.args.get('region') or request.args.get('region_code') or ''
    params = {}
    if region:
        # some mirrors expect query param 'region' or 'region_code'
        params['region'] = region
    try:
        for attempt in ("province", "provinces.json", "provinces"):
            try:
                r = try_remote_json(attempt, params=params)
                if r:
                    return Response(r.content, status=r.status_code, content_type=r.headers.get('Content-Type','application/json'))
            except Exception:
                continue
        return jsonify([]), 503
    except Exception as e:
        app.logger.exception("PSGC provinces proxy failed: %s", e)
        return jsonify([]), 503

@app.route('/api/cities')
def proxy_cities():
    province = request.args.get('province') or request.args.get('province_code') or ''
    params = {}
    if province:
        params['province'] = province
    try:
        # try common candidate endpoints
        for attempt in ("city", "cities.json", "cities-municipalities.json", "cities-municipalities"):
            try:
                r = try_remote_json(attempt, params=params)
                if r:
                    return Response(r.content, status=r.status_code, content_type=r.headers.get('Content-Type','application/json'))
            except Exception:
                continue
        return jsonify([]), 503
    except Exception as e:
        app.logger.exception("PSGC cities proxy failed: %s", e)
        return jsonify([]), 503

@app.route('/api/barangays')
def proxy_barangays():
    city = request.args.get('city') or request.args.get('city_code') or ''
    params = {}
    if city:
        params['city'] = city
    try:
        for attempt in ("barangay", "barangays.json", "barangays"):
            try:
                r = try_remote_json(attempt, params=params)
                if r:
                    return Response(r.content, status=r.status_code, content_type=r.headers.get('Content-Type','application/json'))
            except Exception:
                continue
        return jsonify([]), 503
    except Exception as e:
        app.logger.exception("PSGC barangays proxy failed: %s", e)
        return jsonify([]), 503


# Template context processor to make cart_count, user info, and theme settings available in all templates
@app.context_processor
def inject_cart_count():
    context = {
        'cart_count': get_cart_count(),
        # default for seller inbox badge so templates don't error even if not logged in
        'unread_chat_count': 0,
    }

    # Default navbar avatar (generic)
    try:
        context['navbar_avatar_url'] = url_for('static', filename='user_avatar.png')
    except Exception:
        context['navbar_avatar_url'] = '/static/user_avatar.png'
    
    # Add search parameter from query string for search bar persistence
    context['search'] = request.args.get('search', '')
    
    # --- THEME SETTINGS BLOCK START ---
    # --- THEME SETTINGS BLOCK START ---
    # Example: fetch from DB; fallback to defaults if not set
    try:
        theme = ThemeSetting.query.first()
        context['theme_logo'] = theme.logo_filename if theme and theme.logo_filename else None
        context['theme_site_name'] = theme.site_name if theme and theme.site_name else "Kids & Baby Store"
        context['theme_primary_color'] = theme.primary_color if theme and theme.primary_color else "#0066ff"
        context['theme_secondary_color'] = theme.secondary_color if theme and theme.secondary_color else "#59b5fc"
        context['theme_footer_color'] = theme.footer_color if theme and theme.footer_color else "#232323"
    except Exception:
        # fallback defaults if ThemeSetting not ready
        context['theme_logo'] = None
        context['theme_site_name'] = "Kids & Baby Store"
        context['theme_primary_color'] = "#0066ff"
        context['theme_secondary_color'] = "#59b5fc"
        context['theme_footer_color'] = "#232323"

    # --- THEME SETTINGS BLOCK END ---

    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            active_role = session.get('active_role', user.role)
            context['current_user'] = user
            context['active_role'] = active_role

            # Try admin avatar first when admin
            # Use session avatar URL if available (immediately updated after profile changes)
            if 'navbar_avatar_url' in session:
                context['navbar_avatar_url'] = session['navbar_avatar_url']
                if 'avatar_timestamp' not in session:
                    session['avatar_timestamp'] = int(time.time())
            else:
                # Use helper function to get current avatar URL
                context['navbar_avatar_url'] = get_user_avatar_url(user.id, user.role)
                # Store in session for future requests
                session['navbar_avatar_url'] = context['navbar_avatar_url']
                session['avatar_timestamp'] = int(time.time())
            
            # Check if user can be a seller
            seller_app = SellerApplication.query.filter_by(user_id=user.id, status='approved').first()
            context['can_be_seller'] = user.role == 'seller' or (seller_app is not None)
            # Generic notifications in header for any role
            context['unread_notifications_count'] = Notification.query.filter_by(user_id=user.id, is_read=False).count()
            context['recent_notifications'] = Notification.query.filter_by(user_id=user.id).order_by(Notification.created_at.desc()).limit(5).all()

            # Seller chat inbox badge: count unread messages sent by buyers to this seller
            from sqlalchemy import and_
            try:
                context['unread_chat_count'] = StoreChatMessage.query.filter(
                    and_(
                        StoreChatMessage.seller_id == user.id,
                        StoreChatMessage.sender_role == 'buyer',
                        StoreChatMessage.is_read == False,
                    )
                ).count()
            except Exception:
                # If table not ready or query fails, leave default 0
                context['unread_chat_count'] = 0

            # Backward/role-specific keys for templates
            if user.role == 'admin':
                context['admin_unread_notifications'] = context['unread_notifications_count']
                context['admin_recent_notifications'] = context['recent_notifications']
            if active_role == 'seller' or user.role == 'seller':
                context['seller_unread_notifications'] = context['unread_notifications_count']
                context['seller_recent_notifications'] = context['recent_notifications']
            if active_role == 'buyer' or user.role == 'buyer':
                context['buyer_unread_notifications'] = context['unread_notifications_count']
                context['buyer_recent_notifications'] = context['recent_notifications']
    
    # Add utility functions to templates
    context['get_available_stock'] = get_available_stock
    
    return context


# --- Helper function to get user avatar URL ---
def get_user_avatar_url(user_id, user_role=None):
    """Get the current avatar URL for a user, checking file system with proper fallback"""
    try:
        upload_root = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
        if user_role == 'admin':
            avatar_rel = os.path.join('admin_avatars', f"admin_avatar_{user_id}.png")
        else:
            avatar_rel = os.path.join('user_avatars', f"user_avatar_{user_id}.png")
        avatar_path = os.path.join(upload_root, avatar_rel)
        if os.path.exists(avatar_path):
            return url_for('static', filename=f'uploads/{avatar_rel.replace("\\", "/")}')
    except Exception:
        pass
    return url_for('static', filename='user_avatar.png')  # Fallback

@app.context_processor
def avatar_helper():
    """Make avatar helper function available in all templates"""
    return dict(get_user_avatar_url=get_user_avatar_url)


def fetch_psgc(endpoint, params=None, timeout=15, max_pages=0, per_page=None, retry=2, backoff=1.0):
    """
    Fetch JSON list from PSGC and support pagination.
    - endpoint: e.g. "regions", "provinces", "cities-municipalities", "barangays"
    - params: dict of query params to send (will be copied per page)
    - timeout: per-request timeout
    - max_pages: 0 => iterate until no more pages; >0 => stop after that many pages
    - per_page: if supported by PSGC, pass as 'perPage' or 'limit' (function will try 'perPage' then 'limit')
    - retry: number of retries on transient errors
    - backoff: seconds to wait between retries (increases by factor 2)
    Returns: list of rows (possibly empty). On error returns the rows collected so far.
    """
    base_url = PSGC_BASE.rstrip('/') + '/' + endpoint.lstrip('/')
    collected = []
    page = 1
    done = False

    # Prepare params copy so we don't mutate caller's dict
    base_params = dict(params or {})

    # Decide on per-page key - try common conventions
    if per_page:
        # prefer 'perPage' then 'limit'
        base_params.setdefault('perPage', per_page)
        base_params.setdefault('limit', per_page)

    while not done:
        req_params = dict(base_params)
        # common pagination param names: page, pageNumber, page_no
        req_params.setdefault('page', page)
        req_params.setdefault('pageNumber', page)

        attempt = 0
        while attempt <= retry:
            try:
                resp = requests.get(base_url, params=req_params, timeout=timeout)
                resp.raise_for_status()
                data = resp.json()
                # Try to extract list payload robustly:
                rows = None
                if isinstance(data, list):
                    rows = data
                elif isinstance(data, dict):
                    # common container keys
                    for key in ('data','results','items','rows','results.items'):
                        if key in data and isinstance(data[key], list):
                            rows = data[key]
                            break
                    if rows is None:
                        # If response contains 'meta' with pagination info and 'data' list
                        if 'data' in data and isinstance(data['data'], list):
                            rows = data['data']
                        else:
                            # Attempt to find first list value
                            for v in data.values():
                                if isinstance(v, list):
                                    rows = v
                                    break
                    # Some PSGC endpoints return {"results": {"items": [...], "meta": {...}}}
                    if rows is None:
                        # Deep check
                        maybe = data.get('results') or data.get('data') or data.get('items')
                        if isinstance(maybe, dict):
                            for k in ('items','rows','data','results'):
                                if k in maybe and isinstance(maybe[k], list):
                                    rows = maybe[k]
                                    break
                # If still None, treat as empty list
                if rows is None:
                    rows = []

                # Append found rows
                if isinstance(rows, list) and rows:
                    collected.extend(rows)

                # Pagination termination logic:
                # - if no rows returned -> done
                if not rows:
                    done = True
                    break

                # - if max_pages is set and we've reached it
                if max_pages and page >= max_pages:
                    done = True
                    break

                # Try to detect if response includes meta/total_pages or links:
                total_pages = None
                if isinstance(data, dict):
                    meta = data.get('meta') or data.get('pagination') or data.get('paging')
                    if isinstance(meta, dict):
                        total_pages = meta.get('totalPages') or meta.get('total_pages') or meta.get('last_page') or meta.get('total_pages_count')
                    # links
                    links = data.get('links') or data.get('_links')
                    if isinstance(links, dict) and links.get('next') in (None, '', False):
                        done = True
                        break
                # If we don't have meta, increment page and continue
                page += 1
                # Safety: stop if page gets absurdly large (guard)
                if page > 10000:
                    app.logger.warning("PSGC fetch reached page cap for %s", endpoint)
                    done = True
                    break

                # Small polite pause to avoid hammering
                time.sleep(0.05)
                break  # success -> break retry loop

            except RequestException as exc:
                attempt += 1
                app.logger.warning("PSGC request error (attempt %s/%s) for %s page %s: %s", attempt, retry, endpoint, page, exc)
                if attempt > retry:
                    app.logger.exception("PSGC fetch failed permanently for %s page %s: %s", endpoint, page, exc)
                    # stop pagination and return what we have
                    done = True
                    break
                else:
                    time.sleep(backoff * (2 ** (attempt - 1)))
            except ValueError as exc:
                # JSON parse error
                app.logger.exception("PSGC returned non-JSON for %s page %s: %s", endpoint, page, exc)
                done = True
                break

    return collected

# Initialize SocketIO first
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Set up Google OAuth
google_bp = make_google_blueprint(
    client_id=app.config.get('GOOGLE_OAUTH_CLIENT_ID'),
    client_secret=app.config.get('GOOGLE_OAUTH_CLIENT_SECRET'),
    scope=[
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile"
    ],
    redirect_to="index"
)
app.register_blueprint(google_bp, url_prefix="/login")

# Add account selection prompt to Google OAuth
google_bp.authorization_url_params = {"prompt": "select_account"}



# QR Code Generation Functions
def generate_qr_code(order_id):
    """Generate unique QR code for order"""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    order_part = str(order_id).zfill(6)
    qr_code = f"KIDS{order_part}{timestamp}"
    return qr_code

def generate_tracking_number():
    """Generate unique tracking number"""
    random_part = ''.join(random.choices(string.digits, k=9))
    return f"TRK{random_part}"

def generate_batch_code():
    """Generate batch code for logistics"""
    date_part = datetime.now().strftime('%Y%m%d')
    time_part = datetime.now().strftime('%H%M')
    return f"BATCH{date_part}{time_part}"

def create_qr_image(qr_code, size=200):
    """Create QR code image as base64 string"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_code)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()
    
    return img_base64

def create_order_label_data(order):
    """Create comprehensive label data for QR code"""
    label_data = {
        'order_id': order.id,
        'buyer_name': f"{order.buyer.first_name} {order.buyer.last_name}",
        'buyer_phone': order.buyer.phone,
        'buyer_email': order.buyer.email,
        'total_amount': float(order.total_amount),
        'payment_method': order.payment_method,
        'shipping_address': order.shipping_address,
        'created_at': order.created_at.isoformat(),
        'items': []
    }
    
    # Add product information
    for item in order.items:
        item_data = {
            'product_id': item.product_id,
            'product_name': item.product.name,
            'quantity': item.quantity,
            'price': float(item.price_at_time),
            'seller_name': f"{item.product.seller.first_name} {item.product.seller.last_name}",
            'seller_id': item.product.seller_id
        }
        label_data['items'].append(item_data)
    
    return label_data

ALLOWED_IMAGE_EXT = {'png', 'jpg', 'jpeg'}
ALLOWED_VIDEO_EXT = {'mp4', 'webm', 'ogg', 'm4v', 'mov'}
MAX_VIDEO_BYTES = 50 * 1024 * 1024  # 50MB server-side safety limit

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXT

# Lightweight migration helper for SQLite to add product.video_filename if missing
from sqlalchemy import text as _sa_text

def ensure_product_video_column():
    try:
        inspector = sa_inspect(db.engine)
        try:
            cols = {c['name'] for c in inspector.get_columns('product')}
        except Exception:
            return
        stmts = []
        if 'video_filename' not in cols:
            stmts.append("ALTER TABLE product ADD COLUMN video_filename VARCHAR(255)")
        for s in stmts:
            db.session.execute(_sa_text(s))
        if stmts:
            db.session.commit()
    except Exception:
        db.session.rollback()
        pass

def ensure_product_gallery_column():
    try:
        inspector = sa_inspect(db.engine)
        try:
            cols = {c['name'] for c in inspector.get_columns('product')}
        except Exception:
            return
        if 'gallery' not in cols:
            # JSON type works for MySQL 5.7+/MariaDB 10.4+ (alias) and SQLite (as TEXT)
            db.session.execute(_sa_text("ALTER TABLE product ADD COLUMN gallery JSON"))
            db.session.commit()
    except Exception:
        db.session.rollback()
        pass

def ensure_return_request_request_type_column():
    """Ensure ReturnRequest has request_type column ("return" or "refund")."""
    try:
        inspector = sa_inspect(db.engine)
        try:
            cols = {c['name'] for c in inspector.get_columns('return_request')}
        except Exception:
            return
        if 'request_type' not in cols:
            db.session.execute(_sa_text("ALTER TABLE return_request ADD COLUMN request_type VARCHAR(20)"))
            db.session.commit()
    except Exception:
        db.session.rollback()
        pass

# Ensure Review has a JSON 'media' column to store uploaded images/videos
# and keep backward-compatible image_filename usage.
def ensure_review_media_column():
    try:
        inspector = sa_inspect(db.engine)
        try:
            cols = {c['name'] for c in inspector.get_columns('review')}
        except Exception:
            return
        if 'media' not in cols:
            db.session.execute(_sa_text("ALTER TABLE review ADD COLUMN media JSON"))
            db.session.commit()
    except Exception:
        db.session.rollback()
        pass

# Ensure Review has verified_purchase (BOOL) and order_id (INT) columns
# to match the ORM model and avoid 1054 unknown column errors
def ensure_review_extra_columns():
    try:
        inspector = sa_inspect(db.engine)
        try:
            cols = {c['name'] for c in inspector.get_columns('review')}
        except Exception:
            return
        stmts = []
        if 'verified_purchase' not in cols:
            # MySQL/MariaDB: BOOLEAN is alias of TINYINT(1)
            stmts.append("ALTER TABLE review ADD COLUMN verified_purchase BOOLEAN NOT NULL DEFAULT 0")
        if 'order_id' not in cols:
            stmts.append("ALTER TABLE review ADD COLUMN order_id INTEGER NULL")
        for s in stmts:
            db.session.execute(_sa_text(s))
        if stmts:
            db.session.commit()
    except Exception:
        db.session.rollback()
        pass

# Ensure DeliveryPersonnel has extended profile fields (address/id)
def ensure_delivery_personnel_extra_columns():
    try:
        inspector = sa_inspect(db.engine)
        try:
            cols = {c['name'] for c in inspector.get_columns('delivery_personnel')}
        except Exception:
            return
        to_add = []
        if 'address' not in cols:
            to_add.append("ALTER TABLE delivery_personnel ADD COLUMN address TEXT")
        if 'id_type' not in cols:
            to_add.append("ALTER TABLE delivery_personnel ADD COLUMN id_type VARCHAR(40)")
        if 'id_number' not in cols:
            to_add.append("ALTER TABLE delivery_personnel ADD COLUMN id_number VARCHAR(60)")
        if 'id_document' not in cols:
            to_add.append("ALTER TABLE delivery_personnel ADD COLUMN id_document VARCHAR(255)")
        if 'photo_path' not in cols:
            to_add.append("ALTER TABLE delivery_personnel ADD COLUMN photo_path VARCHAR(255)")
        for stmt in to_add:
            db.session.execute(_sa_text(stmt))
        if to_add:
            db.session.commit()
    except Exception:
        db.session.rollback()
        pass

# Ensure migration runs once per process before handling requests (Flask 3.x safe)
@app.before_request
def _run_light_migrations_once():
    if not app.config.get('_video_migration_ran', False):
        try:
            ensure_product_video_column()
            app.config['_video_migration_ran'] = True
        except Exception:
            # Avoid blocking requests if migration check fails
            app.config['_video_migration_ran'] = True  # prevent repeated attempts
            pass
    # Ensure tables exist for new features (e.g., ReturnRequest, ReturnPickup)
    if not app.config.get('_schema_ready', False):
        try:
            db.create_all()
            app.config['_schema_ready'] = True
        except Exception:
            app.config['_schema_ready'] = True
            pass

    # Auto-approve stale return requests past review_deadline (every ~5 minutes)
    try:
        last = app.config.get('_returns_escalation_last')
        now = datetime.utcnow()
        if not last or (now - last).total_seconds() > 300:
            _auto_approve_overdue_returns()
            app.config['_returns_escalation_last'] = now
    except Exception:
        pass

# Ensure migration runs before any endpoint uses Product
@app.before_request
def _ensure_schema_migrations():
    try:
        ensure_product_video_column()
        ensure_return_request_request_type_column()
        ensure_review_media_column()
        ensure_review_extra_columns()
        ensure_product_gallery_column()
        ensure_delivery_personnel_extra_columns()
        ensure_notification_extra_columns()
    except Exception:
        # Avoid blocking requests if migration check fails
        pass


# PSGC sync helper (paste this into app.py AFTER your existing api_streets_db route)
# NOTE: requests is already imported in your app.py; this snippet uses app.logger (no additional imports).

PSGC_BASE = "https://psgc.cloud/api"

# helper: try multiple possible key names from PSGC payloads
def _get_field(obj, candidates, default=None):
    for k in candidates:
        if isinstance(obj, dict) and k in obj and obj[k] not in (None, ''):
            return obj[k]
    return default


def upsert_region(code, name):
    if not code:
        return
    r = Region.query.filter_by(code=code).first()
    if r:
        r.name = name or r.name
    else:
        r = Region(code=code, name=name or code)
        db.session.add(r)

def upsert_province(code, name, region_code):
    if not code:
        return
    p = Province.query.filter_by(code=code).first()
    if p:
        p.name = name or p.name
        p.region_code = region_code or p.region_code
    else:
        p = Province(code=code, name=name or code, region_code=region_code or '')
        db.session.add(p)

def upsert_city(code, name, province_code):
    if not code:
        return
    c = City.query.filter_by(code=code).first()
    if c:
        c.name = name or c.name
        c.province_code = province_code or c.province_code
    else:
        c = City(code=code, name=name or code, province_code=province_code or '')
        db.session.add(c)

def upsert_barangay(code, name, city_code):
    if not code:
        return
    b = Barangay.query.filter_by(code=code).first()
    if b:
        b.name = name or b.name
        b.city_code = city_code or b.city_code
    else:
        b = Barangay(code=code, name=name or code, city_code=city_code or '')
        db.session.add(b)

def sync_regions():
    rows = fetch_psgc("regions")
    count = 0
    for item in rows:
        code = _get_field(item, ['code', 'psgcCode', 'regionCode', 'region_code'])
        name = _get_field(item, ['name', 'regionName', 'region_name'])
        if not code and 'region' in item:
            code = _get_field(item['region'], ['code','psgcCode'])
            name = _get_field(item['region'], ['name'])
        if not code:
            continue
        upsert_region(code, name)
        count += 1
    db.session.commit()
    return count

def sync_provinces():
    rows = fetch_psgc("provinces")
    count = 0
    for item in rows:
        code = _get_field(item, ['code','psgcCode','provinceCode','province_code'])
        name = _get_field(item, ['name','provinceName','province_name'])
        parent = _get_field(item, ['regionCode','region_code','region','region_code'])
        if not parent and isinstance(item, dict) and 'region' in item and isinstance(item['region'], dict):
            parent = _get_field(item['region'], ['code','psgcCode'])
        if not code:
            continue
        upsert_province(code, name, parent or '')
        count += 1
    db.session.commit()
    return count


def upsert_city_municipality(psgc_code, name, prov_id=None, type=None, zip_code=None, district=None):
    if not psgc_code:
        return
    cm = CityMunicipality.query.filter_by(psgc_code=psgc_code).first()
    if cm:
        cm.name = name or cm.name
        cm.province_id = prov_id or cm.province_id
        cm.type = type or cm.type
        cm.zip_code = zip_code or cm.zip_code
        cm.district = district or cm.district
    else:
        cm = CityMunicipality(
            psgc_code=psgc_code,
            name=name or psgc_code,
            province_id=prov_id or None,
            type=type,
            zip_code=zip_code,
            district=district
        )
        db.session.add(cm)
        
        
def sync_cities():
    rows = fetch_psgc("cities-municipalities")
    count = 0
    for item in rows:
        code = _get_field(item, ['code','psgcCode','cityMunCode','cityMunicipalityCode','psgc_code'])
        name = _get_field(item, ['name','cityMunName','city_municipality_name','cityName'])
        parent_code = _get_field(item, ['provinceCode','province_code','provCode'])
        # resolve province_id if we have a parent_code (which may be province code)
        prov_id = None
        if parent_code:
            prov = Province.query.filter_by(code=parent_code).first()
            if prov:
                prov_id = prov.id
        # fallback: if item has 'province' dict with 'id' or 'psgcCode' etc.
        upsert_city_municipality(code, name, prov_id=prov_id, type=_get_field(item, ['type']), zip_code=_get_field(item, ['zip_code','zipCode']))
        count += 1
    db.session.commit()
    return count
def sync_barangays():
    rows = fetch_psgc("barangays")
    count = 0
    for item in rows:
        code = _get_field(item, ['code','psgcCode','barangayCode','brgyCode','barangay_code'])
        name = _get_field(item, ['name','barangay','barangayName','brgy_name'])
        parent = _get_field(item, ['cityMunCode','cityCode','city_code','city_municipality_code','cityMunicipalityCode'])
        if not parent and isinstance(item, dict) and 'city' in item and isinstance(item['city'], dict):
            parent = _get_field(item['city'], ['code','psgcCode'])
        if not code:
            continue
        upsert_barangay(code, name, parent or '')
        count += 1
    db.session.commit()
    return count

@app.route('/admin/sync-psgc', methods=['GET','POST'])
def admin_sync_psgc():
    """
    Admin-only route to fetch the PSGC dataset and populate local tables.
    This version performs an inline admin check so it can be placed before
    the admin_required decorator is declared elsewhere in the file.
    """
    # inline admin check (avoids using @admin_required which may be defined later)
    if not is_admin():
        flash('Admin access required.', 'error')
        return redirect(url_for('index'))

    try:
        r_count = sync_regions()
        p_count = sync_provinces()
        c_count = sync_cities()
        b_count = sync_barangays()
        flash(f"PSGC sync completed: regions={r_count}, provinces={p_count}, cities={c_count}, barangays={b_count}", 'success')
    except Exception as e:
        app.logger.exception("PSGC sync failed: %s", e)
        flash("PSGC sync failed. Check logs.", 'danger')
    return redirect(request.referrer or url_for('admin_dashboard'))

# Optional programmatic helper if you prefer running from Python shell:
def sync_all_psgc():
    """Programmatic sync helper. Run inside app.app_context()"""
    r = sync_regions()
    p = sync_provinces()
    c = sync_cities()
    b = sync_barangays()
    return {"regions": r, "provinces": p, "cities": c, "barangays": b}


# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)  # Not hashed as requested
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text, nullable=False)
    role = db.Column(db.String(20), default='buyer')  # buyer, seller, admin
    status = db.Column(db.String(20), default='active')  # active, pending, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Security settings
    two_factor_enabled = db.Column(db.Boolean, default=False)  # Two-factor authentication
    email_notifications = db.Column(db.Boolean, default=True)  # Email notifications
    email_verified = db.Column(db.Boolean, default=False)
    verification_code = db.Column(db.String(10))
    
     # NEW: path to uploaded valid ID (relative/public path)
    valid_id = db.Column(db.String(255), nullable=True)

class SellerApplication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    store_name = db.Column(db.String(120), nullable=False)
    store_description = db.Column(db.Text)
    store_category = db.Column(db.String(100), nullable=False)
    business_address = db.Column(db.Text, nullable=False)
    school_id_document = db.Column(db.String(255))  # File path for uploaded document
    gcash_number = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # New fields for enhanced seller profile
    store_logo = db.Column(db.String(255))  # Store logo file path
    store_mission = db.Column(db.Text)  # Store mission statement
    return_policy = db.Column(db.Text)  # Return policy description
    return_days = db.Column(db.Integer, default=7)  # Return period in days
    refund_method = db.Column(db.String(50), default='Original Payment Method')  # Refund method
    business_registration = db.Column(db.String(255))  # Business registration document
    valid_id = db.Column(db.String(255))  # Valid ID document
    
    user = db.relationship('User', backref='seller_applications', foreign_keys=[user_id])


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, processing, shipped, completed, cancelled
    payment_method = db.Column(db.String(50), nullable=False)
    payment_status = db.Column(db.String(20), default='pending')  # pending, paid, failed, refunded
    shipping_address = db.Column(db.Text, nullable=False)
    stock_deducted = db.Column(db.Boolean, default=False)  # TRUE kapag na-process na ng seller
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # QR Code and Tracking fields
    qr_code = db.Column(db.String(255), unique=True)
    tracking_number = db.Column(db.String(50), unique=True)
    batch_code = db.Column(db.String(50))
    label_generated_at = db.Column(db.DateTime)
    packed_at = db.Column(db.DateTime)
    picked_up_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime)
    packed_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    picked_up_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    delivered_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    shipping_notes = db.Column(db.Text)
    delivery_notes = db.Column(db.Text)
    
    buyer = db.relationship('User', backref='orders', foreign_keys=[buyer_id])
    packed_by_user = db.relationship('User', foreign_keys=[packed_by], backref='packed_orders')
    picked_up_by_user = db.relationship('User', foreign_keys=[picked_up_by], backref='picked_up_orders')
    delivered_by_user = db.relationship('User', foreign_keys=[delivered_by], backref='delivered_orders')

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price_at_time = db.Column(db.Float, nullable=False)  # Price when ordered
    order = db.relationship('Order', backref='items')
    product = db.relationship('Product')

class Cart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='cart_items')
    product = db.relationship('Product')

class OrderLabel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    qr_code = db.Column(db.String(255), unique=True, nullable=False)
    tracking_number = db.Column(db.String(50), unique=True, nullable=False)
    batch_code = db.Column(db.String(50), nullable=False)
    label_data = db.Column(db.JSON, nullable=False)
    status = db.Column(db.String(20), default='generated')  # generated, printed, packed, picked_up, in_transit, delivered, returned
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    packed_at = db.Column(db.DateTime)
    picked_up_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime)
    returned_at = db.Column(db.DateTime)
    packed_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    picked_up_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    delivered_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    returned_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    shipping_notes = db.Column(db.Text)
    delivery_notes = db.Column(db.Text)
    return_notes = db.Column(db.Text)
    
    order = db.relationship('Order', backref='labels')


class SellerOrderSeen(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, index=True, nullable=False)
    order_id = db.Column(db.Integer, index=True, nullable=False)
    seen_at = db.Column(db.DateTime, default=datetime.utcnow)

# Return & Refund Request model
class ReturnRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    order_item_id = db.Column(db.Integer, db.ForeignKey('order_item.id'), nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    reason_other = db.Column(db.Text)  # Additional reason details when "Others" is selected
    description = db.Column(db.Text)  # Buyer's detailed description of the issue
    quantity = db.Column(db.Integer, default=1)  # Quantity requested for return
    images = db.Column(db.JSON)  # List of image paths
    video_filename = db.Column(db.String(255))  # Video filename
    request_type = db.Column(db.String(20), nullable=False)  # 'return' or 'refund'
    status = db.Column(db.String(30), default='submitted')  # Updated status values
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)
    processed_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    refund_amount = db.Column(db.Float)
    admin_notes = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    seller_response_reason = db.Column(db.Text)  # Reason provided by seller when rejecting

    order = db.relationship('Order', backref='return_requests')
    order_item = db.relationship('OrderItem')
    buyer = db.relationship('User', foreign_keys=[buyer_id])
    seller = db.relationship('User', foreign_keys=[seller_id])

# Restock Request model
class RestockRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    requested_quantity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)
    processed_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    admin_notes = db.Column(db.Text)
    approved_quantity = db.Column(db.Integer)  # Quantity approved by admin
    
    # Relationships
    product = db.relationship('Product', backref='restock_requests')
    seller = db.relationship('User', foreign_keys=[seller_id], backref='restock_requests')
    processor = db.relationship('User', foreign_keys=[processed_by])

# Rider pickup task for returns
class ReturnPickup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    return_request_id = db.Column(db.Integer, db.ForeignKey('return_request.id'), nullable=False)
    rider_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(30), default='available')  # available, waiting_rider_pickup, rider_picked_up, rider_delivered_to_seller
    buyer_address = db.Column(db.Text)
    seller_address = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    picked_up_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime)

    return_request = db.relationship('ReturnRequest', backref='pickup_task')
    rider = db.relationship('User', foreign_keys=[rider_id])

def _auto_approve_overdue_returns():
    overdue = ReturnRequest.query.filter(
        ReturnRequest.status.in_(['submitted','seller_reviewing']),
        ReturnRequest.review_deadline != None,
        ReturnRequest.review_deadline <= datetime.utcnow()
    ).all()
    for rr in overdue:
        # Move to waiting_rider_pickup and create a pickup task
        rr.status = 'waiting_rider_pickup'
        buyer_addr = rr.order.shipping_address if rr.order else ''
        seller_addr = ''
        try:
            appq = SellerApplication.query.filter_by(user_id=rr.seller_id, status='approved').first()
            seller_addr = appq.business_address if appq and appq.business_address else ''
        except Exception:
            seller_addr = ''
        task = ReturnPickup(return_request_id=rr.id, buyer_address=buyer_addr, seller_address=seller_addr, status='available')
        db.session.add(task)
        try:
            push_notification(rr.buyer_id, 'Your return/refund request was auto-approved. A rider will pick up your parcel.')
            socketio.emit('return_pickup_available', {'return_id': rr.id}, room='riders')
        except Exception:
            pass
    if overdue:
        db.session.commit()

class QRScanLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    order_label_id = db.Column(db.Integer, db.ForeignKey('order_label.id'), nullable=False)
    qr_code = db.Column(db.String(255), nullable=False)
    scanned_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    scan_type = db.Column(db.String(20), nullable=False)  # packing, pickup, delivery, return, inquiry
    scan_location = db.Column(db.String(255))
    scan_notes = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    order = db.relationship('Order', backref='scan_logs')
    order_label = db.relationship('OrderLabel', backref='scan_logs')
    scanned_by_user = db.relationship('User', backref='qr_scans')

class DeliveryPersonnel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    employee_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    vehicle_type = db.Column(db.String(50))
    vehicle_number = db.Column(db.String(20))
    status = db.Column(db.String(20), default='active')  # active, inactive, on_duty, off_duty
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = db.relationship('User', backref='delivery_personnel')

# Temporarily commented out to allow server startup
# class ProductQR(db.Model):
#     id = db.Column(db.Integer, primary_key=True)
#     product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
#     qr_code = db.Column(db.String(255), unique=True, nullable=False)
#     batch_number = db.Column(db.String(50))
#     manufacturing_date = db.Column(db.Date)
#     expiry_date = db.Column(db.Date)
#     status = db.Column(db.String(20), default='active')  # active, sold, returned, damaged, expired
#     created_at = db.Column(db.DateTime, default=datetime.utcnow)
#     updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
#     
#     product = db.relationship('Product', backref='qr_codes')

class Wishlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='wishlist_items')
    product = db.relationship('Product')

class Address(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    label = db.Column(db.String(50), nullable=False)  # Home, Work, etc.
    full_address = db.Column(db.Text, nullable=False)
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    region = db.Column(db.String(120), nullable=True)
    province = db.Column(db.String(120), nullable=True)
    city = db.Column(db.String(120), nullable=True)
    barangay = db.Column(db.String(120), nullable=True)
    street = db.Column(db.String(255), nullable=True)
    user = db.relationship('User', backref='addresses')
    latitude = db.Column(db.Float, default=None)
    longitude = db.Column(db.Float, default=None)

class OAuth(OAuthConsumerMixin, db.Model):
    provider_user_id = db.Column(db.String(256), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey(User.id), nullable=False)
    user = db.relationship("User")
    
    def __init__(self, **kwargs):
        super(OAuth, self).__init__(**kwargs)
        if 'token' not in kwargs:
            self.token = {}

class AdminProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    full_name = db.Column(db.String(160), nullable=False)
    contact_number = db.Column(db.String(20))
    system_role = db.Column(db.String(50), default='Administrator')
    last_login = db.Column(db.DateTime)
    account_status = db.Column(db.String(20), default='Active')
    two_factor_enabled = db.Column(db.Boolean, default=False)
    password_reset_required = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = db.relationship('User', backref='admin_profile')

class AdminSecurityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    details = db.Column(db.Text)
    user = db.relationship('User', backref='security_logs')


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    # Optional rich fields
    image_url = db.Column(db.String(255))        # avatar/thumbnail for the notification (single)
    link = db.Column(db.String(255))             # where to go when clicked
    type = db.Column(db.String(40))              # e.g., 'chat', 'order', 'system'
    actor_user_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # who triggered it (e.g., rider)
    order_id = db.Column(db.Integer)             # associated order (for thumbnails)
    images = db.Column(db.JSON)                  # list of image URLs (e.g., ['/static/uploads/...','...'])
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Disambiguate the two FKs to User with foreign_keys on each relationship
    user = db.relationship('User', foreign_keys=[user_id], backref='notifications')
    actor = db.relationship('User', foreign_keys=[actor_user_id])

# Generic wallet ledger for riders and sellers
class WalletTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    amount = db.Column(db.Float, nullable=False)  # positive for credit, negative for debit
    type = db.Column(db.String(20), default='credit')  # credit or debit
    source = db.Column(db.String(50))  # order_delivery, payout, adjustment
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='wallet_transactions')
    order = db.relationship('Order', backref='wallet_transactions')

# Earnings split configuration (commission released on buyer confirmation -> completed)
RIDER_EARNING_RATE = 0.15   # 15% of order total to the rider
SELLER_EARNING_RATE = 0.80  # 80% to seller(s) (distributed by item proportion)
ADMIN_EARNING_RATE = 0.05   # 5% to admin(s)


def credit_wallet(user_id: int, amount: float, source: str, order_id: int = None):
    if amount == 0:
        return
    tx = WalletTransaction(user_id=user_id, order_id=order_id, amount=float(amount), type='credit', source=source)
    db.session.add(tx)


def get_user_earnings(user_id: int, period: str = 'today') -> float:
    """Return sum of credits for a user within the period: today|week|month|all."""
    now = datetime.utcnow()
    q = WalletTransaction.query.filter_by(user_id=user_id, type='credit')
    if period == 'today':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        q = q.filter(WalletTransaction.created_at >= start)
    elif period == 'week':
        start = now - timedelta(days=7)
        q = q.filter(WalletTransaction.created_at >= start)
    elif period == 'month':
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        q = q.filter(WalletTransaction.created_at >= start)
    return float(q.with_entities(db.func.coalesce(db.func.sum(WalletTransaction.amount), 0.0)).scalar() or 0.0)


def push_notification(user_id: int, message: str, image_url: str = None, link: str = None, actor_user_id: int = None, type: str = None, order_id: int = None, images: list = None):
    """Create a notification and emit it via websockets. If order_id or an "Order #123" appears in message, attach product thumbnails."""
    try:
        # Infer order_id from message if not provided
        if order_id is None:
            try:
                import re as _re
                m = _re.search(r"order\s*#(\d+)", message, _re.IGNORECASE)
                if m:
                    order_id = int(m.group(1))
            except Exception:
                pass
        # Build images list from order if available and not explicitly provided
        if images is None and order_id:
            try:
                o = Order.query.filter_by(id=order_id).first()
                if o and o.items:
                    imgs = []
                    for it in o.items:
                        fn = getattr(it.product, 'image_filename', None)
                        if fn:
                            imgs.append(url_for('static', filename=f'uploads/{fn}'))
                        if len(imgs) >= 4:
                            break
                    images = imgs or None
            except Exception:
                images = None
        n = Notification(user_id=user_id, message=message, image_url=image_url, link=link, actor_user_id=actor_user_id, type=type, order_id=order_id, images=images)
        db.session.add(n)
        db.session.commit()
    except Exception:
        db.session.rollback()
    # real-time push
    try:
        payload = {'message': message}
        if image_url:
            payload['image_url'] = image_url
        if link:
            payload['link'] = link
        if type:
            payload['type'] = type
        if actor_user_id:
            payload['actor_user_id'] = actor_user_id
        if order_id:
            payload['order_id'] = order_id
        if images:
            payload['images'] = images
        socketio.emit('notification', payload, room=f'user_{user_id}')
    except Exception:
        pass


def _admins():
    return User.query.filter_by(role='admin').all()


def _order_already_commissioned(order_id: int) -> bool:
    return WalletTransaction.query.filter_by(order_id=order_id, source='order_commission').first() is not None


def _release_commissions(order: 'Order'):
    """Release commissions once buyer confirms receipt (status: completed). Safe to call idempotently."""
    if _order_already_commissioned(order.id):
        return
    total = float(order.total_amount)
    # Rider
    if order.picked_up_by:
        credit_wallet(order.picked_up_by, total * RIDER_EARNING_RATE, 'order_commission', order.id)
    # Sellers: proportional by item subtotal
    seller_totals = {}
    for it in order.items:
        seller_totals.setdefault(it.product.seller_id, 0.0)
        seller_totals[it.product.seller_id] += float(it.price_at_time) * it.quantity
    seller_total_amount = sum(seller_totals.values()) or 0.0
    if seller_total_amount > 0:
        for sid, sub in seller_totals.items():
            credit_wallet(sid, (sub / seller_total_amount) * (total * SELLER_EARNING_RATE), 'order_commission', order.id)
    # Admins
    admins = _admins()
    if admins:
        admin_amount_each = (total * ADMIN_EARNING_RATE) / len(admins)
        for a in admins:
            credit_wallet(a.id, admin_amount_each, 'order_commission', order.id)
    db.session.commit()


# Chat message model
class StoreChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    message = db.Column(db.Text, nullable=False)
    sender_role = db.Column(db.String(10), nullable=False)  # 'buyer' or 'seller'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

    buyer = db.relationship('User', foreign_keys=[buyer_id])
    seller = db.relationship('User', foreign_keys=[seller_id])
    product = db.relationship('Product')

# Buyer ↔ Rider chat messages
class RiderChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rider_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    message = db.Column(db.Text, nullable=False)
    sender_role = db.Column(db.String(10), nullable=False)  # 'buyer' or 'rider'
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    buyer = db.relationship('User', foreign_keys=[buyer_id])
    rider = db.relationship('User', foreign_keys=[rider_id])
    order = db.relationship('Order')


class HeroSlide(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image_filename = db.Column(db.String(255), nullable=False)
    title = db.Column(db.String(255))
    description = db.Column(db.Text)
    link = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ThemeSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    logo_filename = db.Column(db.String(255))
    site_name = db.Column(db.String(100), default='Kids & Baby Store')
    primary_color = db.Column(db.String(20), default='#0066ff')
    secondary_color = db.Column(db.String(20), default='#59b5fc')
    footer_color = db.Column(db.String(20), default='#232323')
    slide_duration = db.Column(db.Float, default=6)
    transition_duration = db.Column(db.Float, default=0.8)
    
    
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    cover_image_filename = db.Column(db.String(255))

    subcategories = db.relationship('Subcategory', backref='category', lazy=True)

class Subcategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    status = db.Column(db.String(20), default='active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    products = db.relationship('Product', backref='subcategory', lazy=True)
    
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)
    image_filename = db.Column(db.String(120))
    # NEW: optional product video filename (stored under static/uploads/videos)
    video_filename = db.Column(db.String(255))
    # NEW: additional gallery images (list of filenames under static/uploads)
    gallery = db.Column(db.JSON)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    subcategory_id = db.Column(db.Integer, db.ForeignKey('subcategory.id'))  # <-- NEW
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='active')
    featured = db.Column(db.Boolean, default=False)
    show_in_new_arrival = db.Column(db.Boolean, default=False)   # <-- NEW FLAG
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    category = db.relationship('Category', backref='products')
    # Cascade deletes from User -> products at ORM level; DB-level CASCADE may require a migration
    seller = db.relationship('User', backref=db.backref('products', cascade='all, delete-orphan'))
    
class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1-5 stars
    title = db.Column(db.String(120))
    content = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='published')  # published, pending, hidden
    image_filename = db.Column(db.String(255))  # legacy single image support
    media = db.Column(db.JSON)  # list of {type:'image'|'video', 'path': '/static/uploads/reviews/...'}
    verified_purchase = db.Column(db.Boolean, default=False)  # True if user purchased product
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))  # Link to purchase order

    product = db.relationship('Product', backref='reviews')
    user = db.relationship('User', backref='reviews')
    order = db.relationship('Order', backref='reviews')


class Coupon(db.Model):
    """Simple coupon/discount model for checkout."""
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(255))
    # 'percent' = percentage (e.g. 10 => 10% off subtotal), 'fixed' = fixed peso value
    discount_type = db.Column(db.String(20), default='percent')
    discount_value = db.Column(db.Float, nullable=False)
    min_order_amount = db.Column(db.Float, default=0.0)  # minimum subtotal required
    max_uses = db.Column(db.Integer)  # null/None = unlimited
    used_count = db.Column(db.Integer, default=0)
    valid_from = db.Column(db.DateTime)
    valid_until = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Follow(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('follower_id', 'seller_id', name='uq_follower_seller'),
    )

    follower = db.relationship('User', foreign_keys=[follower_id], backref='following')
    seller = db.relationship('User', foreign_keys=[seller_id], backref='followers')

class RiderApplication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    vehicle_type = db.Column(db.String(50), nullable=False)
    vehicle_number = db.Column(db.String(20), nullable=False)
    employee_id = db.Column(db.String(50))  # Optional, can be generated
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    applied_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id'))

    # Explicit relationships to disambiguate foreign keys:
    user = db.relationship(
        'User',
        foreign_keys=[user_id],
        backref=db.backref('rider_applications', lazy='dynamic')
    )
    reviewer = db.relationship(
        'User',
        foreign_keys=[reviewed_by],
        backref=db.backref('rider_reviews', lazy='dynamic')
    )




# Helper to notify all admins
def notify_admins(message, *, type=None, link=None, image_url=None):
    """Notify all admins and emit real-time. Optional metadata: type/link/image_url."""
    admin_users = User.query.filter_by(role='admin').all()
    ids = []
    for admin in admin_users:
        n = Notification(user_id=admin.id, message=message, type=type, link=link, image_url=image_url)
        db.session.add(n)
        ids.append(admin.id)
    db.session.commit()
    try:
        for aid in ids:
            payload = {'message': message}
            if type: payload['type'] = type
            if link: payload['link'] = link
            if image_url: payload['image_url'] = image_url
            socketio.emit('notification', payload, room=f'user_{aid}')
    except Exception:
        pass


# Configure OAuth storage after models are defined
google_bp.storage = SQLAlchemyStorage(OAuth, db.session, user=lambda: User.query.get(session.get('user_id')) if 'user_id' in session else None, user_required=False)

# OAuth signal handler
@oauth_authorized.connect_via(google_bp)
def google_logged_in(blueprint, token):
    """
    Google OAuth login handler.
    Modified to enforce ADMIN APPROVAL before a user (Googleâ€‘registered) can log in.
    A Google signâ€‘in will:
      - Create a 'pending' user (status='pending') if new.
      - NOT start a session until the account is approved (status becomes 'active').
      - Block login for existing OAuth or email accounts whose status != 'active'.
    """
    if not token:
        flash('Failed to log in with Google.', 'error')
        return False
    
    resp = blueprint.session.get("/oauth2/v3/userinfo")
    if not resp.ok:
        flash('Failed to fetch user info from Google.', 'error')
        return False
    
    google_info = resp.json()
    google_user_id = str(google_info.get("sub", google_info.get("id", "")))
    
    # Check if OAuth record already exists
    oauth_record = OAuth.query.filter_by(
        provider=blueprint.name,
        provider_user_id=google_user_id
    ).first()
    
    if oauth_record:
        user = oauth_record.user
        # ENFORCE ADMIN APPROVAL
        if user.status != 'active':
            flash('Your account is pending admin approval. Please wait for confirmation before logging in.', 'warning')
            return False
        # Proceed with normal login
        session['user_id'] = user.id
        session['user_name'] = f"{user.first_name} {user.last_name}"
        session['user_role'] = user.role
        session['active_role'] = user.role
        flash('Welcome back!', 'success')
        return False  # Do not resave token
    
    # If user exists (matched by email) but no OAuth record yet
    user = User.query.filter_by(email=google_info["email"]).first()
    if user:
        # If user exists but NOT yet approved
        if user.status != 'active':
            flash('Your account is pending admin approval. You will be able to log in once approved.', 'warning')
            # Do NOT create OAuth record yet (to avoid premature login linkage)
            return False
        # User active: create OAuth link and log in
        oauth_record = OAuth(
            provider=blueprint.name,
            provider_user_id=google_user_id,
            user=user,
            token=token
        )
        db.session.add(oauth_record)
        db.session.commit()
        session['user_id'] = user.id
        session['user_name'] = f"{user.first_name} {user.last_name}"
        session['user_role'] = user.role
        session['active_role'] = user.role
        flash('Google account linked successfully!', 'success')
        return False
    
    # New Google user: create as PENDING (requires admin approval)
    new_user = User(
        first_name=google_info.get("given_name", "Google"),
        last_name=google_info.get("family_name", "User"),
        email=google_info["email"],
        password="google_oauth",  # still a placeholder (should be replaced / hashed in production)
        phone="",
        address="",
        role="buyer",
        status="pending",          # CRITICAL: must be approved before login
        email_verified=True        # Mark email verified (Google guarantees it); approval still required
    )
    db.session.add(new_user)
    db.session.commit()
    
    # Notify admins there is a new pending Google registration
    try:
        notify_admins(f'New Google registration pending approval: {new_user.first_name} {new_user.last_name} ({new_user.email})')
    except Exception:
        pass
    
    flash('Account created and pending admin approval. You will be able to log in once an administrator approves your account.', 'info')
    # IMPORTANT: Do NOT create OAuth record or start a session yet.
    return False



# Helper functions
def validate_password(password):
    """Validate password against professional requirements"""
    if len(password) < 8 or len(password) > 12:
        return False, "Password must be 8-12 characters long"
    
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r"\d", password):
        return False, "Password must contain at least one number"
    
    if not re.search(r"[!@#$%^&*\-_]", password):
        return False, "Password must contain at least one special character (!@#$%^&*-_)"
    
    # Check for common weak passwords
    weak_passwords = ['password', 'password123', '12345678', 'qwerty123', 'admin123']
    if password.lower() in weak_passwords:
        return False, "This is a common weak password, please choose a stronger one"
    
    return True, "Password is strong"

def calculate_password_strength(password):
    """Calculate password strength score (0-100)"""
    score = 0
    
    # Length score (0-25)
    if len(password) >= 8:
        score += min(25, len(password) * 2)
    
    # Character type scores
    if re.search(r"[A-Z]", password):
        score += 20
    if re.search(r"[a-z]", password):
        score += 20
    if re.search(r"\d", password):
        score += 15
    if re.search(r"[!@#$%^&*\-_]", password):
        score += 20
    
    # Deduct for common patterns
    if password.lower() in ['password', 'password123', '12345678']:
        score = max(0, score - 30)
    
    return min(100, score)

def _send_refund_email(user, amount, order_id):
    try:
        subject = f"Refund processed for Order #{order_id}"
        body = (
            f"Hi {getattr(user,'first_name','Customer')},\n\n"
            f"Your return/refund has been completed. We credited ₱{float(amount):,.2f} to your wallet.\n"
            f"Order ID: {order_id}\n\n"
            "Thank you for shopping with us.\n"
            "Kids & Baby Store Team"
        )
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = app.config['MAIL_SENDER']
        msg['To'] = user.email
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(app.config['MAIL_SENDER'], app.config['MAIL_APP_PASSWORD'])
            smtp.send_message(msg)
    except Exception as e:
        app.logger.exception('Failed to send refund email to %s: %s', getattr(user,'email','unknown'), e)


def get_cart_count():
    if 'user_id' not in session:
        return 0
    user = User.query.get(session['user_id'])
    if not user or user.role == 'admin':
        return 0
    # Only show cart count in buyer mode
    active_role = session.get('active_role', user.role)
    if active_role != 'buyer':
        return 0
    return Cart.query.filter_by(user_id=session['user_id']).count()

def can_user_review_product(user_id, product_id):
    """
    Check if a user can review a product based on purchase history.
    Returns: (can_review: bool, order_id: int or None, message: str)
    """
    # Check if user already reviewed this product
    existing_review = Review.query.filter_by(user_id=user_id, product_id=product_id).first()
    if existing_review:
        return False, None, "You have already reviewed this product."
    
    # Find completed or delivered orders containing this product
    completed_orders = Order.query.filter(
        Order.buyer_id == user_id,
        Order.status.in_(['completed', 'delivered'])
    ).all()
    
    for order in completed_orders:
        for item in order.items:
            if item.product_id == product_id:
                # Check if review is within 30 days of delivery (optional)
                if order.delivered_at:
                    days_since_delivery = (datetime.utcnow() - order.delivered_at).days
                    if days_since_delivery > 30:
                        return False, None, "Review period (30 days after delivery) has expired."
                
                return True, order.id, "You can review this product."
    
    return False, None, "You need to purchase this product to leave a review."

def get_user_purchased_products(user_id):
    """
    Get list of products that user has purchased and can review.
    Returns list of dicts with product info and review eligibility.
    """
    purchased_products = []
    completed_orders = Order.query.filter(
        Order.buyer_id == user_id,
        Order.status.in_(['completed', 'delivered'])
    ).order_by(Order.delivered_at.desc()).all()
    
    seen_products = set()
    for order in completed_orders:
        for item in order.items:
            if item.product_id not in seen_products:
                seen_products.add(item.product_id)
                can_review, order_id, message = can_user_review_product(user_id, item.product_id)
                purchased_products.append({
                    'product': item.product,
                    'order': order,
                    'can_review': can_review,
                    'review_message': message,
                    'order_id': order_id
                })
    
    return purchased_products

def get_available_stock(product_id):
    """Get available stock for display purposes.
    
    Implements real-time stock management:
    - Stock deducted immediately when buyer places order
    - Stock returns if buyer cancels BEFORE seller processes
    - Stock never returns for returns/completed orders
    """
    try:
        from sqlalchemy import func
        product = Product.query.get(product_id)
        if not product:
            return 0
        
        # Check if there's a pending restock request
        pending_restock = RestockRequest.query.filter_by(
            product_id=product_id, 
            status='pending'
        ).first()
        
        if pending_restock:
            # If there's a pending restock request, treat as out of stock until approved
            app.logger.info(f"Product {product_id} has pending restock request - treating as out of stock")
            return 0
        
        # NEW RULE: Stock is deducted immediately when buyer places order
        # Calculate current stock after all completed orders and immediate deductions
        completed_deductions = db.session.query(
            func.sum(OrderItem.quantity)
        ).join(Order).filter(
            OrderItem.product_id == product_id,
            Order.status.in_(['completed', 'delivered'])  # Completed orders permanently deduct stock
        ).scalar() or 0
        
        # NEW RULE: Stock deducted immediately for all orders (pending, processing, etc.)
        # This represents orders that have been placed but not yet cancelled
        active_orders = db.session.query(
            func.sum(OrderItem.quantity)
        ).join(Order).filter(
            OrderItem.product_id == product_id,
            Order.status.in_(['pending', 'to_pay', 'processing', 'ready_for_pickup', 'to_ship', 'in_transit', 'delivered']),
            Order.status != 'cancelled'  # Exclude cancelled orders
        ).scalar() or 0
        
        # NEW RULE: Returned items deduct stock again (never return to inventory)
        # Note: Return system uses different models, will handle separately
        returned_deductions = 0  # Placeholder for return logic
        
        # Add approved restock quantities
        approved_restock = db.session.query(
            func.sum(RestockRequest.approved_quantity)
        ).filter(
            RestockRequest.product_id == product_id,
            RestockRequest.status == 'approved'
        ).scalar() or 0
        
        # Calculate available stock:
        # physical_stock - completed_orders - active_orders - returned_items
        # Note: approved_restock is already included in product.stock from admin approval
        available_stock = product.stock - completed_deductions - active_orders - returned_deductions
        result = max(int(available_stock), 0)
        
        # Debug output
        app.logger.info(f"Product {product_id}: stock={product.stock}, completed={completed_deductions}, active={active_orders}, returned={returned_deductions}, restock={approved_restock}, available={result}")
        
        return result
    except Exception as e:
        app.logger.error(f"Error calculating available stock for product {product_id}: {e}")
        return 0

@app.route('/debug-products')
def debug_products():
    """Debug route to list all products and their stock status"""
    if not session.get('user_id') or session.get('active_role') != 'admin':
        return "Admin access required", 403
    
    products = Product.query.all()
    product_info = []
    
    for product in products:
        available_stock = get_available_stock(product.id)
        
        # Get detailed reservation information
        from sqlalchemy import func
        reserved_stock = db.session.query(
            func.sum(OrderItem.quantity)
        ).join(Order).filter(
            OrderItem.product_id == product.id,
            Order.status.in_(['pending', 'to_pay', 'processing'])
        ).scalar() or 0
        
        payment_reserved = db.session.query(
            func.sum(OrderItem.quantity)
        ).join(Order).filter(
            OrderItem.product_id == product.id,
            Order.payment_status.in_(['pending', 'awaiting_payment', 'failed']),
            Order.status != 'cancelled'
        ).scalar() or 0
        
        total_reserved = max(reserved_stock, payment_reserved)
        
        product_info.append({
            'id': product.id,
            'name': product.name,
            'stock': product.stock,
            'reserved_stock': reserved_stock,
            'payment_reserved': payment_reserved,
            'total_reserved': total_reserved,
            'available_stock': available_stock,
            'status': 'Out of Stock' if available_stock <= 0 else f'In Stock ({available_stock})'
        })
    
    # Sort by name for easier finding
    product_info.sort(key=lambda x: x['name'].lower())
    
    html = "<h2>Product Stock Status Debug</h2>"
    html += "<table border='1' style='border-collapse: collapse; width: 100%;'>"
    html += "<tr><th>ID</th><th>Name</th><th>Total Stock</th><th>Reserved</th><th>Payment Reserved</th><th>Total Reserved</th><th>Available</th><th>Status</th></tr>"
    for p in product_info:
        row_color = 'red' if p['available_stock'] <= 0 else 'green'
        html += f"<tr style='color: {row_color};'>"
        html += f"<td>{p['id']}</td>"
        html += f"<td>{p['name']}</td>"
        html += f"<td>{p['stock']}</td>"
        html += f"<td>{p['reserved_stock']}</td>"
        html += f"<td>{p['payment_reserved']}</td>"
        html += f"<td>{p['total_reserved']}</td>"
        html += f"<td>{p['available_stock']}</td>"
        html += f"<td>{p['status']}</td>"
        html += "</tr>"
    html += "</table>"
    
    # Add force restock buttons for out of stock items
    html += "<h3>Force Restock Out of Stock Items</h3>"
    for p in product_info:
        if p['available_stock'] <= 0:
            html += f"<div style='margin: 10px 0; padding: 10px; border: 1px solid #ccc;'>"
            html += f"<strong>{p['name']}</strong> (ID: {p['id']}) - "
            html += f"Stock: {p['stock']}, Reserved: {p['total_reserved']}, Available: {p['available_stock']}"
            html += f" <a href='/force-restock/{p['id']}' style='margin-left: 10px;' class='btn btn-primary btn-sm'>Force Restock +10</a>"
            html += f" <a href='/clear-reservations/{p['id']}' style='margin-left: 5px;' class='btn btn-warning btn-sm'>Clear All Reservations</a>"
            html += f"</div>"
    
    return html

@app.route('/force-restock/<int:product_id>')
def force_restock(product_id):
    """Force restock a product for testing"""
    if not session.get('user_id') or session.get('active_role') != 'admin':
        return "Admin access required", 403
    
    product = Product.query.get(product_id)
    if not product:
        return f"Product {product_id} not found", 404
    
    # Force add 10 to stock
    product.stock += 10
    db.session.commit()
    
    # Emit real-time update
    available_stock = get_available_stock(product_id)
    try:
        socketio.emit('product_stock_update', {
            'product_id': product_id,
            'stock': available_stock,
            'available_stock': available_stock
        }, broadcast=True)
    except Exception as e:
        pass
    
    return f"Product '{product.name}' (ID: {product_id}) force restocked by 10. New stock: {product.stock}, Available: {available_stock}. <a href='/debug-products'>Back to debug</a>"

@app.route('/clear-reservations/<int:product_id>')
def clear_reservations(product_id):
    """Clear all reservations for a product (for testing)"""
    if not session.get('user_id') or session.get('active_role') != 'admin':
        return "Admin access required", 403
    
    product = Product.query.get(product_id)
    if not product:
        return f"Product {product_id} not found", 404
    
    # Cancel all pending orders for this product
    orders_to_cancel = db.session.query(Order).join(OrderItem).filter(
        OrderItem.product_id == product_id,
        Order.status.in_(['pending', 'to_pay', 'processing'])
    ).all()
    
    cancelled_count = 0
    for order in orders_to_cancel:
        order.status = 'cancelled'
        order.updated_at = datetime.utcnow()
        cancelled_count += 1
    
    db.session.commit()
    
    # Emit real-time update
    available_stock = get_available_stock(product_id)
    try:
        socketio.emit('product_stock_update', {
            'product_id': product_id,
            'stock': available_stock,
            'available_stock': available_stock
        }, broadcast=True)
    except Exception as e:
        pass
    
    return f"Cleared {cancelled_count} orders for product '{product.name}' (ID: {product_id}). Available stock: {available_stock}. <a href='/debug-products'>Back to debug</a>"


@app.route('/set-out-of-stock/<int:product_id>')
def set_out_of_stock(product_id):
    """Temporarily set a product as out of stock for testing"""
    if not session.get('user_id') or session.get('active_role') != 'admin':
        return "Admin access required", 403
    
    product = Product.query.get(product_id)
    if not product:
        return f"Product {product_id} not found", 404
    
    # Temporarily set stock to 0 for testing
    original_stock = product.stock
    product.stock = 0
    db.session.commit()
    
    # Emit real-time update
    if 'socketio' in globals():
        socketio.emit('product_stock_update', {
            'product_id': product_id,
            'stock': 0,
            'available_stock': 0
        })
    
    return f"Product '{product.name}' (ID: {product_id}) set to out of stock. Original stock: {original_stock}. <a href='/debug-products'>View all products</a>"


def calculate_coupon_discount(code, subtotal):
    """Validate a coupon code and compute its discount for the given subtotal.

    Returns (coupon_obj_or_None, discount_amount: float, error_message: str or None).
    """
    if not code:
        return None, 0.0, None

    normalized = code.strip().upper()
    if not normalized:
        return None, 0.0, None

    # Case-insensitive lookup
    coupon = Coupon.query.filter(db.func.upper(Coupon.code) == normalized).first()
    if not coupon or not coupon.is_active:
        return None, 0.0, "Invalid or inactive coupon code."

    now = datetime.utcnow()
    if coupon.valid_from and now < coupon.valid_from:
        return None, 0.0, "This coupon is not yet valid."
    if coupon.valid_until and now > coupon.valid_until:
        return None, 0.0, "This coupon has already expired."

    min_amount = coupon.min_order_amount or 0.0
    if subtotal < min_amount:
        return None, 0.0, f"Minimum order amount for this coupon is ₱{min_amount:,.2f}."

    if coupon.max_uses is not None and coupon.used_count is not None:
        if coupon.used_count >= coupon.max_uses:
            return None, 0.0, "This coupon has reached its maximum number of uses."

    if coupon.discount_type == 'percent':
        discount_amount = subtotal * (coupon.discount_value / 100.0)
    elif coupon.discount_type == 'fixed':
        discount_amount = coupon.discount_value
    elif coupon.discount_type == 'free_shipping':
        # Shipping will be set to 0 at the route level; no direct subtotal discount needed here
        discount_amount = 0.0
    else:
        # Unknown type: treat as no discount
        return None, 0.0, "Invalid or unsupported coupon type."

    # Do not allow discount to exceed subtotal
    discount_amount = max(0.0, min(discount_amount, subtotal))
    return coupon, float(discount_amount), None


def is_admin():
    if 'user_id' not in session:
        return False
    user = User.query.get(session['user_id'])
    return user and user.role == 'admin'

def is_seller():
    if 'user_id' not in session:
        return False
    user = User.query.get(session['user_id'])
    if not user:
        return False
    # Admins may access seller pages for management purposes
    if user.role == 'admin':
        return True
    # Require Seller mode AND an approved seller application (prevents early access)
    active_role = session.get('active_role', user.role)
    if active_role != 'seller':
        return False
    approved = SellerApplication.query.filter_by(user_id=user.id, status='approved').first()
    return approved is not None

def login_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def admin_required(f):
    def decorated_function(*args, **kwargs):
        if not is_admin():
            flash('Admin access required.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def seller_required(f):
    def decorated_function(*args, **kwargs):
        if not is_seller():
            flash('Seller access required.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Rider role helpers

def is_rider():
    if 'user_id' not in session:
        return False
    user = User.query.get(session['user_id'])
    if not user:
        return False
    active_role = session.get('active_role', user.role)
    return (user.role == 'rider' or active_role == 'rider') and user.status == 'active'


def rider_required(f):
    def decorated_function(*args, **kwargs):
        if not is_rider():
            flash('Rider access required.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# PayMongo Configuration
PAYMONGO_PUBLIC_KEY = 'pk_test_your_public_key_here'
PAYMONGO_SECRET_KEY = 'sk_test_your_secret_key_here'

# send account status update email (approve/reject)
def send_account_status_email(to_email, approved=True, reason=None):
    """
    Sends an email to the user notifying them whether their account was approved or rejected.
    approved: bool
    reason: optional rejection reason string
    """
    try:
        if approved:
            subject = "Your Kids & Baby Store account has been approved"
            body = f"Hello,\n\nYour Kids & Baby Store account has been approved by our administrator. You may now log in using your registered email.\n\nThank you,\nKids & Baby Store Team"
        else:
            subject = "Your Kids & Baby Store account registration was not approved"
            msg_reason = f"\n\nReason: {reason}" if reason else ""
            body = f"Hello,\n\nWe reviewed your account registration and it has not been approved at this time.{msg_reason}\n\nIf you need assistance, please contact support.\n\nRegards,\nKids & Baby Store Team"

        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = app.config['MAIL_SENDER']
        msg['To'] = to_email
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(app.config['MAIL_SENDER'], app.config['MAIL_APP_PASSWORD'])
            smtp.send_message(msg)
    except Exception as e:
        # log and continue (don't raise)
        app.logger.exception("Failed to send account status email to %s: %s", to_email, e)


def send_coupon_email(user, coupon, discount_text=None):
    """Send a professional coupon email to a buyer.

    discount_text is an optional human-friendly summary, e.g. "10% off your next order".
    """
    try:
        subject = "You received a new coupon from Kids & Baby Store"
        discount_label = discount_text
        if not discount_label:
            if coupon.discount_type == 'percent':
                discount_label = f"{coupon.discount_value:.0f}% off your order"
            else:
                discount_label = f"₱{coupon.discount_value:,.2f} off your order"

        min_order_part = ""
        if coupon.min_order_amount:
            min_order_part = f" (min. order ₱{coupon.min_order_amount:,.2f})"

        validity_part = ""
        if coupon.valid_until:
            validity_part = f" until {coupon.valid_until.strftime('%Y-%m-%d')}"

        body = (
            f"Hi {user.first_name},\n\n"
            f"You have received a new coupon for our Kids & Baby Store.\n\n"
            f"Code: {coupon.code}\n"
            f"Offer: {discount_label}{min_order_part}{validity_part}.\n\n"
            "To use this coupon, enter the code on the checkout page before placing your order.\n\n"
            "Thank you for shopping with us!\n"
            "Kids & Baby Store Team"
        )

        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = app.config['MAIL_SENDER']
        msg['To'] = user.email
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(app.config['MAIL_SENDER'], app.config['MAIL_APP_PASSWORD'])
            smtp.send_message(msg)
    except Exception as e:
        app.logger.exception("Failed to send coupon email to %s: %s", getattr(user, 'email', 'unknown'), e)

# Replace the existing index() and admin_hero_slides() with these versions.

# ---- Return/Refund real-time helper ----

def _emit_return_update(rr, extra=None):
    try:
        payload = {
            'return_id': rr.id,
            'order_id': rr.order_id,
            'status': rr.status,
            'buyer_id': rr.buyer_id,
            'seller_id': rr.seller_id
        }
        if extra and isinstance(extra, dict):
            payload.update(extra)
        # Notify buyer and seller rooms
        socketio.emit('return_update', payload, room=f'user_{rr.buyer_id}')
        socketio.emit('return_update', payload, room=f'user_{rr.seller_id}')
        # Riders may show available/active counts
        socketio.emit('return_update', payload, room='riders')
    except Exception:
        pass

# Ensure Notification has rich fields (image_url, link, type, actor_user_id)

def ensure_notification_extra_columns():
    try:
        inspector = sa_inspect(db.engine)
        try:
            cols = {c['name'] for c in inspector.get_columns('notification')}
        except Exception:
            return
        stmts = []
        if 'image_url' not in cols:
            stmts.append("ALTER TABLE notification ADD COLUMN image_url VARCHAR(255)")
        if 'link' not in cols:
            stmts.append("ALTER TABLE notification ADD COLUMN link VARCHAR(255)")
        if 'type' not in cols:
            stmts.append("ALTER TABLE notification ADD COLUMN type VARCHAR(40)")
        if 'actor_user_id' not in cols:
            stmts.append("ALTER TABLE notification ADD COLUMN actor_user_id INTEGER")
        if 'order_id' not in cols:
            stmts.append("ALTER TABLE notification ADD COLUMN order_id INTEGER")
        if 'images' not in cols:
            # Prefer JSON; MariaDB accepts JSON alias to LONGTEXT
            stmts.append("ALTER TABLE notification ADD COLUMN images JSON")
        for s in stmts:
            db.session.execute(_sa_text(s))
        if stmts:
            db.session.commit()
    except Exception:
        db.session.rollback()
        pass

@app.route('/')
def index():
    # All users (buyers and sellers) see the homepage when logged in
    # Get unique categories to avoid duplicates
    all_categories = Category.query.filter_by(status='active').order_by(Category.name).all()
    # Remove duplicates by keeping only the first occurrence of each name
    seen_names = set()
    categories = []
    for cat in all_categories:
        if cat.name not in seen_names:
            seen_names.add(cat.name)
            categories.append(cat)
    recent_products = Product.query.order_by(Product.created_at.desc()).limit(8).all()
    # Get hero slides in upload order (oldest first) so first uploaded appears first
    hero_slides = HeroSlide.query.filter_by(is_active=True).order_by(HeroSlide.created_at.asc()).limit(6).all()

    # Brands - example: using SellerApplication.store_name and store_logo (approved only)
    brands = []
    brand_rows = SellerApplication.query.filter_by(status='approved').all()
    for b in brand_rows:
        # Only include brands that have active products
        active_products_count = Product.query.filter_by(seller_id=b.user_id, status='active').count()
        if active_products_count == 0:
            continue
            
        brand_dict = {
            'id': b.user_id,
            'user_id': b.user_id,
            'store_name': b.store_name,
            'name': b.store_name,
            'logo': b.store_logo
        }
        try:
            seller_products = Product.query.filter_by(seller_id=b.user_id, status='active')\
                                           .order_by(Product.created_at.desc())\
                                           .limit(6).all()
            brand_dict['products'] = [
                {
                    'id': p.id,
                    'name': p.name,
                    'price': p.price,
                    'image_filename': p.image_filename
                } for p in seller_products
            ]
        except Exception:
            brand_dict['products'] = []

        brands.append(brand_dict)

    approved_products = Product.query.filter_by(status='active').order_by(Product.created_at.desc()).limit(8).all()
    # New Arrivals (admin controlled)
    new_arrivals = Product.query.filter_by(status='active', show_in_new_arrival=True).order_by(Product.created_at.desc()).limit(8).all()

    return render_template('index.html',
        categories=categories,
        recent_products=recent_products,
        hero_slides=hero_slides,
        brands=brands,
        approved_products=approved_products,
        new_arrivals=new_arrivals
    )





@app.route('/admin/hero-slides', methods=['GET', 'POST'])
@admin_required
def admin_hero_slides():
    if request.method == 'POST':
        # Handle upload
        file = request.files.get('image')
        link = request.form.get('link', '')
        if not file or not file.filename:
            flash('Please select an image to upload.', 'danger')
            return redirect(url_for('admin_hero_slides'))

        filename = secure_filename(file.filename)
        # Use upload folder
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
        file.save(upload_path)

        slide = HeroSlide(
            image_filename=filename,
            link=link,
            is_active=True
        )
        db.session.add(slide)
        db.session.commit()
        flash('Slide added!', 'success')
        return redirect(url_for('admin_hero_slides'))

    # Return slides in upload order (oldest first). Pass variable hero_slides to template (template expects hero_slides).
    hero_slides = HeroSlide.query.filter_by(is_active=True).order_by(HeroSlide.created_at.asc()).all()
    badge_counts = get_admin_badge_counts()
    return render_template('admin/hero_slides.html', hero_slides=hero_slides, **badge_counts)
    
    
@app.route('/dashboard')
@login_required
def dashboard():
    user = User.query.get(session['user_id'])
    active_role = session.get('active_role', user.role)
    
    if user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif active_role == 'seller':
        return redirect(url_for('seller_dashboard'))
    elif user.role == 'rider' or active_role == 'rider':
        return redirect(url_for('rider_dashboard'))
    else:
        # Buyer dashboard - show recent orders and recommendations
        # Notify buyer if seller application was approved (one-time per session)
        approved_app = SellerApplication.query.filter_by(user_id=session['user_id'], status='approved').first()
        if approved_app and not session.get('seller_approved_notified'):
            flash('Your account has been approved to become a seller. You can switch to Seller mode from the header.', 'success')
            session['seller_approved_notified'] = True
        recent_orders = Order.query.filter_by(buyer_id=session['user_id']).order_by(Order.created_at.desc()).limit(5).all()
        wishlist_items = Wishlist.query.filter_by(user_id=session['user_id']).limit(6).all()
        return render_template('buyer_dashboard.html', 
                             recent_orders=recent_orders, 
                             wishlist_items=wishlist_items)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password']
        remember = 'remember' in request.form

        # ----------------------------------------------------
        # Direct admin login ("admin" or "admin@kidscommerce.com")
        # ----------------------------------------------------
        admin_identifiers = ('admin', 'admin@kidscommerce.com')
        if email.lower() in admin_identifiers:
            admin_email = 'admin@kidscommerce.com'
            allowed_admin_passwords = ('admin123', 'Admin123!')  # support both defaults

            admin = User.query.filter_by(email=admin_email, role='admin').first()

            # If admin doesn't exist yet, create it only when a known default password is used
            if admin is None:
                if password not in allowed_admin_passwords:
                    flash('Invalid email or password.', 'error')
                    return render_template('login.html')

                admin = User(
                    first_name='Admin',
                    last_name='User',
                    email=admin_email,
                    password=password,
                    phone='1234567890',
                    address='Admin Office',
                    role='admin',
                    status='active',
                    email_verified=True
                )
                db.session.add(admin)
                db.session.commit()
            else:
                # Make sure admin is active and email-verified
                if admin.status != 'active':
                    admin.status = 'active'
                admin.email_verified = True

                # If user typed one of the known default passwords, sync it
                if password in allowed_admin_passwords and admin.password != password:
                    admin.password = password

                db.session.commit()

                # Final password check for admin
                if admin.password != password:
                    flash('Invalid email or password.', 'error')
                    return render_template('login.html')

            # Log admin in and go straight to dashboard
            session['user_id'] = admin.id
            session['user_name'] = f"{admin.first_name} {admin.last_name}"
            session['user_role'] = admin.role
            session['active_role'] = admin.role

            admin_profile = AdminProfile.query.filter_by(user_id=admin.id).first()
            if admin_profile:
                admin_profile.last_login = datetime.utcnow()
                db.session.commit()

            log_admin_action('Login', f'Admin login from IP: {request.remote_addr}')
            return redirect(url_for('admin_dashboard'))

        # ----------------------------------------------------
        # Normal login (buyers / sellers and non-direct admins)
        # ----------------------------------------------------
        # Check user by email only
        user = User.query.filter_by(email=email).first()

        # If credentials are correct but the account is not yet active,
        # show a clear status message instead of a generic login error.
        if user and user.password == password and user.status != 'active':
            # Rider accounts that are still pending admin review
            if user.role == 'rider' and user.status == 'pending':
                return render_template('rider/account_under_review.html', user=user)

            # Other pending accounts (e.g., buyers/sellers)
            if user.status == 'pending':
                return render_template('registration_status.html', role=(user.role or 'buyer'))

            # Rejected or otherwise inactive accounts
            if user.status == 'rejected':
                flash('Your account registration was not approved. You may update your information and reapply.', 'error')
            else:
                flash('Your account is not active. Please contact support for assistance.', 'error')
            return render_template('login.html')

        # --- START: Email verification check ---
        if user and user.password == password and user.status == 'active':
            # Only check email verification for non-admin users
            if user.role != 'admin' and hasattr(user, 'email_verified') and not getattr(user, 'email_verified', False):
                flash('Please verify your email before logging in.', 'warning')
                return redirect(url_for('verify_email', email=email))
        # --- END: Email verification check ---

        if user and user.password == password and user.status == 'active':
            session['user_id'] = user.id
            session['user_name'] = f"{user.first_name} {user.last_name}"
            session['user_role'] = user.role
            session['active_role'] = user.role  # Set initial active role

            # Update admin profile last login if admin user
            if user.role == 'admin':
                admin_profile = AdminProfile.query.filter_by(user_id=user.id).first()
                if admin_profile:
                    admin_profile.last_login = datetime.utcnow()
                    db.session.commit()
                log_admin_action('Login', f'Admin login from IP: {request.remote_addr}')

            # Redirect based on role
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user.role == 'seller':
                return redirect(url_for('seller_dashboard'))
            elif user.role == 'rider':
                return redirect(url_for('rider_dashboard'))
            else:
                return redirect(url_for('index'))
        else:
            flash('Invalid email or password.', 'error')

    return render_template('login.html')


# Helper: send 6-digit verification email (shared by registration/forgot-password)

def send_verification_email(email, code):
    try:
        subject = 'Your Kids & Baby Store verification code'
        body = f'Your verification code is {code}. It will expire in 5 minutes.'
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = app.config['MAIL_SENDER']
        msg['To'] = email
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(app.config['MAIL_SENDER'], app.config['MAIL_APP_PASSWORD'])
            smtp.send_message(msg)
        return True
    except Exception as e:
        app.logger.exception('send_verification_email failed for %s: %s', email, e)
        return False

# Basic disposable/inaccessible email checks
DISPOSABLE_DOMAINS = set([
    'mailinator.com','yopmail.com','guerrillamail.com','10minutemail.com','getnada.com','tempmail.com','tempmailo.com','sharklasers.com','trashmail.com','burnermail.io','throwawaymail.com'
])

def is_disposable_or_invalid_email(address:str)->bool:
    """Cheap local filter for obvious trash / unreachable domains.

    This does NOT talk to external APIs; it only checks known disposable domains
    and basic DNS. Used as a first line of defense before hitting EmailListVerify.
    """
    try:
        if not address or '@' not in address:
            return True
        local, domain = address.rsplit('@', 1)
        domain = domain.lower().strip()
        if domain in DISPOSABLE_DOMAINS:
            return True
        # Enhanced validation for Gmail addresses
        if domain == 'gmail.com':
            # Check for obviously fake Gmail usernames
            # Real Gmail usernames don't have consecutive dots, start/end with dots
            # and have reasonable length (6-30 characters)
            if len(local) < 6 or len(local) > 30:
                return True
            if '..' in local or local.startswith('.') or local.endswith('.'):
                return True
            # Check for obviously random patterns (too many consecutive consonants)
            consonant_pattern = re.compile(r'[bcdfghjklmnpqrstvwxyz]{4,}')
            if consonant_pattern.search(local.lower()):
                return True
        # Optional MX lookup if dnspython exists
        try:
            import dns.resolver  # type: ignore
            try:
                answers = dns.resolver.resolve(domain, 'MX')
                if not answers:
                    return True
            except Exception:
                return True
        except Exception:
            # Fallback: basic A record check
            try:
                import socket
                socket.gethostbyname(domain)
            except Exception:
                return True
    except Exception:
        return True
    return False


# External email verification via EmailListVerify
EMAILLISTVERIFY_API_URL = "https://apps.emaillistverify.com/api/verifyEmail"


def verify_gmail_smtp(address: str) -> tuple[bool, str]:
    """Simple SMTP verification for Gmail addresses without external API.
    
    Returns (is_valid, message)
    """
    try:
        if not address.endswith('@gmail.com'):
            return (False, 'Only Gmail addresses are supported')
        
        # Basic SMTP check - try to connect to Gmail's SMTP server
        import smtplib
        import socket
        
        # Connect to Gmail SMTP server
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
        server.ehlo()
        server.starttls()
        server.ehlo()
        
        # Try to verify the address exists (this is a basic check)
        # Note: Gmail often doesn't reveal if addresses exist for privacy reasons
        # but we can at least verify the server is reachable
        server.mail('test@gmail.com')
        code, message = server.rcpt(address)
        server.quit()
        
        # If we get a 250 response, the address might exist
        # If we get 550, it definitely doesn't exist
        if code == 250:
            return (True, 'Gmail address appears to be valid')
        elif code == 550:
            return (False, 'This Gmail address does not exist')
        else:
            # For other codes, be conservative and allow it
            return (True, 'Gmail address format verified')
            
    except smtplib.SMTPServerDisconnected:
        return (True, 'Gmail address format verified (SMTP unavailable)')
    except smtplib.SMTPConnectError:
        return (True, 'Gmail address format verified (SMTP connection failed)')
    except socket.timeout:
        return (True, 'Gmail address format verified (SMTP timeout)')
    except Exception as e:
        return (True, f'Gmail address format verified (SMTP error: {str(e)[:50]})')


def verify_email_with_emaillistverify(address: str, return_status: bool = False):
    """Validate an email using the EmailListVerify HTTP API.

    Returns True if the email is considered deliverable/valid, False if it is
    definitely bad (invalid mailbox, syntax, etc).

    If return_status=True, returns a tuple (is_valid: bool, provider_status: str|None)
    where provider_status is the raw status string from ELV, e.g., 'ok', 'failed', 'unknown'.

    If no API key is configured or the API call fails, this returns True so we
    don't block all registrations just because the third‑party service is down.
    Configure the API key via .env as EMAILLISTVERIFY_API_KEY.
    """
    address = (address or "").strip()
    if not address or '@' not in address:
        return (False, None) if return_status else False

    api_key = os.getenv('EMAILLISTVERIFY_API_KEY') or os.getenv('EMAILLISTVERIFY_SECRET')
    if not api_key:
        # No API key configured; fail open for development, log warning
        app.logger.warning('EmailListVerify API key not configured - skipping external validation')
        return (True, 'skipped_no_key') if return_status else True

    try:
        resp = requests.get(
            EMAILLISTVERIFY_API_URL,
            params={"secret": api_key, "email": address},
            timeout=8,
        )
        if resp.status_code != 200:
            app.logger.warning(
                "EmailListVerify non-200 (%s) for %s: %s",
                resp.status_code,
                address,
                (resp.text or "")[:200],
            )
            return (False, 'unavailable_http') if return_status else False
        status = (resp.text or "").strip().lower()
        domain = address.split('@', 1)[-1].lower()
        # According to EmailListVerify docs, 'ok' means deliverable.
        if status == 'ok':
            return (True, status) if return_status else True
        # Be strict for gmail.com: any non-'ok' means invalid/non-existent
        if domain == 'gmail.com':
            return (False, status) if return_status else False
        # Treat clear failure statuses as invalid for non-gmail as well
        if status in ('fail', 'failed', 'invalid', 'error', 'bad', 'unknown_email', 'unknown_user', 'no_mailbox', 'does_not_exist'):
            return (False, status) if return_status else False
        # For other responses (e.g. 'unknown', temporary), fail open for non-gmail
        return (True, status) if return_status else True
    except Exception as e:
        app.logger.exception('EmailListVerify error for %s: %s', address, e)
        return (False, 'unavailable_error') if return_status else False

@app.route('/register-hub')
def register_hub():
    """Deprecated registration hub. Redirect users directly to buyer registration."""
    return redirect(url_for('register_buyer'))


@app.route('/register-multistep')
def register_multistep():
    """
    Modern multi-step registration form with role selection, progress tracking, and dynamic fields.
    Single-page form with smooth transitions between steps.
    """
    return render_template('register_multiStep.html')


@app.route('/register-buyer')
def register_buyer():
    """
    Buyer-specific registration route that renders the buyer registration form.
    This is the primary registration page for customers.
    """
    return render_template('register.html')


# Step 1: start registration, validate input, create OTP, do not save to DB yet
@app.route('/api/check-email', methods=['POST'])
def api_check_email():
    """AJAX endpoint to validate an email before registration step 2.

    Checks:
    - Gmail-only policy
    - Duplicate (already registered) accounts
    - Local disposable/invalid domains
    - External EmailListVerify result
    """
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip()
    if not email:
        return jsonify(ok=False, message='Email is required.')

    # Gmail-only policy
    if not email.endswith('@gmail.com'):
        return jsonify(ok=False, message='Please register using a Gmail address.')

    # Duplicate (non-rejected) account
    existing_user = User.query.filter_by(email=email).first()
    if existing_user and existing_user.status != 'rejected':
        return jsonify(ok=False, message='This email address is already registered. Please use a different email or try logging in.')

    # Local disposable / invalid
    if is_disposable_or_invalid_email(email):
        return jsonify(ok=False, message='Disposable or invalid email addresses are not allowed.')

    # External verification (EmailListVerify or fallback SMTP)
    api_key = os.getenv('EMAILLISTVERIFY_API_KEY') or os.getenv('EMAILLISTVERIFY_SECRET')
    if not api_key:
        # Use enhanced local validation + SMTP check for Gmail
        if is_disposable_or_invalid_email(email):
            return jsonify(ok=False, message='Disposable or invalid email addresses are not allowed.')
        
        # Additional SMTP verification for Gmail
        if email.endswith('@gmail.com'):
            smtp_valid, smtp_message = verify_gmail_smtp(email)
            if not smtp_valid:
                return jsonify(ok=False, message=smtp_message)
            return jsonify(ok=True, message=smtp_message, provider_status='smtp_verified')
        else:
            return jsonify(ok=True, message='Email format validated', provider_status='local_only')
    
    # Use EmailListVerify API if key is available
    valid, raw_status = verify_email_with_emaillistverify(email, return_status=True)
    if not valid:
        # Friendlier messages
        status_msg_map = {
            'invalid': 'That email address is invalid.',
            'fail': 'We can’t find that Gmail account. Use an existing Gmail address.',
            'failed': 'We can’t find that Gmail account. Use an existing Gmail address.',
            'unknown_email': 'We can’t find that Gmail account. Use an existing Gmail address.',
            'unknown_user': 'We can’t find that Gmail account. Use an existing Gmail address.',
            'no_mailbox': 'We can’t find that Gmail account. Use an existing Gmail address.',
            'does_not_exist': 'We can’t find that Gmail account. Use an existing Gmail address.',
            'error': 'We could not verify this email right now. Please try again.',
        }
        # Unavailable cases -> block with a clear message
        if (raw_status or '').lower().startswith('unavailable'):
            return jsonify(ok=False, message='Email verification is temporarily unavailable. Please try again later.', provider_status=(raw_status or 'unavailable'))
        msg = status_msg_map.get((raw_status or '').lower(), 'We couldn’t verify this email. Please use an existing Gmail address.')
        return jsonify(ok=False, message=msg, provider_status=(raw_status or 'failed'))

    # ok=True — pass through provider_status as-is so UI can decide whether to show green badge
    # For development without API key, show a friendly message
    if raw_status == 'skipped_no_key':
        return jsonify(ok=True, message='Email format validated (external verification skipped in development)', provider_status='skipped')
    return jsonify(ok=True, message='OK', provider_status=(raw_status or 'ok'))


# --- Fallback OTP pre-verification when external ELV is unavailable ---
@app.route('/api/send-email-otp', methods=['POST'])
def api_send_email_otp():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip()
    if not email or not email.endswith('@gmail.com'):
        return jsonify(ok=False, message='Enter a valid Gmail address first.')
    # Generate 6-digit code, 5-minute expiry
    code = str(random.randint(100000, 999999))
    session['email_preverify'] = {
        'email': email,
        'code': code,
        'exp': (datetime.utcnow() + timedelta(minutes=5)).isoformat()
    }
    # Send the code
    if not send_verification_email(email, code):
        return jsonify(ok=False, message='Failed to send verification code. Try again later.')
    return jsonify(ok=True, message='Verification code sent.')


@app.route('/api/verify-email-otp', methods=['POST'])
def api_verify_email_otp():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip()
    code = (data.get('code') or '').strip()
    stash = session.get('email_preverify') or {}
    if not email or not code:
        return jsonify(ok=False, message='Email and code are required.')
    if not stash or stash.get('email') != email:
        return jsonify(ok=False, message='Please send a new code first.')
    # Check expiry
    try:
        exp = datetime.fromisoformat(stash.get('exp'))
        if datetime.utcnow() > exp:
            return jsonify(ok=False, message='Code expired. Please request a new one.')
    except Exception:
        pass
    if stash.get('code') != code:
        return jsonify(ok=False, message='Invalid code. Please try again.')
    # Mark pre-verified
    session['email_preverified'] = email
    return jsonify(ok=True, message='Email verified by code.')


@app.route('/register/start', methods=['POST'])
def register_start():
    role = (request.form.get('role') or 'buyer').strip().lower()
    if role not in ('buyer','rider'):
        role = 'buyer'

    # Extract fields per role
    if role == 'rider':
        email = (request.form.get('rider_email') or '').strip()
        password = request.form.get('rider_password') or ''
        first_name = (request.form.get('rider_first_name') or '').strip()
        last_name = (request.form.get('rider_last_name') or '').strip()
        raw_phone = (request.form.get('rider_phone') or '').strip()
        street = request.form.get('rider_street_address') or ''
        barangay = request.form.get('rider_barangay') or ''
        city = request.form.get('rider_city') or ''
        province = request.form.get('rider_province') or ''
        region = request.form.get('rider_region') or ''
        address_full = request.form.get('rider_address') or ''
        vehicle_type = (request.form.get('rider_vehicle_type') or '').strip()
        vehicle_number = (request.form.get('rider_vehicle_number') or '').strip()
        file = request.files.get('rider_valid_id')
        terms_accepted = request.form.get('rider_terms')
    else:
        email = (request.form.get('email') or '').strip()
        password = request.form.get('password') or ''
        first_name = (request.form.get('first_name') or '').strip()
        last_name = (request.form.get('last_name') or '').strip()
        raw_phone = (request.form.get('phone') or '').strip()
        street = request.form.get('street_address') or ''
        barangay = request.form.get('barangay') or ''
        city = request.form.get('city') or ''
        province = request.form.get('province') or ''
        region = request.form.get('region') or ''
        address_full = request.form.get('address') or ''
        vehicle_type = ''
        vehicle_number = ''
        file = request.files.get('valid_id')
        terms_accepted = request.form.get('terms')

    # Preserve all current validations
    if not email:
        flash('Email is required.', 'danger'); return render_template('register.html')
    if not password:
        flash('Password is required.', 'danger'); return render_template('register.html')
    if not first_name:
        flash('First name is required.', 'danger'); return render_template('register.html')
    if not last_name:
        flash('Last name is required.', 'danger'); return render_template('register.html')

    phone_digits = ''.join(ch for ch in raw_phone if ch.isdigit())
    if len(phone_digits) != 11:
        flash('Phone number must be exactly 11 digits.', 'danger'); return render_template('register.html')

    # Maintain your Gmail-only policy
    if not email.endswith('@gmail.com'):
        flash('Please register using a Gmail address.', 'danger'); return render_template('register.html')

    if not terms_accepted:
        flash('You must accept the terms and conditions to register.', 'danger'); return render_template('register.html')

    # Check duplicate email that is not rejected
    existing_user = User.query.filter_by(email=email).first()
    if existing_user and existing_user.status != 'rejected':
        flash('This email address is already registered. Please use a different email or try logging in.', 'danger')
        return render_template('register.html')

    # Local disposable / invalid email checks
    if is_disposable_or_invalid_email(email):
        flash('Disposable or invalid email addresses are not allowed.', 'danger')
        return render_template('register.html')

    # External real-time validation via EmailListVerify
    # Only runs when EMAILLISTVERIFY_API_KEY is configured in your .env.
    api_key = os.getenv('EMAILLISTVERIFY_API_KEY') or os.getenv('EMAILLISTVERIFY_SECRET')
    if api_key and not verify_email_with_emaillistverify(email):
        flash('Please enter a valid email address. We could not verify this email.', 'danger')
        return render_template('register.html')

    # Require ID for rider; leave buyer as-is if your current flow requires valid_id too
    if role == 'rider' and (not file or not file.filename):
        flash('Please upload a clear copy of your government-issued ID (JPG, PNG, PDF).', 'danger')
        return render_template('register.html')

    # Save the uploaded ID temporarily (not tied to a DB row yet)
    tmp_id_path = None
    if file and file.filename:
        filename = secure_filename(file.filename)
        ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S_')
        filename = ts + filename
        tmp_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'tmp')
        os.makedirs(tmp_dir, exist_ok=True)
        file_path = os.path.join(tmp_dir, filename)
        file.save(file_path)
        tmp_id_path = '/static/uploads/tmp/' + filename

    # Create OTP (5-minute expiry)
    code = str(random.randint(100000, 999999))
    session['reg_data'] = {
        'role': role,
        'email': email,
        'password': password,
        'first_name': first_name,
        'last_name': last_name,
        'phone': phone_digits,
        'street': street,
        'barangay': barangay,
        'city': city,
        'province': province,
        'region': region,
        'address_full': address_full,
        'vehicle_type': vehicle_type,
        'vehicle_number': vehicle_number,
        'tmp_valid_id': tmp_id_path,
    }
    session['reg_code'] = code
    session['reg_code_expires'] = (datetime.utcnow() + timedelta(minutes=5)).isoformat()

    # Send verification email
    if not send_verification_email(email, code):
        flash('Failed to send verification code. Please try again later.', 'danger')
        return render_template('register.html')

    # Go to verify page
    return redirect(url_for('verify_email', email=email))

# Backward compatible endpoint name (HTML action changed to /register/start). Finalization happens after OTP.
@app.route('/register', methods=['GET'])
def register():
    return render_template('register.html')
    if request.method == 'POST':
        # Get role first to determine which field names to use
        role = request.form.get('role', 'buyer').strip().lower() or 'buyer'
        if role not in ('buyer', 'rider'):
            role = 'buyer'
        
        # Get field values based on role
        if role == 'rider':
            email = request.form.get('rider_email', '').strip()
            password = request.form.get('rider_password', '')
            first_name = request.form.get('rider_first_name', '').strip()
            last_name = request.form.get('rider_last_name', '').strip()
            raw_phone = request.form.get('rider_phone', '').strip()
            address_full = request.form.get('rider_address', '')
            street = request.form.get('rider_street_address', '')
            barangay = request.form.get('rider_barangay', '')
            city = request.form.get('rider_city', '')
            province = request.form.get('rider_province', '')
            region = request.form.get('rider_region', '')
            vehicle_type = request.form.get('rider_vehicle_type', '').strip()
            vehicle_number = request.form.get('rider_vehicle_number', '').strip()
            valid_id_file = request.files.get('rider_valid_id')
            terms_accepted = request.form.get('rider_terms')
        else:
            # Buyer fields (original)
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')
            first_name = request.form.get('first_name', '').strip()
            last_name = request.form.get('last_name', '').strip()
            raw_phone = request.form.get('phone', '').strip()
            address_full = request.form.get('address', '')
            street = request.form.get('street_address', '') or request.form.get('street', '')
            barangay = request.form.get('barangay', '')
            city = request.form.get('city', '')
            province = request.form.get('province', '')
            region = request.form.get('region', '')
            vehicle_type = request.form.get('vehicle_type', '').strip()
            vehicle_number = request.form.get('vehicle_number', '').strip()
            valid_id_file = None
            terms_accepted = request.form.get('terms')
        
        # Validate required fields
        if not email:
            flash('Email is required.', 'danger')
            return render_template('register.html')
        if not password:
            flash('Password is required.', 'danger')
            return render_template('register.html')
        if not first_name:
            flash('First name is required.', 'danger')
            return render_template('register.html')
        if not last_name:
            flash('Last name is required.', 'danger')
            return render_template('register.html')
        
        # Phone validation
        phone_digits = ''.join(ch for ch in raw_phone if ch.isdigit())
        if len(phone_digits) != 11:
            flash('Phone number must be exactly 11 digits.', 'danger')
            return render_template('register.html')
        phone = phone_digits

        # Enforce Gmail policy if you want (your original code required gmail)
        if not email.endswith('@gmail.com'):
            flash('Please register using a Gmail address.', 'danger')
            # Always show the unified registration page
            return render_template('register.html')
        
        # Validate terms acceptance
        if not terms_accepted:
            flash('You must accept the terms and conditions to register.', 'danger')
            return render_template('register.html')

        # --- START: duplicate email handling (allow reuse if previous account was rejected) ---
        existing_user = User.query.filter_by(email=email).first()
        if existing_user and existing_user.status != 'rejected':
            # Single clear error message
            flash('This email address is already registered. Please use a different email or try logging in.', 'danger')
            return render_template('register.html')
        # If status == 'rejected', we will *reuse* that user row instead of inserting a new one
        rejected_user = existing_user if existing_user and existing_user.status == 'rejected' else None
        # --- END: duplicate email handling ---

        # Handle uploaded ID document
        valid_id_filename = None
        file = valid_id_file  # Use the role-specific file variable we already set

        # For rider applications, validate required fields
        if role == 'rider':
            if not vehicle_type:
                flash('Vehicle type is required to register as a rider.', 'danger')
                return render_template('register.html')
            if not vehicle_number:
                flash('Vehicle plate number is required to register as a rider.', 'danger')
                return render_template('register.html')
            if (not file or not file.filename):
                flash('Please upload a clear copy of your government-issued ID (JPG, PNG, PDF).', 'danger')
                return render_template('register.html')

        if file and file.filename:
            filename = secure_filename(file.filename)
            _, ext = os.path.splitext(filename)
            ext = (ext or '').lower()
            allowed_ext = {'.png', '.jpg', '.jpeg', '.pdf'}
            if ext not in allowed_ext:
                flash('Invalid ID file type. Allowed formats: JPG, PNG, PDF.', 'danger')
                return render_template('register.html')

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            filename = timestamp + filename
            upload_path = os.path.join(app.config['UPLOAD_FOLDER'], 'documents')
            os.makedirs(upload_path, exist_ok=True)
            file.save(os.path.join(upload_path, filename))
            # store relative path (or absolute as you prefer)
            valid_id_filename = f"/static/uploads/documents/{filename}"

        # Create or update user with pending status (cannot login until admin approves)
        code = str(random.randint(100000, 999999))

        if rejected_user:
            # Reuse the existing rejected account: update its details and reset to pending
            new_user = rejected_user
            new_user.first_name = first_name
            new_user.last_name = last_name
            new_user.password = password  # In production, hash this!
            new_user.phone = phone
            new_user.address = address_full or (', '.join(filter(None, [street, barangay, city, province, region])))
            new_user.role = role
            new_user.status = 'pending'
            new_user.email_verified = False
            new_user.verification_code = code
        else:
            new_user = User(
                first_name=first_name,
                last_name=last_name,
                email=email,
                password=password,   # In production, hash this!
                phone=phone,
                address=address_full or (', '.join(filter(None, [street, barangay, city, province, region]))),
                email_verified=False,
                verification_code=code,
                status='pending',   # IMPORTANT: pending until admin approves
                role=role
            )

        # attach valid_id if uploaded (assumes User model now includes valid_id column)
        if valid_id_filename:
            new_user.valid_id = valid_id_filename

        # Only add to session if this is a brand new user, not a reused rejected one
        if not rejected_user:
            db.session.add(new_user)

        db.session.flush()

        # If rider signup, also create a RiderApplication record so admins can review
        if role == 'rider':
            try:
                rider_app = RiderApplication(
                    user_id=new_user.id,
                    vehicle_type=vehicle_type,
                    vehicle_number=vehicle_number,
                    status='pending'
                )
                db.session.add(rider_app)
            except Exception:
                app.logger.exception("Failed to create RiderApplication for new rider signup")

        try:
            if any([street, barangay, city, province, region, address_full]):
                addr = Address(
                    user_id=new_user.id,
                    label='Home',
                    full_address=address_full or (', '.join(filter(None, [street, barangay, city, province, region]))),
                    is_default=True,
                    region=region or None,
                    province=province or None,
                    city=str(city) or None,
                    barangay=barangay or None,
                    street=street or None,
                    latitude=request.form.get('latitude') or None,
                    longitude=request.form.get('longitude') or None
                )
                db.session.add(addr)
        except Exception:
            app.logger.exception("Failed to create address record for new user")

        db.session.commit()

        # Notify admins in-app
        try:
            account_type = 'Rider' if role == 'rider' else 'Buyer'
            notify_admins(f'New {account_type} account registration pending approval: {first_name} {last_name} ({email})')
        except Exception:
            app.logger.exception("Failed to notify admins of new registration")

        # Optionally send email to user that registration is pending
        try:
            msg = MIMEText("Thank you for registering. Your application is now under review. We will notify you via email once an administrator has reviewed your account.")
            msg['Subject'] = 'Registration Submitted - Pending Approval'
            msg['From'] = app.config['MAIL_SENDER']
            msg['To'] = email
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
                smtp.login(app.config['MAIL_SENDER'], app.config['MAIL_APP_PASSWORD'])
                smtp.send_message(msg)
        except Exception:
            app.logger.exception("Failed to send pending email to user")

        # After successful registration:
        # - Buyers go to the generic registration_status page
        # - Riders go straight to the dedicated rider account-under-review page
        if role == 'rider':
            return render_template('rider/account_under_review.html', user=new_user)
        return redirect(url_for('registration_status', role=role))

    return render_template('register.html')


@app.route('/verify-email', methods=['GET', 'POST'])
def verify_email():
    email = request.args.get('email') or request.form.get('email')
    # Registration-OTP path (session-based)
    if 'reg_data' in session and email == session.get('reg_data', {}).get('email'):
        if request.method == 'POST':
            code = (request.form.get('code') or '').strip()
            stored = session.get('reg_code')
            exp_iso = session.get('reg_code_expires')
            expired = False
            try:
                if exp_iso:
                    expired = datetime.utcnow() > datetime.fromisoformat(exp_iso)
            except Exception:
                expired = True
            if expired or not stored or code != stored:
                flash('Disposable email addresses are not allowed.' if is_disposable_or_invalid_email(email) else 'Invalid or expired verification code.', 'danger')
                # Do not finalize
                return render_template('verify_email.html', email=email)

            # Code matches -> finalize original registration (save to DB now)
            data = session.pop('reg_data')
            session.pop('reg_code', None)
            session.pop('reg_code_expires', None)

            role = data.get('role','buyer')
            email = data['email']
            first_name = data['first_name']; last_name = data['last_name']
            phone = data['phone']; password = data['password']
            street = data.get('street',''); barangay = data.get('barangay',''); city = data.get('city','')
            province = data.get('province',''); region = data.get('region',''); address_full = data.get('address_full','')
            vehicle_type = data.get('vehicle_type'); vehicle_number = data.get('vehicle_number')
            tmp_valid_id = data.get('tmp_valid_id')

            # Re-check duplicate (race condition)
            existing_user = User.query.filter_by(email=email).first()
            rejected_user = existing_user if existing_user and existing_user.status == 'rejected' else None

            # move tmp file to documents
            valid_id_filename = None
            if tmp_valid_id:
                try:
                    # tmp_valid_id like /static/uploads/tmp/filename
                    fn = os.path.basename(tmp_valid_id)
                    src = os.path.join(app.config['UPLOAD_FOLDER'], 'tmp', fn)
                    dst_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'documents')
                    os.makedirs(dst_dir, exist_ok=True)
                    dst = os.path.join(dst_dir, fn)
                    if os.path.exists(src):
                        os.replace(src, dst)
                        valid_id_filename = f"/static/uploads/documents/{fn}"
                except Exception:
                    app.logger.exception('Failed to move temporary ID file for %s', email)

            code2 = str(random.randint(100000, 999999))

            if rejected_user:
                new_user = rejected_user
                new_user.first_name = first_name
                new_user.last_name = last_name
                new_user.password = password
                new_user.phone = phone
                new_user.address = address_full or (', '.join(filter(None, [street, barangay, city, province, region])))
                new_user.role = role
                new_user.status = 'pending'
                new_user.email_verified = False
                new_user.verification_code = code2
            else:
                new_user = User(
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    password=password,
                    phone=phone,
                    address=address_full or (', '.join(filter(None, [street, barangay, city, province, region]))),
                    email_verified=False,
                    verification_code=code2,
                    status='pending',
                    role=role
                )
                db.session.add(new_user)
            if valid_id_filename:
                new_user.valid_id = valid_id_filename

            db.session.flush()

            # Optional: create rider application and address now
            if role == 'rider':
                try:
                    rider_app = RiderApplication(
                        user_id=new_user.id,
                        vehicle_type=vehicle_type,
                        vehicle_number=vehicle_number,
                        status='pending'
                    )
                    db.session.add(rider_app)
                except Exception:
                    app.logger.exception('Failed to create RiderApplication (finalize)')

            try:
                if any([street, barangay, city, province, region, address_full]):
                    addr = Address(
                        user_id=new_user.id,
                        label='Home',
                        full_address=address_full or (', '.join(filter(None, [street, barangay, city, province, region]))),
                        is_default=True,
                        region=region or None,
                        province=province or None,
                        city=str(city) or None,
                        barangay=barangay or None,
                        street=street or None,
                        latitude=request.form.get('latitude') or None,
                        longitude=request.form.get('longitude') or None
                    )
                    db.session.add(addr)
            except Exception:
                app.logger.exception('Failed to create address for finalized registration')

            db.session.commit()

            # Notify admins
            try:
                account_type = 'Rider' if role == 'rider' else 'Buyer'
                notify_admins(f'New {account_type} account registration pending approval: {first_name} {last_name} ({email})')
            except Exception:
                pass

            if role == 'rider':
                return render_template('rider/account_under_review.html', user=new_user)
            return redirect(url_for('registration_status', role=role))

        # GET: render verify page with email displayed
        return render_template('verify_email.html', email=email)

    # Legacy path: verifying an already-saved user (forgot password / older flow)
    if request.method == 'POST':
        code = request.form.get('code')
        user = User.query.filter_by(email=email).first()
        if user and user.verification_code == code:
            user.email_verified = True
            user.verification_code = None
            db.session.commit()
            flash('Email verified! You can now log in.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Invalid verification code.', 'danger')
    return render_template('verify_email.html', email=email)


@app.route('/seller-register', methods=['GET', 'POST'])
def seller_register():
    # Get current user if logged in
    current_user = None
    if 'user_id' in session:
        current_user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        # Handle file upload
        school_id_file = None
        if 'school_id' in request.files:
            file = request.files['school_id']
            if file and file.filename:
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
                filename = timestamp + filename
                upload_path = os.path.join(app.config['UPLOAD_FOLDER'], 'documents')
                if not os.path.exists(upload_path):
                    os.makedirs(upload_path)
                file.save(os.path.join(upload_path, filename))
                school_id_file = filename

        # Validate phone and GCash numbers as exactly 11 digits (numbers only)
        raw_phone = request.form.get('phone', '').strip()
        phone_digits = ''.join(ch for ch in raw_phone if ch.isdigit())
        if len(phone_digits) != 11:
            flash('Phone number must be exactly 11 digits.', 'error')
            return render_template('seller_register.html', user=current_user)

        raw_gcash = request.form.get('gcash_number', '').strip()
        gcash_digits = ''.join(ch for ch in raw_gcash if ch.isdigit())
        if len(gcash_digits) != 11:
            flash('GCash number must be exactly 11 digits.', 'error')
            return render_template('seller_register.html', user=current_user)

        if current_user:
            # Existing user applying to be seller
            user = current_user
            # Update user info if provided
            user.first_name = request.form['first_name']
            user.last_name = request.form['last_name']
            user.phone = phone_digits
            user.address = request.form['address']
        else:
            # New user registration (fallback for non-logged users)
            first_name = request.form['first_name']
            last_name = request.form['last_name']
            email = request.form['email']
            phone = phone_digits
            address = request.form['address']

            if User.query.filter_by(email=email).first():
                flash('Email already registered.', 'error')
                return render_template('seller_register.html', user=current_user)

            user = User(
                first_name=first_name,
                last_name=last_name,
                email=email,
                password="seller_app_" + datetime.now().strftime('%Y%m%d%H%M%S'),
                phone=phone,
                address=address,
                # Register as a seller account (awaiting approval)
                role='seller',
                status='pending'
            )
            db.session.add(user)
            db.session.flush()

        # Create seller application (business address is the same as the seller's personal address)
        seller_app = SellerApplication(
            user_id=user.id,
            store_name=request.form['store_name'],
            store_description=request.form.get('store_description', ''),
            store_category=request.form['store_category'],
            business_address=user.address,
            school_id_document=school_id_file,
            gcash_number=gcash_digits
        )

        db.session.add(seller_app)
        db.session.commit()

        flash('Seller application submitted successfully! You will be notified within 1-3 business days.', 'success')
        # Notify all admins of new seller application
        try:
            notify_admins(
                f'New seller application from {user.first_name} {user.last_name} ({user.email}) - Store: {seller_app.store_name}',
                type='seller_application',
                link=url_for('admin_seller_applications')
            )
        except Exception:
            pass

        if current_user:
            return redirect(url_for('profile'))
        else:
            return redirect(url_for('login'))
    
    return render_template('seller_register.html', user=current_user)

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        if user:
            # Generate reset code
            reset_code = str(random.randint(100000, 999999))
            user.verification_code = reset_code
            db.session.commit()
            try:
                send_verification_email(email, reset_code)
            except Exception as e:
                # EMAIL ERROR: Log error without printing
                flash('Failed to send reset code. Please try again.', 'danger')
                return render_template('forgot_password.html')
            flash('A reset code has been sent to your email.', 'info')
            return redirect(url_for('reset_password', email=email))
        else:
            flash('Email not found.', 'danger')
    return render_template('forgot_password.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    email = request.args.get('email') or request.form.get('email')
    if request.method == 'POST':
        code = request.form['code']
        new_password = request.form['new_password']
        user = User.query.filter_by(email=email).first()
        if user and user.verification_code == code:
            user.password = new_password  # Hash in production!
            user.verification_code = None
            user.email_verified = True
            db.session.commit()
            flash('Password reset successful! You can now log in.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Invalid code or email.', 'danger')
    return render_template('reset_password.html', email=email)


@app.route('/resend-verification-code', methods=['POST'])
def resend_verification_code():
    email = request.form['email']
    # Registration (session) path
    if 'reg_data' in session and email == session.get('reg_data',{}).get('email'):
        code = str(random.randint(100000, 999999))
        session['reg_code'] = code
        session['reg_code_expires'] = (datetime.utcnow() + timedelta(minutes=5)).isoformat()
        if send_verification_email(email, code):
            flash('A new verification code has been sent to your email.', 'info')
        else:
            flash('Failed to resend verification code. Please try again.', 'danger')
        return redirect(url_for('verify_email', email=email))
    # Legacy: user exists in DB
    user = User.query.filter_by(email=email).first()
    if user:
        code = str(random.randint(100000, 999999))
        user.verification_code = code
        db.session.commit()
        if send_verification_email(email, code):
            flash('A new verification code has been sent to your email.', 'info')
        else:
            flash('Failed to resend verification code. Please try again.', 'danger')
    else:
        flash('User not found.', 'danger')
    return redirect(url_for('verify_email', email=email))


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


@app.route('/admin')
@admin_required
def admin_dashboard():
    total_users = User.query.count()
    from sqlalchemy import distinct
    # Explicit select() for SQLAlchemy 2.x compatibility when using IN()
    approved_app_users = db.select(SellerApplication.user_id).where(
        SellerApplication.status == 'approved'
    )
    total_sellers = db.session.query(db.func.count(distinct(User.id))).filter(
        db.or_(User.role == 'seller', User.id.in_(approved_app_users))
    ).scalar() or 0
    total_buyers = db.session.query(db.func.count(distinct(User.id))).filter(
        User.role == 'buyer',
        ~User.id.in_(approved_app_users)
    ).scalar() or 0
    total_riders = User.query.filter_by(role='rider').count()
    pending_rider_applications = RiderApplication.query.filter_by(status='pending').count()

    pending_applications = SellerApplication.query.filter_by(status='pending').count()
    pending_products = Product.query.filter(Product.status == 'pending').count()
    total_products = Product.query.count()
    total_orders = Order.query.count()
    # Admin commission based on released commissions (wallet), not raw order totals
    admins = User.query.filter_by(role='admin').all()
    admin_ids = [a.id for a in admins] or [0]
    admin_commission_total = float(
        db.session.query(db.func.coalesce(db.func.sum(WalletTransaction.amount), 0.0))
        .filter(
            WalletTransaction.user_id.in_(admin_ids),
            WalletTransaction.type == 'credit',
            WalletTransaction.source == 'order_commission'
        ).scalar() or 0.0
    )
    total_sales = admin_commission_total / 0.05 if admin_commission_total else 0.0
    commission = admin_commission_total
    total_commission = commission  # Add alias for template compatibility
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    pending_seller_apps = SellerApplication.query.filter_by(status='pending').all()
    admin_unread_notifications = Notification.query.filter_by(user_id=session['user_id'], is_read=False).count()
    recent_notifications = Notification.query.filter_by(user_id=session['user_id']).order_by(Notification.created_at.desc()).limit(10).all()
    pending_registrations_count = User.query.filter_by(status='pending', role='buyer').count()
    
    # Get badge counts for sidebar
    badge_counts = get_admin_badge_counts()

    return render_template(
        'admin/dashboard.html',
        total_users=total_users,
        total_buyers=total_buyers,
        total_sellers=total_sellers,
        total_riders=total_riders,
        pending_products=pending_products,
        total_products=total_products,
        total_orders=total_orders,
        total_sales=total_sales,
        commission=commission,
        total_commission=total_commission,  # Add alias for template compatibility
        recent_orders=recent_orders,
        pending_seller_apps=pending_seller_apps,
        moment=datetime.utcnow,
        admin_unread_notifications=admin_unread_notifications,
        recent_notifications=recent_notifications,
        **badge_counts
    )


@app.route('/api/admin/badge-counts')
@admin_required
def api_admin_badge_counts():
    """API endpoint to get current admin badge counts for real-time updates"""
    badge_counts = get_admin_badge_counts()
    return jsonify(badge_counts)


def get_admin_badge_counts():
    """Helper function to get admin badge counts for sidebar"""
    pending_registrations_count = User.query.filter_by(status='pending', role='buyer').count()
    pending_rider_applications = RiderApplication.query.filter_by(status='pending').count()
    pending_applications = SellerApplication.query.filter_by(status='pending').count()
    pending_products_count = Product.query.filter(Product.status == 'pending').count()
    pending_restock_count = RestockRequest.query.filter_by(status='pending').count()
    
    return {
        'pending_registrations_count': pending_registrations_count,
        'pending_rider_applications_count': pending_rider_applications,
        'pending_applications': pending_applications,
        'pending_products_count': pending_products_count,
        'pending_restock_count': pending_restock_count
    }


@app.route('/admin/rider-applications')
@admin_required
def admin_rider_applications():
    applications = RiderApplication.query.order_by(RiderApplication.applied_at.desc()).all()
    badge_counts = get_admin_badge_counts()
    return render_template('admin/rider_applications.html', 
                         applications=applications,
                         **badge_counts)


@app.route('/admin/seller-applications')
@admin_required
def admin_seller_applications():
    applications = SellerApplication.query.order_by(SellerApplication.applied_at.desc()).all()
    badge_counts = get_admin_badge_counts()
    return render_template('admin/seller_applications.html', 
                         applications=applications,
                         **badge_counts)


@app.route('/admin/pending-registrations')
@admin_required
def admin_pending_registrations():
    # Show only buyers with status == 'pending' (exclude riders and sellers)
    pending_users = User.query.filter_by(status='pending', role='buyer').order_by(User.created_at.asc()).all()
    badge_counts = get_admin_badge_counts()
    return render_template('admin/pending_registrations.html', 
                         pending_users=pending_users,
                         **badge_counts)

@app.route('/admin/approve-registration/<int:user_id>', methods=['POST','GET'])
@admin_required
def admin_approve_registration(user_id):
    user = User.query.get_or_404(user_id)
    if user.status != 'pending':
        flash('User is not pending.', 'info')
        return redirect(url_for('admin_pending_registrations'))

    user.status = 'active'
    user.email_verified = True  # optional: treat admin approval as verification
    db.session.commit()

    # In-app notification
    try:
        db.session.add(Notification(user_id=user.id, message='Your account registration has been approved. You can now log in.'))
        db.session.commit()
    except Exception:
        db.session.rollback()

    # Send approval email
    try:
        send_account_status_email(user.email, approved=True)
    except Exception:
        app.logger.exception("Failed to send approval email to %s", user.email)

    flash(f'User {user.first_name} {user.last_name} approved.', 'success')
    return redirect(url_for('admin_pending_registrations'))

@app.route('/admin/reject-registration/<int:user_id>', methods=['POST','GET'])
@admin_required
def admin_reject_registration(user_id):
    user = User.query.get_or_404(user_id)
    if user.status != 'pending':
        flash('User is not pending.', 'info')
        return redirect(url_for('admin_pending_registrations'))

    # Option 1: mark rejected, keep record
    user.status = 'rejected'
    db.session.commit()

    # In-app notification
    try:
        db.session.add(Notification(user_id=user.id, message='Your account registration was not approved.'))
        db.session.commit()
    except Exception:
        db.session.rollback()

    # Send rejection email (optional reason)
    reason = request.args.get('reason') or request.form.get('reason') or None
    try:
        send_account_status_email(user.email, approved=False, reason=reason)
    except Exception:
        app.logger.exception("Failed to send rejection email to %s", user.email)

    flash(f'User {user.first_name} {user.last_name} rejected.', 'info')
    return redirect(url_for('admin_pending_registrations'))



@app.route('/admin/approve-seller/<int:app_id>')
@admin_required
def approve_seller(app_id):
    application = SellerApplication.query.get_or_404(app_id)
    application.status = 'approved'
    application.reviewed_at = datetime.utcnow()
    application.reviewed_by = session['user_id']

    # Ensure the seller has a store logo, provide default if missing
    if not application.store_logo:
        application.store_logo = '/static/uploads/default-store-logo.png'

    # Promote the user to seller and activate the account if needed
    user = User.query.get(application.user_id)
    if user:
        user.role = 'seller'
        if user.status != 'active':
            user.status = 'active'
        try:
            db.session.add(Notification(user_id=user.id, message='Your seller application was approved. You now have seller access.'))
        except Exception:
            pass

    db.session.commit()
    
    # Notify all admins about the new brand addition
    try:
        notify_admins(
            f"New brand added: {application.store_name} is now available in the brand section",
            type='brand_added',
            link=f'/store/{application.user_id}',
            image_url=application.store_logo
        )
    except Exception:
        pass
    
    flash('Seller application approved successfully! Store added to brand section.', 'success')
    return redirect(url_for('admin_seller_applications'))


@app.route('/admin/reject-seller/<int:app_id>')
@admin_required
def reject_seller(app_id):
    application = SellerApplication.query.get_or_404(app_id)
    application.status = 'rejected'
    application.reviewed_at = datetime.utcnow()
    application.reviewed_by = session['user_id']

    # Send notification to the user
    user = User.query.get(application.user_id)
    if user:
        try:
            db.session.add(Notification(user_id=user.id, message='Your seller application was rejected.'))
        except Exception:
            pass

    db.session.commit()
    flash('Seller application rejected.', 'info')
    return redirect(url_for('admin_seller_applications'))


@app.route('/admin/coupons', methods=['GET', 'POST'])
@admin_required
def admin_coupons():
    """Professional coupon management and automatic generation for admins."""
    # List existing coupons
    coupons = Coupon.query.order_by(Coupon.created_at.desc()).all()

    if request.method == 'POST':
        mode = request.form.get('mode', 'manual')

        # --- Manual create / update coupon ---
        if mode == 'manual':
            code = (request.form.get('code') or '').strip().upper()
            description = (request.form.get('description') or '').strip()
            discount_type = request.form.get('discount_type') or 'percent'
            try:
                discount_value = float(request.form.get('discount_value') or 0)
            except ValueError:
                flash('Discount value must be a number.', 'danger')
                return redirect(url_for('admin_coupons'))

            try:
                min_order_amount = float(request.form.get('min_order_amount') or 0)
            except ValueError:
                flash('Minimum order amount must be a number.', 'danger')
                return redirect(url_for('admin_coupons'))

            max_uses_raw = request.form.get('max_uses') or ''
            max_uses = None
            if max_uses_raw.strip():
                try:
                    max_uses = int(max_uses_raw)
                except ValueError:
                    flash('Maximum uses must be an integer.', 'danger')
                    return redirect(url_for('admin_coupons'))

            # Parse validity dates (optional)
            def _parse_date(field_name):
                val = (request.form.get(field_name) or '').strip()
                if not val:
                    return None
                try:
                    return datetime.strptime(val, '%Y-%m-%d')
                except ValueError:
                    flash(f'Invalid date for {field_name.replace("_", " ")}. Use YYYY-MM-DD.', 'danger')
                    raise

            try:
                valid_from = _parse_date('valid_from')
                valid_until = _parse_date('valid_until')
            except Exception:
                return redirect(url_for('admin_coupons'))

            if not code:
                flash('Coupon code is required.', 'danger')
                return redirect(url_for('admin_coupons'))

            # Create coupon
            existing = Coupon.query.filter(db.func.upper(Coupon.code) == code).first()
            if existing:
                flash('Coupon code already exists. Please choose another.', 'danger')
                return redirect(url_for('admin_coupons'))

            coupon = Coupon(
                code=code,
                description=description,
                discount_type=discount_type,
                discount_value=discount_value,
                min_order_amount=min_order_amount,
                max_uses=max_uses,
                valid_from=valid_from,
                valid_until=valid_until,
                is_active=True
            )
            db.session.add(coupon)
            db.session.commit()
            flash(f'Coupon {coupon.code} created successfully.', 'success')
            return redirect(url_for('admin_coupons'))

        # --- Automatic generation based on customer segment ---
        if mode == 'auto':
            segment = request.form.get('segment') or 'all'
            discount_type = request.form.get('auto_discount_type') or 'percent'
            try:
                discount_value = float(request.form.get('auto_discount_value') or 0)
            except ValueError:
                flash('Discount value must be a number.', 'danger')
                return redirect(url_for('admin_coupons'))

            try:
                min_order_amount = float(request.form.get('auto_min_order_amount') or 0)
            except ValueError:
                flash('Minimum order amount must be a number.', 'danger')
                return redirect(url_for('admin_coupons'))

            # How long the coupon is valid from today (in days)
            try:
                valid_days = int(request.form.get('auto_valid_days') or 30)
            except ValueError:
                flash('Valid days must be an integer.', 'danger')
                return redirect(url_for('admin_coupons'))

            # Segment-specific thresholds for loyal buyers
            try:
                min_orders = int(request.form.get('min_orders') or 3)
            except ValueError:
                min_orders = 3
            try:
                min_spent = float(request.form.get('min_spent') or 1000)
            except ValueError:
                min_spent = 1000.0

            # Optional explicit code; otherwise auto-generate professional code
            manual_code = (request.form.get('auto_code') or '').strip().upper()
            if manual_code:
                code = manual_code
            else:
                prefix = {
                    'new': 'NEW',
                    'loyal': 'LOYAL',
                    'all': 'SALE'
                }.get(segment, 'SALE')
                random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                code = f"{prefix}-{random_part}"

            now = datetime.utcnow()
            valid_from = now
            valid_until = now + timedelta(days=valid_days)

            description = (request.form.get('auto_description') or '').strip()
            if not description:
                if discount_type == 'percent':
                    description = f"{discount_value:.0f}% off for selected buyers"
                else:
                    description = f"₱{discount_value:,.2f} off for selected buyers"

            # Ensure code unique
            existing = Coupon.query.filter(db.func.upper(Coupon.code) == code.upper()).first()
            if existing:
                flash('Generated coupon code already exists. Please try again.', 'danger')
                return redirect(url_for('admin_coupons'))

            coupon = Coupon(
                code=code,
                description=description,
                discount_type=discount_type,
                discount_value=discount_value,
                min_order_amount=min_order_amount,
                max_uses=None,  # unlimited by default for campaigns
                valid_from=valid_from,
                valid_until=valid_until,
                is_active=True
            )
            db.session.add(coupon)
            db.session.flush()  # get coupon.id

            # Determine target buyers based on segment
            buyer_query = User.query.filter_by(role='buyer')

            if segment == 'new':
                # Buyers with no orders yet
                buyer_query = buyer_query.outerjoin(Order, Order.buyer_id == User.id).group_by(User.id).having(
                    db.func.count(Order.id) == 0
                )
            elif segment == 'loyal':
                # Buyers with either enough orders or total spend
                buyer_query = buyer_query.join(Order, Order.buyer_id == User.id).group_by(User.id).having(
                    (db.func.count(Order.id) >= min_orders) |
                    (db.func.coalesce(db.func.sum(Order.total_amount), 0) >= min_spent)
                )
            else:
                # 'all' buyers – keep base query
                pass

            target_buyers = buyer_query.all()

            discount_label = None
            if discount_type == 'percent':
                discount_label = f"{discount_value:.0f}% off your next order"
            else:
                discount_label = f"₱{discount_value:,.2f} off your next order"

            # Create in-site notifications and send emails
            notified_count = 0
            for buyer in target_buyers:
                # Notification text kept concise but clear
                message = (
                    f"You received a new coupon {coupon.code}: {discount_label}. "
                    f"Valid until {coupon.valid_until.strftime('%Y-%m-%d')}"
                )
                db.session.add(Notification(user_id=buyer.id, message=message))
                try:
                    send_coupon_email(buyer, coupon, discount_label)
                except Exception:
                    # Log but do not break the campaign
                    pass
                notified_count += 1

            db.session.commit()
            flash(
                f"Automatic coupon {coupon.code} created and sent to {notified_count} buyer(s).",
                'success'
            )
            return redirect(url_for('admin_coupons'))

    badge_counts = get_admin_badge_counts()
    return render_template('admin/coupons.html', coupons=coupons, **badge_counts)


@app.route('/admin/coupons/<int:coupon_id>/toggle', methods=['POST'])
@admin_required
def admin_toggle_coupon(coupon_id):
    """Enable or disable a coupon from the admin panel."""
    coupon = Coupon.query.get_or_404(coupon_id)
    coupon.is_active = not coupon.is_active
    db.session.commit()
    flash(f'Coupon {coupon.code} is now {"active" if coupon.is_active else "inactive"}.', 'success')
    return redirect(url_for('admin_coupons'))


# Helper function to log admin actions
def log_admin_action(action, details=None):
    if is_admin() and 'user_id' in session:
        log = AdminSecurityLog(
            user_id=session['user_id'],
            action=action,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', ''),
            details=details
        )
        db.session.add(log)
        db.session.commit()

@app.route('/admin/profile')
@admin_required
def admin_profile():
    user = User.query.get(session['user_id'])
    admin_profile = AdminProfile.query.filter_by(user_id=session['user_id']).first()
    if not admin_profile:
        # Create admin profile if it doesn't exist
        admin_profile = AdminProfile(
            user_id=session['user_id'],
            full_name=f"{user.first_name} {user.last_name}",
            contact_number=user.phone,
            system_role='Administrator'
        )
        db.session.add(admin_profile)
        db.session.commit()

    # Compute avatar URL using helper function
    admin_avatar_url = get_user_avatar_url(user.id, 'admin')
    
    recent_logs = AdminSecurityLog.query.filter_by(user_id=session['user_id']).order_by(AdminSecurityLog.timestamp.desc()).limit(10).all()
    badge_counts = get_admin_badge_counts()
    return render_template('admin/profile.html', 
                         user=user, 
                         admin_profile=admin_profile, 
                         recent_logs=recent_logs, 
                         admin_avatar_url=admin_avatar_url,
                         **badge_counts)

@app.route('/admin/update-profile', methods=['POST'])
@admin_required
def update_admin_profile():
    user = User.query.get(session['user_id'])
    admin_profile = AdminProfile.query.filter_by(user_id=session['user_id']).first()
    if not admin_profile:
        # Create admin profile record on first update if it doesn't exist yet
        admin_profile = AdminProfile(
            user_id=session['user_id'],
            full_name=f"{user.first_name} {user.last_name}",
            contact_number=user.phone,
            system_role='Administrator'
        )
        db.session.add(admin_profile)
        db.session.flush()

    form = request.form

    # Update user basic info (use get so missing fields don't crash)
    if 'first_name' in form:
        user.first_name = form.get('first_name', user.first_name)
    if 'last_name' in form:
        user.last_name = form.get('last_name', user.last_name)
    if 'email' in form:
        user.email = form.get('email', user.email)
    if 'phone' in form:
        user.phone = form.get('phone', user.phone)

    # Update admin profile core fields (also tolerant of missing keys)
    if 'full_name' in form:
        admin_profile.full_name = form.get('full_name', admin_profile.full_name)
    if 'contact_number' in form:
        admin_profile.contact_number = form.get('contact_number', admin_profile.contact_number)
    if 'system_role' in form:
        admin_profile.system_role = form.get('system_role', admin_profile.system_role)

    admin_profile.updated_at = datetime.utcnow()

    # Optional avatar upload
    file = request.files.get('avatar')
    if file and file.filename:
        try:
            from PIL import Image
            # Ensure target directory exists
            avatar_dir = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], 'admin_avatars')
            os.makedirs(avatar_dir, exist_ok=True)

            # Save temporary file
            temp_path = os.path.join(avatar_dir, f"tmp_admin_{user.id}")
            file.save(temp_path)

            # Open, normalize and resize, then save as PNG
            img = Image.open(temp_path)
            img = img.convert('RGB')
            img.thumbnail((256, 256))
            final_name = f"admin_avatar_{user.id}.png"
            final_path = os.path.join(avatar_dir, final_name)
            img.save(final_path, format='PNG')
        except Exception:
            # Do not block profile updates if avatar processing fails
            pass
        finally:
            try:
                if 'temp_path' in locals() and os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
    
    db.session.commit()
    
    # Update session user_name to reflect changes in dropdown
    session['user_name'] = f"{user.first_name} {user.last_name}"
    
    # Update session with new avatar URL for immediate dropdown update
    avatar_rel = os.path.join('admin_avatars', f"admin_avatar_{user.id}.png")
    upload_root = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
    avatar_path = os.path.join(upload_root, avatar_rel)
    if os.path.exists(avatar_path):
        session['navbar_avatar_url'] = url_for('static', filename=f'uploads/{avatar_rel.replace("\\", "/")}')
        session['avatar_timestamp'] = int(time.time())  # Force cache refresh
    
    log_admin_action('Profile Updated', 'Admin profile information updated')
    flash('Admin profile updated successfully!', 'success')
    return redirect(url_for('admin_profile'))

@app.route('/admin/users')
@admin_required
def admin_users():
    search = request.args.get('search', '')
    status = request.args.get('status', 'all')
    role = request.args.get('role', 'all')
    
    query = User.query
    
    if search:
        query = query.filter(
            db.or_(
                User.first_name.contains(search),
                User.last_name.contains(search),
                User.email.contains(search)
            )
        )
    
    if status != 'all':
        query = query.filter_by(status=status)
    
    if role != 'all':
        query = query.filter_by(role=role)
    
    users = query.order_by(User.created_at.desc()).all()
    
    log_admin_action('Users List Accessed')
    badge_counts = get_admin_badge_counts()
    return render_template('admin/users.html', 
                         users=users, 
                         search=search, 
                         status=status, 
                         role=role,
                         **badge_counts)


# Add this route to app.py (place it with other @admin_required admin routes)
@app.route('/admin/user/<int:user_id>')
@admin_required
def admin_view_user(user_id):
    """
    Admin-only full profile view for a specific user.
    Shows user core fields, addresses, seller applications, notifications and uploaded documents.
    """
    user = User.query.get_or_404(user_id)

    # Basic related info
    addresses = Address.query.filter_by(user_id=user.id).order_by(Address.is_default.desc(), Address.created_at.asc()).all()
    seller_apps = SellerApplication.query.filter_by(user_id=user.id).order_by(SellerApplication.applied_at.desc()).all()
    notifications = Notification.query.filter_by(user_id=user.id).order_by(Notification.created_at.desc()).limit(50).all()

    # Helpful aggregated counts
    total_orders = Order.query.filter_by(buyer_id=user.id).count()
    total_products = Product.query.filter_by(seller_id=user.id).count()
    reviews = Review.query.filter_by(user_id=user.id).order_by(Review.created_at.desc()).limit(10).all()

    badge_counts = get_admin_badge_counts()
    return render_template('admin/user_profile.html',
                           user=user,
                           addresses=addresses,
                           seller_apps=seller_apps,
                           notifications=notifications,
                           total_orders=total_orders,
                           total_products=total_products,
                           recent_reviews=reviews,
                           **badge_counts)


@app.route('/admin/block-user/<int:user_id>')
@admin_required
def block_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.role != 'admin':  # Prevent blocking other admins
        user.status = 'suspended'
        db.session.commit()
        log_admin_action('User Blocked', f'User {user.first_name} {user.last_name} ({user.email}) blocked')
        flash(f'User {user.first_name} {user.last_name} has been blocked.', 'success')
    else:
        flash('Cannot block admin users.', 'error')
    return redirect(url_for('admin_users'))

@app.route('/admin/unblock-user/<int:user_id>')
@admin_required
def unblock_user(user_id):
    user = User.query.get_or_404(user_id)
    user.status = 'active'
    db.session.commit()
    log_admin_action('User Unblocked', f'User {user.first_name} {user.last_name} ({user.email}) unblocked')
    flash(f'User {user.first_name} {user.last_name} has been unblocked.', 'success')
    return redirect(url_for('admin_users'))

def _delete_products_for_user(user_id: int):
    """Hard-delete all products owned by user_id, including dependent rows and media.
    If an order contains the seller's items, we remove those items, adjust the order total,
    and delete the order entirely if it becomes empty.
    """
    products = Product.query.filter_by(seller_id=user_id).all()
    pids = [p.id for p in products]
    return _delete_products_by_ids(pids, products_override=products)


def _delete_products_by_ids(product_ids: list[int], products_override=None):
    """Hard-delete specific products by ID, cleaning dependent rows and orders.
    Returns stats dict.
    """
    if not product_ids:
        return {'deleted_products': 0, 'skipped': 0, 'orders_deleted': 0, 'orders_adjusted': 0}

    if products_override is None:
        products = Product.query.filter(Product.id.in_(product_ids)).all()
    else:
        products = products_override

    if not products:
        return {'deleted_products': 0, 'skipped': 0, 'orders_deleted': 0, 'orders_adjusted': 0}

    pids = [p.id for p in products]

    # 1) Orders that contain these products
    items = OrderItem.query.filter(OrderItem.product_id.in_(pids)).all()
    affected_order_ids = set(it.order_id for it in items)
    removed_sum = {}
    for it in items:
        removed_sum[it.order_id] = removed_sum.get(it.order_id, 0.0) + float(it.price_at_time) * int(it.quantity)

    if affected_order_ids:
        # Delete order-linked artifacts for those orders if they end up empty later
        # First remove the specific items from those orders
        OrderItem.query.filter(OrderItem.order_id.in_(affected_order_ids), OrderItem.product_id.in_(pids)).delete(synchronize_session=False)

        # Adjust or delete orders now that items are removed
        orders_deleted = 0
        orders_adjusted = 0
        for oid in list(affected_order_ids):
            o = Order.query.get(oid)
            if not o:
                continue
            remaining = OrderItem.query.filter_by(order_id=oid).count()
            if remaining == 0:
                # Clean linked artifacts then delete order
                QRScanLog.query.filter_by(order_id=oid).delete(synchronize_session=False)
                OrderLabel.query.filter_by(order_id=oid).delete(synchronize_session=False)
                ReturnRequest.query.filter_by(order_id=oid).delete(synchronize_session=False)
                RiderChatMessage.query.filter_by(order_id=oid).delete(synchronize_session=False)
                WalletTransaction.query.filter_by(order_id=oid).delete(synchronize_session=False)
                db.session.delete(o)
                orders_deleted += 1
            else:
                dec = float(removed_sum.get(oid, 0.0) or 0.0)
                try:
                    o.total_amount = max(0.0, float(o.total_amount) - dec)
                except Exception:
                    pass
                orders_adjusted += 1
    else:
        orders_deleted = 0
        orders_adjusted = 0

    # 2) Product-dependent rows (scoped to these products)
    # ProductQR.query.filter(ProductQR.product_id.in_(pids)).delete(synchronize_session=False)
    Cart.query.filter(Cart.product_id.in_(pids)).delete(synchronize_session=False)
    Wishlist.query.filter(Wishlist.product_id.in_(pids)).delete(synchronize_session=False)
    StoreChatMessage.query.filter(StoreChatMessage.product_id.in_(pids)).delete(synchronize_session=False)
    Review.query.filter(Review.product_id.in_(pids)).delete(synchronize_session=False)

    # 3) Remove media from disk
    upload_root = os.path.join(app.root_path, app.config.get('UPLOAD_FOLDER', os.path.join('static', 'uploads')))
    def safe_rm(path):
        try:
            if path and os.path.isfile(path):
                os.remove(path)
        except Exception:
            pass

    deleted = 0
    for p in products:
        if p.image_filename:
            safe_rm(os.path.join(upload_root, p.image_filename))
        if p.video_filename:
            safe_rm(os.path.join(upload_root, p.video_filename))
        try:
            if p.gallery:
                for g in (p.gallery or []):
                    safe_rm(os.path.join(upload_root, g))
        except Exception:
            pass
        db.session.delete(p)
        deleted += 1

    return {
        'deleted_products': deleted,
        'skipped': 0,
        'orders_deleted': orders_deleted,
        'orders_adjusted': orders_adjusted,
    }


@app.route('/admin/delete-user/<int:user_id>', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    """Delete a user account.
    - Seller: deletes all their products and cleans orders that contain them.
    - Buyer: deletes their orders and related artifacts.
    - Admin: allowed except the last remaining admin.
    """
    user = User.query.get_or_404(user_id)

    # Prevent deleting last admin
    if user.role == 'admin':
        admin_count = User.query.filter_by(role='admin').count()
        if admin_count <= 1:
            flash('Cannot delete the last admin account.', 'danger')
            return redirect(url_for('admin_users'))

    # Role-specific cleanup
    stats = {'deleted_products': 0, 'orders_deleted': 0, 'orders_adjusted': 0}
    if user.role == 'seller':
        stats = _delete_products_for_user(user.id)
    elif user.role == 'buyer':
        # Delete all orders for this buyer
        o_deleted, o_adjusted = _delete_orders_for_buyer(user.id)
        stats['orders_deleted'] = o_deleted
        stats['orders_adjusted'] = o_adjusted

    # Clean other user-linked records
    AdminProfile.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    SellerApplication.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    DeliveryPersonnel.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    Follow.query.filter(db.or_(Follow.follower_id == user.id, Follow.seller_id == user.id)).delete(synchronize_session=False)
    Notification.query.filter(db.or_(Notification.user_id == user.id, Notification.actor_user_id == user.id)).delete(synchronize_session=False)
    Cart.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    Wishlist.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    StoreChatMessage.query.filter(db.or_(StoreChatMessage.buyer_id == user.id, StoreChatMessage.seller_id == user.id)).delete(synchronize_session=False)
    RiderChatMessage.query.filter(db.or_(RiderChatMessage.buyer_id == user.id, RiderChatMessage.rider_id == user.id)).delete(synchronize_session=False)
    Address.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    OAuth.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    Review.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    WalletTransaction.query.filter_by(user_id=user.id).delete(synchronize_session=False)

    # Finally remove the user
    db.session.delete(user)
    db.session.commit()

    log_admin_action('User Deleted', f'User ID {user_id} deleted; products removed: {stats.get("deleted_products", 0)}, orders deleted: {stats.get("orders_deleted", 0)}, orders adjusted: {stats.get("orders_adjusted", 0)}')
    flash('User and associated data were deleted successfully.', 'success')
    return redirect(url_for('admin_users'))


def _delete_orders_for_buyer(buyer_id: int) -> tuple[int, int]:
    """Delete all orders for a buyer and related artifacts.
    Returns (orders_deleted, orders_adjusted) — adjusted will be 0 since we delete full orders.
    """
    orders = Order.query.filter_by(buyer_id=buyer_id).all()
    deleted = 0
    for o in orders:
        oid = o.id
        # detach reviews referencing this order (from anyone)
        Review.query.filter_by(order_id=oid).update({Review.order_id: None}, synchronize_session=False)
        # linked artifacts
        QRScanLog.query.filter_by(order_id=oid).delete(synchronize_session=False)
        OrderLabel.query.filter_by(order_id=oid).delete(synchronize_session=False)
        ReturnRequest.query.filter_by(order_id=oid).delete(synchronize_session=False)
        RiderChatMessage.query.filter_by(order_id=oid).delete(synchronize_session=False)
        WalletTransaction.query.filter_by(order_id=oid).delete(synchronize_session=False)
        OrderItem.query.filter_by(order_id=oid).delete(synchronize_session=False)
        db.session.delete(o)
        deleted += 1
    return deleted, 0


@app.route('/seller/delete-account', methods=['POST'])
@seller_required
def seller_delete_account():
    """Allow a seller to delete their own account; also removes their products.
    Ends session after deletion.
    """
    uid = session.get('user_id')
    if not uid:
        return redirect(url_for('login'))

    stats = _delete_products_for_user(uid)

    # Remove user-linked records
    AdminProfile.query.filter_by(user_id=uid).delete(synchronize_session=False)
    SellerApplication.query.filter_by(user_id=uid).delete(synchronize_session=False)
    DeliveryPersonnel.query.filter_by(user_id=uid).delete(synchronize_session=False)
    Follow.query.filter(db.or_(Follow.follower_id == uid, Follow.seller_id == uid)).delete(synchronize_session=False)
    Notification.query.filter(db.or_(Notification.user_id == uid, Notification.actor_user_id == uid)).delete(synchronize_session=False)
    Cart.query.filter_by(user_id=uid).delete(synchronize_session=False)
    Wishlist.query.filter_by(user_id=uid).delete(synchronize_session=False)
    StoreChatMessage.query.filter(db.or_(StoreChatMessage.buyer_id == uid, StoreChatMessage.seller_id == uid)).delete(synchronize_session=False)
    RiderChatMessage.query.filter(db.or_(RiderChatMessage.buyer_id == uid, RiderChatMessage.rider_id == uid)).delete(synchronize_session=False)

    user = User.query.get(uid)
    if user:
        db.session.delete(user)
    db.session.commit()

    session.clear()
    flash('Your seller account and products were deleted.', 'success')
    return redirect(url_for('index'))


@app.route('/admin/products')
@admin_required
def admin_products():
    search = request.args.get('search', '')
    status = request.args.get('status', 'all')
    category = request.args.get('category', 'all')
    seller_name = request.args.get('seller', 'all')

    query = Product.query.join(User, Product.seller_id == User.id)

    if search:
        like = f"%{search}%"
        query = query.filter(
            db.or_(
                Product.name.ilike(like),
                Product.description.ilike(like),
                User.first_name.ilike(like),
                User.last_name.ilike(like)
            )
        )

    if status != 'all':
        query = query.filter(Product.status == status)

    if category != 'all':
        # Match by category name
        query = query.join(Category, Product.category_id == Category.id).filter(Category.name == category)

    if seller_name != 'all':
        query = query.filter(User.first_name == seller_name)

    products = query.order_by(Product.created_at.desc()).all()

    log_admin_action('Products List Accessed')
    badge_counts = get_admin_badge_counts()
    return render_template('admin/products.html', 
                         products=products, 
                         search=search, 
                         status=status, 
                         category=category, 
                         seller=seller_name,
                         **badge_counts)

@app.route('/admin/reject-product/<int:product_id>')
@admin_required
def reject_product(product_id):
    product = Product.query.get_or_404(product_id)
    reason = request.args.get('reason', '')
    product.status = 'rejected'
    db.session.commit()
    # Notify seller
    db.session.add(Notification(user_id=product.seller_id, message=f'Your product {product.name} was rejected. Reason: {reason or "No reason provided"}'))
    db.session.commit()
    log_admin_action('Product Rejected', f'Product "{product.name}" (ID: {product.id}) rejected')
    flash(f'Product "{product.name}" has been rejected.', 'warning')
    return redirect(url_for('admin_products', status='pending'))

@app.route('/admin/edit-product/<int:product_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_product(product_id):
    ensure_product_video_column()
    product = Product.query.get_or_404(product_id)
    if request.method == 'POST':
        product.name = request.form['name']
        product.description = request.form['description']
        product.price = float(request.form['price'])
        product.stock = int(request.form['stock'])
        product.category_id = int(request.form['category_id'])
        # Optional image update
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                filename = secure_filename(file.filename)
                filename = datetime.utcnow().strftime('%Y%m%d_%H%M%S_') + filename
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                product.image_filename = filename
        # Optional video update
        if 'video' in request.files:
            v = request.files['video']
            if v and v.filename:
                vext = v.filename.rsplit('.', 1)[-1].lower() if '.' in v.filename else ''
                if vext in ALLOWED_VIDEO_EXT:
                    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'videos'), exist_ok=True)
                    vname = secure_filename(v.filename)
                    vname = datetime.utcnow().strftime('%Y%m%d_%H%M%S_') + vname
                    v.save(os.path.join(app.config['UPLOAD_FOLDER'], 'videos', vname))
                    product.video_filename = 'videos/' + vname
                else:
                    flash('Unsupported video format. Allowed: MP4, WebM, Ogg.', 'danger')
        db.session.commit()
        # Notify seller
        db.session.add(Notification(user_id=product.seller_id, message=f'Admin has updated your product {product.name}.'))
        db.session.commit()
        try:
            available_stock = get_available_stock(product.id)
            socketio.emit('product_stock_update', {
                'product_id': product.id,
                'stock': available_stock,
                'available_stock': available_stock
            }, broadcast=True)
            _emit_seller_stats_update(product.seller_id)
        except Exception:
            pass
        flash('Product updated successfully.', 'success')
        return redirect(url_for('admin_products'))
    categories = Category.query.all()
    badge_counts = get_admin_badge_counts()
    return render_template('admin/edit_product.html', product=product, categories=categories, **badge_counts)

@app.route('/admin/remove-product/<int:product_id>')
@admin_required
def remove_product(product_id):
    product = Product.query.get_or_404(product_id)
    name = product.name
    # Hard-delete and clean dependencies/orders
    stats = _delete_products_by_ids([product.id])
    db.session.commit()
    log_admin_action('Product Deleted', f'Product "{name}" (ID: {product_id}) permanently deleted; orders deleted: {stats.get("orders_deleted",0)}, orders adjusted: {stats.get("orders_adjusted",0)}')
    flash(f'Product "{name}" has been permanently deleted.', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/approve-product/<int:product_id>')
@admin_required
def approve_product(product_id):
    product = Product.query.get_or_404(product_id)
    product.status = 'active'
    db.session.commit()
    log_admin_action('Product Approved', f'Product "{product.name}" (ID: {product.id}) approved')
    # Notify seller
    db.session.add(Notification(user_id=product.seller_id, message=f'Your product {product.name} has been approved and is now live.'))
    db.session.commit()
    flash(f'Product "{product.name}" has been approved.', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/suspend-product/<int:product_id>')
@admin_required
def suspend_product(product_id):
    product = Product.query.get_or_404(product_id)
    product.status = 'inactive'
    db.session.commit()
    log_admin_action('Product Suspended', f'Product "{product.name}" (ID: {product.id}) suspended')
    flash(f'Product "{product.name}" has been suspended.', 'warning')
    return redirect(url_for('admin_products'))

# Bulk action: keep only "Hot Wheels Basic Car" and remove others from buyer-facing places
@app.route('/admin/products/purge-except-hotwheels', methods=['POST'])
@admin_required
def admin_purge_except_hotwheels():
    try:
        # Find products to keep (case-insensitive exact match preferred, fallback to contains pattern)
        keep = Product.query.filter(db.func.lower(Product.name) == db.func.lower('Hot Wheels Basic Car')).all()
        if not keep:
            keep = Product.query.filter(Product.name.ilike('%hot%wheels%basic%car%')).all()
        keep_ids = [p.id for p in keep]
        if not keep_ids:
            flash('No product named "Hot Wheels Basic Car" found. No changes made.', 'warning')
            return redirect(url_for('admin_products'))

        # Soft-remove all other products
        others_q = Product.query.filter(~Product.id.in_(keep_ids))
        affected_products = others_q.count()
        others_q.update({
            Product.status: 'inactive',
            Product.stock: 0,
            Product.featured: False,
            Product.show_in_new_arrival: False
        }, synchronize_session=False)

        # Clean buyer-facing refs: carts, wishlists, hide reviews
        cart_deleted = Cart.query.filter(~Cart.product_id.in_(keep_ids)).delete(synchronize_session=False)
        wishlist_deleted = Wishlist.query.filter(~Wishlist.product_id.in_(keep_ids)).delete(synchronize_session=False)
        Review.query.filter(~Review.product_id.in_(keep_ids)).update({Review.status: 'hidden'}, synchronize_session=False)

        db.session.commit()
        log_admin_action('Bulk Purge Products', f'Kept Hot Wheels Basic Car (IDs: {keep_ids}); deactivated {affected_products} products; removed {cart_deleted} cart items and {wishlist_deleted} wishlist items.')
        flash(f'Kept only "Hot Wheels Basic Car". Deactivated {affected_products} products and cleaned {cart_deleted} cart / {wishlist_deleted} wishlist items.', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.exception('Failed bulk purge except Hot Wheels')
        flash('Failed to purge products. Please try again.', 'danger')
    return redirect(url_for('admin_products'))


@app.route('/admin/nuke-except-hotwheels', methods=['GET', 'POST'])
@admin_required
def admin_nuke_except_hotwheels():
    """
    Permanently delete ALL data except products whose name contains 'Hot Wheels' (case-insensitive).
    Also wipes ALL orders/transactions and notifications. Use with extreme caution.

    Trigger via POST (recommended) or GET with ?confirm=NUKE to allow manual triggering from the browser.
    """
    try:
        # Require explicit confirmation
        confirm = request.values.get('confirm', '').strip().upper()
        if request.method == 'GET' and confirm != 'NUKE':
            flash('Confirmation required. Append ?confirm=NUKE to proceed.', 'warning')
            return redirect(url_for('admin_products'))

        # 1) Identify products to keep (any name containing 'hot' and 'wheels' in order)
        keep = Product.query.filter(Product.name.ilike('%hot%wheels%')).all()
        if not keep:
            # Fallback: keep exact demo name if present
            keep = Product.query.filter(db.func.lower(Product.name) == db.func.lower('Hot Wheels Basic Car')).all()
        keep_ids = [p.id for p in keep]
        if not keep_ids:
            flash("No 'Hot Wheels' products found. Aborting to avoid deleting everything.", 'danger')
            return redirect(url_for('admin_products'))

        # 2) Start wiping transactional data (order-related) first to avoid FK issues
        # Return flows
        ReturnPickup.query.delete(synchronize_session=False)
        # QR logs and labels
        QRScanLog.query.delete(synchronize_session=False)
        OrderLabel.query.delete(synchronize_session=False)
        # Reviews may reference orders; null out order_id to avoid FK blocks, but keep review content for kept products
        Review.query.update({Review.order_id: None}, synchronize_session=False)
        # Rider chats (order-linked) — remove all
        RiderChatMessage.query.delete(synchronize_session=False)
        # Order items then orders
        OrderItem.query.delete(synchronize_session=False)
        ReturnRequest.query.delete(synchronize_session=False)
        WalletTransaction.query.delete(synchronize_session=False)
        Order.query.delete(synchronize_session=False)

        # 3) Clear buyer-facing state
        Cart.query.delete(synchronize_session=False)
        Wishlist.query.delete(synchronize_session=False)

        # 4) Remove notifications (all)
        Notification.query.delete(synchronize_session=False)

        # 5) Permanently delete NON-Hot Wheels products and their dependent rows/files
        remove_q = Product.query.filter(~Product.id.in_(keep_ids))
        to_remove = remove_q.all()

        # Delete dependent records for those products only
        if to_remove:
            ids = [p.id for p in to_remove]
            # Product QR codes
            # ProductQR.query.filter(ProductQR.product_id.in_(ids)).delete(synchronize_session=False)
            # Store chats tied to these products
            StoreChatMessage.query.filter(StoreChatMessage.product_id.in_(ids)).delete(synchronize_session=False)
            # Reviews for removed products
            Review.query.filter(Review.product_id.in_(ids)).delete(synchronize_session=False)

            # Remove media files safely
            upload_root = os.path.join(app.root_path, app.config.get('UPLOAD_FOLDER', os.path.join('static', 'uploads')))
            def safe_rm(path):
                try:
                    if path and os.path.isfile(path):
                        os.remove(path)
                except Exception:
                    pass

            for p in to_remove:
                # main image
                if p.image_filename:
                    safe_rm(os.path.join(upload_root, p.image_filename))
                # video
                if p.video_filename:
                    safe_rm(os.path.join(upload_root, p.video_filename))
                # gallery (list of filenames)
                try:
                    if p.gallery:
                        for g in (p.gallery or []):
                            safe_rm(os.path.join(upload_root, g))
                except Exception:
                    pass
                db.session.delete(p)

        # 6) Normalize kept products (activate and restock to 0 to be explicit)
        for kp in Product.query.filter(Product.id.in_(keep_ids)).all():
            kp.status = 'active'
            kp.featured = False
            kp.show_in_new_arrival = False
            kp.stock = kp.stock or 0

        db.session.commit()
        log_admin_action('NUKE EXCEPT HOT WHEELS', f"Kept products {keep_ids}; wiped orders, transactions, notifications; removed {len(to_remove)} other products.")
        flash(f"Database reset complete. Kept Hot Wheels products (IDs: {keep_ids}); removed {len(to_remove)} other products and wiped transactions/notifications.", 'success')
    except Exception:
        db.session.rollback()
        app.logger.exception('admin_nuke_except_hotwheels failed')
        flash('Purge failed. Check logs for details.', 'danger')
    return redirect(url_for('admin_products'))

@app.route('/admin/orders')
@admin_required
def admin_orders():
    # Get filter parameters
    status = request.args.get('status', 'all')
    payment_status = request.args.get('payment_status', 'all')
    search = request.args.get('search', '')
    date_range = request.args.get('date_range', 'all')
    payment_method = request.args.get('payment_method', 'all')
    
    # Build query with joins
    query = Order.query.join(User, Order.buyer_id == User.id)
    
    # Apply filters
    if status != 'all':
        query = query.filter(Order.status == status)
    
    if payment_status != 'all':
        query = query.filter(Order.payment_status == payment_status)
    
    if payment_method != 'all':
        query = query.filter(Order.payment_method == payment_method)
    
    # Search functionality
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(
                Order.id.like(search_term),
                User.first_name.like(search_term),
                User.last_name.like(search_term),
                User.email.like(search_term),
                User.phone.like(search_term),
                db.cast(Order.id, db.String).like(search_term)
            )
        )
    
    # Date range filtering
    if date_range != 'all':
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        
        if date_range == 'today':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            query = query.filter(Order.created_at >= start_date)
        elif date_range == '7days':
            start_date = now - timedelta(days=7)
            query = query.filter(Order.created_at >= start_date)
        elif date_range == '30days':
            start_date = now - timedelta(days=30)
            query = query.filter(Order.created_at >= start_date)
        elif date_range == '90days':
            start_date = now - timedelta(days=90)
            query = query.filter(Order.created_at >= start_date)
    
    orders = query.order_by(Order.created_at.desc()).all()
    
    log_admin_action('Orders List Accessed')
    badge_counts = get_admin_badge_counts()
    return render_template('admin/orders.html', 
                         orders=orders, 
                         status=status, 
                         payment_status=payment_status,
                         search=search,
                         date_range=date_range,
                         payment_method=payment_method,
                         **badge_counts)

@app.route('/admin/clean-order-removed-items/<int:order_id>', methods=['GET','POST'])
@admin_required
def admin_clean_order_removed_items(order_id):
    order = Order.query.get_or_404(order_id)
    # Optional confirm for GET
    if request.method == 'GET' and request.args.get('confirm') != 'CLEAN':
        flash('Confirmation required. Append ?confirm=CLEAN to proceed.', 'warning')
        return redirect(url_for('admin_orders'))

    # Identify items whose product is missing or not active
    items = list(order.items)
    to_remove_ids = []
    removed_total = 0.0
    for it in items:
        p = it.product
        if (p is None) or (getattr(p, 'status', 'inactive') != 'active'):
            to_remove_ids.append(it.id)
            try:
                removed_total += float(it.price_at_time) * int(it.quantity)
            except Exception:
                pass

    if not to_remove_ids:
        flash('No removed/inactive products found in this order.', 'info')
        return redirect(url_for('admin_orders'))

    # Delete the items
    OrderItem.query.filter(OrderItem.id.in_(to_remove_ids)).delete(synchronize_session=False)

    # Recalculate order or delete if empty
    remaining = OrderItem.query.filter_by(order_id=order.id).count()
    if remaining == 0:
        # Clean linked artifacts then delete order
        QRScanLog.query.filter_by(order_id=order.id).delete(synchronize_session=False)
        OrderLabel.query.filter_by(order_id=order.id).delete(synchronize_session=False)
        ReturnRequest.query.filter_by(order_id=order.id).delete(synchronize_session=False)
        RiderChatMessage.query.filter_by(order_id=order.id).delete(synchronize_session=False)
        WalletTransaction.query.filter_by(order_id=order.id).delete(synchronize_session=False)
        db.session.delete(order)
        db.session.commit()
        log_admin_action('Order Deleted (clean removed items)', f'Order ID {order_id} deleted after removing unavailable products')
        flash(f'Order #{order_id} deleted because all items were unavailable.', 'warning')
        return redirect(url_for('admin_orders'))

    # Adjust total
    try:
        order.total_amount = max(0.0, float(order.total_amount) - removed_total)
    except Exception:
        pass
    db.session.commit()

    log_admin_action('Order Cleaned (removed items)', f'Removed {len(to_remove_ids)} unavailable items from Order ID {order_id}; -₱{removed_total:.2f}')
    flash(f'Removed {len(to_remove_ids)} unavailable item(s) from Order #{order_id}.', 'success')
    return redirect(url_for('admin_orders'))


@app.route('/admin/order-details/<int:order_id>')
@admin_required
def admin_order_details(order_id):
    order = Order.query.get_or_404(order_id)
    badge_counts = get_admin_badge_counts()
    return render_template('admin/order_details.html', order=order, **badge_counts)

@app.route('/admin/bulk-update-orders', methods=['POST'])
@admin_required
def bulk_update_orders():
    order_ids = request.form.getlist('order_ids')
    new_status = request.form.get('new_status')
    
    if not order_ids or not new_status:
        flash('Please select orders and a status.', 'error')
        return redirect(url_for('admin_orders'))
    
    updated_count = 0
    for order_id in order_ids:
        order = Order.query.get(order_id)
        if order:
            order.status = new_status
            order.updated_at = datetime.utcnow()
            updated_count += 1
    
    db.session.commit()
    log_admin_action('Bulk Order Status Update', f'Updated {updated_count} orders to {new_status}')
    flash(f'Successfully updated {updated_count} orders to {new_status}.', 'success')
    return redirect(url_for('admin_orders'))

@app.route('/admin/print-waybill/<int:order_id>')
@admin_required
def print_waybill(order_id):
    order = Order.query.get_or_404(order_id)
    badge_counts = get_admin_badge_counts()
    return render_template('admin/waybill.html', order=order, **badge_counts)

@app.route('/admin/bulk-print-waybills', methods=['POST'])
@admin_required
def bulk_print_waybills():
    order_ids = request.form.getlist('order_ids')
    
    if not order_ids:
        flash('Please select orders to print waybills.', 'error')
        return redirect(url_for('admin_orders'))
    
    orders = Order.query.filter(Order.id.in_(order_ids)).all()
    return render_template('admin/bulk_waybills.html', orders=orders)

@app.route('/admin/refund-order/<int:order_id>')
@admin_required
def refund_order(order_id):
    order = Order.query.get_or_404(order_id)
    order.payment_status = 'refunded'
    order.status = 'cancelled'
    db.session.commit()
    log_admin_action('Order Refunded', f'Order ID: {order.id}, Amount: ${order.total_amount}')
    flash(f'Order #{order.id} has been refunded.', 'success')
    return redirect(url_for('admin_orders'))

@app.route('/admin/cancel-order/<int:order_id>')
@admin_required
def cancel_order_admin(order_id):
    order = Order.query.get_or_404(order_id)
    
    # 🎯 RULE 2: RETURN STOCK ONLY IF CANCELLED BEFORE PROCESSING
    # Restore stock for each item ONLY if order was not processed yet
    original_status = order.status
    if original_status in ['pending', 'to_pay'] and not order.stock_deducted:
        # No need to restore stock since it was never deducted
        app.logger.info(f'Admin cancelled Order {order.id}: No stock to restore (stock was never deducted)')
    elif original_status in ['pending', 'to_pay'] and order.stock_deducted:
        # This case handles old orders where stock was deducted during creation
        for item in order.items:
            product = Product.query.get(item.product_id)
            if product:
                product.stock += item.quantity
                
                # Emit real-time stock update
                try:
                    available_stock = get_available_stock(product.id)
                    socketio.emit('product_stock_update', {
                        'product_id': product.id,
                        'stock': available_stock,
                        'available_stock': available_stock
                    }, broadcast=True)
                except Exception:
                    pass
                
                app.logger.info(f'Admin cancelled Order {order.id}: Stock restored for Product {product.id} (+{item.quantity}) => {product.stock}')
        
        order.stock_deducted = False
    else:
        app.logger.info(f'Admin cancelled Order {order.id}: No stock returned (status: {original_status}, stock_deducted: {order.stock_deducted})')
    
    order.status = 'cancelled'
    if order.payment_status == 'paid':
        order.payment_status = 'refunded'
    
    db.session.commit()
    log_admin_action('Order Cancelled', f'Order ID: {order.id} cancelled by admin')
    
    if original_status in ['pending', 'to_pay']:
        flash(f'Order #{order.id} has been cancelled.', 'warning')
    else:
        flash(f'Order #{order.id} has been cancelled.', 'warning')
    
    return redirect(url_for('admin_orders'))

@app.route('/admin/update-order-status/<int:order_id>/<status>')
@admin_required
def update_order_status_admin(order_id, status):
    order = Order.query.get_or_404(order_id)
    
    valid_statuses = ['pending', 'processing', 'ready_for_pickup', 'to_ship', 'delivered', 'completed', 'returned', 'cancelled']
    if status in valid_statuses:
        order.status = status
        order.updated_at = datetime.utcnow()
        db.session.commit()
        log_admin_action('Order Status Updated', f'Order ID: {order.id} status changed to {status}')
        flash(f'Order #{order.id} status updated to {status}.', 'success')
    
    return redirect(url_for('admin_orders'))

@app.route('/admin/payments')
@admin_required
def admin_payments():
    payment_status = request.args.get('payment_status', 'all')
    
    query = Order.query.join(User, Order.buyer_id == User.id)
    
    if payment_status != 'all':
        query = query.filter(Order.payment_status == payment_status)
    
    payments = query.order_by(Order.created_at.desc()).all()
    total_revenue = db.session.query(db.func.sum(Order.total_amount)).filter_by(payment_status='paid').scalar() or 0
    pending_amount = db.session.query(db.func.sum(Order.total_amount)).filter_by(payment_status='pending').scalar() or 0
    
    log_admin_action('Payments List Accessed')
    badge_counts = get_admin_badge_counts()
    return render_template('admin/payments.html', payments=payments, payment_status=payment_status, 
                         total_revenue=total_revenue, pending_amount=pending_amount,
                         **badge_counts)

@app.route('/admin/assign-rider', methods=['POST'])
@admin_required
def admin_assign_rider():
    try:
        order_id = int(request.form.get('order_id', '0'))
        rider_user_id = int(request.form.get('rider_user_id', '0'))
    except ValueError:
        flash('Invalid parameters.', 'danger')
        return redirect(request.referrer or url_for('admin_orders'))

    order = Order.query.get_or_404(order_id)
    rider = User.query.get(rider_user_id)
    if not rider or rider.role != 'rider':
        flash('Selected user is not a rider.', 'danger')
        return redirect(request.referrer or url_for('admin_orders'))

    order.picked_up_by = rider_user_id
    if order.status == 'ready_for_pickup':
        order.status = 'to_ship'
    db.session.commit()
    try:
        push_notification(rider_user_id, f'Order #{order.id} has been assigned to you.')
        push_notification(order.buyer_id, f'Rider was assigned for Order #{order.id}.')
        for sid in _order_seller_ids(order):
            push_notification(sid, f'Rider assigned for Order #{order.id}.')
    except Exception:
        pass
    flash('Rider assigned successfully.', 'success')
    return redirect(request.referrer or url_for('admin_orders'))


@app.route('/admin/mark-payment-paid/<int:payment_id>')
@admin_required
def mark_payment_paid(payment_id):
    order = Order.query.get_or_404(payment_id)
    order.payment_status = 'paid'
    order.updated_at = datetime.utcnow()
    db.session.commit()
    log_admin_action('Payment Status Updated', f'Payment ID: {payment_id} marked as paid')
    flash(f'Transaction TXN-{payment_id} has been marked as paid.', 'success')
    return redirect(url_for('admin_payments'))

@app.route('/admin/mark-payment-failed/<int:payment_id>')
@admin_required
def mark_payment_failed(payment_id):
    order = Order.query.get_or_404(payment_id)
    
    # Store original status before changing it
    original_status = order.status
    
    # 🎯 RULE 2: RETURN STOCK ONLY IF PAYMENT FAILED BEFORE PROCESSING
    # Restore stock for failed payments ONLY if order was not processed yet
    original_status = order.status
    if original_status in ['pending', 'to_pay'] and not order.stock_deducted:
        # No need to restore stock since it was never deducted
        app.logger.info(f'Payment failed for Order {order.id}: No stock to restore (stock was never deducted)')
    elif original_status in ['pending', 'to_pay'] and order.stock_deducted:
        # This case handles old orders where stock was deducted during creation
        for item in order.items:
            product = Product.query.get(item.product_id)
            if product:
                product.stock += item.quantity
                
                # Emit real-time stock update
                try:
                    available_stock = get_available_stock(product.id)
                    socketio.emit('product_stock_update', {
                        'product_id': product.id,
                        'stock': available_stock,
                        'available_stock': available_stock
                    }, broadcast=True)
                except Exception:
                    pass
                
                app.logger.info(f'Payment failed for Order {order.id}: Stock restored for Product {product.id} (+{item.quantity}) => {product.stock}')
        
        order.stock_deducted = False
    else:
        app.logger.info(f'Payment failed for Order {order.id}: No stock returned (status: {original_status}, stock_deducted: {order.stock_deducted})')
    
    order.payment_status = 'failed'
    order.status = 'cancelled'
    order.updated_at = datetime.utcnow()
    
    db.session.commit()
    log_admin_action('Payment Status Updated', f'Payment ID: {payment_id} marked as failed')
    
    if original_status in ['pending', 'to_pay']:
        flash(f'Transaction TXN-{payment_id} has been marked as failed.', 'warning')
    else:
        flash(f'Transaction TXN-{payment_id} has been marked as failed.', 'warning')
    
    return redirect(url_for('admin_payments'))

@app.route('/admin/process-refund/<int:payment_id>')
@admin_required
def process_refund_payment(payment_id):
    order = Order.query.get_or_404(payment_id)
    order.payment_status = 'refunded'
    order.status = 'cancelled'
    order.updated_at = datetime.utcnow()
    db.session.commit()
    log_admin_action('Payment Refunded', f'Payment ID: {payment_id} refunded')
    flash(f'Transaction TXN-{payment_id} has been refunded successfully.', 'success')
    return redirect(url_for('admin_payments'))

@app.route('/admin/download-receipt/<int:payment_id>')
@admin_required
def download_receipt(payment_id):
    order = Order.query.get_or_404(payment_id)
    log_admin_action('Receipt Downloaded', f'Receipt for Payment ID: {payment_id} downloaded')
    # Here you would generate and return a PDF receipt
    flash(f'Receipt download for TXN-{payment_id} would be implemented here.', 'info')
    return redirect(url_for('admin_payments'))


# ... (existing code)

@app.route('/admin/reports')
@admin_required
def admin_reports():
    """Admin analytics dashboard with basic date filtering.

    The same filters are also forwarded to the export endpoints so exports
    match what the admin is currently viewing.
    """
    from datetime import datetime, timedelta
    from sqlalchemy import extract, func

    # --- Read filter parameters from query string ---
    report_type = request.args.get('report_type', 'monthly')
    start_date_str = request.args.get('start_date', '')
    end_date_str = request.args.get('end_date', '')

    start_date = None
    end_date = None
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        except ValueError:
            start_date = None
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        except ValueError:
            end_date = None

    now = datetime.utcnow()
    # Default window based on report_type if dates not provided
    if not start_date:
        if report_type == 'daily':
            start_date = now - timedelta(days=1)
        elif report_type == 'weekly':
            start_date = now - timedelta(days=7)
        elif report_type == 'yearly':
            start_date = now - timedelta(days=365)
        else:  # monthly (default)
            start_date = now - timedelta(days=180)
    if not end_date:
        end_date = now

    # Base query for PAID orders in the selected date range
    paid_query = Order.query.filter(Order.payment_status == 'paid')
    if start_date:
        paid_query = paid_query.filter(Order.created_at >= start_date)
    if end_date:
        paid_query = paid_query.filter(Order.created_at < end_date + timedelta(days=1))

    # --- Sales Analytics ---
    total_sales = paid_query.with_entities(func.sum(Order.total_amount)).scalar() or 0
    total_orders = paid_query.count()
    total_users = User.query.filter_by(status='active').count()
    total_products = Product.query.filter_by(status='active').count()

    # Time-series sales data depending on report_type
    sales_labels = []
    sales_values = []

    # For SQLite we can safely use strftime for bucketing
    if report_type == 'daily':
        # Group by day (YYYY-MM-DD)
        rows = paid_query.with_entities(
            func.strftime('%Y-%m-%d', Order.created_at).label('bucket'),
            func.sum(Order.total_amount).label('total')
        ).group_by('bucket').order_by('bucket').all()
        sales_labels = [r.bucket for r in rows]
        sales_values = [float(r.total or 0) for r in rows]
    elif report_type == 'weekly':
        # Group by ISO week (YYYY-Www)
        rows = paid_query.with_entities(
            func.strftime('%Y-W%W', Order.created_at).label('bucket'),
            func.sum(Order.total_amount).label('total')
        ).group_by('bucket').order_by('bucket').all()
        sales_labels = [r.bucket for r in rows]
        sales_values = [float(r.total or 0) for r in rows]
    elif report_type == 'yearly':
        # Group by year (YYYY)
        rows = paid_query.with_entities(
            func.strftime('%Y', Order.created_at).label('bucket'),
            func.sum(Order.total_amount).label('total')
        ).group_by('bucket').order_by('bucket').all()
        sales_labels = [r.bucket for r in rows]
        sales_values = [float(r.total or 0) for r in rows]
    else:
        # Default: group by month (YYYY-MM)
        rows = paid_query.with_entities(
            func.strftime('%Y-%m', Order.created_at).label('bucket'),
            func.sum(Order.total_amount).label('total')
        ).group_by('bucket').order_by('bucket').all()
        sales_labels = [r.bucket for r in rows]
        sales_values = [float(r.total or 0) for r in rows]

    # Top selling products within the same range
    top_products_query = paid_query.join(OrderItem).join(Product)
    top_products = top_products_query.with_entities(
        Product.name.label('name'),
        func.sum(OrderItem.quantity).label('total_sold'),
        func.sum(OrderItem.price_at_time * OrderItem.quantity).label('total_revenue')
    ).group_by(Product.id, Product.name).order_by(
        func.sum(OrderItem.quantity).desc()
    ).limit(10).all()

    # Order statistics (also scoped to the same date range)
    order_stats_query = Order.query
    if start_date:
        order_stats_query = order_stats_query.filter(Order.created_at >= start_date)
    if end_date:
        order_stats_query = order_stats_query.filter(Order.created_at < end_date + timedelta(days=1))

    order_stats = {
        'completed': order_stats_query.filter_by(status='completed').count(),
        'pending': order_stats_query.filter_by(status='pending').count(),
        'cancelled': order_stats_query.filter_by(status='cancelled').count(),
        'refunded': order_stats_query.filter(Order.payment_status == 'refunded').count()
    }

    # User growth within the selected date range
    user_growth_query = User.query
    if start_date:
        user_growth_query = user_growth_query.filter(User.created_at >= start_date)
    if end_date:
        user_growth_query = user_growth_query.filter(User.created_at < end_date + timedelta(days=1))

    user_growth = {
        'new_buyers': user_growth_query.filter_by(role='buyer').count(),
        'new_sellers': user_growth_query.filter_by(role='seller').count()
    }

    # Revenue breakdown (5% commission example)
    commission_rate = 5.0
    platform_commission = total_sales * (commission_rate / 100)
    seller_payouts = total_sales - platform_commission
    revenue_breakdown = {
        'platform_commission': platform_commission,
        'seller_payouts': seller_payouts,
        'commission_rate': commission_rate
    }

    # Top sellers by revenue in the selected range
    top_sellers_query = paid_query.join(OrderItem).join(Product).join(User, Product.seller_id == User.id)
    top_sellers_revenue_rows = top_sellers_query.with_entities(
        (User.first_name + ' ' + User.last_name).label('name'),
        func.sum(OrderItem.price_at_time * OrderItem.quantity).label('total_revenue'),
        func.count(func.distinct(Order.id)).label('total_sales')
    ).group_by(User.id).order_by(
        func.sum(OrderItem.price_at_time * OrderItem.quantity).desc()
    ).limit(10).all()

    top_sellers_list = []
    for row in top_sellers_revenue_rows:
        top_sellers_list.append({
            'name': row.name,
            'total_revenue': row.total_revenue,
            'total_sales': row.total_sales
        })

    # Traffic stats (placeholder values for now)
    traffic_stats = {
        'total_visits': '0',
        'unique_visitors': '0',
        'active_users': '0'
    }

    log_admin_action('Reports Accessed')

    # Values for date inputs
    start_date_display = start_date.strftime('%Y-%m-%d') if start_date else ''
    end_date_display = end_date.strftime('%Y-%m-%d') if end_date else ''

    return render_template(
        'admin/reports.html',
        total_sales=total_sales,
        total_orders=total_orders,
        total_users=total_users,
        total_products=total_products,
        sales_labels=sales_labels,
        sales_values=sales_values,
        top_products=top_products,
        order_stats=order_stats,
        user_growth=user_growth,
        revenue_breakdown=revenue_breakdown,
        top_sellers_revenue=top_sellers_list,
        traffic_stats=traffic_stats,
        report_type=report_type,
        start_date=start_date_display,
        end_date=end_date_display
    )



@app.route('/admin/security-settings')
@admin_required
def admin_security_settings():
    admin_profile = AdminProfile.query.filter_by(user_id=session['user_id']).first()
    return render_template('admin/security_settings.html', admin_profile=admin_profile)

@app.route('/admin/update-security', methods=['POST'])
@admin_required
def update_admin_security():
    admin_profile = AdminProfile.query.filter_by(user_id=session['user_id']).first()
    
    admin_profile.two_factor_enabled = 'two_factor' in request.form
    admin_profile.password_reset_required = 'password_reset' in request.form
    admin_profile.updated_at = datetime.utcnow()
    
    db.session.commit()
    log_admin_action('Security Settings Updated')
    flash('Security settings updated successfully!', 'success')
    return redirect(url_for('admin_security_settings'))

@app.route('/admin/activity-logs')
@admin_required
def admin_activity_logs():
    logs = AdminSecurityLog.query.join(User).order_by(AdminSecurityLog.timestamp.desc()).limit(100).all()
    return render_template('admin/activity_logs.html', logs=logs)

@app.route('/admin/notifications')
@admin_required
def admin_notifications():
    notifications = Notification.query.filter_by(user_id=session['user_id']).order_by(Notification.created_at.desc()).all()
    # Mark all as read when viewed
    Notification.query.filter_by(user_id=session['user_id'], is_read=False).update({Notification.is_read: True})
    db.session.commit()
    return render_template('admin/notifications.html', notifications=notifications)

@app.route('/admin/notifications/summary')
@admin_required
def admin_notifications_summary():
    # JSON for header badge/polling
    user_id = session['user_id']
    unread_count = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    recent = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).limit(5).all()
    return jsonify({
        'unread_count': unread_count,
        'recent': [
            {
                'id': n.id,
                'message': n.message,
                'is_read': n.is_read,
                'created_at': n.created_at.strftime('%Y-%m-%d %H:%M:%S')
            } for n in recent
        ]
    })
    


@app.route('/admin/add-rider', methods=['GET', 'POST'])
@admin_required
def admin_add_rider():
    if request.method == 'POST':
        # Get form fields
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        password = request.form['password']
        employee_id = request.form['employee_id']
        vehicle_type = request.form['vehicle_type']
        vehicle_number = request.form['vehicle_number']

        # Create User (rider)
        user = User(
            first_name=name,
            last_name="",
            email=email,
            password=password,  # hash in production
            phone=phone,
            address="",
            role="rider",
            status="active"
        )
        db.session.add(user)
        db.session.flush()  # So we can get user.id

        # Create DeliveryPersonnel record, link to User
        rider = DeliveryPersonnel(
            user_id=user.id,
            employee_id=employee_id,
            name=name,
            phone=phone,
            vehicle_type=vehicle_type,
            vehicle_number=vehicle_number,
            status="active"
        )
        db.session.add(rider)
        db.session.commit()
        flash('Rider account created!', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/add_rider.html')


# Buyer Messages Center (aggregate seller and rider chats)
@app.route('/buyer/messages')
@login_required
def buyer_messages():
    user = User.query.get(session['user_id'])
    active_role = session.get('active_role', user.role)
    if active_role != 'buyer' and user.role != 'buyer':
        flash('Access denied.', 'error')
        return redirect(url_for('index'))

    buyer_id = user.id
    # Seller conversations
    from sqlalchemy import func
    seller_rows = db.session.query(
        StoreChatMessage.seller_id.label('peer_id'),
        func.max(StoreChatMessage.created_at).label('last_at')
    ).filter(StoreChatMessage.buyer_id == buyer_id).group_by(StoreChatMessage.seller_id).all()

    seller_convos = []
    users = {u.id: u for u in User.query.filter(User.id.in_([r.peer_id for r in seller_rows])).all()}
    for r in seller_rows:
        peer = users.get(r.peer_id)
        last_msg = StoreChatMessage.query.filter_by(buyer_id=buyer_id, seller_id=r.peer_id).order_by(StoreChatMessage.created_at.desc()).first()
        unread = StoreChatMessage.query.filter_by(buyer_id=buyer_id, seller_id=r.peer_id, sender_role='seller', is_read=False).count()
        seller_convos.append({
            'peer': peer,
            'last_message': last_msg.message if last_msg else '',
            'last_at': r.last_at,
            'unread': unread
        })

    # Rider conversations
    rider_rows = db.session.query(
        RiderChatMessage.rider_id.label('peer_id'),
        func.max(RiderChatMessage.created_at).label('last_at')
    ).filter(RiderChatMessage.buyer_id == buyer_id).group_by(RiderChatMessage.rider_id).all()

    rider_convos = []
    rider_users = {u.id: u for u in User.query.filter(User.id.in_([r.peer_id for r in rider_rows])).all()}
    for r in rider_rows:
        peer = rider_users.get(r.peer_id)
        last_msg = RiderChatMessage.query.filter_by(buyer_id=buyer_id, rider_id=r.peer_id).order_by(RiderChatMessage.created_at.desc()).first()
        unread = RiderChatMessage.query.filter_by(buyer_id=buyer_id, rider_id=r.peer_id, sender_role='rider', is_read=False).count()
        # Avatar: try DeliveryPersonnel photo
        avatar = None
        try:
            rp = DeliveryPersonnel.query.filter_by(user_id=r.peer_id).first()
            avatar = rp.photo_path if rp and rp.photo_path else None
        except Exception:
            avatar = None
        rider_convos.append({
            'peer': peer,
            'last_message': last_msg.message if last_msg else '',
            'last_at': r.last_at,
            'unread': unread,
            'avatar': avatar
        })

    return render_template('buyer/messages.html', seller_convos=seller_convos, rider_convos=rider_convos)

# Remove a hero slide
@app.route('/admin/remove-hero-slide/<int:slide_id>', methods=['POST'])
@admin_required
def remove_hero_slide(slide_id):
    slide = HeroSlide.query.get_or_404(slide_id)
    # Optionally remove the image file from disk:
    try:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], slide.image_filename))
    except Exception:
        pass
    db.session.delete(slide)
    db.session.commit()
    flash('Slide removed!', 'info')
    return redirect(url_for('admin_hero_slides'))

# Update slideshow settings (duration & transition)
@app.route('/admin/update-slide-settings', methods=['POST'])
@admin_required
def update_slide_settings():
    slide_duration = request.form.get('slide_duration', 6)
    transition_duration = request.form.get('transition_duration', 0.8)
    # Save these settings - see next section for DB solution
    # Example: Save to ThemeSetting (add columns) or a separate table
    theme = ThemeSetting.query.first()
    theme.slide_duration = float(slide_duration)
    theme.transition_duration = float(transition_duration)
    db.session.commit()
    flash("Slideshow settings updated!", "success")
    return redirect(url_for('admin_hero_slides'))


@app.route('/remove-logo', methods=['POST'])
def remove_logo():
    # Only allow admin!
    if session.get('user_role') != 'admin':
        abort(403)
    # Remove the logo from ThemeSetting
    theme = ThemeSetting.query.first()
    if theme and theme.logo_filename:
        theme.logo_filename = None
        db.session.commit()
    flash('Logo removed.')
    return redirect(url_for('theme_settings'))

@app.route('/notifications/summary')
@login_required
def notifications_summary():
    """Return counts used by global badges (notifications, messages, role-specific)."""
    user_id = session['user_id']
    user = User.query.get(user_id)
    unread_count = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    recent = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).limit(5).all()

    # Chat unread count per role
    unread_chat = 0
    try:
        if user.role == 'seller' or session.get('active_role') == 'seller':
            unread_chat = StoreChatMessage.query.filter_by(seller_id=user_id, sender_role='buyer', is_read=False).count()
        elif user.role == 'buyer' or session.get('active_role') == 'buyer':
            unread_chat = StoreChatMessage.query.filter_by(buyer_id=user_id, sender_role='seller', is_read=False).count() \
                          + RiderChatMessage.query.filter_by(buyer_id=user_id, sender_role='rider', is_read=False).count()
        elif user.role == 'rider' or session.get('active_role') == 'rider':
            unread_chat = RiderChatMessage.query.filter_by(rider_id=user_id, sender_role='buyer', is_read=False).count()
    except Exception:
        unread_chat = 0

    # Seller-specific order badge
    seller_unread_orders = 0
    try:
        if user.role == 'seller' or session.get('active_role') == 'seller':
            seller_unread_orders = Notification.query.filter_by(user_id=user_id, is_read=False, type='order').count()
    except Exception:
        seller_unread_orders = 0

    # Admin pending counts
    admin_pending = None
    try:
        if user.role == 'admin':
            admin_pending = {
                'seller_applications': SellerApplication.query.filter_by(status='pending').count(),
                'rider_applications': RiderApplication.query.filter_by(status='pending').count(),
                'registrations': User.query.filter_by(status='pending').count(),
            }
    except Exception:
        admin_pending = None

    return jsonify({
        'unread_count': unread_count,
        'recent': [
            {
                'id': n.id,
                'message': n.message,
                'is_read': n.is_read,
                'created_at': n.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'image_url': getattr(n, 'image_url', None),
                'link': getattr(n, 'link', None),
                'type': getattr(n, 'type', None)
            } for n in recent
        ],
        'unread_chat_count': unread_chat,
        'seller_unread_orders_count': seller_unread_orders,
        'admin_pending': admin_pending
    })

# Mark all current user's notifications as read (used by rider dashboard UI as well)
@app.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def notifications_mark_all_read():
    try:
        Notification.query.filter_by(user_id=session['user_id'], is_read=False).update({Notification.is_read: True})
        db.session.commit()
        return jsonify({'success': True})
    except Exception:
        db.session.rollback()
        return jsonify({'success': False}), 500

@app.route('/notifications/mark-read/<int:notification_id>', methods=['POST','GET'])
@login_required
def notifications_mark_read(notification_id):
    try:
        n = Notification.query.filter_by(id=notification_id, user_id=session['user_id']).first()
        if not n:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        n.is_read = True
        db.session.commit()
        return jsonify({'success': True})
    except Exception:
        db.session.rollback()
        return jsonify({'success': False}), 500
@app.route('/test-notification')
@login_required
def test_notification():
    """Test route to create a notification for testing with live emit"""
    try:
        push_notification(session['user_id'], 'Test notification - Live badge should appear!')
    finally:
        flash('Test notification created!', 'success')
    return redirect(url_for('index'))

@app.route('/admin/export-report')
@admin_required
def admin_export_report():
    """Entry point used by the Reports page export buttons.

    Supports URLs like /admin/export-report?format=csv&detailed=true and
    forwards to the existing helpers that generate CSV/Excel/PDF.
    """
    fmt = request.args.get('format', 'csv')
    detailed = str(request.args.get('detailed', 'false')).lower() == 'true'

    if detailed:
        return export_detailed_report(fmt)
    return export_report(fmt)


@app.route('/admin/export-report/<format>')
@admin_required
def export_report(format):
    from flask import make_response
    import csv
    import io
    from datetime import datetime as dt
    from sqlalchemy import extract, func
    
    log_admin_action('Report Exported', f'Report exported in {format} format')
    
    # Gather comprehensive report data
    total_sales = db.session.query(db.func.sum(Order.total_amount)).filter_by(payment_status='paid').scalar() or 0
    total_orders = Order.query.count()
    total_users = User.query.count()
    total_products = Product.query.count()
    
    # Order status breakdown
    order_stats = {
        'completed': Order.query.filter_by(status='completed').count(),
        'pending': Order.query.filter_by(status='pending').count(),
        'processing': Order.query.filter_by(status='processing').count(),
        'shipped': Order.query.filter_by(status='shipped').count(),
        'delivered': Order.query.filter_by(status='delivered').count(),
        'cancelled': Order.query.filter_by(status='cancelled').count()
    }
    
    # Payment status breakdown
    payment_stats = {
        'paid': Order.query.filter_by(payment_status='paid').count(),
        'pending': Order.query.filter_by(payment_status='pending').count(),
        'failed': Order.query.filter_by(payment_status='failed').count(),
        'refunded': Order.query.filter_by(payment_status='refunded').count()
    }
    
    # Top selling products
    top_products = db.session.query(
        Product.name,
        func.sum(OrderItem.quantity).label('total_sold'),
        func.sum(OrderItem.price_at_time * OrderItem.quantity).label('revenue')
    ).join(OrderItem).join(Order).filter(
        Order.payment_status == 'paid'
    ).group_by(Product.id, Product.name).order_by(
        func.sum(OrderItem.quantity).desc()
    ).limit(10).all()
    
    # Recent orders
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(50).all()
    
    if format == 'csv':
        # Generate comprehensive CSV report
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow(['Kids & Baby Store - Comprehensive Admin Report'])
        writer.writerow(['Generated on:', dt.now().strftime('%B %d, %Y at %I:%M %p')])
        writer.writerow([])
        
        # Summary Statistics
        writer.writerow(['SUMMARY STATISTICS'])
        writer.writerow(['Metric', 'Value'])
        writer.writerow(['Total Sales (Paid Orders)', f'₱{total_sales:,.2f}'])
        writer.writerow(['Total Orders', total_orders])
        writer.writerow(['Total Users', total_users])
        writer.writerow(['Total Products', total_products])
        writer.writerow(['Average Order Value', f'₱{(total_sales / total_orders if total_orders > 0 else 0):,.2f}'])
        writer.writerow([])
        
        # Order Status Breakdown
        writer.writerow(['ORDER STATUS BREAKDOWN'])
        writer.writerow(['Status', 'Count', 'Percentage'])
        for status, count in order_stats.items():
            percentage = (count / total_orders * 100) if total_orders > 0 else 0
            writer.writerow([status.title(), count, f'{percentage:.1f}%'])
        writer.writerow([])
        
        # Payment Status Breakdown
        writer.writerow(['PAYMENT STATUS BREAKDOWN'])
        writer.writerow(['Status', 'Count', 'Percentage'])
        for status, count in payment_stats.items():
            percentage = (count / total_orders * 100) if total_orders > 0 else 0
            writer.writerow([status.title(), count, f'{percentage:.1f}%'])
        writer.writerow([])
        
        # Top Selling Products
        writer.writerow(['TOP 10 SELLING PRODUCTS'])
        writer.writerow(['Rank', 'Product Name', 'Quantity Sold', 'Revenue'])
        for idx, (name, qty, revenue) in enumerate(top_products, 1):
            writer.writerow([idx, name, int(qty), f'₱{revenue:,.2f}'])
        writer.writerow([])
        
        # Recent Orders
        writer.writerow(['RECENT ORDERS (Last 50)'])
        writer.writerow(['Order ID', 'Date', 'Customer', 'Total Amount', 'Payment Status', 'Order Status'])
        for order in recent_orders:
            writer.writerow([
                order.id,
                order.created_at.strftime('%Y-%m-%d %H:%M'),
                f"{order.buyer.first_name} {order.buyer.last_name}",
                f'₱{order.total_amount:,.2f}',
                order.payment_status.title(),
                order.status.title()
            ])
        
        # Create response
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename=admin_report_{dt.now().strftime("%Y%m%d_%H%M%S")}.csv'
        return response
        
    elif format == 'excel':
        try:
            import pandas as pd
            from io import BytesIO
            
            # Create Excel file with multiple comprehensive sheets
            output = BytesIO()
            
            # Summary Sheet
            summary_data = pd.DataFrame({
                'Metric': [
                    'Total Sales (Paid Orders)',
                    'Total Orders',
                    'Total Users',
                    'Total Products',
                    'Average Order Value'
                ],
                'Value': [
                    f'₱{total_sales:,.2f}',
                    total_orders,
                    total_users,
                    total_products,
                    f'₱{(total_sales / total_orders if total_orders > 0 else 0):,.2f}'
                ]
            })
            
            # Order Status Sheet
            order_status_df = pd.DataFrame([
                {'Status': status.title(), 'Count': count, 'Percentage': f'{(count / total_orders * 100 if total_orders > 0 else 0):.1f}%'}
                for status, count in order_stats.items()
            ])
            
            # Payment Status Sheet
            payment_status_df = pd.DataFrame([
                {'Status': status.title(), 'Count': count, 'Percentage': f'{(count / total_orders * 100 if total_orders > 0 else 0):.1f}%'}
                for status, count in payment_stats.items()
            ])
            
            # Top Products Sheet
            top_products_df = pd.DataFrame([
                {
                    'Rank': idx,
                    'Product Name': name,
                    'Quantity Sold': int(qty),
                    'Revenue': f'₱{revenue:,.2f}'
                }
                for idx, (name, qty, revenue) in enumerate(top_products, 1)
            ])
            
            # Recent Orders Sheet
            recent_orders_df = pd.DataFrame([
                {
                    'Order ID': order.id,
                    'Date': order.created_at.strftime('%Y-%m-%d %H:%M'),
                    'Customer': f"{order.buyer.first_name} {order.buyer.last_name}",
                    'Total Amount': f'₱{order.total_amount:,.2f}',
                    'Payment Status': order.payment_status.title(),
                    'Order Status': order.status.title()
                }
                for order in recent_orders
            ])
            
            # Write to Excel with formatting
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Write sheets
                summary_data.to_excel(writer, sheet_name='Summary', index=False)
                order_status_df.to_excel(writer, sheet_name='Order Status', index=False)
                payment_status_df.to_excel(writer, sheet_name='Payment Status', index=False)
                top_products_df.to_excel(writer, sheet_name='Top Products', index=False)
                recent_orders_df.to_excel(writer, sheet_name='Recent Orders', index=False)
                
                # Auto-adjust column widths
                for sheet_name in writer.sheets:
                    worksheet = writer.sheets[sheet_name]
                    for column in worksheet.columns:
                        max_length = 0
                        column_letter = column[0].column_letter
                        for cell in column:
                            try:
                                if len(str(cell.value)) > max_length:
                                    max_length = len(str(cell.value))
                            except:
                                pass
                        adjusted_width = min(max_length + 2, 50)
                        worksheet.column_dimensions[column_letter].width = adjusted_width
            
            response = make_response(output.getvalue())
            response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            response.headers['Content-Disposition'] = f'attachment; filename=admin_report_{dt.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            return response
            
        except ImportError:
            flash('Excel export requires pandas and openpyxl packages to be installed.', 'error')
            return redirect(url_for('admin_reports'))
        
    elif format == 'pdf':
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import inch
            from reportlab.platypus import Table, TableStyle
            from reportlab.lib import colors
            
            # Create PDF
            buffer = io.BytesIO()
            p = canvas.Canvas(buffer, pagesize=A4)
            width, height = A4
            margin = 50
            
            # Title
            p.setFont("Helvetica-Bold", 18)
            p.drawString(margin, height - 50, "Kids & Baby Store")
            p.setFont("Helvetica", 14)
            p.drawString(margin, height - 70, "Comprehensive Admin Report")
            
            # Date
            p.setFont("Helvetica", 10)
            p.drawString(margin, height - 90, f"Generated: {dt.now().strftime('%B %d, %Y at %I:%M %p')}")
            
            # Draw line
            p.line(margin, height - 100, width - margin, height - 100)
            
            y_position = height - 130
            
            # Summary Statistics
            p.setFont("Helvetica-Bold", 14)
            p.drawString(margin, y_position, "Summary Statistics")
            y_position -= 25
            
            p.setFont("Helvetica", 11)
            summary_items = [
                ("Total Sales (Paid Orders):", f"₱{total_sales:,.2f}"),
                ("Total Orders:", str(total_orders)),
                ("Total Users:", str(total_users)),
                ("Total Products:", str(total_products)),
                ("Average Order Value:", f"₱{(total_sales / total_orders if total_orders > 0 else 0):,.2f}")
            ]
            
            for label, value in summary_items:
                p.drawString(margin + 20, y_position, label)
                p.drawString(margin + 250, y_position, value)
                y_position -= 20
            
            y_position -= 10
            
            # Order Status Breakdown
            if y_position < 200:
                p.showPage()
                y_position = height - 50
            
            p.setFont("Helvetica-Bold", 14)
            p.drawString(margin, y_position, "Order Status Breakdown")
            y_position -= 25
            
            p.setFont("Helvetica", 11)
            for status, count in order_stats.items():
                percentage = (count / total_orders * 100) if total_orders > 0 else 0
                p.drawString(margin + 20, y_position, f"{status.title()}:")
                p.drawString(margin + 250, y_position, f"{count} ({percentage:.1f}%)")
                y_position -= 20
            
            y_position -= 10
            
            # Payment Status Breakdown
            if y_position < 200:
                p.showPage()
                y_position = height - 50
            
            p.setFont("Helvetica-Bold", 14)
            p.drawString(margin, y_position, "Payment Status Breakdown")
            y_position -= 25
            
            p.setFont("Helvetica", 11)
            for status, count in payment_stats.items():
                percentage = (count / total_orders * 100) if total_orders > 0 else 0
                p.drawString(margin + 20, y_position, f"{status.title()}:")
                p.drawString(margin + 250, y_position, f"{count} ({percentage:.1f}%)")
                y_position -= 20
            
            y_position -= 10
            
            # Top Selling Products
            if y_position < 300:
                p.showPage()
                y_position = height - 50
            
            p.setFont("Helvetica-Bold", 14)
            p.drawString(margin, y_position, "Top 10 Selling Products")
            y_position -= 25
            
            p.setFont("Helvetica", 10)
            p.drawString(margin + 20, y_position, "Rank")
            p.drawString(margin + 60, y_position, "Product Name")
            p.drawString(margin + 300, y_position, "Qty Sold")
            p.drawString(margin + 380, y_position, "Revenue")
            y_position -= 3
            p.line(margin, y_position, width - margin, y_position)
            y_position -= 15
            
            for idx, (name, qty, revenue) in enumerate(top_products, 1):
                if y_position < 50:
                    p.showPage()
                    y_position = height - 50
                    p.setFont("Helvetica", 10)
                
                product_name = name[:40] + '...' if len(name) > 40 else name
                p.drawString(margin + 20, y_position, str(idx))
                p.drawString(margin + 60, y_position, product_name)
                p.drawString(margin + 300, y_position, str(int(qty)))
                p.drawString(margin + 380, y_position, f"₱{revenue:,.2f}")
                y_position -= 18
            
            # Footer
            p.setFont("Helvetica-Italic", 8)
            p.drawString(margin, 30, "Kids & Baby Store - Admin Dashboard")
            p.drawString(width - margin - 100, 30, f"Page 1")
            
            p.showPage()
            p.save()
            
            buffer.seek(0)
            response = make_response(buffer.getvalue())
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'attachment; filename=admin_report_{dt.now().strftime("%Y%m%d_%H%M%S")}.pdf'
            return response
            
        except ImportError as e:
            flash(f'PDF export requires reportlab package: {str(e)}', 'error')
            return redirect(url_for('admin_reports'))
    else:
        flash('Invalid export format.', 'error')
        return redirect(url_for('admin_reports'))

@app.route('/admin/add-featured-product', methods=['GET', 'POST'])
@admin_required
def admin_add_featured_product():
    if request.method == 'POST':
        # Get form data
        name = request.form['name']
        category_id = int(request.form['category_id'])
        short_description = request.form['short_description']
        description = request.form['description']
        price = float(request.form['price'])
        sale_price = request.form.get('sale_price')
        stock = int(request.form['stock'])
        sku = request.form.get('sku', '')
        tags = request.form.get('tags', '')
        weight = request.form.get('weight')
        dimensions = request.form.get('dimensions', '')
        brand = request.form.get('brand', '')
        featured = 'featured' in request.form
        status = request.form['status']
        action = request.form.get('action', 'save')
        
        # Handle sale price
        if sale_price and float(sale_price) > 0:
            sale_price = float(sale_price)
        else:
            sale_price = None
            
        # Handle weight
        if weight and weight.isdigit():
            weight = int(weight)
        else:
            weight = None
            
        # Generate SKU if empty
        if not sku:
            import random
            sku_base = name.upper().replace(' ', '-')[:10]
            sku = f"{sku_base}-{random.randint(100, 999)}"
            
        # Handle file upload
        image_filename = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                filename = secure_filename(file.filename)
                # Add timestamp to avoid conflicts
                timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                filename = timestamp + filename
                
                if not os.path.exists(app.config['UPLOAD_FOLDER']):
                    os.makedirs(app.config['UPLOAD_FOLDER'])
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_filename = filename
        
        # Set status based on action
        if action == 'draft':
            status = 'draft'
        
        # Create new product with admin as seller
        new_product = Product(
            name=name,
            description=f"{short_description}\n\n{description}",
            price=price,
            stock=stock,
            image_filename=image_filename,
            category_id=category_id,
            seller_id=session['user_id'],  # Admin is the seller
            status=status,
            featured=featured
        )
        
        db.session.add(new_product)
        db.session.flush()  # Get product ID
        
        # Store additional product details (extend Product model or use separate table)
        # For now, we'll add them to a JSON field or description
        additional_details = {
            'sku': sku,
            'tags': tags,
            'weight': weight,
            'dimensions': dimensions,
            'brand': brand,
            'short_description': short_description,
            'sale_price': sale_price
        }
        
        # Store additional details in description for now (you could extend the model)
        full_description = f"{short_description}\n\n{description}"
        if sku:
            full_description += f"\n\nSKU: {sku}"
        if brand:
            full_description += f"\nBrand: {brand}"
        if weight:
            full_description += f"\nWeight: {weight}g"
        if dimensions:
            full_description += f"\nDimensions: {dimensions}"
        if tags:
            full_description += f"\nTags: {tags}"
        if sale_price:
            full_description += f"\nSale Price: â‚±{sale_price:.2f}"
            
        new_product.description = full_description
        
        db.session.commit()
        
        log_admin_action('Featured Product Created', f'Product "{name}" created with ID: {new_product.id}')
        
        if action == 'draft':
            flash(f'Product "{name}" saved as draft successfully!', 'info')
        else:
            flash(f'Featured product "{name}" created successfully!', 'success')
        
        return redirect(url_for('admin_dashboard'))
    
    # GET request - show form
    categories = Category.query.all()
    return render_template('admin/add_featured_product.html', categories=categories)

@app.route('/admin/export-detailed-report/<format>')
@admin_required
def export_detailed_report(format):
    from flask import make_response
    import csv
    import io
    from datetime import datetime as dt
    
    log_admin_action('Detailed Report Exported', f'Detailed report exported in {format} format')
    
    if format == 'csv':
        # Generate detailed CSV report with all data
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Kids & Baby Store - Detailed Admin Report'])
        writer.writerow(['Generated on:', dt.now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow([])
        
        # All Orders
        writer.writerow(['All Orders'])
        writer.writerow(['Order ID', 'Buyer Name', 'Total Amount', 'Status', 'Payment Status', 'Date'])
        orders = Order.query.all()
        for order in orders:
            writer.writerow([
                f'#{order.id}',
                f'{order.buyer.first_name} {order.buyer.last_name}',
                f'â‚±{order.total_amount:.2f}',
                order.status,
                order.payment_status,
                order.created_at.strftime('%Y-%m-%d %H:%M:%S')
            ])
        
        writer.writerow([])
        
        # All Products
        writer.writerow(['All Products'])
        writer.writerow(['Product ID', 'Name', 'Price', 'Stock', 'Seller', 'Status'])
        products = Product.query.all()
        for product in products:
            writer.writerow([
                f'#{product.id}',
                product.name,
                f'â‚±{product.price:.2f}',
                product.stock,
                f'{product.seller.first_name} {product.seller.last_name}',
                product.status
            ])
        
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=detailed_admin_report_{dt.now().strftime("%Y%m%d_%H%M%S")}.csv'
        return response
        
    else:
        # For Excel and PDF, use same logic as above but with more detailed data
        return export_report(format)  # Fallback to regular export for now

@app.route('/admin/change-password', methods=['POST'])
@admin_required
def change_admin_password():
    user = User.query.get(session['user_id'])
    current_password = request.form['current_password']
    new_password = request.form['new_password']
    confirm_password = request.form['confirm_password']
    
    if user.password != current_password:
        flash('Current password is incorrect.', 'error')
    elif new_password != confirm_password:
        flash('New passwords do not match.', 'error')
    else:
        # Validate new password strength
        is_valid, password_message = validate_password(new_password)
        if not is_valid:
            flash(password_message, 'error')
        else:
            user.password = new_password
            admin_profile = AdminProfile.query.filter_by(user_id=session['user_id']).first()
            if admin_profile:
                admin_profile.password_reset_required = False
                admin_profile.updated_at = datetime.utcnow()
            db.session.commit()
            log_admin_action('Password Changed', 'Admin password changed successfully')
            flash('Password changed successfully!', 'success')
    
    return redirect(url_for('admin_profile'))

@app.route('/seller')
@seller_required
def seller_dashboard():
    seller_id = session['user_id']
    products = Product.query.filter_by(seller_id=seller_id).order_by(Product.created_at.desc()).all()

    # Seller stats (delivered revenue + commissioned sales)
    stats = _compute_seller_stats(seller_id)
    total_products = len(products)
    total_orders = stats['total_orders']
    # Show delivered+completed revenue as Total Sales (real-time), and provide commissioned separately if needed
    total_sales = stats['delivered_revenue']

    # Quick 30-day summary for dashboard (orders, items, AOV, product performance, recent tx)
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    start_date = now - timedelta(days=30)
    # Base query: seller's order items in range
    q = db.session.query(OrderItem, Order, Product).join(Order).join(Product).filter(
        Product.seller_id == seller_id,
        Order.created_at >= start_date
    ).order_by(Order.created_at.desc())
    sales_rows = q.all()

    # Totals
    order_ids = []
    items_sold = 0
    paid_revenue = 0.0
    for item, order, _ in sales_rows:
        order_ids.append(order.id)
        items_sold += int(item.quantity)
        if order.payment_status == 'paid':
            paid_revenue += float(item.price_at_time) * int(item.quantity)
    unique_orders = len(set(order_ids))
    aov = (paid_revenue / unique_orders) if unique_orders else 0.0

    # Product performance top 5
    product_perf_map = {}
    for item, order, product in sales_rows:
        perf = product_perf_map.setdefault(product.id, {
            'product_id': product.id,
            'product_name': product.name,
            'product_image': product.image_filename,
            'quantity_sold': 0,
            'revenue': 0.0,
            'order_count': set(),
        })
        perf['quantity_sold'] += int(item.quantity)
        if order.payment_status == 'paid':
            perf['revenue'] += float(item.price_at_time) * int(item.quantity)
        perf['order_count'].add(order.id)
    product_performance = [
        {
            **v,
            'order_count': len(v['order_count']),
            'avg_price': (v['revenue'] / v['quantity_sold']) if v['quantity_sold'] else 0.0,
        }
        for v in product_perf_map.values()
    ]
    product_performance.sort(key=lambda x: x['revenue'], reverse=True)
    product_performance = product_performance[:5]

    # Recent transactions (last 5)
    recent_transactions = [
        {
            'order_id': order.id,
            'order_date': order.created_at,
            'product_name': product.name,
            'product_id': product.id,
            'quantity': item.quantity,
            'unit_price': float(item.price_at_time),
            'total': float(item.price_at_time) * int(item.quantity),
            'buyer_name': f"{order.buyer.first_name} {order.buyer.last_name}",
            'order_status': order.status,
            'payment_status': order.payment_status,
        }
        for item, order, product in sales_rows[:5]
    ]

    # Unread chat count for sidebar badge
    unread_chat_count = StoreChatMessage.query.filter_by(seller_id=seller_id, is_read=False, sender_role='buyer').count()

    return render_template('seller/dashboard.html',
                           products=products,
                           total_products=total_products,
                           total_orders=total_orders,
                           total_sales=total_sales,
                           status_counts=stats['status_counts'],
                           commissioned_sales=stats['commissioned_sales'],
                           unread_chat_count=unread_chat_count,
                           dash_unique_orders=unique_orders,
                           dash_items_sold=items_sold,
                           dash_aov=aov,
                           dash_product_performance=product_performance,
                           dash_recent_transactions=recent_transactions)


# ... (other imports and code above unchanged)

@app.route('/seller/add-product', methods=['GET', 'POST'])
@seller_required
def add_product():
    # Ensure schema supports video uploads
    ensure_product_video_column()
    # Compute the next auto-increment Product ID (preview only)
    next_product_id = (db.session.query(db.func.max(Product.id)).scalar() or 0) + 1

    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = float(request.form['price'])
        stock = int(request.form['stock'])
        category_id = int(request.form['category_id'])
        # Optional subcategory (keep existing behavior if not provided)
        subcategory_id = request.form.get('subcategory_id')
        if subcategory_id and subcategory_id.isdigit():
            subcategory_id = int(subcategory_id)
        else:
            subcategory_id = None

        image_filename = None
        gallery_list = []
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                filename = secure_filename(file.filename)
                filename = datetime.utcnow().strftime('%Y%m%d_%H%M%S_') + filename
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_filename = filename
        # Optional additional images (image2..image5)
        for fld in ('image2','image3','image4','image5'):
            f = request.files.get(fld)
            if f and f.filename:
                fname = secure_filename(f.filename)
                fname = datetime.utcnow().strftime('%Y%m%d_%H%M%S_') + fname
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                gallery_list.append(fname)

        # Optional product video
        video_filename = None
        if 'video' in request.files:
            v = request.files['video']
            if v and v.filename:
                vext = v.filename.rsplit('.', 1)[-1].lower() if '.' in v.filename else ''
                if vext in ALLOWED_VIDEO_EXT:
                    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'videos'), exist_ok=True)
                    vname = secure_filename(v.filename)
                    vname = datetime.utcnow().strftime('%Y%m%d_%H%M%S_') + vname
                    dest = os.path.join(app.config['UPLOAD_FOLDER'], 'videos', vname)
                    # Optional size guard for very large uploads
                    try:
                        v.stream.seek(0, os.SEEK_END)
                        size = v.stream.tell()
                        v.stream.seek(0)
                        if size <= MAX_VIDEO_BYTES:
                            v.save(dest)
                            video_filename = 'videos/' + vname
                        else:
                            flash('Video too large. Maximum 50MB allowed.', 'danger')
                    except Exception:
                        # Fallback if size check not available
                        v.save(dest)
                        video_filename = 'videos/' + vname
                else:
                    flash('Unsupported video format. Allowed: MP4, WebM, Ogg.', 'danger')

        new_product = Product(
            name=name,
            description=description,
            price=price,
            stock=stock,
            category_id=category_id,
            subcategory_id=subcategory_id,
            seller_id=session['user_id'],
            image_filename=image_filename,
            video_filename=video_filename,
            gallery=gallery_list or None,
            status='pending'
        )

        db.session.add(new_product)
        db.session.commit()  # After commit, new_product.id is the real auto-increment ID

        try:
            notify_admins(
                f"New product pending approval from {session['user_name']}: {name} (Product ID: {new_product.id})",
                type='product_pending',
                link=f'/admin/products?filter=pending&product_id={new_product.id}',
                image_url=new_product.image_filename if new_product.image_filename else None
            )
        except Exception:
            pass

        flash(f'Product submitted for review. Assigned Product ID: {new_product.id}. It will appear after admin approval.', 'info')
        return redirect(url_for('seller_dashboard'))

    # GET request
    # Get unique categories to avoid duplicates in dropdown
    all_categories = Category.query.filter_by(status='active').order_by(Category.name).all()
    # Remove duplicates by keeping only the first occurrence of each name
    seen_names = set()
    categories = []
    for cat in all_categories:
        if cat.name not in seen_names:
            seen_names.add(cat.name)
            categories.append(cat)
    subcategories = Subcategory.query.filter_by(status='active').order_by(Subcategory.name).all()  # Ensure template has this
    return render_template('seller/add_product.html',
                           categories=categories,
                           subcategories=subcategories,
                           next_product_id=next_product_id)

# ... (rest of file unchanged)

@app.route('/seller/orders')
@seller_required
def seller_orders():
    seller_id = session['user_id']
    
    # Get filter parameters
    status = request.args.get('status', 'all')
    payment_status = request.args.get('payment_status', 'all')
    search = request.args.get('search', '')
    date_range = request.args.get('date_range', 'all')
    payment_method = request.args.get('payment_method', 'all')
    
    # Build query with joins - only orders that contain products from this seller
    query = Order.query.join(OrderItem).join(Product).filter(
        Product.seller_id == seller_id
    ).distinct()
    
    # Apply filters
    if status != 'all':
        if status == 'new':
            # Show all pending orders (new orders that haven't been processed)
            query = query.filter(Order.status == 'pending')
        elif status == 'processing':
            query = query.filter(Order.status == 'processing')
        elif status == 'ready_for_pickup':
            query = query.filter(Order.status == 'ready_for_pickup')
        elif status == 'to_ship':
            query = query.filter(Order.status == 'to_ship')
        elif status == 'delivered':
            query = query.filter(Order.status == 'delivered')
        elif status == 'completed':
            query = query.filter(Order.status.in_(['completed', 'delivered']))
        elif status == 'returns':
            # Orders with return requests
            query = query.join(ReturnRequest).filter(ReturnRequest.status != 'rejected')
    
    if payment_status != 'all':
        query = query.filter(Order.payment_status == payment_status)
    
    if search:
        search_term = f'%{search}%'
        query = query.filter(
            db.or_(
                Order.id.like(search_term),
                Order.buyer_name.like(search_term),
                Order.buyer_email.like(search_term)
            )
        )
    
    if date_range != 'all':
        now = datetime.utcnow()
        if date_range == 'today':
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            query = query.filter(Order.created_at >= start)
        elif date_range == 'week':
            start = now - timedelta(days=7)
            query = query.filter(Order.created_at >= start)
        elif date_range == 'month':
            start = now - timedelta(days=30)
            query = query.filter(Order.created_at >= start)
    
    if payment_method != 'all':
        query = query.filter(Order.payment_method == payment_method)
    
    # Order by most recent first
    orders = query.order_by(Order.created_at.desc()).all()
    
    # Calculate totals
    total_orders = len(orders)
    total_revenue = 0
    pending_orders = 0
    processing_orders = 0
    completed_orders = 0
    
    for order in orders:
        # Calculate seller's revenue from this order
        seller_items = [item for item in order.items if item.product.seller_id == seller_id]
        order_revenue = sum(item.price_at_time * item.quantity for item in seller_items)
        total_revenue += order_revenue
        
        # Count by status for header badges
        if order.status == 'pending':
            pending_orders += 1
        elif order.status == 'processing':
            processing_orders += 1
        elif order.status in ['completed', 'delivered']:
            completed_orders += 1
    
    # Compute per-order seller summaries and "new" status for Manage Orders tabs
    from datetime import datetime, timedelta
    recent_cutoff = datetime.utcnow() - timedelta(hours=24)

    # Preload seen order IDs for this seller for New Orders logic
    seen_ids = {
        row.order_id for row in SellerOrderSeen.query.filter_by(seller_id=seller_id).all()
    }

    for order in orders:
        seller_items = [item for item in order.items if item.product.seller_id == seller_id]
        order.seller_total = sum(item.price_at_time * item.quantity for item in seller_items)
        order.seller_items_count = sum(item.quantity for item in seller_items)
        order.seller_items = seller_items

        # New Orders tab: pending + unseen (show all new orders regardless of processing status)
        order.is_new = (order.status == 'pending') and (order.id not in seen_ids)
        
        # Processing tab: orders being processed by seller
        order.is_processing_tab = (order.status == 'processing')
        
        # Ready for Pick Up tab
        order.is_ready_tab = (order.status == 'ready_for_pickup')
        
        # To Ship tab
        order.is_to_ship_tab = (order.status == 'to_ship')
        
        # Delivered tab
        order.is_delivered_tab = (order.status == 'delivered')
        
        # Completed tab
        order.is_completed_tab = (order.status == 'completed')
        
        # Returns tab: orders with return requests
        completed_returns = [rr for rr in order.return_requests if rr.status != 'rejected']
        order.is_returns_tab = len(completed_returns) > 0

    # Unread chat count for sidebar badge
    unread_chat_count = StoreChatMessage.query.filter_by(seller_id=seller_id, is_read=False, sender_role='buyer').count()

    # Unread order count for notification badge: recent orders without a seen record
    unread_order_count = db.session.query(Order).join(OrderItem).join(Product).filter(
        Product.seller_id == seller_id,
        Order.created_at >= recent_cutoff
    ).filter(~Order.id.in_(
        db.session.query(SellerOrderSeen.order_id).filter_by(seller_id=seller_id)
    )).distinct().count()

    return render_template('seller/orders.html', 
                         orders=orders, 
                         status=status, 
                         payment_status=payment_status,
                         search=search,
                         date_range=date_range,
                         payment_method=payment_method,
                         unread_chat_count=unread_chat_count,
                         unread_order_count=unread_order_count,
                         total_orders=total_orders,
                         total_revenue=total_revenue,
                         pending_orders=pending_orders,
                         processing_orders=processing_orders,
                         completed_orders=completed_orders)


@app.route('/seller/order/<int:order_id>')
@seller_required
def seller_order_detail(order_id):
    seller_id = session['user_id']
    order = Order.query.get_or_404(order_id)

    # Ensure this seller has items in this order
    seller_items = [item for item in order.items if item.product.seller_id == seller_id]
    if not seller_items:
        flash('You are not authorized to view this order.', 'error')
        return redirect(url_for('seller_orders'))

    seller_total = sum(item.price_at_time * item.quantity for item in seller_items)

    # Mark this order as seen for this seller
    exists = SellerOrderSeen.query.filter_by(seller_id=seller_id, order_id=order.id).first()
    if not exists:
        db.session.add(SellerOrderSeen(seller_id=seller_id, order_id=order.id))
        db.session.commit()

    # Unread chat count for sidebar badge
    unread_chat_count = StoreChatMessage.query.filter_by(seller_id=seller_id, is_read=False, sender_role='buyer').count()

    return render_template('seller/order_detail.html',
                           order=order,
                           seller_items=seller_items,
                           seller_total=seller_total,
                           unread_chat_count=unread_chat_count)

@app.route('/seller/stats/summary')
@seller_required
def seller_stats_summary():
    seller_id = session['user_id']
    stats = _compute_seller_stats(seller_id)
    return jsonify({'success': True, 'data': stats})


@app.route('/seller/sales-report')
@seller_required
def seller_sales_report():
    seller_id = session['user_id']
    
    # Get filter parameters - expanded to match order management filters
    date_range = request.args.get('date_range', '30days')
    product_filter = request.args.get('product', 'all')
    status_filter = request.args.get('status', 'all')  # Order status filter
    payment_status_filter = request.args.get('payment_status', 'paid')  # Default to paid for revenue
    payment_method = request.args.get('payment_method', 'all')
    
    # Date range filtering
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    start_date = None
    
    if date_range == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_range == '7days':
        start_date = now - timedelta(days=7)
    elif date_range == '30days':
        start_date = now - timedelta(days=30)
    elif date_range == '90days':
        start_date = now - timedelta(days=90)
    elif date_range == 'year':
        start_date = now - timedelta(days=365)
    # 'all' means no date filter
    
    # Base query: get all order items for this seller's products
    query = db.session.query(
        OrderItem,
        Order,
        Product
    ).join(Order).join(Product).filter(
        Product.seller_id == seller_id
    )
    
    # Apply payment status filter
    if payment_status_filter != 'all':
        query = query.filter(Order.payment_status == payment_status_filter)
    
    # Apply order status filter
    if status_filter != 'all':
        query = query.filter(Order.status == status_filter)
    
    # Apply payment method filter
    if payment_method != 'all':
        query = query.filter(Order.payment_method == payment_method)
    
    if start_date:
        query = query.filter(Order.created_at >= start_date)
    
    if product_filter != 'all':
        query = query.filter(Product.id == int(product_filter))
    
    # Get all sales data
    sales_data = query.order_by(Order.created_at.desc()).all()
    
    # Calculate summary statistics (legacy, paid order-based)
    legacy_revenue = sum(item.price_at_time * item.quantity for item, order, _ in sales_data if order.payment_status == 'paid')
    
    # Wallet commissions (final revenue after buyer confirms)
    wallet_q = WalletTransaction.query.filter_by(user_id=seller_id, type='credit', source='order_commission')
    if start_date:
        wallet_q = wallet_q.filter(WalletTransaction.created_at >= start_date)
    total_revenue = float(wallet_q.with_entities(db.func.coalesce(db.func.sum(WalletTransaction.amount), 0.0)).scalar() or 0.0)
    total_orders = len(set(order.id for _, order, _ in sales_data))
    total_items_sold = sum(item.quantity for item, _, _ in sales_data)
    paid_orders_count = len(set(order.id for _, order, _ in sales_data if order.payment_status == 'paid'))
    pending_orders_count = len(set(order.id for _, order, _ in sales_data if order.payment_status == 'pending'))
    
    # Order status breakdown
    status_breakdown = {
        'pending': len(set(order.id for _, order, _ in sales_data if order.status == 'pending')),
        'processing': len(set(order.id for _, order, _ in sales_data if order.status == 'processing')),
        'shipped': len(set(order.id for _, order, _ in sales_data if order.status == 'shipped')),
        'completed': len(set(order.id for _, order, _ in sales_data if order.status == 'completed')),
        'cancelled': len(set(order.id for _, order, _ in sales_data if order.status == 'cancelled'))
    }
    
    # Payment status breakdown (kept for reference)
    payment_breakdown = {
        'paid': paid_orders_count,
        'pending': pending_orders_count,
        'failed': len(set(order.id for _, order, _ in sales_data if order.payment_status == 'failed')),
        'refunded': len(set(order.id for _, order, _ in sales_data if order.payment_status == 'refunded'))
    }
    
    # Payment method breakdown
    payment_method_breakdown = {}
    for item, order, product in sales_data:
        method = order.payment_method
        if method not in payment_method_breakdown:
            payment_method_breakdown[method] = {'count': 0, 'revenue': 0}
        if order.payment_status == 'paid':
            payment_method_breakdown[method]['revenue'] += item.price_at_time * item.quantity
        # Count unique orders per method
    for _, order, _ in sales_data:
        method = order.payment_method
        if method in payment_method_breakdown:
            payment_method_breakdown[method]['count'] = len(set(o.id for _, o, _ in sales_data if o.payment_method == method))
    
    # Product performance analysis
    product_stats = {}
    for item, order, product in sales_data:
        if product.id not in product_stats:
            product_stats[product.id] = {
                'product': product,
                'quantity_sold': 0,
                'revenue': 0,
                'order_count': set(),
                'paid_revenue': 0,
                'pending_revenue': 0
            }
        product_stats[product.id]['quantity_sold'] += item.quantity
        product_stats[product.id]['revenue'] += item.price_at_time * item.quantity
        product_stats[product.id]['order_count'].add(order.id)
        
        # Track revenue by payment status
        if order.payment_status == 'paid':
            product_stats[product.id]['paid_revenue'] += item.price_at_time * item.quantity
        elif order.payment_status == 'pending':
            product_stats[product.id]['pending_revenue'] += item.price_at_time * item.quantity
    
    # Convert to list and sort by revenue
    product_performance = [
        {
            'product_id': pid,
            'product_name': stats['product'].name,
            'product_image': stats['product'].image_filename,
            'quantity_sold': stats['quantity_sold'],
            'revenue': stats['revenue'],
            'paid_revenue': stats['paid_revenue'],
            'pending_revenue': stats['pending_revenue'],
            'order_count': len(stats['order_count']),
            'avg_price': stats['revenue'] / stats['quantity_sold'] if stats['quantity_sold'] > 0 else 0,
            'current_stock': stats['product'].stock
        }
        for pid, stats in product_stats.items()
    ]
    product_performance.sort(key=lambda x: x['paid_revenue'], reverse=True)
    
    # Daily sales chart data (last 30 days or selected range)
    daily_sales = {}
    for item, order, product in sales_data:
        date_key = order.created_at.strftime('%Y-%m-%d')
        if date_key not in daily_sales:
            daily_sales[date_key] = {
                'date': date_key, 
                'revenue': 0, 
                'paid_revenue': 0,
                'orders': set(), 
                'items': 0,
                'paid_orders': set()
            }
        daily_sales[date_key]['revenue'] += item.price_at_time * item.quantity
        if order.payment_status == 'paid':
            daily_sales[date_key]['paid_revenue'] += item.price_at_time * item.quantity
            daily_sales[date_key]['paid_orders'].add(order.id)
        daily_sales[date_key]['orders'].add(order.id)
        daily_sales[date_key]['items'] += item.quantity
    
    # Convert to sorted list
    daily_sales_list = [
        {
            'date': data['date'],
            'revenue': data['revenue'],
            'paid_revenue': data['paid_revenue'],
            'order_count': len(data['orders']),
            'paid_order_count': len(data['paid_orders']),
            'items_sold': data['items']
        }
        for date_key, data in daily_sales.items()
    ]
    daily_sales_list.sort(key=lambda x: x['date'])
    
    # Recent transactions (detailed order items) - matches what's in order management
    recent_transactions = [
        {
            'order_id': order.id,
            'order_date': order.created_at,
            'product_name': product.name,
            'product_id': product.id,
            'quantity': item.quantity,
            'unit_price': item.price_at_time,
            'total': item.price_at_time * item.quantity,
            'buyer_name': f"{order.buyer.first_name} {order.buyer.last_name}",
            'buyer_email': order.buyer.email,
            'buyer_phone': order.buyer.phone,
            'order_status': order.status,
            'payment_status': order.payment_status,
            'payment_method': order.payment_method,
            'shipping_address': order.shipping_address,
            'tracking_number': order.tracking_number if hasattr(order, 'tracking_number') else None,
            'stock_deducted': order.stock_deducted if hasattr(order, 'stock_deducted') else False
        }
        for item, order, product in sales_data[:100]  # Increased to 100 for better analysis
    ]
    
    # Get all seller's products for filter dropdown (including inactive for historical data)
    seller_products = Product.query.filter_by(seller_id=seller_id).order_by(Product.name).all()
    
    # Calculate average order value (only paid orders)
    avg_order_value = total_revenue / paid_orders_count if paid_orders_count > 0 else 0
    
    # Potential revenue (pending payments)
    potential_revenue = sum(item.price_at_time * item.quantity for item, order, _ in sales_data if order.payment_status == 'pending')
    
    return render_template('seller/sales_report.html',
                         total_revenue=total_revenue,
                         total_orders=total_orders,
                         paid_orders_count=paid_orders_count,
                         pending_orders_count=pending_orders_count,
                         total_items_sold=total_items_sold,
                         avg_order_value=avg_order_value,
                         potential_revenue=potential_revenue,
                         status_breakdown=status_breakdown,
                         payment_breakdown=payment_breakdown,
                         payment_method_breakdown=payment_method_breakdown,
                         product_performance=product_performance,
                         daily_sales=daily_sales_list,
                         recent_transactions=recent_transactions,
                         seller_products=seller_products,
                         date_range=date_range,
                         product_filter=product_filter,
                         status_filter=status_filter,
                         payment_status_filter=payment_status_filter,
                         payment_method=payment_method,
                         now=datetime.utcnow)

@app.route('/seller/notifications')
@seller_required
def seller_notifications():
    notifications = Notification.query.filter_by(user_id=session['user_id']).order_by(Notification.created_at.desc()).all()
    Notification.query.filter_by(user_id=session['user_id'], is_read=False).update({Notification.is_read: True})
    db.session.commit()
    return render_template('seller/notifications.html', notifications=notifications)

@app.route('/buyer/notifications')
@login_required
def buyer_notifications():
    # Only allow buyers to access this
    user = User.query.get(session['user_id'])
    active_role = session.get('active_role', user.role)
    if active_role != 'buyer' and user.role != 'buyer':
        flash('Access denied.', 'error')
        return redirect(url_for('index'))
    
    notifications = Notification.query.filter_by(user_id=session['user_id']).order_by(Notification.created_at.desc()).all()

    # Build enriched entries with order info when possible
    enriched = []
    for n in notifications:
        order = None
        first_item = None
        tracking = None
        status = None
        try:
            import re as _re
            m = _re.search(r"order\s*#(\d+)", n.message, _re.IGNORECASE)
            if not m:
                m = _re.search(r"Order\s*(\d+)", n.message, _re.IGNORECASE)
            if m:
                oid = int(m.group(1))
                order = Order.query.filter_by(id=oid, buyer_id=session['user_id']).first()
        except Exception:
            order = None
        if order:
            tracking = getattr(order, 'tracking_number', None)
            status = order.status
            try:
                first_item = order.items[0] if order.items else None
            except Exception:
                first_item = None
        # Resolve actor avatar/name for rich chat notifications
        actor = getattr(n, 'actor', None)
        actor_name = None
        actor_avatar = None
        if actor:
            actor_name = f"{actor.first_name} {actor.last_name}"
            # Try DeliveryPersonnel photo for riders
            try:
                rp = DeliveryPersonnel.query.filter_by(user_id=actor.id).first()
                if rp and rp.photo_path:
                    actor_avatar = rp.photo_path
            except Exception:
                actor_avatar = None
        enriched.append({
            'notification': n,
            'order': order,
            'first_item': first_item,
            'tracking': tracking,
            'status': status,
            'actor_name': actor_name,
            'actor_avatar': actor_avatar
        })

    # Mark all as read when viewed
    Notification.query.filter_by(user_id=session['user_id'], is_read=False).update({Notification.is_read: True})
    db.session.commit()
    return render_template('buyer_notifications.html', notifications=notifications, enriched_notifications=enriched)


@app.route('/seller/products/edit/<int:product_id>', methods=['GET', 'POST'])
@seller_required
def seller_edit_product(product_id):
    ensure_product_video_column()
    product = Product.query.filter_by(id=product_id, seller_id=session['user_id']).first_or_404()
    if request.method == 'POST':
        product.name = request.form['name']
        product.description = request.form['description']
        product.price = float(request.form['price'])
        # Stock is no longer updated here - sellers must use restock requests
        # product.stock = int(request.form['stock'])  # REMOVED - use restock requests instead
        product.category_id = int(request.form['category_id'])
        # Optional image update
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                filename = secure_filename(file.filename)
                filename = datetime.utcnow().strftime('%Y%m%d_%H%M%S_') + filename
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                product.image_filename = filename
        
        # Handle gallery images (image2, image3, image4, image5)
        gallery_images = []
        for i in range(2, 6):
            field_name = f'image{i}'
            if field_name in request.files:
                file = request.files[field_name]
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    filename = datetime.utcnow().strftime('%Y%m%d_%H%M%S_') + filename
                    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    gallery_images.append(filename)
        
        # Update gallery if new images were uploaded
        if gallery_images:
            # Merge with existing gallery images, but prioritize new ones
            existing_gallery = product.gallery or []
            # Replace existing images with new ones in the same positions
            for i, new_image in enumerate(gallery_images):
                index = i  # 0-based index for gallery array
                if index < len(existing_gallery):
                    existing_gallery[index] = new_image
                else:
                    existing_gallery.append(new_image)
            product.gallery = existing_gallery
        # Optional video update
        if 'video' in request.files:
            v = request.files['video']
            if v and v.filename:
                vext = v.filename.rsplit('.', 1)[-1].lower() if '.' in v.filename else ''
                if vext in ALLOWED_VIDEO_EXT:
                    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'videos'), exist_ok=True)
                    vname = secure_filename(v.filename)
                    vname = datetime.utcnow().strftime('%Y%m%d_%H%M%S_') + vname
                    v.save(os.path.join(app.config['UPLOAD_FOLDER'], 'videos', vname))
                    product.video_filename = 'videos/' + vname
                else:
                    flash('Unsupported video format. Allowed: MP4, WebM, Ogg.', 'danger')
        # Status logic depending on previous state
        if product.status == 'active':
            product.status = 'pending'  # Re-review after edits
        elif product.status in ['pending', 'rejected', 'inactive']:
            product.status = 'pending'
        db.session.commit()
        # Notify seller (self)
        db.session.add(Notification(user_id=product.seller_id, message=f'Your product {product.name} was updated.'))
        db.session.commit()
        flash('Product updated successfully! Note: Stock quantity changes require admin approval through the restock request system.', 'info')
        return redirect(url_for('seller_products'))
    categories = Category.query.all()
    # Compute what the seller is allowed to do based on status
    editable = True  # All statuses editable per your rules
    status_note = None
    if product.status == 'active':
        status_note = 'Editing will send the product for admin review again.'
    elif product.status == 'rejected':
        status_note = 'Rejected. You can edit and resubmit.'
    elif product.status == 'pending':
        status_note = 'Pending approval. You can still edit it.'
    return render_template('seller/edit_product.html', product=product, categories=categories, editable=editable, status_note=status_note)

@app.route('/seller/products/delete/<int:product_id>', methods=['POST'])
@seller_required
def seller_delete_product(product_id):
    # Ensure the product belongs to the seller
    product = Product.query.filter_by(id=product_id, seller_id=session['user_id']).first_or_404()

    # Hard-delete the product and clean related data and orders
    stats = _delete_products_by_ids([product.id])
    db.session.commit()

    # Notify admins of deletion
    try:
        notify_admins(f'Seller permanently deleted product: {product.name}')
    except Exception:
        pass
    flash('Product permanently deleted and removed from any orders.', 'success')
    return redirect(url_for('seller_products'))

@app.route('/seller/products')
@seller_required
def seller_products():
    seller_id = session['user_id']
    products = Product.query.filter_by(seller_id=seller_id).order_by(Product.created_at.desc()).all()
    categories = {c.id: c.name for c in Category.query.all()}
    return render_template('seller/products.html', products=products, categories=categories, get_available_stock=get_available_stock)

@app.route('/seller/restock/<int:product_id>', methods=['POST'])
@seller_required
def seller_restock_product(product_id):
    """Submit restock request to admin"""
    # Ensure the product belongs to the seller
    product = Product.query.filter_by(id=product_id, seller_id=session['user_id']).first_or_404()
    
    try:
        # Get restock quantity from form
        restock_quantity = int(request.form.get('restock_quantity', 1))
        
        if restock_quantity <= 0:
            flash('Restock quantity must be greater than 0.', 'error')
            return redirect(url_for('seller_products'))
        
        # Check if there's already a pending restock request
        existing_request = RestockRequest.query.filter_by(
            product_id=product_id, 
            seller_id=session['user_id'],
            status='pending'
        ).first()
        
        if existing_request:
            flash(f'You already have a pending restock request for "{product.name}". Please wait for admin approval.', 'warning')
            return redirect(url_for('seller_products'))
        
        # Create restock request
        restock_request = RestockRequest(
            product_id=product_id,
            seller_id=session['user_id'],
            requested_quantity=restock_quantity
        )
        
        db.session.add(restock_request)
        db.session.commit()
        
        flash(f'Restock request for "{product.name}" ({restock_quantity} items) has been submitted to admin for approval.', 'success')
        
        # Log the restock request
        app.logger.info(f"Seller {session['user_id']} submitted restock request for product {product_id}: {restock_quantity} units")
        
    except ValueError:
        flash('Invalid restock quantity.', 'error')
    except Exception as e:
        app.logger.error(f"Error submitting restock request for product {product_id}: {e}")
        flash('An error occurred while submitting the restock request.', 'error')
    
    return redirect(url_for('seller_products'))

@app.route('/seller/cancel-restock/<int:product_id>', methods=['POST'])
@seller_required
def seller_cancel_restock(product_id):
    """Cancel pending restock request"""
    # Ensure the product belongs to the seller
    product = Product.query.filter_by(id=product_id, seller_id=session['user_id']).first_or_404()
    
    try:
        # Find pending restock request
        restock_request = RestockRequest.query.filter_by(
            product_id=product_id, 
            seller_id=session['user_id'],
            status='pending'
        ).first()
        
        if not restock_request:
            flash('No pending restock request found for this product.', 'error')
            return redirect(url_for('seller_products'))
        
        db.session.delete(restock_request)
        db.session.commit()
        
        flash(f'Restock request for "{product.name}" has been cancelled.', 'success')
        
        # Log the cancellation
        app.logger.info(f"Seller {session['user_id']} cancelled restock request for product {product_id}")
        
    except Exception as e:
        app.logger.error(f"Error cancelling restock request for product {product_id}: {e}")
        flash('An error occurred while cancelling the restock request.', 'error')
    
    return redirect(url_for('seller_products'))

@app.route('/admin/restock-requests')
@admin_required
def admin_restock_requests():
    """Admin page to view and manage restock requests"""
    restock_requests = RestockRequest.query.order_by(RestockRequest.created_at.desc()).all()
    
    # Add product and seller information
    requests_data = []
    for req in restock_requests:
        requests_data.append({
            'id': req.id,
            'product': req.product,
            'seller': req.seller,
            'requested_quantity': req.requested_quantity,
            'approved_quantity': req.approved_quantity,
            'status': req.status,
            'created_at': req.created_at,
            'processed_at': req.processed_at,
            'admin_notes': req.admin_notes
        })
    
    # Count pending requests for badge
    pending_count = RestockRequest.query.filter_by(status='pending').count()
    
    badge_counts = get_admin_badge_counts()
    return render_template('admin/restock_requests.html', 
                         restock_requests=requests_data,
                         **badge_counts)

@app.route('/admin/approve-restock/<int:request_id>', methods=['POST'])
@admin_required
def admin_approve_restock(request_id):
    """Approve a restock request"""
    restock_request = RestockRequest.query.get_or_404(request_id)
    
    try:
        # Get approved quantity from form
        approved_quantity = int(request.form.get('approved_quantity', restock_request.requested_quantity))
        admin_notes = request.form.get('admin_notes', '')
        
        if approved_quantity <= 0:
            flash('Approved quantity must be greater than 0.', 'error')
            return redirect(url_for('admin_restock_requests'))
        
        # Update restock request
        restock_request.status = 'approved'
        restock_request.approved_quantity = approved_quantity
        restock_request.processed_at = datetime.utcnow()
        restock_request.processed_by = session['user_id']
        restock_request.admin_notes = admin_notes
        
        # Update product stock
        product = restock_request.product
        old_stock = product.stock
        product.stock += approved_quantity
        product.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Calculate available stock after approval
        available_stock = get_available_stock(product.id)
        
        # Emit real-time stock update to all users
        try:
            socketio.emit('product_stock_update', {
                'product_id': product.id,
                'stock': available_stock,
                'available_stock': available_stock
            }, broadcast=True)
            
            # Notify seller
            push_notification(restock_request.seller_id, 
                           f'Your restock request for "{product.name}" has been approved! {approved_quantity} items added.')
            
        except Exception as e:
            app.logger.error(f"Socket.IO emit error: {e}")
        
        flash(f'Restock request for "{product.name}" approved! Added {approved_quantity} items to inventory.', 'success')
        
        # Log the approval
        app.logger.info(f"Admin {session['user_id']} approved restock request {request_id} for product {product.id}: {approved_quantity} units")
        
    except ValueError:
        flash('Invalid approved quantity.', 'error')
    except Exception as e:
        app.logger.error(f"Error approving restock request {request_id}: {e}")
        flash('An error occurred while approving the restock request.', 'error')
    
    return redirect(url_for('admin_restock_requests'))

@app.route('/admin/reject-restock/<int:request_id>', methods=['POST'])
@admin_required
def admin_reject_restock(request_id):
    """Reject a restock request"""
    restock_request = RestockRequest.query.get_or_404(request_id)
    
    try:
        admin_notes = request.form.get('admin_notes', '')
        
        # Update restock request
        restock_request.status = 'rejected'
        restock_request.processed_at = datetime.utcnow()
        restock_request.processed_by = session['user_id']
        restock_request.admin_notes = admin_notes
        
        db.session.commit()
        
        # Notify seller
        push_notification(restock_request.seller_id, 
                       f'Your restock request for "{restock_request.product.name}" has been rejected.')
        
        flash(f'Restock request for "{restock_request.product.name}" has been rejected.', 'success')
        
        # Log the rejection
        app.logger.info(f"Admin {session['user_id']} rejected restock request {request_id} for product {restock_request.product.id}")
        
    except Exception as e:
        app.logger.error(f"Error rejecting restock request {request_id}: {e}")
        flash('An error occurred while rejecting the restock request.', 'error')
    
    return redirect(url_for('admin_restock_requests'))

@app.route('/shop')
def shop():
    category_id = request.args.get('category')
    subcategory_id = request.args.get('subcategory')
    sort_by = request.args.get('sort', 'featured')
    search = request.args.get('search', '')
    price_min = request.args.get('price_min', '')
    price_max = request.args.get('price_max', '')

    # Show all products in the public shop view
    query = Product.query

    # Category filter
    if category_id:
        try:
            query = query.filter(Product.category_id == int(category_id))
        except ValueError:
            pass

    # Subcategory filter
    if subcategory_id:
        try:
            query = query.filter(Product.subcategory_id == int(subcategory_id))
        except ValueError:
            pass

    # Text search (name + description)
    if search:
        search_filter = or_(
            Product.name.ilike(f'%{search}%'),
            Product.description.ilike(f'%{search}%')
        )
        query = query.filter(search_filter)

    # Price range filters
    try:
        if price_min:
            min_value = float(price_min)
            query = query.filter(Product.price >= min_value)
    except ValueError:
        price_min = ''
    try:
        if price_max:
            max_value = float(price_max)
            query = query.filter(Product.price <= max_value)
    except ValueError:
        price_max = ''

    # Sorting
    if sort_by == 'price_low':
        query = query.order_by(Product.price.asc())
    elif sort_by == 'price_high':
        query = query.order_by(Product.price.desc())
    elif sort_by == 'newest':
        query = query.order_by(Product.created_at.desc())
    else:  # featured
        query = query.order_by(Product.featured.desc(), Product.created_at.desc())

    products = query.all()
    # Compute total sold per product (sum of quantities from completed orders)
    for product in products:
        total_sold = db.session.query(db.func.sum(OrderItem.quantity)).join(Order).filter(
            OrderItem.product_id == product.id,
            Order.status.in_(['completed', 'delivered'])
        ).scalar() or 0
        product.total_sold = int(total_sold)

    # Only show active categories (unique)
    all_categories = Category.query.filter_by(status='active').order_by(Category.name).all()
    # Remove duplicates by keeping only the first occurrence of each name
    seen_names = set()
    categories = []
    for cat in all_categories:
        if cat.name not in seen_names:
            seen_names.add(cat.name)
            categories.append(cat)

    return render_template(
        'shop.html',
        products=products,
        categories=categories,
        current_category=category_id,
        current_subcategory=subcategory_id,
        current_sort=sort_by,
        search=search,
        price_min=price_min,
        price_max=price_max,
    )

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    
    if product.status != 'active':
        flash('Product not available.', 'error')
        return redirect(url_for('shop'))
    
    related_products = Product.query.filter_by(
        category_id=product.category_id, 
        status='active'
    ).filter(Product.id != product_id).limit(4).all()
    
    # Build media list for gallery: primary image, gallery images, optional video
    media_items = []
    if product.image_filename:
        media_items.append({'type':'image', 'path': url_for('static', filename='uploads/' + product.image_filename)})
    if getattr(product, 'gallery', None):
        for fn in product.gallery:
            media_items.append({'type':'image', 'path': url_for('static', filename='uploads/' + fn)})
    if product.video_filename:
        media_items.append({'type':'video', 'path': url_for('static', filename='uploads/' + product.video_filename)})
    if not media_items:
        # fallback placeholder
        media_items.append({'type':'placeholder'})
    
    # Reviews aggregate + sorting
    sort_reviews = request.args.get('sort_reviews', 'latest')
    q = Review.query.filter_by(product_id=product.id, status='published')
    if sort_reviews == 'high':
        q = q.order_by(Review.rating.desc(), Review.created_at.desc())
    elif sort_reviews == 'low':
        q = q.order_by(Review.rating.asc(), Review.created_at.desc())
    else:
        q = q.order_by(Review.created_at.desc())
    reviews = q.all()
    review_count = len(reviews)
    avg_rating = (sum(r.rating for r in reviews) / review_count) if review_count else 0.0

    try:
        available_stock = get_available_stock(product.id)
    except Exception:
        available_stock = max(int(product.stock or 0), 0)
    
    in_wishlist = False
    can_review = False
    review_message = ""
    
    if 'user_id' in session:
        wishlist_item = Wishlist.query.filter_by(
            user_id=session['user_id'], 
            product_id=product_id
        ).first()
        in_wishlist = wishlist_item is not None
        can_review, _, review_message = can_user_review_product(session['user_id'], product_id)
    
    return render_template('product_detail.html', 
                         product=product, 
                         related_products=related_products,
                         in_wishlist=in_wishlist,
                         can_review=can_review,
                         review_message=review_message,
                         reviews=reviews,
                         review_count=review_count,
                         avg_rating=avg_rating,
                         sort_reviews=sort_reviews,
                         available_stock=available_stock,
                         media_items=media_items)

@app.route('/add-to-cart/<int:product_id>')
@login_required
def add_to_cart(product_id):
    # Admin accounts are view-only; block shopping actions
    try:
        if is_admin():
            msg = 'Admin accounts are view-only and cannot add items to cart.'
            if request.headers.get('Content-Type') == 'application/json' or request.is_json:
                return jsonify({'success': False, 'message': msg}), 403
            flash(msg, 'warning')
            return redirect(request.referrer or url_for('product_detail', product_id=product_id))
    except Exception:
        pass
    product = Product.query.get_or_404(product_id)
    
    # Check if product is active
    if product.status != 'active':
        flash('Product not available.', 'error')
        return redirect(request.referrer or url_for('shop'))
    
    # Check if user is trying to buy their own product
    if product.seller_id == session['user_id']:
        flash('You cannot purchase your own products.', 'error')
        return redirect(request.referrer or url_for('shop'))
    
    # Check available stock (considering reserved orders)
    available_stock = get_available_stock(product_id)
    
    # Check if item already in cart
    cart_item = Cart.query.filter_by(user_id=session['user_id'], product_id=product_id).first()
    
    if cart_item:
        # Check available stock before increasing quantity
        if cart_item.quantity >= available_stock:
            flash(f'Cannot add more items. Only {available_stock} items available.', 'error')
        else:
            cart_item.quantity += 1
            db.session.commit()
            flash('Item quantity updated in cart.', 'success')
    else:
        # Check available stock before adding new item
        if available_stock <= 0:
            flash('Product is out of stock.', 'error')
        elif available_stock <= 10:
            flash('Product is low stock. Only a few items remaining!', 'warning')
        else:
            cart_item = Cart(user_id=session['user_id'], product_id=product_id, quantity=1)
            db.session.add(cart_item)
            db.session.commit()
            flash('Product added to cart!', 'success')
    
    # Check if it's an AJAX request
    if request.headers.get('Content-Type') == 'application/json' or request.is_json:
        # Calculate new cart count
        cart_count = Cart.query.filter_by(user_id=session['user_id']).count()
        return jsonify({
            'success': True,
            'message': 'Product added to cart!',
            'cart_count': cart_count
        })
    
    return redirect(request.referrer or url_for('shop'))

@app.route('/add-to-cart-ajax/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart_ajax(product_id):
    # Admin accounts cannot add to cart
    try:
        if is_admin():
            return jsonify({'success': False, 'message': 'Admin accounts are view-only and cannot add items to cart.'}), 403
    except Exception:
        pass
    try:
        product = Product.query.get_or_404(product_id)
    
        # Check if product is active
        if product.status != 'active':
            return jsonify({'success': False, 'message': 'Product not available.'}), 400
        
        # Check if user is trying to buy their own product
        if product.seller_id == session['user_id']:
            return jsonify({'success': False, 'message': 'You cannot purchase your own products.'}), 400
        
        # Parse requested quantity (defaults to 1)
        data = request.get_json(silent=True) or {}
        try:
            req_qty = int(data.get('qty') or data.get('quantity') or 1)
        except Exception:
            req_qty = 1
        if req_qty < 1:
            req_qty = 1
        
        # Check available stock (considering reserved orders)
        available_stock = get_available_stock(product_id)
        if available_stock <= 0:
            return jsonify({'success': False, 'message': 'Product is out of stock.'}), 400
        elif available_stock <= 10:
            return jsonify({'success': False, 'message': 'Product is low stock. Only a few items remaining!'}), 400
        
        # Check if item already in cart
        cart_item = Cart.query.filter_by(user_id=session['user_id'], product_id=product_id).first()
        
        if cart_item:
            current = int(cart_item.quantity or 0)
            can_add = max(available_stock - current, 0)
            if can_add <= 0:
                return jsonify({'success': False, 'message': f'Cannot add more items. Only {available_stock} available.'}), 400
            add_qty = min(req_qty, can_add)
            cart_item.quantity = current + add_qty
        else:
            add_qty = min(req_qty, available_stock)
            if add_qty <= 0:
                if available_stock <= 0:
                    return jsonify({'success': False, 'message': 'Product is out of stock.'}), 400
                else:
                    return jsonify({'success': False, 'message': 'Product is low stock. Only a few items remaining!'}), 400
            cart_item = Cart(user_id=session['user_id'], product_id=product_id, quantity=add_qty)
            db.session.add(cart_item)
        
        db.session.commit()
        
        cart_count = Cart.query.filter_by(user_id=session['user_id']).count()
        msg = 'Added to cart.' if add_qty == req_qty else f'Added {add_qty} (limited by stock).'
        return jsonify({'success': True, 'message': msg, 'cart_count': cart_count, 'new_quantity': cart_item.quantity})
    except Exception:
        return jsonify({'success': False, 'message': 'Error adding product to cart'}), 500


@app.route('/buy-now/<int:product_id>', methods=['GET', 'POST'])
@login_required
def buy_now(product_id):
    """Create a separate cart line for this product (ignoring any existing one) and checkout ONLY that line with the selected qty."""
    # Block admin users
    try:
        if is_admin():
            flash('Admin accounts are view-only and cannot purchase items.', 'warning')
            return redirect(url_for('product_detail', product_id=product_id))
    except Exception:
        pass
    product = Product.query.get_or_404(product_id)

    # Must be active and not buyer's own product
    if product.status != 'active':
        flash('Product not available.', 'error')
        return redirect(url_for('product_detail', product_id=product_id))
    if product.seller_id == session['user_id']:
        flash('You cannot purchase your own products.', 'error')
        return redirect(url_for('product_detail', product_id=product_id))

    # Desired quantity from query string (default 1)
    try:
        req_qty = int(request.args.get('qty', '1'))
    except Exception:
        req_qty = 1
    if req_qty < 1:
        req_qty = 1

    # Stock guard (uses order reservations, not cart contents)
    available_stock = get_available_stock(product_id)
    if available_stock <= 0:
        flash('Product is out of stock.', 'error')
        return redirect(url_for('product_detail', product_id=product_id))
    elif available_stock <= 10:
        flash('Product is low stock. Only a few items remaining!', 'warning')

    add_qty = min(req_qty, max(available_stock, 0))
    if add_qty <= 0:
        flash('Cannot purchase the requested quantity due to stock limits.', 'warning')
        return redirect(url_for('product_detail', product_id=product_id))

    # IMPORTANT: always create a new cart row (do NOT merge with any existing row for same product)
    new_item = Cart(user_id=session['user_id'], product_id=product_id, quantity=add_qty)
    db.session.add(new_item)
    db.session.commit()

    # Redirect to checkout with only this new cart item selected
    return redirect(url_for('checkout', ids=str(new_item.id)))

@app.route('/debug-cart')
@login_required
def debug_cart():
    """Debug route to verify cart sorting"""
    cart_items = Cart.query.filter_by(user_id=session['user_id']).order_by(Cart.created_at.desc()).all()
    
    debug_info = []
    for item in cart_items:
        debug_info.append({
            'id': item.id,
            'product_name': item.product.name,
            'quantity': item.quantity,
            'created_at': item.created_at.strftime('%Y-%m-%d %H:%M:%S')
        })
    
    return jsonify({
        'cart_items': debug_info,
        'total_items': len(debug_info)
    })

@app.route('/test-cart-sort')
@login_required
def test_cart_sort():
    """Test route to verify cart sorting is working"""
    cart_items = Cart.query.filter_by(user_id=session['user_id']).all()
    cart_items.sort(key=lambda x: x.created_at, reverse=True)
    
    result = []
    for i, item in enumerate(cart_items):
        result.append({
            'position': i + 1,
            'id': item.id,
            'product': item.product.name,
            'created_at': item.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'timestamp': item.created_at.timestamp()
        })
    
    return jsonify({
        'success': True,
        'items': result,
        'message': 'Items should be sorted newest first (position 1 = most recent)'
    })

@app.route('/cart')
@login_required
def cart():
    # Admin cannot use cart
    try:
        if is_admin():
            flash('Admin accounts cannot use the cart.', 'warning')
            return redirect(url_for('index'))
    except Exception:
        pass
    
    # Get cart items and sort by most recent first
    cart_items = Cart.query.filter_by(user_id=session['user_id']).all()
    
    # Sort in Python to guarantee ordering (newest first)
    cart_items.sort(key=lambda x: x.created_at, reverse=True)
    
    total = sum(item.product.price * item.quantity for item in cart_items)
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/checkout')
@login_required
def checkout():
    # Admin cannot access checkout
    try:
        if is_admin():
            flash('Admin accounts cannot checkout.', 'warning')
            return redirect(url_for('index'))
    except Exception:
        pass
    # Optional: selected cart item IDs passed from cart via ?ids=1,2,3
    raw_ids = (request.args.get('ids') or '').strip()
    selected_ids = []
    if raw_ids:
        try:
            selected_ids = [int(x) for x in raw_ids.split(',') if x.strip().isdigit()]
        except Exception:
            selected_ids = []

    # Load user's cart; if ids provided, filter to those
    base_query = Cart.query.filter_by(user_id=session['user_id'])
    if selected_ids:
        cart_items = base_query.filter(Cart.id.in_(selected_ids)).all()
    else:
        cart_items = base_query.all()
    
    # Sort by most recent first
    cart_items.sort(key=lambda x: x.created_at, reverse=True)

    if not cart_items:
        flash('Please select at least one item to checkout.', 'warning')
        return redirect(url_for('cart'))

    user = User.query.get(session['user_id'])

    # Get all user addresses, ordered with default address first
    addresses = Address.query.filter_by(user_id=session['user_id']).order_by(
        Address.is_default.desc(),
        Address.created_at.desc()
    ).all()

    # Get default address or first address
    default_address = next((addr for addr in addresses if addr.is_default), addresses[0] if addresses else None)

    # Check if there's a newly added address to auto-select
    new_address_id = session.pop('new_address_id', None)
    if new_address_id:
        # Find the newly added address
        new_address = next((addr for addr in addresses if addr.id == new_address_id), None)
        if new_address:
            default_address = new_address

    # Check if an address was just edited
    edited_address_id = session.pop('edited_address_id', None)

    total = sum(item.product.price * item.quantity for item in cart_items)
    shipping_fee = 50.0 if total > 0 else 0.0  # No shipping when nothing selected (safety)

    # Optional coupon from query string for preview
    coupon_code = request.args.get('coupon_code', '').strip()
    discount_amount = 0.0
    coupon_error = None
    applied_coupon = None

    if coupon_code:
        applied_coupon, discount_amount, coupon_error = calculate_coupon_discount(coupon_code, total)
        # If invalid, do not apply discount
        if coupon_error or not applied_coupon:
            discount_amount = 0.0
            applied_coupon = None
        else:
            # Handle free-shipping coupons by zeroing shipping_fee
            if applied_coupon.discount_type == 'free_shipping':
                shipping_fee = 0.0
            # If discount covers entire order (100% or more), waive shipping fee
            elif discount_amount >= total:
                shipping_fee = 0.0

    grand_total = total - discount_amount + shipping_fee
    # Ensure grand_total doesn't go below 0
    grand_total = max(0.0, grand_total)

    return render_template(
        'checkout.html',
        cart_items=cart_items,
        user=user,
        addresses=addresses,
        default_address=default_address,
        new_address_id=new_address_id,
        edited_address_id=edited_address_id,
        total=total,
        shipping_fee=shipping_fee,
        grand_total=grand_total,
        coupon_code=coupon_code,
        discount_amount=discount_amount,
        coupon_error=coupon_error,
        applied_coupon=applied_coupon,
        selected_cart_item_ids=','.join(str(i) for i in selected_ids)
    )


@app.route('/api/available-coupons')
@login_required
def api_available_coupons():
    """Return active, not-expired, under-limit coupons for the current buyer.

    This powers the "Display Coupon Code" section in checkout.html.
    """
    now = datetime.utcnow()

    query = Coupon.query.filter(Coupon.is_active.is_(True))

    # Valid from / until checks
    query = query.filter(
        db.or_(Coupon.valid_from.is_(None), Coupon.valid_from <= now),
        db.or_(Coupon.valid_until.is_(None), Coupon.valid_until >= now),
    )

    # Usage limit checks: include coupons with no max_uses or used_count < max_uses
    query = query.filter(
        db.or_(
            Coupon.max_uses.is_(None),
            db.and_(Coupon.used_count.isnot(None), Coupon.used_count < Coupon.max_uses),
        )
    )

    coupons = query.order_by(Coupon.created_at.desc()).all()

    def serialize(c: Coupon):
        remaining_uses = None
        if c.max_uses is not None:
            used = c.used_count or 0
            remaining_uses = max(c.max_uses - used, 0)

        return {
            'code': c.code,
            'description': c.description or '',
            'discount_type': c.discount_type,
            'discount_value': float(c.discount_value or 0.0),
            'min_order_amount': float(c.min_order_amount or 0.0),
            'valid_until': c.valid_until.isoformat() if c.valid_until else None,
            'max_uses': c.max_uses,
            'used_count': c.used_count or 0,
            'remaining_uses': remaining_uses,
        }

    return jsonify([serialize(c) for c in coupons])


@app.route('/track-order/<tracking_number>')
def track_order(tracking_number):
    order = Order.query.filter_by(tracking_number=tracking_number).first()
    if not order:
        flash('Order not found.', 'danger')
        return redirect(url_for('index'))
    return render_template('track_order.html', order=order)


@app.route('/track-order-search', methods=['GET', 'POST'])
def track_order_search():
    if request.method == 'POST':
        tracking_number = request.form.get('tracking_number')
        return redirect(url_for('track_order', tracking_number=tracking_number))
    return render_template('track_order_search.html')

@app.route('/process-order', methods=['POST'])
@login_required
def process_order():
    # Admin cannot place orders
    try:
        if is_admin():
            flash('Admin accounts cannot place orders.', 'warning')
            return redirect(url_for('index'))
    except Exception:
        pass
    # Determine selected cart items (if any were specified)
    raw_ids = (request.form.get('selected_cart_item_ids') or '').strip()
    selected_ids = []
    if raw_ids:
        try:
            selected_ids = [int(x) for x in raw_ids.split(',') if x.strip().isdigit()]
        except Exception:
            selected_ids = []

    base_query = Cart.query.filter_by(user_id=session['user_id'])
    if selected_ids:
        cart_items = base_query.filter(Cart.id.in_(selected_ids)).all()
    else:
        cart_items = base_query.all()
    
    # Sort by most recent first
    cart_items.sort(key=lambda x: x.created_at, reverse=True)

    if not cart_items:
        flash('Please select at least one item to checkout.', 'warning')
        return redirect(url_for('cart'))
    
    payment_method = request.form['payment_method']
    coupon_code = request.form.get('coupon_code', '').strip()
    
    # Handle address selection
    address_id = request.form.get('address_id')
    if address_id:
        # User selected an existing address
        selected_address = Address.query.filter_by(id=address_id, user_id=session['user_id']).first()
        if selected_address:
            shipping_address = selected_address.full_address
        else:
            flash('Invalid address selected.', 'error')
            return redirect(url_for('checkout', ids=raw_ids))
    else:
        # Fallback to manual address (for backward compatibility)
        shipping_address = request.form.get('shipping_address', '')
        if not shipping_address:
            flash('Please select or enter a shipping address.', 'error')
            return redirect(url_for('checkout', ids=raw_ids))
    
    # Check stock and product status before creating order
    for cart_item in cart_items:
        # Ensure product is active
        if getattr(cart_item.product, 'status', 'active') != 'active':
            flash(f'{cart_item.product.name} is inactive and cannot be purchased.', 'error')
            return redirect(url_for('cart'))
        available_stock = get_available_stock(cart_item.product_id)
        if cart_item.quantity > available_stock:
            flash(f'Insufficient stock for {cart_item.product.name}. Only {available_stock} items available.', 'error')
            return redirect(url_for('cart'))

    total = sum(item.product.price * item.quantity for item in cart_items)
    shipping_fee = 50.0 if total > 0 else 0.0

    # Apply coupon discount (if any)
    discount_amount = 0.0
    applied_coupon = None
    if coupon_code:
        applied_coupon, discount_amount, coupon_error = calculate_coupon_discount(coupon_code, total)
        if coupon_error or not applied_coupon:
            flash(coupon_error or 'Invalid coupon code.', 'danger')
            # Redirect back to checkout without applying the coupon
            return redirect(url_for('checkout'))

        # Handle free-shipping coupons by zeroing shipping_fee
        if applied_coupon.discount_type == 'free_shipping':
            shipping_fee = 0.0
        # If discount covers entire order (100% or more), waive shipping fee
        elif discount_amount >= total:
            shipping_fee = 0.0

    grand_total = total - discount_amount + shipping_fee
    # Ensure grand_total doesn't go below 0
    grand_total = max(0.0, grand_total)

    # Create order
    new_order = Order(
        buyer_id=session['user_id'],
        total_amount=grand_total,
        payment_method=payment_method,
        shipping_address=shipping_address,
        status='pending'  # Order starts as pending
    )
    
    db.session.add(new_order)
    db.session.flush()  # Get order ID
    
    # Generate QR code and tracking information
    qr_code = generate_qr_code(new_order.id)
    tracking_number = generate_tracking_number()
    batch_code = generate_batch_code()
    
    # Update order with QR code and tracking info
    new_order.qr_code = qr_code
    new_order.tracking_number = tracking_number
    new_order.batch_code = batch_code
    new_order.label_generated_at = datetime.utcnow()
    
    try:
        # Create order items and deduct stock immediately
        for cart_item in cart_items:
            order_item = OrderItem(
                order_id=new_order.id,
                product_id=cart_item.product_id,
                quantity=cart_item.quantity,
                price_at_time=cart_item.product.price
            )
            db.session.add(order_item)
            
            # 🎯 RULE 1: DEDUCT STOCK IMMEDIATELY WHEN BUYER PLACES ORDER
            # Stock is deducted right away, not when seller processes
            product = Product.query.get(cart_item.product_id)
            if product:
                product.stock = max(0, product.stock - cart_item.quantity)
                app.logger.info(f'Order {new_order.id}: Stock deducted for Product {product.id} (-{cart_item.quantity}) => {product.stock}')
        
        # Mark order as stock deducted (already done during creation)
        new_order.stock_deducted = True
        
        # Create order label with QR code data
        label_data = create_order_label_data(new_order)
        order_label = OrderLabel(
            order_id=new_order.id,
            qr_code=qr_code,
            tracking_number=tracking_number,
            batch_code=batch_code,
            label_data=label_data,
            status='generated'
        )
        db.session.add(order_label)

        # If a coupon was applied, increment its usage counter
        if applied_coupon:
            applied_coupon.used_count = (applied_coupon.used_count or 0) + 1
        
        # Remove ONLY the selected cart items from the cart
        if selected_ids:
            Cart.query.filter(Cart.user_id == session['user_id'], Cart.id.in_(selected_ids)).delete(synchronize_session=False)
        else:
            Cart.query.filter_by(user_id=session['user_id']).delete()
        
        # Notify sellers about new order (real-time)
        seller_ids = set()
        for item in new_order.items:
            seller_ids.add(item.product.seller_id)
        
        for seller_id in seller_ids:
            try:
                push_notification(
                    seller_id,
                    f'New order #{new_order.id} received!',
                    link=url_for('seller_orders'),
                    type='order',
                    order_id=new_order.id
                )
            except Exception:
                # Fallback to DB-only notification on error
                db.session.add(Notification(user_id=seller_id, message=f'New order #{new_order.id} received!', type='order'))
            
            # Emit real-time new_order to seller's Socket.IO room
            first_item = new_order.items[0]
            try:
                socketio.emit('new_order', {
                    'order_id': new_order.id,
                    'created_at': new_order.created_at.isoformat(),
                    'buyer_name': f"{new_order.buyer.first_name} {new_order.buyer.last_name}",
                    'buyer_email': new_order.buyer.email,
                    'product_name': first_item.product.name,
                    'product_image': first_item.product.image_filename,
                    'quantity': first_item.quantity,
                    'unit_price': float(first_item.price_at_time),
                    'total_amount': float(new_order.total_amount),
                    'payment_method': new_order.payment_method
                }, room=f'user_{seller_id}')
            except Exception:
                pass  # Ignore socket errors
        
        # Commit the entire transaction
        db.session.commit()
        
    except Exception as e:
        # Rollback on any error to prevent stock inconsistencies
        db.session.rollback()
        app.logger.error(f'Order processing failed: {str(e)}')
        flash('An error occurred while processing your order. Please try again.', 'danger')
        return redirect(url_for('cart'))

    # Redirect straight to order confirmation without a global flash alert
    return redirect(url_for('order_confirmation', order_id=new_order.id))

@app.route('/order-confirmation/<int:order_id>')
@login_required
def order_confirmation(order_id):
    order = Order.query.filter_by(id=order_id, buyer_id=session['user_id']).first_or_404()
    # On the order confirmation page we show a custom success UI, so hide global flash alerts
    return render_template('order_confirmation.html', order=order, hide_flashes=True)


@app.route('/buyer/order/<int:order_id>')
@login_required
def buyer_order_detail(order_id):
    order = Order.query.filter_by(id=order_id, buyer_id=session['user_id']).first_or_404()
    # Calculate estimated delivery date
    estimated_delivery = order.created_at + timedelta(days=3)
    return render_template('buyer/order_detail.html', order=order, estimated_delivery=estimated_delivery)

@app.route('/cancel-order/<int:order_id>', methods=['GET', 'POST'])
@login_required
def cancel_order(order_id):
    print(f"Cancel order route accessed: order_id={order_id}, method={request.method}")
    
    # Handle GET request - show confirmation page
    if request.method == 'GET':
        order = Order.query.filter_by(id=order_id, buyer_id=session['user_id']).first()
        if not order:
            flash('Order not found.', 'danger')
            return redirect(url_for('my_orders'))
        if order.status not in ['pending', 'to_pay']:
            flash(f'Order cannot be cancelled. Current status: {order.status}', 'danger')
            return redirect(url_for('my_orders'))
        return render_template('cancel_order.html', order=order)
    
    # Handle POST request - process cancellation
    order = Order.query.filter_by(id=order_id, buyer_id=session['user_id']).first()
    if not order:
        flash('Order not found.', 'danger')
        return redirect(url_for('my_orders'))
    
    if order.status not in ['pending', 'to_pay']:
        flash(f'Order cannot be cancelled. Current status: {order.status}', 'danger')
        return redirect(url_for('my_orders'))
    
    # Read cancellation reasons from form (REQUIRED)
    reasons = request.form.getlist('cancel_reasons') or []
    other = (request.form.get('cancel_other') or '').strip()
    
    # Validate that at least one reason is provided
    if not reasons and not other:
        flash('Please select at least one reason before cancelling your order.', 'danger')
        return redirect(url_for('my_orders'))
    
    reason_text = ', '.join(reasons)
    if other:
        reason_text = (reason_text + (', ' if reason_text else '') + f'Other: {other}').strip(', ')
    
    # Store original status before changing it
    original_status = order.status
    
    # 🎯 RULE 2: RETURN STOCK ONLY IF BUYER CANCELS BEFORE SELLER PROCESSES
    # Stock should only return if order was still pending/to_pay (not processed by seller yet)
    # Since we now deduct stock immediately, we check if seller hasn't processed it
    if original_status in ['pending', 'to_pay']:
        # Order was not processed by seller yet, return the stock
        for item in order.items:
            product = Product.query.get(item.product_id)
            if product:
                # Return the stock to seller inventory
                product.stock += item.quantity
                app.logger.info(f'Order {order.id} cancelled: Stock restored for Product {product.id} (+{item.quantity}) => {product.stock}')
                
                # Emit real-time stock update with available stock
                try:
                    available_stock = get_available_stock(product.id)
                    socketio.emit('product_stock_update', {
                        'product_id': product.id,
                        'stock': available_stock,
                        'available_stock': available_stock
                    })
                except Exception:
                    pass
    else:
        # Order was already processed by seller, do NOT return stock
        app.logger.info(f'Order {order.id} cancelled: No stock returned (order was already processed by seller)')
    
    # Persist note
    note = f"[Buyer Cancellation] {reason_text}" if reason_text else "[Buyer Cancellation]"
    order.delivery_notes = ((order.delivery_notes or '') + f"\n{datetime.utcnow().isoformat()} {note}").strip()
    order.status = 'cancelled'
    order.updated_at = datetime.utcnow()
    
    db.session.commit()
    
    # Notify buyer (self) and sellers
    push_notification(order.buyer_id, f'Your order #{order.id} has been cancelled successfully.')
    for sid in _order_seller_ids(order):
        push_notification(sid, f'Order #{order.id} was cancelled by the buyer.')
    
    # Emit real-time cancellation event to seller's Socket.IO room
    try:
        socketio.emit('order_cancelled', {
            'order_id': order.id,
            'buyer_id': order.buyer_id,
            'message': f'Order #{order.id} has been cancelled by buyer'
        }, room='sellers')
    except Exception:
        pass
    
    flash('Your order has been cancelled successfully.', 'success')
    return redirect(url_for('my_orders', tab='cancelled'))


@app.route('/api/qr-scan', methods=['POST'])
def api_qr_scan():
    """API endpoint for Android app QR scanning"""
    try:
        data = request.get_json()
        qr_code = data.get('qr_code')
        scan_type = data.get('scan_type')  # packing, pickup, delivery, return
        rider_id = data.get('rider_id')
        scan_notes = data.get('scan_notes', '')
        
        if not qr_code or not scan_type:
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400
        
        order_label = OrderLabel.query.filter_by(qr_code=qr_code).first()
        if not order_label:
            return jsonify({'success': False, 'message': 'QR Code not found'}), 404
        
        order = order_label.order
        
        # Update order label status based on scan type
        if scan_type == 'packing':
            order_label.status = 'packed'
            order_label.packed_at = datetime.utcnow()
            order_label.packed_by = rider_id
            order_label.shipping_notes = scan_notes
        elif scan_type == 'pickup':
            order_label.status = 'picked_up'
            order_label.picked_up_at = datetime.utcnow()
            order_label.picked_up_by = rider_id
        elif scan_type == 'delivery':
            order_label.status = 'delivered'
            order_label.delivered_at = datetime.utcnow()
            order_label.delivered_by = rider_id
            order_label.delivery_notes = scan_notes
        elif scan_type == 'return':
            order_label.status = 'returned'
            order_label.returned_at = datetime.utcnow()
            order_label.returned_by = rider_id
            order_label.return_notes = scan_notes
        
        # Log the scan
        scan_log = QRScanLog(
            order_id=order.id,
            order_label_id=order_label.id,
            qr_code=qr_code,
            scanned_by=rider_id,
            scan_type=scan_type,
            scan_notes=scan_notes,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        db.session.add(scan_log)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'QR Code scanned successfully! Status updated to {scan_type}',
            'order_id': order.id,
            'order_status': order_label.status,
            'customer_name': f"{order.buyer.first_name} {order.buyer.last_name}",
            'customer_phone': order.buyer.phone,
            'shipping_address': order.shipping_address
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/qr-info/<qr_code>')
def api_qr_info(qr_code):
    """API endpoint to get QR code information for Android app"""
    try:
        order_label = OrderLabel.query.filter_by(qr_code=qr_code).first()
        if not order_label:
            return jsonify({'success': False, 'message': 'QR Code not found'}), 404
        
        order = order_label.order
        
        return jsonify({
            'success': True,
            'order_id': order.id,
            'tracking_number': order.tracking_number,
            'status': order_label.status,
            'customer_name': f"{order.buyer.first_name} {order.buyer.last_name}",
            'customer_phone': order.buyer.phone,
            'shipping_address': order.shipping_address,
            'total_amount': float(order.total_amount),
            'payment_method': order.payment_method,
            'created_at': order.created_at.isoformat(),
            'items': [
                {
                    'product_name': item.product.name,
                    'quantity': item.quantity,
                    'price': float(item.price_at_time),
                    'seller_name': f"{item.product.seller.first_name} {item.product.seller.last_name}"
                }
                for item in order.items
            ]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/admin/qr-scan', methods=['GET', 'POST'])
@admin_required
def admin_qr_scan():
    """Admin QR code scanning interface"""
    if request.method == 'POST':
        qr_code = request.form.get('qr_code')
        scan_type = request.form.get('scan_type')
        scan_notes = request.form.get('scan_notes', '')
        
        order_label = OrderLabel.query.filter_by(qr_code=qr_code).first()
        if not order_label:
            flash('QR Code not found!', 'error')
            return redirect(url_for('admin_qr_scan'))
        
        # Update order label status based on scan type
        if scan_type == 'packing':
            order_label.status = 'packed'
            order_label.packed_at = datetime.utcnow()
            order_label.packed_by = session['user_id']
            order_label.shipping_notes = scan_notes
        elif scan_type == 'pickup':
            order_label.status = 'picked_up'
            order_label.picked_up_at = datetime.utcnow()
            order_label.picked_up_by = session['user_id']
        elif scan_type == 'delivery':
            order_label.status = 'delivered'
            order_label.delivered_at = datetime.utcnow()
            order_label.delivered_by = session['user_id']
            order_label.delivery_notes = scan_notes
        elif scan_type == 'return':
            order_label.status = 'returned'
            order_label.returned_at = datetime.utcnow()
            order_label.returned_by = session['user_id']
            order_label.return_notes = scan_notes
        
        # Log the scan
        scan_log = QRScanLog(
            order_id=order_label.order_id,
            order_label_id=order_label.id,
            qr_code=qr_code,
            scanned_by=session['user_id'],
            scan_type=scan_type,
            scan_notes=scan_notes,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        db.session.add(scan_log)
        db.session.commit()
        
        flash(f'QR Code scanned successfully! Status updated to {scan_type}.', 'success')
        return redirect(url_for('admin_qr_scan'))
    
    return render_template('admin/qr_scan.html')

@app.route('/admin/categories', methods=['GET', 'POST'])
@admin_required
def admin_categories():
    if request.method == 'POST':
        name = request.form.get('name')
        if name and not Category.query.filter_by(name=name).first():
            db.session.add(Category(name=name))
            db.session.commit()
            flash('Category added!', 'success')
        else:
            flash('Category already exists or invalid.', 'error')
    categories = Category.query.order_by(Category.name).all()
    badge_counts = get_admin_badge_counts()
    return render_template('admin/categories.html', 
                         categories=categories, 
                         now=datetime.utcnow,
                         **badge_counts)

@app.route('/admin/categories/activate/<int:category_id>', methods=['POST'])
@admin_required
def activate_category(category_id):
    category = Category.query.get_or_404(category_id)
    category.status = 'active'
    db.session.commit()
    
    # Check if it's an AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'status': 'active',
            'message': 'Category set to active.'
        })
    
    flash('Category set to active.', 'success')
    return redirect(url_for('admin_categories'))


@app.route('/admin/categories/delete/<int:category_id>', methods=['POST'])
@admin_required
def soft_delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    category.status = 'inactive'
    db.session.commit()
    
    # Check if it's an AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'status': 'inactive',
            'message': 'Category set to inactive.'
        })
    
    flash('Category set to inactive.', 'info')
    return redirect(url_for('admin_categories'))

# --- CATEGORY EDIT / PERMANENT DELETE ROUTES ---
@app.route('/admin/categories/edit/<int:category_id>', methods=['GET', 'POST'])
@admin_required
def edit_category(category_id):
    """
    Simple edit view for categories. GET shows a small edit form (rendered inline)
    POST updates name/description/status and optionally processes an uploaded cover image.
    """
    category = Category.query.get_or_404(category_id)

    if request.method == 'POST':
        # Basic fields
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        status = request.form.get('status', category.status)

        if name:
            category.name = name
        category.description = description
        category.status = status

        # Optional cover image upload (same processing as update_category_cover)
        file = request.files.get('cover_image')
        if file and file.filename:
            if not allowed_file(file.filename):
                flash('Invalid cover file type. Use JPG or PNG.', 'danger')
                return redirect(url_for('edit_category', category_id=category.id))

            upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'categories')
            os.makedirs(upload_dir, exist_ok=True)
            try:
                img = Image.open(file.stream).convert('RGB')
                target_w, target_h = 1000, 150
                img_w, img_h = img.size
                target_ratio = target_w / target_h
                img_ratio = img_w / img_h

                if img_ratio > target_ratio:
                    new_w = int(target_ratio * img_h)
                    left = (img_w - new_w) // 2
                    img = img.crop((left, 0, left + new_w, img_h))
                else:
                    new_h = int(img_w / target_ratio)
                    top = (img_h - new_h) // 2
                    img = img.crop((0, top, img_w, top + new_h))

                img = img.resize((target_w, target_h), Image.LANCZOS)

                filename = f"cat_{category_id}_{int(time.time())}.jpg"
                filepath = os.path.join(upload_dir, filename)
                img.save(filepath, format='JPEG', quality=85)

                # remove old file if exists
                old = category.cover_image_filename
                if old:
                    try:
                        old_path = os.path.join(upload_dir, old)
                        if os.path.exists(old_path):
                            os.remove(old_path)
                    except Exception:
                        app.logger.exception("Failed to remove old category cover")

                category.cover_image_filename = filename
            except Exception:
                app.logger.exception("Failed processing uploaded category cover")
                flash('Failed to process uploaded image.', 'danger')
                return redirect(url_for('edit_category', category_id=category.id))

        db.session.commit()
        flash('Category updated successfully.', 'success')
        return redirect(url_for('admin_categories'))

    # GET -> show small inline edit page using the same base layout
    # Keeps UI consistent without requiring a new template file.
    return render_template_string("""
    {% extends "base.html" %}
    {% block title %}Edit Category - {{ category.name }}{% endblock %}
    {% block content %}
    <div class="container py-4">
      <div class="card shadow-sm">
        <div class="card-header">
          <h5 class="mb-0">Edit Category: {{ category.name }}</h5>
        </div>
        <div class="card-body">
          <form method="POST" enctype="multipart/form-data">
            <div class="mb-3">
              <label class="form-label">Name</label>
              <input class="form-control" name="name" value="{{ category.name }}" required>
            </div>
            <div class="mb-3">
              <label class="form-label">Description</label>
              <textarea class="form-control" name="description" rows="3">{{ category.description or '' }}</textarea>
            </div>
            <div class="mb-3">
              <label class="form-label">Status</label>
              <select class="form-select" name="status">
                <option value="active" {% if category.status == 'active' %}selected{% endif %}>Active</option>
                <option value="inactive" {% if category.status != 'active' %}selected{% endif %}>Inactive</option>
              </select>
            </div>
            <div class="mb-3">
              <label class="form-label">Cover Image (optional, recommended 1000Ã—150)</label>
              <input type="file" name="cover_image" accept="image/png,image/jpeg" class="form-control">
              <div class="form-text">If provided, this will overwrite the current cover.</div>
            </div>

            <div class="d-flex gap-2">
              <button class="btn btn-primary" type="submit">Save changes</button>
              <a href="{{ url_for('admin_categories') }}" class="btn btn-secondary">Back to Categories</a>
            </div>
          </form>
        </div>
      </div>
    </div>
    {% endblock %}
    """, category=category)


@app.route('/admin/categories/delete-permanent/<int:category_id>', methods=['POST'], endpoint='delete_category')
@admin_required
def delete_category(category_id):
    """
    Permanently delete a category (this is the endpoint your template expects:
    url_for('delete_category', category_id=...)). This will remove the DB row
    and associated cover file if present.
    """
    category = Category.query.get_or_404(category_id)
    # Remove cover image from disk if present
    upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'categories')
    old = category.cover_image_filename
    try:
        if old:
            old_path = os.path.join(upload_dir, old)
            if os.path.exists(old_path):
                os.remove(old_path)
    except Exception:
        app.logger.exception("Failed to remove category cover while deleting category")

    # Optionally: you might want to reassign or delete related subcategories/products first.
    # For now, attempt to delete row and commit (will fail if FK constraints prevent deletion).
    try:
        db.session.delete(category)
        db.session.commit()
        flash('Category permanently deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.exception("Failed to permanently delete category: %s", e)
        flash('Failed to delete category. Make sure there are no dependent records (products/subcategories).', 'danger')

    return redirect(url_for('admin_categories'))

@app.route('/admin/category/<int:category_id>/update-cover', methods=['POST'])
@admin_required
def update_category_cover(category_id):
    category = Category.query.get_or_404(category_id)
    file = request.files.get('cover_image')
    if not file or not file.filename:
        flash('No file selected.', 'warning')
        return redirect(url_for('admin_categories'))

    if not allowed_file(file.filename):
        flash('Invalid file type. Please upload JPG or PNG.', 'danger')
        return redirect(url_for('admin_categories'))

    upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'categories')
    os.makedirs(upload_dir, exist_ok=True)

    try:
        img = Image.open(file.stream).convert('RGB')
        target_w, target_h = 1000, 150
        img_w, img_h = img.size
        target_ratio = target_w / target_h
        img_ratio = img_w / img_h

        if img_ratio > target_ratio:
            new_w = int(target_ratio * img_h)
            left = (img_w - new_w) // 2
            img = img.crop((left, 0, left + new_w, img_h))
        else:
            new_h = int(img_w / target_ratio)
            top = (img_h - new_h) // 2
            img = img.crop((0, top, img_w, top + new_h))

        img = img.resize((target_w, target_h), Image.LANCZOS)

        ext = 'jpg'
        base = secure_filename(category.name.replace(' ', '_').lower())[:50]
        filename = f"cat_{category_id}_{int(time.time())}.{ext}"
        filepath = os.path.join(upload_dir, filename)
        img.save(filepath, format='JPEG', quality=85)

        # remove old file if exists
        old = category.cover_image_filename
        if old:
            try:
                old_path = os.path.join(upload_dir, old)
                if os.path.exists(old_path):
                    os.remove(old_path)
            except Exception:
                app.logger.exception("Failed to remove old category cover")

        category.cover_image_filename = filename
        db.session.commit()
        flash('Category cover updated.', 'success')
    except Exception as e:
        app.logger.exception("Error saving category cover")
        flash('Failed to save cover image. Try again.', 'error')

    return redirect(url_for('admin_categories'))



@app.route('/admin/theme-settings', methods=['GET', 'POST'])
@admin_required
def theme_settings():
    theme = ThemeSetting.query.first()
    # If theme row doesn't exist, create one!
    if theme is None:
        theme = ThemeSetting(
            site_name="Kids & Baby Store",
            primary_color="#0066ff",
            secondary_color="#59b5fc",
            footer_color="#232323"
        )
        db.session.add(theme)
        db.session.commit()
    if request.method == 'POST':
        # Handle logo upload
        file = request.files.get('logo')
        if file and file.filename:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            theme.logo_filename = filename

        theme.site_name = request.form.get('site_name', theme.site_name)
        theme.primary_color = request.form.get('primary_color', theme.primary_color)
        theme.secondary_color = request.form.get('secondary_color', theme.secondary_color)
        theme.footer_color = request.form.get('footer_color', theme.footer_color)
        db.session.commit()
        flash('Theme updated!', 'success')
        return redirect(url_for('theme_settings'))
    badge_counts = get_admin_badge_counts()
    return render_template('admin/theme_settings.html', theme=theme, **badge_counts)

@app.route('/admin/toggle-new-arrival/<int:product_id>', methods=['POST'])
@admin_required
def admin_toggle_new_arrival(product_id):
    product = Product.query.get_or_404(product_id)
    product.show_in_new_arrival = not bool(product.show_in_new_arrival)
    db.session.commit()
    flash(f'Updated New Arrival status for "{product.name}".', 'success')
    return redirect(request.referrer or url_for('admin_products'))


@app.route('/seller/print-label/<int:order_id>')
@seller_required
def seller_print_label(order_id):
    """Print shipping label for seller"""
    order = Order.query.get_or_404(order_id)
    order_label = OrderLabel.query.filter_by(order_id=order_id).first()
    
    if not order_label:
        flash('Order label not found!', 'error')
        return redirect(url_for('seller_orders'))
    
    # Check if seller has products in this order
    seller_has_products = any(item.product.seller_id == session['user_id'] for item in order.items)
    if not seller_has_products:
        flash('You are not authorized to view this order.', 'error')
        return redirect(url_for('seller_orders'))
    
    # Get seller's application information
    seller_app = SellerApplication.query.filter_by(user_id=session['user_id'], status='approved').first()
    
    # Generate QR code image
    qr_image = create_qr_image(order_label.qr_code)
    
    return render_template('seller/print_label.html', 
                         order=order, 
                         order_label=order_label,
                         qr_image=qr_image,
                         seller_app=seller_app)

@app.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    data = request.json
    
    # PayMongo checkout session creation
    headers = {
        'Authorization': f'Basic {PAYMONGO_SECRET_KEY}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'data': {
            'attributes': {
                'amount': int(data['amount'] * 100),  # Convert to centavos
                'currency': 'PHP',
                'description': f'Order from Kids & Baby Store',
                'line_items': data['line_items'],
                'payment_method_types': ['card', 'gcash', 'paymaya'],
                'success_url': request.url_root + f'payment-success?order_id={data["order_id"]}',
                'cancel_url': request.url_root + 'cart'
            }
        }
    }
    
    try:
        response = requests.post(
            'https://api.paymongo.com/v1/checkout_sessions',
            headers=headers,
            json=payload
        )
        
        if response.status_code == 200:
            checkout_data = response.json()
            return jsonify({'success': True, 'checkout_url': checkout_data['data']['attributes']['checkout_url']})
        else:
            return jsonify({'success': False, 'error': 'Payment session creation failed'})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})



@app.route('/payment-success')
@login_required
def payment_success():
    order_id = request.args.get('order_id')
    if order_id:
        order = Order.query.filter_by(id=order_id, buyer_id=session['user_id']).first()
        if order:
            order.payment_status = 'paid'
            db.session.commit()
            flash('Payment successful! Your order is confirmed.', 'success')
        return redirect(url_for('order_confirmation', order_id=order_id))
    return redirect(url_for('index'))

@app.route('/update-cart', methods=['POST'])
@login_required
def update_cart():
    data = request.json
    product_id = data.get('product_id')
    quantity = int(data.get('quantity', 1))
    
    cart_item = Cart.query.filter_by(user_id=session['user_id'], product_id=product_id).first()
    
    if cart_item:
        if quantity > 0:
            cart_item.quantity = quantity
        else:
            db.session.delete(cart_item)
        
        db.session.commit()
        
        # Calculate new totals
        cart_items = Cart.query.filter_by(user_id=session['user_id']).order_by(Cart.created_at.desc()).all()
        total = sum(item.product.price * item.quantity for item in cart_items)
        cart_count = len(cart_items)
        # --- START: Add item_total for this cart item ---
        item_total = cart_item.product.price * cart_item.quantity if quantity > 0 else 0
        # --- END ---
        return jsonify({
            'success': True,
            'total': total,
            'cart_count': cart_count,
            'item_total': item_total  # Added for per-item price update
        })
    
    return jsonify({'success': False})

@app.route('/remove-from-cart/<int:product_id>')
@login_required
def remove_from_cart(product_id):
    Cart.query.filter_by(user_id=session['user_id'], product_id=product_id).delete()
    db.session.commit()
    flash('Item removed from cart.', 'info')
    return redirect(url_for('cart'))

@app.route('/update-cart-quantity', methods=['POST'])
@login_required
def update_cart_quantity():
    data = request.get_json()
    cart_item_id = data.get('cart_item_id')
    new_quantity = data.get('quantity')
    
    if not cart_item_id or not new_quantity:
        return jsonify({'success': False, 'message': 'Invalid data'})
    
    # Get the cart item
    cart_item = Cart.query.filter_by(id=cart_item_id, user_id=session['user_id']).first()
    
    if not cart_item:
        return jsonify({'success': False, 'message': 'Cart item not found'})
    
    # Check if quantity is valid
    if new_quantity < 1:
        return jsonify({'success': False, 'message': 'Quantity must be at least 1'})
    
    # Check available stock (considering reserved orders)
    available_stock = get_available_stock(cart_item.product_id)
    if new_quantity > available_stock:
        return jsonify({'success': False, 'message': f'Only {available_stock} items available in stock'})
    
    # Update quantity
    cart_item.quantity = new_quantity
    db.session.commit()
    
    # Calculate totals
    item_total = cart_item.product.price * new_quantity
    cart_total = sum(item.product.price * item.quantity for item in Cart.query.filter_by(user_id=session['user_id']).order_by(Cart.created_at.desc()).all())
    
    return jsonify({
        'success': True,
        'item_total': item_total,
        'cart_total': cart_total,
        'max_stock': available_stock
    })

@app.route('/remove-from-cart', methods=['POST'])
@login_required
def remove_from_cart_ajax():
    data = request.get_json()
    cart_item_id = data.get('cart_item_id')
    
    if not cart_item_id:
        return jsonify({'success': False, 'message': 'Invalid data'})
    
    # Get the cart item
    cart_item = Cart.query.filter_by(id=cart_item_id, user_id=session['user_id']).first()
    
    if not cart_item:
        return jsonify({'success': False, 'message': 'Cart item not found'})
    
    # Remove the item
    db.session.delete(cart_item)
    db.session.commit()
    
    # Calculate new cart total
    cart_total = sum(item.product.price * item.quantity for item in Cart.query.filter_by(user_id=session['user_id']).order_by(Cart.created_at.desc()).all())
    
    return jsonify({
        'success': True,
        'cart_total': cart_total
    })

@app.route('/update-order-status/<int:order_id>/<status>')
@seller_required
def update_order_status(order_id, status):
    order = Order.query.get_or_404(order_id)
    
    # Check if seller owns any products in this order
    seller_products = [item.product_id for item in order.items if item.product.seller_id == session['user_id']]
    
    if not seller_products:
        return redirect(url_for('seller_orders'))

# Prevent seller updates once a rider has accepted/picked up the order
    if order.status in ['to_ship', 'in_transit', 'delivered']:
        flash('This order is now handled by a rider and can no longer be updated by the seller.', 'warning')
        return redirect(url_for('seller_orders'))

    # Only allow 'processing' and 'ready_for_pickup' on seller side
    valid_statuses = ['processing', 'ready_for_pickup']
    if status not in valid_statuses:
        flash('Invalid status for seller. Use "Confirm" then "Ready to Pick Up".', 'error')
        return redirect(url_for('seller_orders'))

    order.status = status
    order.updated_at = datetime.utcnow()

    # Notify buyer based on status
    if status == 'processing':
        try:
            push_notification(order.buyer_id, f'Your order #{order.id} is processing.')
        except Exception:
            db.session.add(Notification(user_id=order.buyer_id, message=f'Your order #{order.id} is processing.'))
    elif status == 'ready_for_pickup':
        # Show out-for-delivery message instead of ready-for-pickup
        msg = f'Your order #{order.id} is out for delivery.'
        db.session.add(Notification(user_id=order.buyer_id, message=msg))
        try:
            socketio.emit('order_available', {
                'order_id': order.id,
                'total_amount': order.total_amount,
                'seller_ids': list({it.product.seller_id for it in order.items})
            }, room='riders')
        except Exception:
            pass

    db.session.commit()
    try:
        _emit_seller_stats_update(session['user_id'])
    except Exception:
        pass
    flash(f'Order status updated to {status}.', 'success')
    return redirect(url_for('seller_orders'))

@app.route('/seller/confirm-order/<int:order_id>')
@seller_required
def seller_confirm_order(order_id):
    """Seller confirms order. Reserve stock implicitly; real stock is deducted upon delivery."""
    order = Order.query.get_or_404(order_id)

    # Check if seller owns any products in this order
    seller_products = [item for item in order.items if item.product.seller_id == session['user_id']]

    if not seller_products:
        flash('You are not authorized to confirm this order.', 'error')
        return redirect(url_for('seller_orders'))

    if order.status != 'pending':
        flash('Order is not in pending status.', 'error')
        return redirect(url_for('seller_orders'))

    try:
        # Handle stock management - stock is now automatically reserved when orders are placed
        # No need to auto-increase stock when confirming orders

        # Update order status only
        order.status = 'processing'
        db.session.commit()

        push_notification(order.buyer_id, f'Your order is now being processed.')
        flash('Order confirmed successfully. Preparing for pickup.', 'success')

        # Update seller stats panel
        _emit_seller_stats_update(session['user_id'])
    except Exception:
        db.session.rollback()
        flash('Error confirming order. Please try again.', 'error')

    return redirect(url_for('seller_orders'))

@app.route('/seller/order/<int:order_id>/process', methods=['POST'])
@seller_required
def seller_process_order(order_id):
    """Seller processes an order (moves from pending to processing)."""
    order = Order.query.get_or_404(order_id)
    
    # Check if seller owns any products in this order
    seller_products = [item for item in order.items if item.product.seller_id == session['user_id']]
    
    if not seller_products:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'You are not authorized to process this order.'})
        flash('You are not authorized to process this order.', 'error')
        return redirect(url_for('seller_orders'))
    
    if order.status != 'pending':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Order must be pending to be processed.'})
        flash('Order must be pending to be processed.', 'error')
        return redirect(url_for('seller_orders'))
    
    try:
        # Update order status
        order.status = 'processing'
        order.updated_at = datetime.utcnow()

        # Handle stock management - stock is now automatically reserved when orders are placed
        # No need to auto-increase stock when processing orders

        # Mark as seen by seller (remove from new orders)
        seen_record = SellerOrderSeen.query.filter_by(seller_id=session['user_id'], order_id=order.id).first()
        if not seen_record:
            db.session.add(SellerOrderSeen(seller_id=session['user_id'], order_id=order.id))

        db.session.commit()

        # Notify buyer
        try:
            push_notification(order.buyer_id, f'Your order #{order.id} is now being processed.')
        except Exception:
            db.session.add(Notification(user_id=order.buyer_id, message=f'Your order #{order.id} is now being processed.'))

        # Update seller stats
        try:
            _emit_seller_stats_update(session['user_id'])
        except Exception:
            pass
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': 'Order processed successfully.'})
        
        flash('Order processed successfully.', 'success')
        return redirect(url_for('seller_orders'))
        
    except Exception as e:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Error processing order.'})
        flash('Error processing order. Please try again.', 'error')
        return redirect(url_for('seller_orders'))

@app.route('/seller/order/<int:order_id>/ready-for-pickup', methods=['POST'])
@seller_required
def seller_ready_for_pickup(order_id):
    """Seller marks an order ready for pickup. Broadcasts to available riders only."""
    order = Order.query.get_or_404(order_id)

    # Check if seller owns any products in this order
    seller_id = session['user_id']
    seller_products = [item for item in order.items if item.product.seller_id == seller_id]
    if not seller_products:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'You are not authorized to mark this order as ready for pickup.'})
        flash('You are not authorized to mark this order as ready for pickup.', 'error')
        return redirect(url_for('seller_orders'))

    # Only from pending/processing
    if order.status not in ['pending', 'processing']:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Order must be pending/processing before marking as ready.'})
        flash('Order must be pending/processing before marking as ready.', 'error')
        return redirect(url_for('seller_orders'))

    order.status = 'ready_for_pickup'
    order.packed_at = datetime.utcnow()
    order.packed_by = seller_id
    
    # Handle stock management - add requested quantity to available stock if needed
    for item in seller_products:
        current_stock = item.product.stock
        requested_quantity = item.quantity
        
        # If requested quantity exceeds current stock, add the difference to available stock
        if requested_quantity > current_stock:
            stock_to_add = requested_quantity - current_stock
            item.product.stock += stock_to_add
            
            # Log the stock addition for reference
            print(f"Added {stock_to_add} units to product {item.product.name} (ID: {item.product.id}) - New stock: {item.product.stock}")
    
    db.session.commit()

    # Notify buyer and broadcast to available riders (buyer sees out-for-delivery)
    push_notification(order.buyer_id, f'Your order #{order.id} is out for delivery.')
    try:
        from sqlalchemy import or_
        available = DeliveryPersonnel.query.filter(DeliveryPersonnel.status.in_(['active','on_duty'])).all()
        payload = {
            'order_id': order.id,
            'total_amount': order.total_amount,
            'seller_id': seller_id
        }
        for r in available:
            socketio.emit('order_available', payload, room=f'user_{r.user_id}')
        _emit_seller_stats_update(seller_id)
    except Exception:
        pass

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': 'Order marked ready for pickup.'})
    
    flash('Order marked ready for pickup.', 'success')
    return redirect(url_for('seller_orders'))

@app.route('/seller/cancel-order/<int:order_id>')
@seller_required
def seller_cancel_order(order_id):
    """Disabled: cancellation is rider-only per system rules."""
    flash('Cancellation is handled by riders. Please coordinate with the assigned rider or admin.', 'warning')
    return redirect(url_for('seller_orders'))
    
    # Check if seller owns any products in this order
    seller_products = [item.product_id for item in order.items if item.product.seller_id == session['user_id']]
    
    if not seller_products:
        flash('You are not authorized to cancel this order.', 'error')
        return redirect(url_for('seller_orders'))
    
    if order.status in ['accepted_by_rider', 'in_transit', 'delivered', 'completed']:
        flash('Cannot cancel orders once a rider has accepted or it is in transit/completed.', 'error')
        return redirect(url_for('seller_orders'))
    
    try:
        # Restore stock if order was processing (stock was deducted)
        if order.stock_deducted:
            for item in order.items:
                if item.product.seller_id == session['user_id']:
                    item.product.stock += item.quantity
        
        # Update order status
        order.status = 'cancelled'
        order.stock_deducted = False  # Reset flag
        
        db.session.commit()
        
        # Notify buyer
        db.session.add(Notification(
            user_id=order.buyer_id,
            message=f'Your order #{order.id} has been cancelled by the seller.'
        ))
        db.session.commit()
        
        flash('Order cancelled successfully! Stock has been restored.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash('Error cancelling order. Please try again.', 'error')
    
    return redirect(url_for('seller_orders'))

@app.route('/seller/add-tracking/<int:order_id>')
@seller_required
def add_tracking_number(order_id):
    """Disabled: tracking and delivery are handled by riders in the new workflow."""
    flash('Tracking and delivery are handled by riders. Use "Ready to Pick Up" and let riders handle pickup and delivery.', 'info')
    return redirect(url_for('seller_orders'))

@app.route('/profile')
@login_required
def profile():
    user = User.query.get(session['user_id'])
    active_role = session.get('active_role', user.role)
    
    if user.role == 'admin':
        return redirect(url_for('admin_profile'))
    elif active_role == 'seller':
        return redirect(url_for('seller_profile'))
    elif user.role == 'rider' or active_role == 'rider':
        return redirect(url_for('rider_dashboard'))
    else:
        # Buyer profile
        addresses = Address.query.filter_by(user_id=session['user_id']).all()
        return render_template('buyer_profile.html', user=user, addresses=addresses)

@app.route('/buyer-profile')
@login_required
def buyer_profile():
    user = User.query.get(session['user_id'])
    addresses = Address.query.filter_by(user_id=session['user_id']).all()
    return render_template('buyer_profile.html', user=user, addresses=addresses)

@app.route('/buyer/order/<int:order_id>/received', methods=['POST'])
@login_required
def buyer_confirm_received(order_id):
    """Buyer taps 'Order Received' -> status completed and release commissions."""
    order = Order.query.get_or_404(order_id)
    if order.buyer_id != session['user_id']:
        flash('You are not allowed to confirm this order.', 'error')
        return redirect(url_for('dashboard'))
    if order.status != 'delivered':
        flash('Order must be delivered before confirmation.', 'warning')
        return redirect(url_for('dashboard'))

    order.status = 'completed'
    order.updated_at = datetime.utcnow()
    db.session.commit()

    # Release commissions and notify
    _release_commissions(order)
    push_notification(order.buyer_id, f'Thank you! Order #{order.id} marked as received.')
    for sid in _order_seller_ids(order):
        push_notification(sid, f'Order #{order.id} completed. Commission released.')
        _emit_seller_stats_update(sid)
    if order.picked_up_by:
        push_notification(order.picked_up_by, f'Order #{order.id} completed. Commission released.')

    # Optional: notify admins as well
    for a in _admins():
        push_notification(a.id, f'Order #{order.id} completed by buyer. Commissions released.')

    flash('Order confirmed. Thank you!', 'success')
    return redirect(url_for('my_orders'))

@app.route('/seller-profile')
@seller_required
def seller_profile():
    user = User.query.get(session['user_id'])
    seller_app = SellerApplication.query.filter_by(user_id=session['user_id'], status='approved').first()
    
    # Get seller statistics
    total_products = Product.query.filter_by(seller_id=session['user_id']).count()
    total_orders = db.session.query(Order).join(OrderItem).join(Product).filter(Product.seller_id == session['user_id']).count()
    total_sales = db.session.query(db.func.sum(OrderItem.price_at_time * OrderItem.quantity)).join(Product).filter(Product.seller_id == session['user_id'], Order.payment_status == 'paid').scalar() or 0
    
    return render_template('seller_profile.html', user=user, seller_app=seller_app, 
                         total_products=total_products, total_orders=total_orders, total_sales=total_sales)

@app.route('/update-store-info', methods=['POST'])
@seller_required
def update_store_info():
    seller_app = SellerApplication.query.filter_by(user_id=session['user_id'], status='approved').first()
    if not seller_app:
        flash('Seller application not found.', 'error')
        return redirect(url_for('seller_profile'))
    
    seller_app.store_name = request.form['store_name']
    seller_app.store_category = request.form['store_category']
    
    # Handle store logo upload
    if 'store_logo' in request.files:
        file = request.files['store_logo']
        if file and file.filename:
            filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{session['user_id']}_store_logo_{file.filename}")
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'documents', filename)
            file.save(file_path)
            seller_app.store_logo = f"/static/uploads/documents/{filename}"
    
    # Commit with retry logic for connection issues
    max_retries = 3
    for attempt in range(max_retries):
        try:
            db.session.commit()
            flash('Store information updated successfully!', 'success')
            return redirect(url_for('seller_profile'))
        except Exception as e:
            db.session.rollback()
            if attempt < max_retries - 1:
                # Wait a moment before retrying
                time.sleep(0.5)
                continue
            else:
                # Log the error and show user-friendly message
                app.logger.error(f"Database error in update_store_info: {str(e)}")
                flash('An error occurred while updating your store information. Please try again.', 'error')
                return redirect(url_for('seller_profile'))

@app.route('/update-store-description', methods=['POST'])
@seller_required
def update_store_description():
    seller_app = SellerApplication.query.filter_by(user_id=session['user_id'], status='approved').first()
    if not seller_app:
        flash('Seller application not found.', 'error')
        return redirect(url_for('seller_profile'))
    
    seller_app.store_description = request.form['store_description']
    seller_app.store_mission = request.form.get('store_mission', '')
    
    # Commit with retry logic for connection issues
    max_retries = 3
    for attempt in range(max_retries):
        try:
            db.session.commit()
            flash('Store description updated successfully!', 'success')
            return redirect(url_for('seller_profile'))
        except Exception as e:
            db.session.rollback()
            if attempt < max_retries - 1:
                time.sleep(0.5)
                continue
            else:
                app.logger.error(f"Database error in update_store_description: {str(e)}")
                flash('An error occurred while updating your store description. Please try again.', 'error')
                return redirect(url_for('seller_profile'))

@app.route('/update-return-policy', methods=['POST'])
@seller_required
def update_return_policy():
    seller_app = SellerApplication.query.filter_by(user_id=session['user_id'], status='approved').first()
    if not seller_app:
        flash('Seller application not found.', 'error')
        return redirect(url_for('seller_profile'))
    
    seller_app.return_policy = request.form['return_policy']
    seller_app.return_days = int(request.form.get('return_days', 7))
    seller_app.refund_method = request.form.get('refund_method', 'Original Payment Method')
    
    # Commit with retry logic for connection issues
    max_retries = 3
    for attempt in range(max_retries):
        try:
            db.session.commit()
            flash('Return policy updated successfully!', 'success')
            return redirect(url_for('seller_profile'))
        except Exception as e:
            db.session.rollback()
            if attempt < max_retries - 1:
                time.sleep(0.5)
                continue
            else:
                app.logger.error(f"Database error in update_return_policy: {str(e)}")
                flash('An error occurred while updating your return policy. Please try again.', 'error')
                return redirect(url_for('seller_profile'))

@app.route('/upload-business-documents', methods=['POST'])
@seller_required
def upload_business_documents():
    seller_app = SellerApplication.query.filter_by(user_id=session['user_id'], status='approved').first()
    if not seller_app:
        flash('Seller application not found.', 'error')
        return redirect(url_for('seller_profile'))
    
    # Handle business registration upload
    if 'business_registration' in request.files:
        file = request.files['business_registration']
        if file and file.filename:
            filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{session['user_id']}_business_reg_{file.filename}")
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'documents', filename)
            file.save(file_path)
            seller_app.business_registration = f"/static/uploads/documents/{filename}"
    
    # Handle valid ID upload
    if 'valid_id' in request.files:
        file = request.files['valid_id']
        if file and file.filename:
            filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{session['user_id']}_valid_id_{file.filename}")
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'documents', filename)
            file.save(file_path)
            seller_app.valid_id = f"/static/uploads/documents/{filename}"
    
    db.session.commit()
    flash('Business documents uploaded successfully!', 'success')
    return redirect(url_for('seller_profile'))

@app.route('/update-seller-info', methods=['POST'])
@seller_required
def update_seller_info():
    user = User.query.get(session['user_id'])
    seller_app = SellerApplication.query.filter_by(user_id=session['user_id'], status='approved').first()
    
    # Update user info
    user.first_name = request.form['first_name']
    user.last_name = request.form['last_name']
    user.phone = request.form['phone']
    
    # Update seller app info
    if seller_app:
        seller_app.business_address = request.form['business_address']
        seller_app.gcash_number = request.form.get('gcash_number', '')
    
    db.session.commit()
    
    # Update session user_name to reflect changes in dropdown
    session['user_name'] = f"{user.first_name} {user.last_name}"
    
    # Update session with new avatar URL for immediate dropdown update
    avatar_rel = os.path.join('user_avatars', f"user_avatar_{user.id}.png")
    upload_root = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
    avatar_path = os.path.join(upload_root, avatar_rel)
    if os.path.exists(avatar_path):
        session['navbar_avatar_url'] = url_for('static', filename=f'uploads/{avatar_rel.replace("\\", "/")}')
        session['avatar_timestamp'] = int(time.time())  # Force cache refresh
    
    flash('Seller information updated successfully!', 'success')
    return redirect(url_for('seller_profile'))

@app.route('/my-orders')
@login_required
def my_orders():
    user_id = session['user_id']
    # Fetch all orders for buyer
    all_orders = Order.query.filter_by(buyer_id=user_id).order_by(Order.created_at.desc()).all()

    # Groupings for tabs
    # To Pay: ALL pending orders (both COD and non-COD) that haven't been processed by seller
    to_pay = [o for o in all_orders if o.status in ['pending', 'to_pay']]
    to_ship = [o for o in all_orders if o.status in ['processing', 'ready_for_pickup']]
    to_receive = [o for o in all_orders if o.status in ['to_ship', 'in_transit', 'delivered']]
    completed = [o for o in all_orders if o.status == 'completed']
    cancelled = [o for o in all_orders if o.status == 'cancelled']

    # Buyer returns list for the Returns/Refund tab
    returns = ReturnRequest.query.filter_by(buyer_id=user_id).order_by(ReturnRequest.created_at.desc()).all()

    # Add review eligibility for each order item
    for order in all_orders:
        for item in order.items:
            can_review, order_id, message = can_user_review_product(user_id, item.product_id)
            item.can_review = can_review
            item.review_message = message
            # Track if already reviewed to show "Rated" state
            item.has_review = Review.query.filter_by(user_id=user_id, product_id=item.product_id).first() is not None

    active_tab = request.args.get('tab', 'to_pay')

    return render_template('my_orders.html',
        orders=all_orders,
        to_pay=to_pay,
        to_ship=to_ship,
        to_receive=to_receive,
        completed=completed,
        cancelled=cancelled,
        returns=returns,
        active_tab=active_tab
    )

@app.route('/wishlist')
@login_required
def wishlist():
    wishlist_items = Wishlist.query.filter_by(user_id=session['user_id']).all()
    return render_template('wishlist.html', wishlist_items=wishlist_items)

@app.route('/add-to-wishlist/<int:product_id>')
@login_required
def add_to_wishlist(product_id):
    existing = Wishlist.query.filter_by(user_id=session['user_id'], product_id=product_id).first()
    if not existing:
        wishlist_item = Wishlist(user_id=session['user_id'], product_id=product_id)
        db.session.add(wishlist_item)
        db.session.commit()
        flash('Added to wishlist!', 'success')
    else:
        flash('Item already in wishlist.', 'info')
    return redirect(request.referrer or url_for('shop'))

@app.route('/remove-from-wishlist/<int:product_id>')
@login_required
def remove_from_wishlist(product_id):
    Wishlist.query.filter_by(user_id=session['user_id'], product_id=product_id).delete()
    db.session.commit()
    flash('Removed from wishlist.', 'info')
    return redirect(url_for('wishlist'))

@app.route('/upload-avatar', methods=['POST'])
@login_required
def upload_avatar():
    """Upload and save a square PNG avatar for the current user under
    static/uploads/user_avatars/user_avatar_{user.id}.png
    """
    try:
        user = User.query.get(session['user_id'])
        if 'avatar' not in request.files:
            flash('No file provided.', 'error')
            return redirect(url_for('profile'))
        f = request.files['avatar']
        if not f or not f.filename:
            flash('Please choose an image.', 'warning')
            return redirect(url_for('profile'))
        # Validate extension
        ext = (f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else '')
        if ext not in ALLOWED_IMAGE_EXT:
            flash('Unsupported image type. Please upload JPG or PNG.', 'danger')
            return redirect(url_for('profile'))
        # Ensure folder exists
        avatar_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'user_avatars')
        os.makedirs(avatar_dir, exist_ok=True)
        # Load image and convert to 1:1 square PNG
        img = Image.open(f.stream).convert('RGBA')
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        img = img.crop((left, top, left + side, top + side)).resize((256, 256), Image.LANCZOS)
        # Save as canonical filename the UI expects
        out_path = os.path.join(avatar_dir, f'user_avatar_{user.id}.png')
        img.save(out_path, format='PNG', optimize=True)
        
        # Update session with new avatar URL for immediate dropdown update
        avatar_rel = os.path.join('user_avatars', f"user_avatar_{user.id}.png")
        session['navbar_avatar_url'] = url_for('static', filename=f'uploads/{avatar_rel.replace("\\", "/")}')
        session['avatar_timestamp'] = int(time.time())  # Force cache refresh
        
        flash('Profile picture updated!', 'success')
    except Exception as e:
        app.logger.exception('Failed to upload avatar: %s', e)
        flash('Failed to upload profile picture. Please try again.', 'danger')
    return redirect(url_for('profile'))


@app.route('/update-profile', methods=['POST'])
@login_required
def update_profile():
    user = User.query.get(session['user_id'])
    active_role = session.get('active_role', user.role)
    
    # Get form data with fallbacks to existing values
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    phone = request.form.get('phone', '').strip()
    address = request.form.get('address', '').strip()
    
    # Validate and update first name (required)
    if first_name:
        user.first_name = first_name
    elif not user.first_name:
        flash('First name is required.', 'error')
        if user.role == 'admin':
            return redirect(url_for('admin_profile'))
        elif active_role == 'seller':
            return redirect(url_for('seller_profile'))
        else:
            return redirect(url_for('buyer_profile'))
    
    # Validate and update last name (required)
    if last_name:
        user.last_name = last_name
    elif not user.last_name:
        flash('Last name is required.', 'error')
        if user.role == 'admin':
            return redirect(url_for('admin_profile'))
        elif active_role == 'seller':
            return redirect(url_for('seller_profile'))
        else:
            return redirect(url_for('buyer_profile'))
    
    # Validate and update phone number (optional but validated if provided)
    if phone:
        # Remove common separators and spaces
        phone_cleaned = phone.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
        if not phone_cleaned.isdigit() or len(phone_cleaned) < 10:
            flash('Please enter a valid phone number (at least 10 digits).', 'error')
            if user.role == 'admin':
                return redirect(url_for('admin_profile'))
            elif active_role == 'seller':
                return redirect(url_for('seller_profile'))
            else:
                return redirect(url_for('buyer_profile'))
        user.phone = phone
    
    # Update address (optional)
    if address:
        user.address = address
    
    db.session.commit()
    session['user_name'] = f"{user.first_name} {user.last_name}"
    
    # Update session with new avatar URL for immediate dropdown update
    avatar_rel = os.path.join('user_avatars', f"user_avatar_{user.id}.png")
    upload_root = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
    avatar_path = os.path.join(upload_root, avatar_rel)
    if os.path.exists(avatar_path):
        session['navbar_avatar_url'] = url_for('static', filename=f'uploads/{avatar_rel.replace("\\", "/")}')
        session['avatar_timestamp'] = int(time.time())  # Force cache refresh
    
    # Provide specific feedback about what was updated
    updated_fields = []
    if first_name: updated_fields.append('name')
    if phone: updated_fields.append('phone number')
    if address: updated_fields.append('address')
    
    if updated_fields:
        fields_text = ', '.join(updated_fields)
        flash(f'Profile updated successfully! Updated: {fields_text}.', 'success')
    else:
        flash('No changes were made to your profile.', 'info')
    
    # Redirect based on user role
    if user.role == 'admin':
        return redirect(url_for('admin_profile'))
    elif active_role == 'seller':
        return redirect(url_for('seller_profile'))
    else:
        return redirect(url_for('buyer_profile'))

# --- Add this route to allow sellers to remove their store logo ---
@app.route('/remove-store-logo', methods=['POST'])
@seller_required
def remove_store_logo():
    """
    Remove the current seller store logo (file on disk + DB field).
    Only available to the logged-in seller who owns the SellerApplication.
    """
    seller_app = SellerApplication.query.filter_by(user_id=session['user_id']).first()
    if not seller_app:
        flash('Seller application not found.', 'error')
        return redirect(url_for('seller_profile'))

    if not seller_app.store_logo:
        flash('No store logo to remove.', 'info')
        return redirect(url_for('seller_profile'))

    try:
        logo_path = seller_app.store_logo  # e.g. "/static/uploads/documents/xxx.png" or "uploads/..."
        # Resolve filesystem path robustly
        if logo_path.startswith('/'):
            fs_path = os.path.join(app.root_path, logo_path.lstrip('/'))
        else:
            # If saved without leading slash assume it's relative to static/
            fs_path = os.path.join(app.root_path, 'static', logo_path)

        # Remove file if it exists
        if os.path.exists(fs_path):
            os.remove(fs_path)

        # Clear DB field
        seller_app.store_logo = None
        db.session.commit()

        flash('Store logo removed successfully.', 'success')
    except Exception as e:
        app.logger.exception("Failed to remove store logo")
        db.session.rollback()
        flash('Failed to remove store logo. Please try again later.', 'danger')

    return redirect(url_for('seller_profile'))


@app.route('/change-password', methods=['POST'])
@login_required
def change_password():
    user = User.query.get(session['user_id'])
    current_password = request.form['current_password']
    new_password = request.form['new_password']
    confirm_password = request.form['confirm_password']
    
    if user.password != current_password:
        flash('Current password is incorrect.', 'error')
    elif new_password != confirm_password:
        flash('New passwords do not match.', 'error')
    else:
        user.password = new_password
        
        # Update security settings
        user.two_factor_enabled = 'two_factor' in request.form
        user.email_notifications = 'email_notifications' in request.form
        
        db.session.commit()
        flash('Password and security settings updated successfully!', 'success')
    
    # Redirect based on user role
    if is_seller():
        return redirect(url_for('seller_profile'))
    else:
        return redirect(url_for('profile'))


@app.route('/add-address', methods=['POST'])
@login_required
def add_address():
    """
    FIX: Use .get() for 'label' to avoid BadRequestKeyError when the field is missing.
    All other logic unchanged exactly as requested.
    """
    label = request.form.get('label', 'Address')  # <-- changed from request.form['label']
    full_address = request.form['full_address']
    is_default = 'is_default' in request.form
    latitude = request.form.get('latitude')
    longitude = request.form.get('longitude')
    region = request.form.get('region')
    province = request.form.get('province')
    city = request.form.get('city')
    barangay = request.form.get('barangay')
    street = request.form.get('street_address') or request.form.get('street')
    if is_default:
        Address.query.filter_by(user_id=session['user_id'], is_default=True).update({'is_default': False})
    new_address = Address(
        user_id=session['user_id'],
        label=label,
        full_address=full_address,
        is_default=is_default,
        latitude=float(latitude) if latitude else None,
        longitude=float(longitude) if longitude else None,
        region=region or None,
        province=province or None,
        city=str(city) if city else None,
        barangay=barangay or None,
        street=street or None
    )
    db.session.add(new_address)
    db.session.commit()
    
    # Store the newly added address ID in session for auto-selection
    session['new_address_id'] = new_address.id
    
    flash('Address added successfully!', 'success')
    
    # Redirect to referring page or profile
    return_to = request.form.get('return_to') or request.referrer
    if return_to and 'checkout' in return_to:
        return redirect(url_for('checkout'))
    return redirect(url_for('profile'))

# ... keep all existing imports and code above unchanged ...

@app.route('/edit-address/<int:address_id>', methods=['POST'])
@login_required
def edit_address(address_id):
    """Edit an existing address record for the logged-in user."""
    address = Address.query.filter_by(id=address_id, user_id=session['user_id']).first_or_404()

    # Basic required fields (same as simple add form)
    label = request.form.get('label', address.label).strip()
    full_address = request.form.get('full_address', address.full_address).strip()
    is_default = 'is_default' in request.form

    # Optional structured fields (used by advanced add modal if present)
    region = request.form.get('region')
    province = request.form.get('province')
    city = request.form.get('city')
    barangay = request.form.get('barangay')
    street = request.form.get('street_address') or request.form.get('street')
    latitude = request.form.get('latitude')
    longitude = request.form.get('longitude')

    # If setting this as default, unset previous default
    if is_default:
        Address.query.filter_by(user_id=session['user_id'], is_default=True).update({'is_default': False})

    # Apply updates
    address.label = label or address.label
    address.full_address = full_address or address.full_address
    address.is_default = is_default

    # Update optional structured fields only if provided
    if region: address.region = region
    if province: address.province = province
    if city: address.city = str(city)
    if barangay: address.barangay = barangay
    if street: address.street = street
    if latitude:
        try: address.latitude = float(latitude)
        except ValueError: pass
    if longitude:
        try: address.longitude = float(longitude)
        except ValueError: pass

    db.session.commit()
    
    # Store the edited address ID in session for feedback
    session['edited_address_id'] = address.id
    
    flash('Address updated successfully!', 'success')
    
    # Redirect to referring page or profile
    return_to = request.form.get('return_to') or request.referrer
    if return_to and 'checkout' in return_to:
        return redirect(url_for('checkout'))
    return redirect(url_for('profile'))

# ... keep the rest of the file below unchanged ...


@app.route('/api/get-address/<int:address_id>')
@login_required
def get_address_details(address_id):
    """API endpoint to get address details as JSON for editing"""
    address = Address.query.filter_by(id=address_id, user_id=session['user_id']).first()
    if not address:
        return jsonify({'success': False, 'message': 'Address not found'}), 404
    
    return jsonify({
        'success': True,
        'address': {
            'id': address.id,
            'label': address.label,
            'full_address': address.full_address,
            'street': address.street or '',
            'region': address.region or '',
            'province': address.province or '',
            'city': address.city or '',
            'barangay': address.barangay or '',
            'is_default': address.is_default
        }
    })

@app.route('/delete-address/<int:address_id>')
@login_required
def delete_address(address_id):
    address = Address.query.filter_by(id=address_id, user_id=session['user_id']).first_or_404()
    db.session.delete(address)
    db.session.commit()
    flash('Address deleted.', 'info')
    return redirect(url_for('profile'))

@app.route('/google-login')
def google_login():
    return redirect(url_for("google.login"))

@app.route('/check-password-strength', methods=['POST'])
def check_password_strength():
    """API endpoint for real-time password strength checking"""
    data = request.get_json()
    password = data.get('password', '')
    
    if not password:
        return jsonify({'strength': 0, 'level': 'weak', 'message': 'Enter a password'})
    
    strength = calculate_password_strength(password)
    
    if strength < 40:
        level = 'weak'
        color = 'danger'
    elif strength < 70:
        level = 'medium'
        color = 'warning'
    else:
        level = 'strong'
        color = 'success'
    
    is_valid, message = validate_password(password)
    
    return jsonify({
        'strength': strength,
        'level': level,
        'color': color,
        'is_valid': is_valid,
        'message': message
    })


# ... (existing imports, models, routes above)

from werkzeug.utils import secure_filename

# --- Add this route below your other routes ---

@app.route('/submit-review/<int:product_id>', methods=['POST'])
@login_required
def submit_review(product_id):
    product = Product.query.get_or_404(product_id)
    user_id = session['user_id']
    
    # Verify user can review this product
    can_review, order_id, message = can_user_review_product(user_id, product_id)
    if not can_review:
        flash(message, 'error')
        return redirect(request.referrer or url_for('product_detail', product_id=product_id))
    
    # Validate rating
    try:
        rating = int(request.form.get('rating', 0))
        if rating < 1 or rating > 5:
            flash('Please provide a rating between 1 and 5 stars.', 'error')
            return redirect(request.referrer or url_for('product_detail', product_id=product_id))
    except ValueError:
        flash('Invalid rating value.', 'error')
        return redirect(request.referrer or url_for('product_detail', product_id=product_id))
    
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()  # optional per requirement
    
    # Handle multiple media uploads (images/videos)
    media_files = request.files.getlist('media[]') or []
    saved_media = []
    first_image_filename = None
    review_img_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'reviews')
    review_vid_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'reviews', 'videos')
    os.makedirs(review_img_dir, exist_ok=True)
    os.makedirs(review_vid_dir, exist_ok=True)

    for f in media_files:
        if not f or not f.filename:
            continue
        ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
        safe_name = secure_filename(f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{user_id}_{product_id}_{f.filename}")
        try:
            if ext in ALLOWED_IMAGE_EXT:
                path = os.path.join(review_img_dir, safe_name)
                f.save(path)
                url_path = f"reviews/{safe_name}"
                saved_media.append({'type': 'image', 'path': f"/static/uploads/{url_path}"})
                if not first_image_filename:
                    first_image_filename = safe_name
            elif ext in ALLOWED_VIDEO_EXT:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(0)
                if size and size > MAX_VIDEO_BYTES:
                    flash('Video too large. Max 50MB.', 'warning')
                    continue
                path = os.path.join(review_vid_dir, safe_name)
                f.save(path)
                url_path = f"reviews/videos/{safe_name}"
                saved_media.append({'type': 'video', 'path': f"/static/uploads/{url_path}"})
            else:
                flash('Unsupported file type skipped.', 'warning')
        except Exception:
            flash('Failed to upload one of the files. Skipped.', 'warning')
            continue

    # Save review with verified purchase
    new_review = Review(
        product_id=product_id,
        user_id=user_id,
        rating=rating,
        title=title,
        content=content or None,
        status='published',
        created_at=datetime.utcnow(),
        image_filename=first_image_filename,  # legacy image support
        media=saved_media if saved_media else None,
        verified_purchase=True,  # User has been verified through can_user_review_product
        order_id=order_id  # Link to the purchase order
    )

    db.session.add(new_review)
    db.session.commit()

    flash('Thank you for your verified review!', 'success')
    # After rating, go back to My Orders so the button shows "Rated"
    if request.referrer and '/my-orders' in request.referrer:
        return redirect(url_for('my_orders', tab='completed'))
    return redirect(url_for('product_detail', product_id=product_id, _anchor='reviews'))


@app.route('/set-role/<role>')
@login_required
def set_role(role):
    user = User.query.get(session['user_id'])
    role = (role or '').strip().lower()
    if role == 'buyer':
        session['active_role'] = 'buyer'
        flash('Switched to Buyer mode', 'success')
        return redirect(request.referrer or url_for('index'))
    if role == 'seller':
        seller_app = SellerApplication.query.filter_by(user_id=user.id, status='approved').first()
        if user.role == 'seller' or seller_app:
            session['active_role'] = 'seller'
            flash('Switched to Seller mode', 'success')
            return redirect(url_for('seller_dashboard'))
        flash('You are not approved as a seller yet.', 'error')
        return redirect(request.referrer or url_for('index'))
    if role == 'rider':
        # Optional: allow riders to set active role if they are a rider
        if user.role == 'rider':
            session['active_role'] = 'rider'
            flash('Switched to Rider mode', 'success')
            return redirect(url_for('rider_dashboard'))
        flash('Rider mode is not available for your account.', 'error')
        return redirect(request.referrer or url_for('index'))
    flash('Unknown role.', 'error')
    return redirect(request.referrer or url_for('index'))


@app.route('/switch-role')
@login_required
def switch_role():
    user = User.query.get(session['user_id'])
    current_active_role = session.get('active_role', user.role)
    
    # Check if user has an approved seller application
    seller_app = SellerApplication.query.filter_by(user_id=user.id, status='approved').first()
    
    if current_active_role == 'buyer':
        # Switch to seller mode
        if user.role == 'seller' or seller_app:
            session['active_role'] = 'seller'
            flash('Switched to Seller mode', 'success')
            return redirect(url_for('seller_dashboard'))
        else:
            flash('You are not approved as a seller yet.', 'error')
    elif current_active_role == 'seller':
        # Switch to buyer mode
        session['active_role'] = 'buyer'
        flash('Switched to Buyer mode', 'success')
        return redirect(url_for('index'))
    else:
        flash('Role switching not available for your account type.', 'error')
    
    return redirect(request.referrer or url_for('index'))


@app.route('/store/<int:seller_id>')
def store_page(seller_id):
    seller = User.query.get_or_404(seller_id)
    seller_app = SellerApplication.query.filter_by(user_id=seller_id, status='approved').first()
    if not seller_app:
        flash('Store not found or not approved.', 'error')
        return redirect(url_for('shop'))

    # products and categories
    products = Product.query.filter_by(seller_id=seller_id, status='active').all()
    categories = Category.query.all()
    now = datetime.utcnow()
    # Filter new arrivals (products added in the last 30 days)
    new_arrivals = [p for p in products if p.created_at and p.created_at > (now - timedelta(days=30))]
    # Filter top selling (example: sort by sold attribute, if exists)
    top_selling = sorted(products, key=lambda p: getattr(p, 'sold', 0), reverse=True)[:6]

    # Followers count (accurate)
    try:
        followers_count = Follow.query.filter_by(seller_id=seller_id).count()
    except Exception:
        followers_count = 0

    # Average rating across this seller's published reviews
    try:
        avg_rating = db.session.query(db.func.avg(Review.rating))\
            .join(Product, Review.product_id == Product.id)\
            .filter(Product.seller_id == seller_id, Review.status == 'published')\
            .scalar()
        store_rating = float(avg_rating) if avg_rating is not None else 0.0
    except Exception:
        store_rating = 0.0

    # Is current user following this store?
    is_following = False
    if 'user_id' in session:
        is_following = Follow.query.filter_by(follower_id=session['user_id'], seller_id=seller_id).first() is not None

    return render_template(
        'store_page.html',
        seller=seller,
        seller_app=seller_app,
        store_rating=round(store_rating, 1),
        followers_count=followers_count,
        is_following=is_following,
        products=products,
        categories=categories,
        new_arrivals=new_arrivals,
        top_selling=top_selling,
        store_rating_raw=store_rating  # optional if you want unrounded value in template
    )

@app.route('/follow-store/<int:seller_id>', methods=['POST'])
@login_required
def follow_store(seller_id):
    # Prevent self-follow
    if session.get('user_id') == seller_id:
        flash('You cannot follow your own store.', 'warning')
        return redirect(url_for('store_page', seller_id=seller_id))

    existing = Follow.query.filter_by(follower_id=session['user_id'], seller_id=seller_id).first()
    if existing:
        # Unfollow
        try:
            db.session.delete(existing)
            db.session.commit()
            flash('You have unfollowed this store.', 'info')
        except Exception:
            db.session.rollback()
            app.logger.exception("Failed to unfollow store")
            flash('Unable to unfollow at the moment. Please try again.', 'danger')
    else:
        # Follow
        try:
            new_follow = Follow(follower_id=session['user_id'], seller_id=seller_id)
            db.session.add(new_follow)
            db.session.commit()
            flash('You are now following this store!', 'success')
        except Exception:
            db.session.rollback()
            app.logger.exception("Failed to follow store")
            flash('Unable to follow at the moment. Please try again.', 'danger')

    return redirect(url_for('store_page', seller_id=seller_id))


# ... keep existing imports ...

@app.template_filter('comma')
def comma_format(value, digits=None):
    """
    Format numbers with thousands separators.
    - Accepts int, float, or numeric strings (with or without commas).
    - For floats, defaults to 2 decimal places (configurable via |comma(2)).
    - Falls back to string if value isn't numeric.
    Usage:
      {{ 1234567 | comma }}           -> "1,234,567"
      {{ 1234567.8 | comma }}         -> "1,234,567.80"
      {{ 1234567.891 | comma(3) }}    -> "1,234,567.891"
      {{ "1234567.8" | comma }}       -> "1,234,567.80"
    """
    try:
        # Normalize strings to numeric first
        if isinstance(value, str):
            cleaned = value.strip().replace(',', '')
            # Try integer first
            if cleaned.isdigit():
                value = int(cleaned)
            else:
                value = float(cleaned)

        # Integers
        if isinstance(value, int):
            return f"{value:,}"

        # Floats
        if isinstance(value, float):
            if digits is None:
                digits = 2
            return f"{value:,.{digits}f}"

        # Other numeric-like types (Decimal, etc.)
        try:
            as_float = float(value)
            if digits is None:
                digits = 2
            return f"{as_float:,.{digits}f}"
        except Exception:
            return str(value)
    except Exception:
        # As a last resort, just stringify
        return str(value)

# ... rest of app.py unchanged ...

@app.route('/chat')
@login_required
def chat_list():
    user_id = session['user_id']
    active_role = session.get('active_role', 'buyer')
    # Build conversation list with expected fields for template
    convos = []
    users_by_id = {}
    if active_role == 'buyer':
        rows = db.session.query(StoreChatMessage.seller_id, db.func.max(StoreChatMessage.created_at).label('last_at')).filter_by(buyer_id=user_id).group_by(StoreChatMessage.seller_id).order_by(db.func.max(StoreChatMessage.created_at).desc()).all()
        peer_ids = [r[0] for r in rows]
        users_by_id = {u.id: u for u in User.query.filter(User.id.in_(peer_ids)).all()}
        for sid, _ in rows:
            last = StoreChatMessage.query.filter_by(buyer_id=user_id, seller_id=sid).order_by(StoreChatMessage.created_at.desc()).first()
            unread = StoreChatMessage.query.filter_by(buyer_id=user_id, seller_id=sid, sender_role='seller', is_read=False).count()
            convos.append(type('Obj', (), {'seller_id': sid, 'last_message': getattr(last,'message',''), 'unread_count': unread}))
    else:
        rows = db.session.query(StoreChatMessage.buyer_id, db.func.max(StoreChatMessage.created_at).label('last_at')).filter_by(seller_id=user_id).group_by(StoreChatMessage.buyer_id).order_by(db.func.max(StoreChatMessage.created_at).desc()).all()
        peer_ids = [r[0] for r in rows]
        users_by_id = {u.id: u for u in User.query.filter(User.id.in_(peer_ids)).all()}
        for bid, _ in rows:
            last = StoreChatMessage.query.filter_by(seller_id=user_id, buyer_id=bid).order_by(StoreChatMessage.created_at.desc()).first()
            unread = StoreChatMessage.query.filter_by(seller_id=user_id, buyer_id=bid, sender_role='buyer', is_read=False).count()
            convos.append(type('Obj', (), {'buyer_id': bid, 'last_message': getattr(last,'message',''), 'unread_count': unread}))
    return render_template('store_chat.html', chats=convos, users_by_id=users_by_id, chat_messages=[], selected_chat=None)

@app.route('/chat/<int:seller_id>', methods=['GET', 'POST'])
@login_required
def chat_window(seller_id):
    buyer_id = session['user_id']
    product_id = request.args.get('product_id', type=int)
    seller = User.query.get_or_404(seller_id)
    chat_messages = StoreChatMessage.query.filter_by(buyer_id=buyer_id, seller_id=seller_id).order_by(StoreChatMessage.created_at.asc()).all()
    # Mark all as read
    StoreChatMessage.query.filter_by(buyer_id=buyer_id, seller_id=seller_id, sender_role='seller').update({'is_read': True})
    db.session.commit()

    # Get all seller products for attachment
    buyer_products = Product.query.filter_by(seller_id=seller_id, status='active').all()
    prefill_product = None
    prefill_message = ""
    if product_id:
        prefill_product = Product.query.get(product_id)
        if prefill_product:
            prefill_message = f"Hi, I am interested in the {prefill_product.name} (â‚±{prefill_product.price:,.2f}). Is this item still available?"

    # Handle POST (send message)
    if request.method == 'POST':
        message = request.form.get('message')
        attached_product_id = request.form.get('product_id') or None
        chat = StoreChatMessage(
            buyer_id=buyer_id,
            seller_id=seller_id,
            message=message,
            sender_role='buyer',
            product_id=attached_product_id if attached_product_id else None,
            created_at=datetime.utcnow(),
            is_read=False
        )
        db.session.add(chat)
        db.session.commit()
        return redirect(url_for('chat_window', seller_id=seller_id))

    # Build users_by_id and computed chat list for sidebar badges
    users_by_id = {seller.id: seller}
    # Compose a minimal sidebar with single selected chat and unread=0
    chats = []
    last_msg = chat_messages[-1].message if chat_messages else ''
    chats.append(type('Obj', (), {'seller_id': seller.id, 'last_message': last_msg, 'unread_count': 0}))
    return render_template(
        'store_chat.html',
        chats=chats,
        users_by_id=users_by_id,
        chat_messages=chat_messages,
        selected_chat=seller,
        buyer_products=buyer_products,
        prefill_product=prefill_product,
        prefill_message=prefill_message
    )

# Seller chat with buyers
@app.route('/seller/chat/<int:buyer_id>', methods=['GET', 'POST'])
@login_required
@seller_required
def seller_chat_with_buyer(buyer_id):
    seller_id = session['user_id']
    buyer = User.query.get_or_404(buyer_id)
    
    # Get chat messages between this seller and buyer
    chat_messages = StoreChatMessage.query.filter_by(buyer_id=buyer_id, seller_id=seller_id).order_by(StoreChatMessage.created_at.asc()).all()
    
    # Mark all messages from buyer as read
    StoreChatMessage.query.filter_by(buyer_id=buyer_id, seller_id=seller_id, sender_role='buyer').update({'is_read': True})
    db.session.commit()
    
    # Get seller products for attachment
    seller_products = Product.query.filter_by(seller_id=seller_id, status='active').all()
    
    # Handle POST (send message)
    if request.method == 'POST':
        message = request.form.get('message')
        attached_product_id = request.form.get('product_id') or None
        
        if message:
            chat = StoreChatMessage(
                buyer_id=buyer_id,
                seller_id=seller_id,
                message=message,
                sender_role='seller',
                product_id=attached_product_id if attached_product_id else None,
                created_at=datetime.utcnow(),
                is_read=False
            )
            db.session.add(chat)
            db.session.commit()
            return redirect(url_for('seller_chat_with_buyer', buyer_id=buyer_id))
    
    # Build users_by_id and computed chat list for sidebar
    users_by_id = {buyer.id: buyer}
    # Compose a minimal sidebar with single selected chat and unread=0
    chats = []
    last_msg = chat_messages[-1].message if chat_messages else ''
    chats.append(type('Obj', (), {'buyer_id': buyer.id, 'last_message': last_msg, 'unread_count': 0}))
    
    return render_template(
        'seller_chat.html',
        chats=chats,
        users_by_id=users_by_id,
        chat_messages=chat_messages,
        selected_chat=buyer,
        seller_products=seller_products
    )


@app.route('/seller/inbox')
@login_required
def seller_inbox():
    seller_id = session['user_id']
    buyer_id = request.args.get('buyer_id', type=int)
    buyers = db.session.query(User).join(StoreChatMessage, User.id == StoreChatMessage.buyer_id)\
        .filter(StoreChatMessage.seller_id == seller_id)\
        .group_by(User.id).all()
    # Add unread count and last message per buyer
    for buyer in buyers:
        buyer.unread_count = StoreChatMessage.query.filter_by(
            seller_id=seller_id, buyer_id=buyer.id, is_read=False, sender_role='buyer'
        ).count()
        buyer.last_message = StoreChatMessage.query.filter_by(
            seller_id=seller_id, buyer_id=buyer.id
        ).order_by(StoreChatMessage.created_at.desc()).first()
    chat_thread = []
    if buyer_id:
        # Mark all buyer's messages as read
        StoreChatMessage.query.filter_by(seller_id=seller_id, buyer_id=buyer_id, sender_role='buyer', is_read=False).update({'is_read': True})
        db.session.commit()
        chat_thread = StoreChatMessage.query.filter_by(seller_id=seller_id, buyer_id=buyer_id)\
            .order_by(StoreChatMessage.created_at.asc()).all()
    products = Product.query.filter_by(seller_id=seller_id, status='active').all()
    quick_replies = [
        "Hello! How can I help you today?",
        "This product is available.",
        "Shipping is usually 1-3 days.",
        "Thank you for your order!"
    ]
    return render_template(
        'seller/inbox.html',
        buyers=buyers,
        chat_thread=chat_thread,
        products=products,
        quick_replies=quick_replies,
        selected_buyer_id=buyer_id
    )



@app.route('/rider-register')
def rider_register():
    """Public rider registration entry point.

    Shows the dedicated rider signup form, which posts to /register with role="rider".
    """
    return render_template('rider/register.html')


# -----------------------------
# Rider Dashboard and API
# -----------------------------

@app.route('/rider')
@login_required
@rider_required
def rider_dashboard():
    user_id = session['user_id']
    rider_profile = DeliveryPersonnel.query.filter_by(user_id=user_id).first()
    notifications = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).limit(20).all()

    earnings_today = get_user_earnings(user_id, 'today')
    earnings_week = get_user_earnings(user_id, 'week')
    earnings_month = get_user_earnings(user_id, 'month')

    # Completed deliveries count (delivered by this rider)
    completed_deliveries = Order.query.filter(
        Order.delivered_by == user_id,
        Order.status.in_(['delivered', 'completed'])
    ).count()

    # Rider payout metrics
    delivered_not_completed = Order.query.filter(
        Order.picked_up_by == user_id,
        Order.status == 'delivered'
    ).all()
    pending_payout_amount = sum(float(o.total_amount) * RIDER_EARNING_RATE for o in delivered_not_completed)
    released_amount = WalletTransaction.query.with_entities(db.func.coalesce(db.func.sum(WalletTransaction.amount), 0.0))\
        .filter_by(user_id=user_id, type='credit', source='order_commission').scalar() or 0.0

    # Earnings trend (last 14 days)
    from sqlalchemy import func
    days = 14
    base_q = db.session.query(
        func.date(WalletTransaction.created_at).label('d'),
        func.coalesce(func.sum(WalletTransaction.amount), 0.0).label('amt')
    ).filter(
        WalletTransaction.user_id == user_id,
        WalletTransaction.type == 'credit',
        WalletTransaction.source == 'order_commission'
    ).group_by(func.date(WalletTransaction.created_at)).all()
    by_date = {str(d): float(a) for d, a in base_q}
    from datetime import date, timedelta
    labels = []
    values = []
    today = date.today()
    for i in range(days-1, -1, -1):
        dt = today - timedelta(days=i)
        key = dt.strftime('%Y-%m-%d')
        labels.append(key)
        values.append(round(by_date.get(key, 0.0), 2))

    # Available orders for immediate render (subset)
    available_orders = Order.query.filter_by(status='ready_for_pickup').order_by(Order.created_at.asc()).limit(20).all()

    # Active orders for this rider
    active_orders = Order.query.filter(
        Order.picked_up_by == user_id,
        Order.status.in_(['to_ship', 'in_transit'])
    ).order_by(Order.updated_at.desc()).all()

    is_online = bool(rider_profile and rider_profile.status in ('on_duty',))

# Return pickups counters for quick access on dashboard
    returns_available_count = ReturnPickup.query.filter_by(status='available').count()
    returns_active_count = ReturnPickup.query.filter(ReturnPickup.rider_id==user_id, ReturnPickup.status.in_(['waiting_rider_pickup','rider_picked_up','rider_delivered_to_seller'])).count()

    return render_template('rider/dashboard.html',
                           rider=rider_profile,
                           notifications=notifications,
                           earnings_today=earnings_today,
                           earnings_week=earnings_week,
                           earnings_month=earnings_month,
                           completed_deliveries=completed_deliveries,
                           pending_payout_amount=pending_payout_amount,
                           released_amount=released_amount,
                           is_online=is_online,
                           earnings_labels=labels,
                           earnings_values=values,
                           available_orders=available_orders,
                           active_orders=active_orders,
                           returns_available_count=returns_available_count,
                           returns_active_count=returns_active_count)


@app.route('/rider/orders')
@login_required
@rider_required
def rider_orders_list():
    user_id = session['user_id']
    status = request.args.get('status', 'all')
    search = request.args.get('q', '').strip()
    date_from = request.args.get('from')
    date_to = request.args.get('to')

    # Incoming ready_for_pickup orders (not yet assigned)
    incoming_q = Order.query.filter_by(status='ready_for_pickup')

    # My orders
    my_q = Order.query.filter(Order.picked_up_by == user_id)

    # Apply filters to my orders
    if status != 'all':
        my_q = my_q.filter(Order.status == status)
    if search:
        my_q = my_q.join(User, Order.buyer_id == User.id).filter(
            db.or_(db.cast(Order.id, db.String).ilike(f"%{search}%"),
                   User.first_name.ilike(f"%{search}%"),
                   User.last_name.ilike(f"%{search}%"))
        )
    from datetime import datetime as _dt
    try:
        if date_from:
            my_q = my_q.filter(Order.created_at >= _dt.strptime(date_from, '%Y-%m-%d'))
        if date_to:
            my_q = my_q.filter(Order.created_at <= _dt.strptime(date_to, '%Y-%m-%d'))
    except Exception:
        pass

    incoming_orders = incoming_q.order_by(Order.created_at.asc()).all()
    my_orders = my_q.order_by(Order.created_at.desc()).all()

    return render_template('rider/orders.html', incoming_orders=incoming_orders, my_orders=my_orders, status=status, q=search, date_from=date_from or '', date_to=date_to or '')


@app.route('/rider/orders/<int:order_id>')
@login_required
@rider_required
def rider_order_detail(order_id):
    user_id = session['user_id']
    order = Order.query.get_or_404(order_id)
    # Allow viewing if it's ready or belongs to rider
    if not (order.status == 'ready_for_pickup' or order.picked_up_by == user_id):
        flash('You are not allowed to view this order.', 'error')
        return redirect(url_for('rider_orders_list'))

    # Ensure QR code exists
    if not getattr(order, 'qr_code', None):
        try:
            order.qr_code = generate_qr_code(order.id)
            db.session.commit()
        except Exception:
            db.session.rollback()
    qr_img_b64 = create_qr_image(order.qr_code) if order.qr_code else None

    # Resolve seller info (first item)
    seller = None
    store_name = None
    pickup_address = None
    try:
        first_item = order.items[0] if order.items else None
        if first_item:
            seller = first_item.product.seller
            appq = SellerApplication.query.filter_by(user_id=seller.id, status='approved').first()
            store_name = appq.store_name if appq else None
            pickup_address = appq.business_address if appq else None
    except Exception:
        pass

    return render_template('rider/order_detail.html', order=order, qr_img_b64=qr_img_b64, seller=seller, store_name=store_name, pickup_address=pickup_address)


@app.route('/rider/profile')
@login_required
@rider_required
def rider_profile_settings():
    user = User.query.get(session['user_id'])
    rp = DeliveryPersonnel.query.filter_by(user_id=user.id).first()
    return render_template('rider/profile.html', user=user, rider_profile=rp)


@app.route('/rider/profile', methods=['POST'])
@login_required
@rider_required
def rider_profile_update():
    user = User.query.get(session['user_id'])
    rp = DeliveryPersonnel.query.filter_by(user_id=user.id).first()
    if not rp:
        rp = DeliveryPersonnel(user_id=user.id, employee_id=f'EMP{user.id:04d}', name=f"{user.first_name} {user.last_name}", phone=user.phone, status='active')
        db.session.add(rp)
        db.session.flush()

    # Update personal info
    first = request.form.get('first_name', user.first_name).strip()
    last = request.form.get('last_name', user.last_name).strip()
    phone_raw = request.form.get('phone', user.phone or '').strip()
    phone_digits = ''.join(ch for ch in (phone_raw or '') if ch.isdigit())
    if phone_digits and len(phone_digits) != 11:
        flash('Contact number must be exactly 11 digits.', 'danger')
        return redirect(url_for('rider_profile_settings'))

    user.first_name = first or user.first_name
    user.last_name = last or user.last_name
    if phone_digits:
        user.phone = phone_digits
        rp.phone = phone_digits

    rp.address = request.form.get('address', rp.address or '')
    rp.id_type = request.form.get('id_type', rp.id_type or '')
    rp.id_number = request.form.get('id_number', rp.id_number or '')

    # ID document upload
    idf = request.files.get('id_document')
    if idf and idf.filename:
        safe = secure_filename(idf.filename)
        filename = datetime.utcnow().strftime('%Y%m%d_%H%M%S_') + safe
        dest_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'documents')
        os.makedirs(dest_dir, exist_ok=True)
        idf.save(os.path.join(dest_dir, filename))
        rp.id_document = f"/static/uploads/documents/{filename}"

    # Avatar upload
    file = request.files.get('avatar')
    if file and file.filename:
        try:
            from PIL import Image
            avatar_dir = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'], 'user_avatars')
            os.makedirs(avatar_dir, exist_ok=True)
            temp_path = os.path.join(avatar_dir, f"tmp_user_{user.id}")
            file.save(temp_path)
            img = Image.open(temp_path)
            img = img.convert('RGB')
            img.thumbnail((256, 256))
            final_name = f"user_avatar_{user.id}.png"
            img.save(os.path.join(avatar_dir, final_name), format='PNG')
            rp.photo_path = f"/static/uploads/user_avatars/{final_name}"
        except Exception:
            pass
        finally:
            try:
                if 'temp_path' in locals() and os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass

    db.session.commit()
    
    # Update session user_name to reflect changes in dropdown
    session['user_name'] = f"{user.first_name} {user.last_name}"
    
    # Update session with new avatar URL for immediate dropdown update
    avatar_rel = os.path.join('user_avatars', f"user_avatar_{user.id}.png")
    upload_root = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
    avatar_path = os.path.join(upload_root, avatar_rel)
    if os.path.exists(avatar_path):
        session['navbar_avatar_url'] = url_for('static', filename=f'uploads/{avatar_rel.replace("\\", "/")}')
        session['avatar_timestamp'] = int(time.time())  # Force cache refresh
    
    flash('Profile updated successfully.', 'success')
    return redirect(url_for('rider_profile_settings'))


@app.route('/rider/notifications')
@login_required
@rider_required
def rider_notifications():
    user_id = session['user_id']
    notifications = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).all()
    Notification.query.filter_by(user_id=user_id, is_read=False).update({Notification.is_read: True})
    db.session.commit()
    return render_template('rider/notifications.html', notifications=notifications)


@app.route('/rider/toggle-availability', methods=['POST'])
@login_required
@rider_required
def rider_toggle_availability():
    user_id = session['user_id']
    rp = DeliveryPersonnel.query.filter_by(user_id=user_id).first()
    if not rp:
        return jsonify({'success': False, 'message': 'No rider profile found.'}), 400
    # Toggle between on_duty and off_duty
    rp.status = 'off_duty' if rp.status == 'on_duty' else 'on_duty'
    db.session.commit()
    return jsonify({'success': True, 'status': rp.status})


@app.route('/rider/orders/available')
@login_required
@rider_required
def rider_available_orders():
    # Only show orders marked ready_for_pickup (not yet accepted). In this flow, orders are single-seller.
    orders = Order.query.filter_by(status='ready_for_pickup').order_by(Order.created_at.asc()).all()

    def _default_coords(uid):
        addr = Address.query.filter_by(user_id=uid, is_default=True).first()
        if addr and addr.latitude is not None and addr.longitude is not None:
            return float(addr.latitude), float(addr.longitude)
        return None, None

    def _haversine_km(lat1, lon1, lat2, lon2):
        from math import radians, sin, cos, asin, sqrt
        R = 6371.0
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
        c = 2*asin(sqrt(a))
        return R*c

    as_dict = []
    for o in orders:
        # Resolve primary seller and pickup address (best-effort)
        seller = o.items[0].product.seller if o.items else None
        seller_name = f"{seller.first_name} {seller.last_name}" if seller else "Seller"
        pickup_address = None
        try:
            if seller and getattr(seller, 'seller_applications', None):
                appq = seller.seller_applications.filter_by(status='approved').first()
                if appq and appq.business_address:
                    pickup_address = appq.business_address
        except Exception:
            pickup_address = None

        # Distance best-effort: default addresses if both sides have coordinates
        dist_km = None
        try:
            if seller:
                s_lat, s_lon = _default_coords(seller.id)
                b_lat, b_lon = _default_coords(o.buyer_id)
                if s_lat is not None and b_lat is not None:
                    dist_km = round(_haversine_km(s_lat, s_lon, b_lat, b_lon), 1)
        except Exception:
            dist_km = None

        as_dict.append({
            'id': o.id,
            'total_amount': float(o.total_amount),
            'created_at': o.created_at.isoformat(),
            'seller_ids': list({it.product.seller_id for it in o.items}),
            'seller_name': seller_name,
            'pickup_address': pickup_address,
            'dropoff_address': o.shipping_address,
            'fare_estimate': round(float(o.total_amount) * RIDER_EARNING_RATE, 2),
            'distance_km': dist_km
        })
    return jsonify({'orders': as_dict})


def _order_seller_ids(order):
    return list({it.product.seller_id for it in order.items})


def _emit_order_update(event_name, order):
    payload = {
        'order_id': order.id,
        'status': order.status,
        'total_amount': order.total_amount
    }
    # Push to buyer
    try:
        socketio.emit(event_name, payload, room=f'user_{order.buyer_id}')
    except Exception:
        pass
    # Push to each seller involved
    for sid in _order_seller_ids(order):
        try:
            socketio.emit(event_name, payload, room=f'user_{sid}')
        except Exception:
            pass


def _compute_seller_stats(seller_id: int) -> dict:
    """Compute seller stats used by dashboard and real-time updates."""
    from sqlalchemy import func, distinct
    # Total orders containing this seller's products
    total_orders = db.session.query(func.count(distinct(Order.id))).join(OrderItem).join(Product)\
        .filter(Product.seller_id == seller_id).scalar() or 0

    # Delivered + completed revenue (seller-side item sum)
    delivered_statuses = ['delivered', 'completed']
    delivered_revenue = db.session.query(func.coalesce(func.sum(OrderItem.price_at_time * OrderItem.quantity), 0.0))\
        .join(Order).join(Product).filter(
            Product.seller_id == seller_id,
            Order.status.in_(delivered_statuses)
        ).scalar() or 0.0

    # Commissioned sales (wallet credits already released)
    commissioned_sales = db.session.query(func.coalesce(func.sum(WalletTransaction.amount), 0.0))\
        .filter(
            WalletTransaction.user_id == seller_id,
            WalletTransaction.type == 'credit',
            WalletTransaction.source == 'order_commission'
        ).scalar() or 0.0

    # Order status breakdown for this seller (distinct orders per status)
    def _status_count(st):
        return db.session.query(func.count(distinct(Order.id))).join(OrderItem).join(Product).filter(
            Product.seller_id == seller_id,
            Order.status == st
        ).scalar() or 0

    status_counts = {
        'pending': _status_count('pending'),
        'ready_for_pickup': _status_count('ready_for_pickup'),
        'completed': _status_count('completed'),
        'cancelled': _status_count('cancelled'),
        'delivered': _status_count('delivered')
    }

    return {
        'total_orders': int(total_orders),
        'delivered_revenue': float(delivered_revenue),
        'commissioned_sales': float(commissioned_sales),
        'status_counts': status_counts
    }


def _emit_seller_stats_update(seller_id: int):
    try:
        stats = _compute_seller_stats(seller_id)
        socketio.emit('seller_stats_update', stats, room=f'user_{seller_id}')
    except Exception:
        pass


def _deduct_stock_for_order_if_needed(order: 'Order'):
    """Idempotently deduct real stock for all products in the order if not yet deducted."""
    if getattr(order, 'stock_deducted', False):
        return
    seller_ids = set()
    for item in order.items:
        # Deduct from actual product stock
        p = item.product
        if p and isinstance(item.quantity, int):
            p.stock = max(0, int(p.stock) - int(item.quantity))
            seller_ids.add(p.seller_id)
            # Push product stock update globally and to seller
            try:
                available_stock = get_available_stock(p.id)
                socketio.emit('product_stock_update', {
                    'product_id': p.id,
                    'stock': available_stock,
                    'available_stock': available_stock
                }, broadcast=True)
            except Exception:
                pass
    order.stock_deducted = True
    db.session.commit()
    # Update sellers' dashboards
    for sid in seller_ids:
        _emit_seller_stats_update(sid)


@app.route('/rider/order/<int:order_id>/json')
@login_required
@rider_required
def rider_order_json(order_id):
    order = Order.query.get_or_404(order_id)
    # Rider can view only if ready_for_pickup or assigned to them
    if order.status not in ['ready_for_pickup','to_ship','in_transit','delivered']:
        return jsonify({'error':'Not viewable'}), 403
    if order.status != 'ready_for_pickup' and order.picked_up_by != session['user_id']:
        return jsonify({'error':'Not viewable'}), 403

    # Ensure QR exists and prepare base64 image for modal
    if not getattr(order, 'qr_code', None):
        try:
            order.qr_code = generate_qr_code(order.id)
            db.session.commit()
        except Exception:
            db.session.rollback()
    qr_img_b64 = create_qr_image(order.qr_code) if order.qr_code else None

    # Seller + store info (first seller in order)
    seller = None
    store_name = None
    pickup_address = None
    try:
        first_item = order.items[0] if order.items else None
        if first_item:
            seller = first_item.product.seller
            appq = SellerApplication.query.filter_by(user_id=seller.id, status='approved').first()
            store_name = appq.store_name if appq else None
            pickup_address = appq.business_address if appq else None
    except Exception:
        pass

    items = []
    for it in order.items:
        items.append({
            'name': it.product.name,
            'qty': it.quantity,
            'price': float(it.price_at_time),
            'seller_id': it.product.seller_id
        })

    return jsonify({
        'id': order.id,
        'buyer': {
            'name': f"{order.buyer.first_name} {order.buyer.last_name}",
            'phone': order.buyer.phone,
            'email': order.buyer.email
        },
        'shipping_address': order.shipping_address,
        'total_amount': float(order.total_amount),
        'items': items,
        'status': order.status,
        'seller': {
            'name': f"{seller.first_name} {seller.last_name}" if seller else None,
            'store_name': store_name,
        },
        'pickup_address': pickup_address,
        'qr_code': order.qr_code,
        'qr_image': (f"data:image/png;base64,{qr_img_b64}" if qr_img_b64 else None)
    })

@app.route('/rider/order/<int:order_id>/mark-delivered', methods=['POST'])
@login_required
@rider_required
def rider_mark_delivered(order_id):
    """Rider marks an order as delivered (moves from to_ship to delivered)."""
    order = Order.query.get_or_404(order_id)
    
    # Verify this order is assigned to this rider and in correct status
    if order.picked_up_by != session['user_id'] or order.status != 'to_ship':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Order cannot be marked as delivered.'})
        flash('Order cannot be marked as delivered.', 'error')
        return redirect(url_for('rider_orders_list'))
    
    try:
        # Update order status
        order.status = 'delivered'
        order.updated_at = datetime.utcnow()
        
        # Deduct stock from seller inventory when order is delivered
        # Stock was reserved when order was placed, now we actually deduct it
        if not order.stock_deducted:
            for item in order.items:
                product = Product.query.get(item.product_id)
                if product:
                    # Actually deduct the stock from seller's inventory
                    product.stock = max(0, product.stock - item.quantity)
                    app.logger.info(f'Stock deducted for Product {product.id} (-{item.quantity}) => {product.stock}')
            
            # Mark stock as deducted
            order.stock_deducted = True
            app.logger.info(f'Order {order.id} delivered: Stock deducted from seller inventory')
        
        db.session.commit()
        
        # Send notifications to buyer and sellers
        try:
            push_notification(order.buyer_id, f'Order #{order.id} has been delivered! Please confirm receipt.')
            for seller_id in _order_seller_ids(order):
                push_notification(seller_id, f'Order #{order.id} has been delivered to buyer.')
        except Exception:
            pass
        
        # Emit socket events for real-time updates
        _emit_order_update('order_delivered', order)
        
        # Update seller stats
        for seller_id in _order_seller_ids(order):
            _emit_seller_stats_update(seller_id)
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': 'Order marked as delivered.'})
        flash('Order marked as delivered successfully.', 'success')
        return redirect(url_for('rider_orders_list'))
        
    except Exception as e:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Error marking order as delivered.'})
        flash('Error marking order as delivered. Please try again.', 'error')
        return redirect(url_for('rider_orders_list'))


@app.route('/buyer/order/<int:order_id>/confirm-receipt', methods=['POST'])
@login_required
def buyer_confirm_receipt(order_id):
    """Buyer confirms order receipt (moves from delivered to completed)."""
    order = Order.query.get_or_404(order_id)
    
    # Verify this order belongs to the buyer and is in delivered status
    if order.buyer_id != session['user_id'] or order.status != 'delivered':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Order cannot be confirmed.'})
        flash('Order cannot be confirmed.', 'error')
        return redirect(url_for('my_orders'))
    
    try:
        # Update order status
        order.status = 'completed'
        order.updated_at = datetime.utcnow()
        
        # 🎯 RULE 4: ORDER COMPLETION DOES NOT RETURN STOCK
        # Stock was already deducted when order was placed, so no action needed here
        # Even if all stocks are bought, product stays Out of Stock
        app.logger.info(f'Order {order.id} completed: No stock action taken (already deducted at order placement)')
        
        db.session.commit()
        
        # Send notifications to sellers
        try:
            for seller_id in _order_seller_ids(order):
                push_notification(seller_id, f'Order #{order.id} has been confirmed by buyer and completed!')
        except Exception:
            pass
        
        # Emit socket events for real-time updates
        _emit_order_update('order_completed', order)
        
        # Update seller stats
        for seller_id in _order_seller_ids(order):
            _emit_seller_stats_update(seller_id)
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': 'Order confirmed and completed!'})
        flash('Order confirmed successfully! Thank you for your purchase.', 'success')
        return redirect(url_for('my_orders'))
        
    except Exception as e:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Error confirming order.'})
        flash('Error confirming order. Please try again.', 'error')
        return redirect(url_for('my_orders'))


def _order_seller_ids(order):
    """Helper function to get all seller IDs for an order."""
    return list(set(item.product.seller_id for item in order.items))


def _emit_seller_stats_update(seller_id):
    """Emit real-time stats update to seller."""
    try:
        # Import socketio here to avoid circular imports
        from flask_socketio import emit
        socketio.emit('stats_update', room=f'seller_{seller_id}')
    except Exception:
        pass


@app.route('/rider/order/<int:order_id>/accept', methods=['POST'])
@login_required
@rider_required
def rider_accept_order(order_id):
    order = Order.query.get_or_404(order_id)
    if order.status != 'ready_for_pickup':
        flash('Order is not available for acceptance.', 'error')
        return redirect(url_for('rider_dashboard'))

    # Assign rider and move to to_ship immediately
    order.picked_up_by = session['user_id']
    order.picked_up_at = datetime.utcnow()
    order.status = 'to_ship'
    order.updated_at = datetime.utcnow()
    db.session.commit()

    # Notify buyer and sellers
    push_notification(order.buyer_id, f'Rider accepted order #{order.id}.')
    for sid in _order_seller_ids(order):
        push_notification(sid, f'Your order #{order.id} was accepted by a rider.')

    _emit_order_update('order_accepted', order)
    flash('Order accepted.', 'success')
    return redirect(url_for('rider_dashboard'))


@app.route('/rider/order/<int:order_id>/reject', methods=['POST'])
@login_required
@rider_required
def rider_reject_order(order_id):
    order = Order.query.get_or_404(order_id)
    if order.status != 'ready_for_pickup':
        flash('Order is not available for rejection.', 'error')
        return redirect(url_for('rider_dashboard'))

    # Order remains in ready_for_pickup status for other riders to see
    # Just remove it from this rider's view
    flash('Order rejected. Available for other riders.', 'info')
    return redirect(url_for('rider_dashboard'))


@app.route('/rider/order/<int:order_id>/picked-up', methods=['POST'])
@login_required
@rider_required
def rider_mark_picked_up(order_id):
    order = Order.query.get_or_404(order_id)
    if order.picked_up_by != session['user_id']:
        flash('You cannot mark this order as picked up.', 'error')
        return redirect(url_for('rider_dashboard'))
    # Normalize to new flow: picked up => to_ship
    order.status = 'to_ship'
    if not order.picked_up_at:
        order.picked_up_at = datetime.utcnow()
    db.session.commit()

    push_notification(order.buyer_id, f'Rider picked up order #{order.id}.')
    for sid in _order_seller_ids(order):
        push_notification(sid, f'Order #{order.id} picked up by rider.')

    _emit_order_update('order_picked_up', order)
    flash('Order marked as picked up.', 'success')
    return redirect(url_for('rider_dashboard'))


@app.route('/rider/active/<int:order_id>')
@login_required
@rider_required
def rider_active_order(order_id):
    order = Order.query.get_or_404(order_id)
    if order.picked_up_by != session['user_id'] and order.status not in ['ready_for_pickup','to_ship','in_transit','delivered']:
        flash('Not allowed to view this order.', 'error')
        return redirect(url_for('rider_dashboard'))
    # Resolve pickup address
    seller = order.items[0].product.seller if order.items else None
    pickup_address = None
    try:
        if seller and getattr(seller, 'seller_applications', None):
            appq = seller.seller_applications.filter_by(status='approved').first()
            if appq and appq.business_address:
                pickup_address = appq.business_address
    except Exception:
        pickup_address = None
    # Buyer default address for lat/lng
    s_lat = s_lon = b_lat = b_lon = None
    try:
        s_addr = Address.query.filter_by(user_id=seller.id, is_default=True).first() if seller else None
        b_addr = Address.query.filter_by(user_id=order.buyer_id, is_default=True).first()
        if s_addr and s_addr.latitude is not None and s_addr.longitude is not None:
            s_lat, s_lon = float(s_addr.latitude), float(s_addr.longitude)
        if b_addr and b_addr.latitude is not None and b_addr.longitude is not None:
            b_lat, b_lon = float(b_addr.latitude), float(b_addr.longitude)
    except Exception:
        pass
    return render_template('rider/active.html', order=order, pickup_address=pickup_address,
                           s_lat=s_lat, s_lon=s_lon, b_lat=b_lat, b_lon=b_lon)


@app.route('/rider/order/<int:order_id>/problem', methods=['POST'])
@login_required
@rider_required
def rider_problem_report(order_id):
    order = Order.query.get_or_404(order_id)
    if order.picked_up_by and order.picked_up_by != session['user_id']:
        return jsonify({'success': False, 'message': 'Not allowed'}), 403
    note = request.form.get('note', '').strip() or 'Problem reported by rider.'
    order.delivery_notes = (order.delivery_notes or '') + f"\n[{datetime.utcnow().isoformat()}] {note}"
    db.session.commit()
    push_notification(order.buyer_id, f'Rider reported a delivery issue for Order #{order.id}.')
    for sid in _order_seller_ids(order):
        push_notification(sid, f'Rider reported a delivery issue for Order #{order.id}.')
    return jsonify({'success': True})


@app.route('/rider/order/<int:order_id>/cancel', methods=['POST'])
@login_required
@rider_required
def rider_cancel_order(order_id):
    order = Order.query.get_or_404(order_id)
    if order.status not in ['ready_for_pickup', 'to_ship', 'in_transit'] or \
       (order.picked_up_by and order.picked_up_by != session['user_id']):
        flash('You cannot cancel this order now.', 'error')
        return redirect(url_for('rider_dashboard'))

    order.status = 'cancelled'
    order.updated_at = datetime.utcnow()
    # Reset assignment if any
    if order.picked_up_by == session['user_id']:
        order.picked_up_by = None
    db.session.commit()

    push_notification(order.buyer_id, f'Order #{order.id} was cancelled by rider.')
    for sid in _order_seller_ids(order):
        push_notification(sid, f'Order #{order.id} was cancelled by rider.')

    _emit_order_update('order_cancelled', order)
    flash('Order cancelled.', 'info')
    return redirect(url_for('rider_dashboard'))


@app.route('/registration-status')
def registration_status():
    """Simple confirmation view shown after a successful registration.

    Displays a professional confirmation message and current review status
    for buyers and riders (front-end status only).
    """
    role = (request.args.get('role') or 'buyer').strip().lower()
    if role not in ('buyer', 'rider'):
        role = 'buyer'
    return render_template('registration_status.html', role=role)


@app.route('/admin/approve-rider/<int:app_id>', methods=['GET', 'POST'])
@admin_required
def approve_rider(app_id):
    application = RiderApplication.query.get_or_404(app_id)
    application.status = 'approved'
    application.reviewed_at = datetime.utcnow()
    application.reviewed_by = session['user_id']
    rider = DeliveryPersonnel(
        user_id=application.user_id,
        employee_id=f"EMP{application.id:04d}",
        name=f"{application.user.first_name} {application.user.last_name}",
        phone=application.user.phone,
        vehicle_type=application.vehicle_type,
        vehicle_number=application.vehicle_number,
        status='active'
    )
    db.session.add(rider)
    application.user.role = 'rider'
    db.session.commit()
    flash('Rider application approved successfully!', 'success')
    return redirect(url_for('admin_rider_applications'))


@app.route('/admin/reject-rider/<int:app_id>', methods=['POST'])
@admin_required
def reject_rider(app_id):
    application = RiderApplication.query.get_or_404(app_id)
    application.status = 'rejected'
    application.reviewed_at = datetime.utcnow()
    application.reviewed_by = session['user_id']
    
    # Get rejection reason from form if provided
    reason = request.form.get('reason', '')
    
    db.session.commit()
    flash('Rider application rejected.', 'info')
    return redirect(url_for('admin_rider_applications'))




@app.route('/seller/send-message/<int:buyer_id>', methods=['POST'])
@login_required
def send_chat_message(buyer_id):
    seller_id = session['user_id']
    message = request.form.get('message')
    product_id = request.form.get('product_id')
    if message:
        chat = StoreChatMessage(
            buyer_id=buyer_id,
            seller_id=seller_id,
            message=message,
            sender_role='seller',
            product_id=product_id if product_id else None,
            created_at=datetime.utcnow(),
            is_read=False
        )
        db.session.add(chat)
        db.session.commit()
        try:
            push_notification(
                buyer_id,
                'New message from seller.',
                type='chat',
                link=url_for('chat_window', seller_id=seller_id),
                actor_user_id=seller_id
            )
        except Exception:
            pass
        try:
            socketio.emit('new_message', {
                'from_user_id': seller_id,
                'to_user_id': buyer_id,
                'sender_role': 'seller',
                'message': message
            }, room=f'user_{buyer_id}')
        except Exception:
            pass
    return redirect(url_for('seller_inbox', buyer_id=buyer_id))


@app.route('/send-message/<int:seller_id>', methods=['POST'])
@login_required
def send_message(seller_id):
    buyer_id = session['user_id']
    message = request.form['message']
    product_id = request.form.get('product_id')
    chat_msg = StoreChatMessage(
        buyer_id=buyer_id,
        seller_id=seller_id,
        product_id=product_id if product_id else None,
        message=message,
        sender_role='buyer'
    )
    db.session.add(chat_msg)
    db.session.commit()
    try:
        push_notification(
            seller_id,
            'New message from a buyer.',
            type='chat',
            link=url_for('seller_inbox', buyer_id=buyer_id),
            actor_user_id=buyer_id
        )
    except Exception:
        pass
    try:
        socketio.emit('new_message', {
            'from_user_id': buyer_id,
            'to_user_id': seller_id,
            'sender_role': 'buyer',
            'message': message
        }, room=f'user_{seller_id}')
    except Exception:
        pass
    return redirect(url_for('chat_window', seller_id=seller_id))

# ===== Return & Refund Routes =====
@app.route('/buyer/returns')
@login_required
def buyer_returns_index():
    rr = ReturnRequest.query.filter(
        ReturnRequest.buyer_id == session['user_id'],
        ReturnRequest.status != 'cancelled'
    ).order_by(ReturnRequest.created_at.desc()).all()
    return render_template('buyer/returns_index.html', requests=rr)

@app.route('/buyer/returns/new/<int:order_item_id>', methods=['GET','POST'])
@login_required
def buyer_new_return(order_item_id):
    item = OrderItem.query.get_or_404(order_item_id)
    order = Order.query.get_or_404(item.order_id)
    if order.buyer_id != session['user_id']:
        flash('Not allowed.', 'danger')
        return redirect(url_for('my_orders'))
    # Eligibility: delivered OR completed within 7 days
    eligible = False
    if order.status == 'delivered':
        eligible = True
    elif order.status == 'completed':
        try:
            if order.delivered_at and (datetime.utcnow() - order.delivered_at) <= timedelta(days=7):
                eligible = True
        except Exception:
            eligible = False
    if not eligible:
        flash('Return/Refund can only be requested after delivery and within 7 days of completion.', 'warning')
        return redirect(url_for('my_orders'))

    # Prevent duplicate active request for same item
    dup = ReturnRequest.query.filter(
        ReturnRequest.order_item_id == item.id,
        ReturnRequest.status.in_(['submitted','waiting_seller_approval','refund_approved','return_approved','waiting_rider_pickup','rider_picked_up_item','rider_delivered_to_seller','seller_checking_item','refund_processing'])
    ).first()
    if dup:
        return redirect(url_for('buyer_return_detail', return_id=dup.id))

    if request.method == 'POST':
        request_type = (request.form.get('request_type') or '').strip().lower()  # 'return' | 'refund'
        reason = (request.form.get('reason') or '').strip()
        reason_other = (request.form.get('reason_other') or '').strip()
        description = (request.form.get('description') or '').strip()
        qty = max(1, min(int(request.form.get('quantity','1') or 1), int(item.quantity)))

        # Server-side validations using unified 'media[]'
        errors = []
        if request_type not in ('return','refund'):
            errors.append('Please select Return or Refund.')
        if not reason:
            errors.append('Please select a reason for your return/refund.')
        if reason == 'Others' and not reason_other:
            errors.append('Please provide the reason details for "Others".')
        media_list = [f for f in request.files.getlist('media[]') if f and f.filename]
        if len(media_list) == 0:
            errors.append('Please upload at least one photo or video as evidence.')
        # limit
        if len(media_list) > 6:
            media_list = media_list[:6]
        if not description:
            errors.append('Please describe the issue in the description box.')

        # Classify by extension
        ALLOWED_IMAGES = {'jpg','jpeg','png'}
        ALLOWED_VIDEOS = {'mp4','mov'}
        imgs = []
        vids = []
        for f in media_list:
            ext = (f.filename.rsplit('.',1)[-1] if '.' in f.filename else '').lower()
            if ext in ALLOWED_IMAGES:
                imgs.append(f)
            elif ext in ALLOWED_VIDEOS:
                vids.append(f)
            else:
                errors.append(f'Unsupported file type: {ext}. Allowed: JPG, PNG, MP4, MOV.')
        # Only keep first video if multiple
        if len(vids) > 1:
            vids = vids[:1]

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('buyer/return_form.html', order=order, item=item)

        rr = ReturnRequest(
            order_id=order.id,
            order_item_id=item.id,
            buyer_id=order.buyer_id,
            seller_id=item.product.seller_id,
            reason=reason,
            reason_other=reason_other if reason == 'Others' else None,
            description=description,
            quantity=qty,
            request_type=request_type,
            status='submitted'
        )
        db.session.add(rr)
        db.session.flush()
        # Evidence uploads
        saved_images = []
        base_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'returns', str(rr.id))
        os.makedirs(os.path.join(base_dir, 'images'), exist_ok=True)
        for f in imgs[:6]:
            name = datetime.utcnow().strftime('%Y%m%d_%H%M%S_') + secure_filename(f.filename)
            f.save(os.path.join(base_dir, 'images', name))
            saved_images.append(f'returns/{rr.id}/images/{name}')
        # Save first video if any
        video_path = None
        if vids:
            os.path.exists(os.path.join(base_dir, 'video')) or os.makedirs(os.path.join(base_dir, 'video'), exist_ok=True)
            v = vids[0]
            vname = datetime.utcnow().strftime('%Y%m%d_%H%M%S_') + secure_filename(v.filename)
            v.save(os.path.join(base_dir, 'video', vname))
            video_path = f'returns/{rr.id}/video/{vname}'
        
        # Update the return request with saved media paths
        rr.images = saved_images if saved_images else None
        rr.video_filename = video_path
        db.session.commit()
        # Update order status (buyer-facing) to indicate submission
        try:
            order.status = 'return_submitted'
            order.updated_at = datetime.utcnow()
        except Exception:
            pass
        db.session.commit()
        # Notify parties and emit realtime update
        push_notification(item.product.seller_id, f'Return/Refund requested for Order #{order.id} — {item.product.name}.')
        push_notification(order.buyer_id, f'Return/Refund request RR-{rr.id} submitted.')
        _emit_return_update(rr)
        flash('Return/Refund Request Submitted Successfully', 'success')
        return redirect(url_for('buyer_return_detail', return_id=rr.id))

    return render_template('buyer/return_form.html', order=order, item=item)

@app.route('/buyer/returns/<int:return_id>')
@login_required
def buyer_return_detail(return_id):
    rr = ReturnRequest.query.get_or_404(return_id)
    if rr.buyer_id != session['user_id']:
        flash('Not allowed.', 'danger')
        return redirect(url_for('buyer_returns_index'))
    return render_template('buyer/return_detail.html', rr=rr)

@app.route('/buyer/returns/<int:return_id>/cancel', methods=['POST'])
@login_required
def buyer_return_cancel(return_id):
    rr = ReturnRequest.query.get_or_404(return_id)
    if rr.buyer_id != session['user_id']:
        flash('Not allowed.', 'danger')
        return redirect(url_for('buyer_returns_index'))
    if rr.status not in ['submitted', 'waiting_seller_approval', 'seller_reviewing']:
        flash('You can cancel only before the seller processes your request.', 'warning')
        return redirect(url_for('buyer_return_detail', return_id=return_id))
    rr.status = 'cancelled'
    db.session.commit()
    push_notification(rr.seller_id, f'Buyer cancelled the return/refund request RR-{rr.id}.')
    flash('Return request cancelled successfully! You can submit a new request anytime.', 'success')
    return redirect(url_for('buyer_returns_index'))

# Seller review actions
@app.route('/seller/returns')
@seller_required
def seller_returns_index():
    seller_id = session['user_id']

    # Get all return requests for this seller EXCEPT cancelled ones
    all_return_requests = ReturnRequest.query.filter(
        ReturnRequest.seller_id == seller_id,
        ReturnRequest.status != 'cancelled'
    ).order_by(ReturnRequest.created_at.desc()).all()

    # Filter pending requests - only show submitted status
    pending_requests = [r for r in all_return_requests if r.status in [
        'submitted', 'seller_reviewing', 'waiting_seller_approval'
    ]]

    # Get completed returns/refunds for this seller - only fully completed ones
    completed_returns = ReturnRequest.query.filter(
        ReturnRequest.seller_id == seller_id,
        ReturnRequest.status.in_(['completed', 'refunded'])
    ).order_by(ReturnRequest.updated_at.desc()).all()

    # Get statistics
    total_requests = len(all_return_requests)
    pending_count = len(pending_requests)
    completed_count = len(completed_returns)
    approved_requests = len([r for r in all_return_requests if r.status in ['waiting_rider_pickup', 'rider_to_seller', 'item_received_by_seller', 'refund_processing', 'refunded']])

    return render_template('seller/returns.html',
                         requests=pending_requests,  # Only pending requests
                         completed_returns=completed_returns,
                         total_requests=total_requests,
                         pending_requests=pending_count,
                         completed_count=completed_count,
                         approved_requests=approved_requests)

@app.route('/seller/returns/<int:return_id>')
@seller_required
def seller_return_detail(return_id):
    rr = ReturnRequest.query.get_or_404(return_id)
    if rr.seller_id != session['user_id']:
        flash('Not allowed.', 'danger')
        return redirect(url_for('seller_returns_index'))
    
    # Mark as under review if this is the first view
    if rr.status == 'submitted':
        rr.status = 'waiting_seller_approval'
        db.session.commit()
    
    return render_template('seller/return_detail.html', rr=rr)

@app.route('/seller/returns/<int:return_id>/approve', methods=['POST'])
@seller_required
def seller_return_approve(return_id):
    rr = ReturnRequest.query.get_or_404(return_id)
    if rr.seller_id != session['user_id']:
        flash('Not allowed.', 'danger')
        return redirect(url_for('seller_returns_index'))
    
    if rr.request_type == 'refund':
        # REFUND ONLY - No rider involvement
        rr.status = 'refund_approved'
        # Process refund immediately
        try:
            amount = float(rr.order_item.price_at_time) * int(rr.order_item.quantity)
            credit_wallet(rr.buyer_id, amount, 'return_refund', rr.order_id)
            rr.refund_amount = amount
            rr.status = 'refunded'
            # Update order status
            rr.order.status = 'refunded'
            rr.order.updated_at = datetime.utcnow()
        except Exception as e:
            app.logger.error(f"Refund processing error: {e}")
            rr.status = 'refund_processing'
        
        db.session.commit()
        push_notification(rr.buyer_id, f'Refund for RR-{rr.id} has been approved and processed.')
        _emit_return_update(rr)
        
    else:  # rr.request_type == 'return'
        # RETURN ITEM - Rider involvement required
        rr.status = 'return_approved'
        # Create rider pickup task
        buyer_addr = rr.order.shipping_address
        seller_addr = None
        try:
            appq = SellerApplication.query.filter_by(user_id=rr.seller_id, status='approved').first()
            seller_addr = appq.business_address if appq and appq.business_address else ''
        except Exception:
            seller_addr = ''
        task = ReturnPickup(return_request_id=rr.id, buyer_address=buyer_addr, seller_address=seller_addr, status='available')
        db.session.add(task)
        db.session.commit()
        push_notification(rr.buyer_id, f'Return request RR-{rr.id} approved. A rider will pick up your item.')
        try:
            socketio.emit('return_pickup_available', {'return_id': rr.id}, room='riders')
        except Exception:
            pass
        _emit_return_update(rr)
    
    return redirect(url_for('seller_return_detail', return_id=return_id))

@app.route('/seller/returns/<int:return_id>/reject', methods=['POST'])
@seller_required
def seller_return_reject(return_id):
    rr = ReturnRequest.query.get_or_404(return_id)
    if rr.seller_id != session['user_id']:
        flash('Not allowed.', 'danger')
        return redirect(url_for('seller_returns_index'))
    rr.status = 'rejected'
    rr.seller_response_reason = (request.form.get('seller_reason') or 'No reason provided.').strip()
    db.session.commit()
    push_notification(rr.buyer_id, f'Return request RR-{rr.id} was rejected. Reason: {rr.seller_response_reason}')
    _emit_return_update(rr)
    return redirect(url_for('seller_return_detail', return_id=return_id))

@app.route('/seller/returns/<int:return_id>/mark-received', methods=['POST'])
@seller_required
def seller_return_mark_received(return_id):
    rr = ReturnRequest.query.get_or_404(return_id)
    if rr.seller_id != session['user_id']:
        flash('Not allowed.', 'danger')
        return redirect(url_for('seller_returns_index'))
    
    # Update status to show seller is checking item
    rr.status = 'seller_checking_item'
    db.session.commit()
    _emit_return_update(rr)
    
    return redirect(url_for('seller_return_detail', return_id=return_id))

@app.route('/seller/returns/<int:return_id>/start-refund', methods=['POST'])
@seller_required
def seller_return_start_refund(return_id):
    rr = ReturnRequest.query.get_or_404(return_id)
    if rr.seller_id != session['user_id']:
        flash('Not allowed.', 'danger')
        return redirect(url_for('seller_returns_index'))
    rr.status = 'refund_processing'
    db.session.commit()
    _emit_return_update(rr)
    push_notification(rr.buyer_id, f'Refund for RR-{rr.id} is processing.')
    return redirect(url_for('seller_return_detail', return_id=return_id))

@app.route('/seller/returns/<int:return_id>/complete', methods=['POST'])
@seller_required
def seller_return_complete(return_id):
    rr = ReturnRequest.query.get_or_404(return_id)
    if rr.seller_id != session['user_id']:
        flash('Not allowed.', 'danger')
        return redirect(url_for('seller_returns_index'))
    
    # Credit buyer wallet
    try:
        amount = float(rr.order_item.price_at_time) * int(rr.order_item.quantity)
        credit_wallet(rr.buyer_id, amount, 'return_refund', rr.order_id)
        rr.refund_amount = amount
    except Exception:
        app.logger.exception('Failed to credit refund for RR-%s', rr.id)
    
    # Update status to completed
    if rr.request_type == 'return':
        rr.status = 'return_refunded'
    else:
        rr.status = 'refunded'
    
    # Update order status
    rr.order.status = 'refunded'
    rr.order.payment_status = 'refunded'
    rr.order.updated_at = datetime.utcnow()
    
    db.session.commit()
    _emit_return_update(rr)
    push_notification(rr.buyer_id, f'Refund for RR-{rr.id} completed. Amount credited to your wallet.')
    try:
        user = User.query.get(rr.buyer_id)
        _send_refund_email(user, amount, rr.order_id)
    except Exception:
        pass
    flash('Return/refund completed successfully.', 'success')
    return redirect(url_for('seller_return_detail', return_id=return_id))

# Rider chat routes
@app.route('/rider/chat/<int:buyer_id>', methods=['GET', 'POST'])
@login_required
@rider_required
def rider_chat_thread(buyer_id):
    rider_id = session['user_id']
    if request.method == 'POST':
        msg = (request.form.get('message') or '').strip()
        if msg:
            db.session.add(RiderChatMessage(buyer_id=buyer_id, rider_id=rider_id, message=msg, sender_role='rider'))
            db.session.commit()
            try:
                rider_user = User.query.get(rider_id)
                rp = DeliveryPersonnel.query.filter_by(user_id=rider_id).first()
                img = getattr(rp, 'photo_path', None) or url_for('static', filename='user_avatar.png')
                push_notification(
                    buyer_id,
                    f"Rider {rider_user.first_name} messaged you.",
                    image_url=img,
                    link=url_for('buyer_rider_chat', rider_id=rider_id),
                    actor_user_id=rider_id,
                    type='chat'
                )
                socketio.emit('chat_rider', {'from': 'rider', 'message': msg}, room=f'user_{buyer_id}')
            except Exception:
                pass
        return redirect(url_for('rider_chat_thread', buyer_id=buyer_id))

    # Load thread and mark buyer messages as read
    RiderChatMessage.query.filter_by(buyer_id=buyer_id, rider_id=rider_id, sender_role='buyer', is_read=False).update({RiderChatMessage.is_read: True})
    db.session.commit()
    thread = RiderChatMessage.query.filter_by(buyer_id=buyer_id, rider_id=rider_id).order_by(RiderChatMessage.created_at.asc()).all()
    buyer = User.query.get(buyer_id)
    # Use helper function to get buyer avatar URL
    buyer_avatar_url = get_user_avatar_url(buyer_id, buyer.role if buyer else None)
    return render_template('rider/chat.html', thread=thread, buyer=buyer, buyer_avatar_url=buyer_avatar_url)

@app.route('/buyer/chat/rider/<int:rider_id>', methods=['GET', 'POST'])
@login_required
def buyer_rider_chat(rider_id):
    buyer_id = session['user_id']
    # Only buyers should initiate; admins/sellers/riders will still be allowed for simplicity
    if request.method == 'POST':
        msg = (request.form.get('message') or '').strip()
        if msg:
            db.session.add(RiderChatMessage(buyer_id=buyer_id, rider_id=rider_id, message=msg, sender_role='buyer'))
            db.session.commit()
            try:
                buyer_user = User.query.get(buyer_id)
                img = url_for('static', filename='user_avatar.png')
                push_notification(
                    rider_id,
                    f"Buyer {buyer_user.first_name} sent you a message.",
                    image_url=img,
                    link=url_for('rider_chat_thread', buyer_id=buyer_id),
                    actor_user_id=buyer_id,
                    type='chat'
                )
                socketio.emit('chat_rider', {'from': 'buyer', 'message': msg}, room=f'user_{rider_id}')
            except Exception:
                pass
        return redirect(url_for('buyer_rider_chat', rider_id=rider_id))

    RiderChatMessage.query.filter_by(buyer_id=buyer_id, rider_id=rider_id, sender_role='rider', is_read=False).update({RiderChatMessage.is_read: True})
    db.session.commit()
    thread = RiderChatMessage.query.filter_by(buyer_id=buyer_id, rider_id=rider_id).order_by(RiderChatMessage.created_at.asc()).all()
    rider = User.query.get(rider_id)
    # Rider profile for avatar
    rider_profile = DeliveryPersonnel.query.filter_by(user_id=rider_id).first()
    return render_template('buyer/rider_chat.html', thread=thread, rider=rider, rider_profile=rider_profile)

# Rider flows for return pickups
@app.route('/rider/returns')
@login_required
@rider_required
def rider_returns():
    available = ReturnPickup.query.filter_by(status='available').all()
    active = ReturnPickup.query.filter(ReturnPickup.rider_id==session['user_id'], ReturnPickup.status.in_(['waiting_rider_pickup','rider_picked_up','rider_delivered_to_seller'])).all()
    return render_template('rider/returns.html', available=available, active=active)

@app.route('/rider/returns/<int:task_id>/accept', methods=['POST'])
@login_required
@rider_required
def rider_return_accept(task_id):
    t = ReturnPickup.query.get_or_404(task_id)
    if t.status != 'available':
        flash('Task not available.', 'warning')
        return redirect(url_for('rider_returns'))
    t.status = 'waiting_rider_pickup'
    t.rider_id = session['user_id']
    db.session.commit()
    rr = t.return_request
    rr.status = 'waiting_rider_pickup'
    db.session.commit()
    _emit_return_update(rr, {'pickup_status': t.status})
    push_notification(rr.buyer_id, f'Rider accepted your return pickup RR-{rr.id} and is on the way.')
    return redirect(url_for('rider_returns'))

@app.route('/rider/returns/<int:task_id>/to-pickup', methods=['POST'])
@login_required
@rider_required
def rider_return_to_pickup(task_id):
    t = ReturnPickup.query.get_or_404(task_id)
    if t.rider_id != session['user_id']:
        flash('Not allowed.', 'danger')
        return redirect(url_for('rider_returns'))
    t.status = 'waiting_rider_pickup'
    db.session.commit()
    rr = t.return_request
    rr.status = 'waiting_rider_pickup'
    db.session.commit()
    _emit_return_update(rr, {'pickup_status': t.status})
    return redirect(url_for('rider_returns'))

@app.route('/rider/returns/<int:task_id>/picked-up', methods=['POST'])
@login_required
@rider_required
def rider_return_picked_up(task_id):
    t = ReturnPickup.query.get_or_404(task_id)
    if t.rider_id != session['user_id']:
        flash('Not allowed.', 'danger')
        return redirect(url_for('rider_returns'))
    t.status = 'rider_picked_up'
    t.picked_up_at = datetime.utcnow()
    db.session.commit()
    rr = t.return_request
    rr.status = 'rider_picked_up_item'
    db.session.commit()
    _emit_return_update(rr, {'pickup_status': t.status})
    push_notification(rr.buyer_id, f'Rider picked up your return parcel RR-{rr.id}.')
    return redirect(url_for('rider_returns'))

@app.route('/rider/returns/<int:task_id>/to-seller', methods=['POST'])
@login_required
@rider_required
def rider_return_to_seller(task_id):
    t = ReturnPickup.query.get_or_404(task_id)
    if t.rider_id != session['user_id']:
        flash('Not allowed.', 'danger')
        return redirect(url_for('rider_returns'))
    t.status = 'rider_delivered_to_seller'
    db.session.commit()
    rr = t.return_request
    rr.status = 'rider_delivered_to_seller'
    db.session.commit()
    _emit_return_update(rr, {'pickup_status': t.status})
    push_notification(rr.buyer_id, f'Return parcel RR-{rr.id} has been delivered to the seller.')
    return redirect(url_for('rider_returns'))

@app.route('/rider/returns/<int:task_id>/not-delivered', methods=['POST'])
@login_required
@rider_required
def rider_return_not_delivered(task_id):
    t = ReturnPickup.query.get_or_404(task_id)
    if t.rider_id != session['user_id']:
        flash('Not allowed.', 'danger')
        return redirect(url_for('rider_returns'))
    t.status = 'not_delivered'
    db.session.commit()
    rr = t.return_request
    try:
        rr.status = 'return_failed'
        db.session.commit()
    except Exception:
        pass
    _emit_return_update(rr, {'pickup_status': t.status})
    push_notification(rr.buyer_id, f'Return parcel RR-{rr.id} delivery attempt failed.')
    return redirect(url_for('rider_returns'))

@app.route('/rider/returns/<int:task_id>/delivered', methods=['POST'])
@login_required
@rider_required
def rider_return_delivered(task_id):
    t = ReturnPickup.query.get_or_404(task_id)
    if t.rider_id != session['user_id']:
        flash('Not allowed.', 'danger')
        return redirect(url_for('rider_returns'))
    t.status = 'delivered'
    t.delivered_at = datetime.utcnow()
    db.session.commit()
    rr = t.return_request
    
    # 🎯 RULE 3: RETURN & REFUND STILL DEDUCTS STOCK
    # Returned items NEVER return to stock - always deduct again
    try:
        product = rr.order_item.product
        order = rr.order
        returned_quantity = int(rr.quantity)
        
        # Always deduct stock for returns (never add back to inventory)
        product.stock = max(0, int(product.stock) - returned_quantity)
        
        app.logger.info(f'Stock deducted by rider delivery: Product {product.id} (-{returned_quantity}) => {product.stock}')
        
        # Broadcast real-time stock update
        try:
            available_stock = get_available_stock(product.id)
            socketio.emit('product_stock_update', {
                'product_id': product.id,
                'stock': available_stock,
                'available_stock': available_stock
            }, broadcast=True)
            _emit_seller_stats_update(product.seller_id)
        except Exception:
            pass
    except Exception:
        app.logger.exception('Stock deduction failed for rider delivery RR-%s', rr.id)
    
    # Mark buyer-facing "Returned to Seller – Completed" state
    rr.status = 'item_received_by_seller'
    db.session.commit()
    _emit_return_update(rr, {'pickup_status': t.status})
    push_notification(rr.buyer_id, f'Return parcel RR-{rr.id} delivered to seller. Waiting for seller confirmation.')
    return redirect(url_for('rider_returns'))

# --- Stock Correction Route ---
@app.route('/admin/correct-stock/<int:product_id>/<int:quantity_change>', methods=['POST'])
@admin_required
def admin_correct_stock(product_id, quantity_change):
    """Admin route to manually correct stock levels"""
    product = Product.query.get_or_404(product_id)
    old_stock = product.stock
    product.stock += quantity_change  # negative to deduct, positive to add
    
    # Ensure stock doesn't go below 0
    if product.stock < 0:
        product.stock = 0
    
    db.session.commit()
    
    # Broadcast real-time stock update
    try:
        available_stock = get_available_stock(product.id)
        socketio.emit('product_stock_update', {
            'product_id': product.id,
            'stock': available_stock,
            'available_stock': available_stock
        }, broadcast=True)
        _emit_seller_stats_update(product.seller_id)
    except Exception:
        pass
    
    action = "deducted" if quantity_change < 0 else "added"
    log_admin_action('Stock Correction', f'Product {product_id} ({product.name}): {quantity_change} units {action}. Stock changed from {old_stock} to {product.stock}')
    
    flash(f'Stock corrected for {product.name}: {old_stock} → {product.stock} ({action} {abs(quantity_change)} units)', 'success')
    return redirect(url_for('admin_products'))

# --- Search suggestions API ---
@app.route('/api/search/suggest')
def api_search_suggest():
    """
    Lightweight autosuggest endpoint used by the global search box.
    Returns up to ?limit (default 5) matches for products and stores/brands.

    Response shape expected by frontend (see templates/base.html):
      {
        "products": [ {"id": 1, "name": "..", "price": 123.45, "image": "/static/uploads/..."}, ... ],
        "stores":   [ {"id": 9, "name": "Store Name", "logo": "/static/uploads/..."}, ... ]
      }
    """
    q = (request.args.get('q') or '').strip()
    if not q:
        return jsonify({"products": [], "stores": []})

    # Bound limit to prevent heavy queries
    try:
        limit = int(request.args.get('limit', 5))
    except Exception:
        limit = 5
    limit = max(1, min(limit, 10))

    # Products: match on name or description; only active
    try:
        product_rows = (
            Product.query
            .filter(Product.status == 'active')
            .filter(or_(Product.name.ilike(f"%{q}%"), Product.description.ilike(f"%{q}%")))
            .order_by(Product.featured.desc(), Product.created_at.desc())
            .limit(limit)
            .all()
        )
    except Exception:
        product_rows = []

    products = []
    for p in product_rows:
        try:
            img = url_for('static', filename=f'uploads/{p.image_filename}') if getattr(p, 'image_filename', None) else None
        except Exception:
            img = None
        try:
            price = float(p.price) if p.price is not None else None
        except Exception:
            price = None
        products.append({
            'id': p.id,
            'name': p.name,
            'price': price,
            'image': img,
        })

    # Stores/Brands: SellerApplication (approved) by store_name
    try:
        store_rows = (
            SellerApplication.query
            .filter_by(status='approved')
            .filter(SellerApplication.store_name.ilike(f"%{q}%"))
            .order_by(SellerApplication.store_name.asc())
            .limit(limit)
            .all()
        )
    except Exception:
        store_rows = []

    stores = []
    for s in store_rows:
        try:
            logo = url_for('static', filename=f'uploads/{s.store_logo}') if getattr(s, 'store_logo', None) else None
        except Exception:
            logo = None
        stores.append({
            'id': s.user_id,   # seller id used by /store/<id>
            'name': s.store_name,
            'logo': logo,
        })

    return jsonify({'products': products, 'stores': stores})


@socketio.on('join')
def on_join(data):
    # Handle both old format {room: 'user_123'} and new format {user_id: 123}
    if 'room' in data:
        room = data['room']
    elif 'user_id' in data:
        room = f"user_{data['user_id']}"
    else:
        return
    join_room(room)

@socketio.on('join_seller_room')
def on_join_seller_room(data):
    seller_id = data.get('seller_id')
    if seller_id:
        join_room(f'user_{seller_id}')


if __name__ == "__main__":
    with app.app_context():
        # Create all database tables
        db.create_all()
        
        # seeding logic...
        categories = [
            'Baby Clothes & Accessories',
            'Toys & Games',
            'Educational Materials',
            'Strollers & Gear',
            'Nursery Furniture',
            'Safety and Health'
        ]
        for cat_name in categories:
            if not Category.query.filter_by(name=cat_name).first():
                db.session.add(Category(name=cat_name))
        admin = User.query.filter_by(email='admin@kidscommerce.com').first()
        if not admin:
            admin = User(
                first_name="Admin",
                last_name="Account",
                email="admin@kidscommerce.com",
                password="your_hashed_password_here",
                phone="0000000000",
                address="System Address",
                role="admin",
                status="active"
            )
            db.session.add(admin)
        db.session.commit()
    app.run(debug=True)

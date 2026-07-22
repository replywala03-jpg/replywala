import streamlit as st
import re
import time
import pickle
import json
import os
import requests
import stripe 
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from openai import OpenAI
from dotenv import load_dotenv

# --- Page Configuration ---
st.set_page_config(
    page_title="ReplyWala - YouTube Comment AI",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Load environment
load_dotenv()
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")

# One-Time Price IDs
STARTER_INR = os.getenv("STRIPE_STARTER_INR")
STARTER_USD = os.getenv("STRIPE_STARTER_USD")
POPULAR_INR = os.getenv("STRIPE_POPULAR_INR")
POPULAR_USD = os.getenv("STRIPE_POPULAR_USD")
PRO_INR = os.getenv("STRIPE_PRO_INR")
PRO_USD = os.getenv("STRIPE_PRO_USD")

# Subscription Price IDs
LIGHT_INR = os.getenv("STRIPE_LIGHT_INR")
LIGHT_USD = os.getenv("STRIPE_LIGHT_USD")
PRO_SUB_INR = os.getenv("STRIPE_PRO_SUB_INR")
PRO_SUB_USD = os.getenv("STRIPE_PRO_SUB_USD")
UNLIMITED_INR = os.getenv("STRIPE_UNLIMITED_INR")
UNLIMITED_USD = os.getenv("STRIPE_UNLIMITED_USD")

# Helper function to get the right price ID based on currency
def get_price_id(price_inr, price_usd):
    """Return the appropriate price ID based on user's currency"""
    if currency['code'] == 'INR':
        return price_inr
    else:
        return price_usd

# --- Geolocation Detection ---
def detect_country():
    """Detect user's country from IP address with manual override"""
    # Check for manual override via URL parameter
    import streamlit as st
    
    # Get query parameters
    query_params = st.query_params
    override = query_params.get('country', None)
    
    if override:
        if override.upper() == 'IN':
            return 'IN'
        elif override.upper() == 'US':
            return 'US'
        elif override.upper() == 'GB':
            return 'GB'
        elif override.upper() == 'EU':
            return 'EU'
        else:
            return override.upper()
    
    # If no override, detect via IP
    try:
        response = requests.get('https://ipapi.co/json/', timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get('country_code', 'US')
    except:
        pass
    return 'US'  # Default to US if detection fails

def get_currency(country_code):
    """Return currency symbol and code based on country"""
    if country_code == 'IN':
        return {'symbol': '₹', 'code': 'INR', 'is_india': True}
    else:
        return {'symbol': '$', 'code': 'USD', 'is_india': False}

def get_pricing(country_code):
    """Return pricing based on country"""
    if country_code == 'IN':
        return {
            'free': {'replies': 10, 'label': 'Free'},
            'starter': {'replies': 100, 'price': 49, 'label': 'Starter'},
            'popular': {'replies': 500, 'price': 149, 'label': 'Popular'},
            'pro': {'replies': 1500, 'price': 399, 'label': 'Pro'}
        }
    else:
        return {
            'free': {'replies': 10, 'label': 'Free'},
            'starter': {'replies': 100, 'price': 4.99, 'label': 'Starter'},
            'popular': {'replies': 500, 'price': 14.99, 'label': 'Popular'},
            'pro': {'replies': 1500, 'price': 39.99, 'label': 'Pro'}
        }
# --- Usage Tracking ---
USAGE_FILE = 'usage.json'

def get_user_id():
    """Get unique user identifier (email or IP-based)"""
    # For now, use a simple approach - we'll use email later
    return 'default_user'

def load_usage(user_id):
    """Load usage data for a user"""
    if os.path.exists(USAGE_FILE):
        with open(USAGE_FILE, 'r') as f:
            data = json.load(f)
            return data.get(user_id, {})
    return {}

def save_usage(user_id, usage_data):
    """Save usage data for a user"""
    data = {}
    if os.path.exists(USAGE_FILE):
        with open(USAGE_FILE, 'r') as f:
            data = json.load(f)
    data[user_id] = usage_data
    with open(USAGE_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_usage(user_id):
    """Get current usage with free tier tracking"""
    usage = load_usage(user_id)
    today = datetime.now().date().isoformat()
    
    # Initialize if no data
    if not usage:
        usage = {
            'free_used': 0,
            'free_quota': 10,
            'paid_used': 0,
            'last_reset': today,
            'total_replies': 0
        }
    
    # Reset free tier monthly
    if usage.get('last_reset') != today:
        # Check if it's a new month
        last_reset = datetime.strptime(usage['last_reset'], '%Y-%m-%d')
        if last_reset.month != datetime.now().month:
            usage['free_used'] = 0
            usage['last_reset'] = today
    
    return usage

def can_use_free(usage):
    """Check if user has free replies remaining"""
    return usage['free_used'] < usage['free_quota']

def get_remaining_free(usage):
    """Get remaining free replies"""
    return usage['free_quota'] - usage['free_used']

def track_reply_used(user_id):
    """Track when a reply is used"""
    usage = get_usage(user_id)
    
    if can_use_free(usage):
        usage['free_used'] += 1
    else:
        usage['paid_used'] += 1
    
    usage['total_replies'] += 1
    save_usage(user_id, usage)
    return usage

def get_remaining_paid(usage):
    """Get remaining paid replies (for display)"""
    # For now, assume unlimited paid replies (will be tracked via Stripe later)
    return "Unlimited"

# --- Professional CSS ---
st.markdown("""
<style>
    /* Force white background */
    .stApp { background-color: #ffffff !important; }
    .stApp > div { background-color: #ffffff !important; }
    
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;}
    
    /* Main container */
    .main-container {
        max-width: 1100px;
        margin: 0 auto;
        padding: 0 24px;
        background: #ffffff;
    }
    
    /* Navigation */
    .navbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 16px 0;
        border-bottom: 1px solid #eef2f7;
        margin-bottom: 24px;
        flex-wrap: wrap;
        gap: 12px;
    }
    .logo {
        font-size: 24px;
        font-weight: 800;
        color: #1a1a2e;
        letter-spacing: -0.5px;
    }
    .logo span { color: #e94560; }
    
    .nav-links {
        display: flex;
        gap: 24px;
        align-items: center;
        flex-wrap: wrap;
    }
    .nav-links a {
        color: #4a4a6a;
        text-decoration: none;
        font-weight: 500;
        font-size: 14px;
        padding: 8px 4px;
        border-bottom: 2px solid transparent;
        transition: all 0.2s;
        cursor: pointer;
    }
    .nav-links a:hover {
        color: #e94560;
        border-bottom-color: #e94560;
    }
    .nav-links a.active {
        color: #e94560;
        border-bottom-color: #e94560;
        font-weight: 600;
    }
    
    .btn-connect {
        background: #1a1a2e !important;
        color: white !important;
        border: none !important;
        padding: 8px 20px !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 13px !important;
        cursor: pointer !important;
        transition: all 0.3s !important;
    }
    .btn-connect:hover {
        background: #2d2d44 !important;
        transform: translateY(-2px);
    }
    
    .badge-success {
        background: #e8f8f5;
        color: #00b894;
        padding: 4px 14px;
        border-radius: 20px;
        font-size: 13px;
        font-weight: 600;
        display: inline-block;
    }
    
    /* Hero */
    .hero {
        text-align: center;
        padding: 24px 0 20px 0;
    }
    .hero h1 {
        font-size: 34px;
        font-weight: 800;
        color: #1a1a2e;
        letter-spacing: -1px;
        margin-bottom: 6px;
    }
    .hero h1 span { color: #e94560; }
    .hero p {
        font-size: 15px;
        color: #636e72;
        font-weight: 400;
    }
    
    /* Steps */
    .steps {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 16px;
        margin: 20px 0 28px 0;
    }
    .step-card {
        background: #f8f9fc;
        border-radius: 12px;
        padding: 18px 20px;
        text-align: center;
        border: 1px solid #eef2f7;
    }
    .step-number {
        font-size: 26px;
        font-weight: 700;
        color: #e94560;
        display: block;
    }
    .step-title {
        font-size: 14px;
        font-weight: 600;
        color: #1a1a2e;
        margin: 4px 0 2px 0;
    }
    .step-desc {
        font-size: 12px;
        color: #636e72;
        margin: 0;
    }
    
    /* Main Card */
    .main-card {
        background: #ffffff;
        border-radius: 16px;
        padding: 28px 32px;
        box-shadow: 0 4px 24px rgba(0,0,0,0.06);
        border: 1px solid #eef2f7;
        margin-bottom: 20px;
    }
    
    .input-row {
        display: flex;
        gap: 16px;
        align-items: flex-end;
        flex-wrap: wrap;
    }
    .input-group {
        flex: 1;
        min-width: 180px;
    }
    .input-group label {
        display: block;
        font-size: 13px;
        font-weight: 600;
        color: #1a1a2e;
        margin-bottom: 4px;
    }
    .input-group input {
        width: 100%;
        padding: 10px 16px;
        border: 2px solid #eef2f7;
        border-radius: 10px;
        font-size: 14px;
        color: #1a1a2e;
        background: #ffffff;
        transition: border-color 0.2s;
        box-sizing: border-box;
    }
    .input-group input:focus {
        border-color: #e94560;
        outline: none;
        box-shadow: 0 0 0 4px rgba(233, 69, 96, 0.08);
    }
    .input-group input::placeholder {
        color: #b0b8c8;
    }
    
    .btn-primary {
        background: linear-gradient(135deg, #e94560, #c0392b) !important;
        color: white !important;
        border: none !important;
        padding: 10px 28px !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        cursor: pointer !important;
        transition: all 0.3s !important;
        min-width: 120px;
    }
    .btn-primary:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 24px rgba(233, 69, 96, 0.3) !important;
    }
    
    .btn-green {
        background: linear-gradient(135deg, #00b894, #00a381) !important;
        color: white !important;
        border: none !important;
        padding: 6px 16px !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 12px !important;
        cursor: pointer !important;
        transition: all 0.3s !important;
        width: 100%;
    }
    .btn-green:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0, 184, 148, 0.3) !important;
    }
    
    .comment-box {
        background: #f8f9fc;
        padding: 12px 16px;
        border-radius: 10px;
        margin-bottom: 6px;
        border-left: 4px solid #e94560;
    }
    .comment-box .author {
        font-weight: 600;
        color: #1a1a2e;
        font-size: 13px;
    }
    .comment-box .text {
        color: #2d3436;
        margin: 2px 0 0 0;
        font-size: 14px;
    }
    
    .reply-box {
        background: #e8f8f5;
        padding: 12px 16px;
        border-radius: 10px;
        margin-bottom: 6px;
        border-left: 4px solid #00b894;
    }
    .reply-box .label {
        font-weight: 600;
        color: #00b894;
        font-size: 13px;
    }
    .reply-box .text {
        color: #1a1a2e;
        margin: 2px 0 0 0;
        font-size: 14px;
    }
    
    .stats-row {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        margin: 12px 0;
    }
    .stat-item {
        background: #f8f9fc;
        border-radius: 10px;
        padding: 12px;
        text-align: center;
        border: 1px solid #eef2f7;
    }
    .stat-item .number {
        font-size: 24px;
        font-weight: 700;
        color: #1a1a2e;
    }
    .stat-item .label {
        font-size: 12px;
        color: #636e72;
        font-weight: 500;
    }
    
    .divider {
        border: none;
        height: 1px;
        background: #eef2f7;
        margin: 16px 0;
    }
    
    .footer-text {
        text-align: center;
        color: #b0b8c8;
        font-size: 13px;
        padding: 20px 0 12px 0;
        border-top: 1px solid #eef2f7;
        margin-top: 12px;
    }
    .footer-text strong { color: #1a1a2e; }
    
    /* Pricing Grid */
    .pricing-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 16px;
        margin: 20px 0;
    }
    .pricing-card {
        background: #ffffff;
        border-radius: 16px;
        padding: 24px 20px;
        text-align: center;
        border: 2px solid #eef2f7;
        transition: all 0.3s;
    }
    .pricing-card:hover {
        border-color: #e94560;
        transform: translateY(-4px);
        box-shadow: 0 8px 30px rgba(0,0,0,0.08);
    }
    .pricing-card.popular {
        border-color: #e94560;
        background: #fef5f6;
    }
    .pricing-card.free-card {
        border-color: #00b894;
        background: #f0faf8;
    }
    .pricing-card .plan-name {
        font-size: 18px;
        font-weight: 700;
        color: #1a1a2e;
    }
    .pricing-card .plan-price {
        font-size: 28px;
        font-weight: 800;
        color: #1a1a2e;
        margin: 8px 0;
    }
    .pricing-card .plan-price span {
        font-size: 13px;
        font-weight: 400;
        color: #636e72;
    }
    .pricing-card .plan-features {
        list-style: none;
        padding: 0;
        text-align: left;
    }
    .pricing-card .plan-features li {
        padding: 5px 0;
        font-size: 12px;
        color: #2d3436;
        border-bottom: 1px solid #f0f0f0;
    }
    .pricing-card .plan-features li:last-child {
        border-bottom: none;
    }
    .pricing-card .plan-features li::before {
        content: "✅ ";
    }
    
    .badge-popular {
        background: #e94560;
        color: white;
        padding: 2px 12px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 600;
        display: inline-block;
        margin-bottom: 8px;
    }
    .badge-free {
        background: #00b894;
        color: white;
        padding: 2px 12px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 600;
        display: inline-block;
        margin-bottom: 8px;
    }
    
    .features-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 20px;
        margin: 20px 0;
    }
    .feature-item {
        background: #f8f9fc;
        border-radius: 12px;
        padding: 20px 24px;
        border: 1px solid #eef2f7;
    }
    .feature-item .icon {
        font-size: 28px;
    }
    .feature-item .title {
        font-size: 16px;
        font-weight: 600;
        color: #1a1a2e;
        margin: 4px 0 2px 0;
    }
    .feature-item .desc {
        font-size: 13px;
        color: #636e72;
        margin: 0;
    }
    
    .usage-bar {
        background: #eef2f7;
        border-radius: 20px;
        padding: 2px;
        margin: 8px 0;
        height: 8px;
        overflow: hidden;
    }
    .usage-bar-fill {
        background: linear-gradient(90deg, #00b894, #00a381);
        height: 8px;
        border-radius: 20px;
        transition: width 0.5s;
    }
    
    .stTextInput input, .stNumberInput input {
        border: 2px solid #eef2f7 !important;
        border-radius: 10px !important;
        padding: 10px 16px !important;
        font-size: 14px !important;
        color: #1a1a2e !important;
        background: #ffffff !important;
        width: 100% !important;
        box-sizing: border-box !important;
    }
    .stTextInput input:focus, .stNumberInput input:focus {
        border-color: #e94560 !important;
        box-shadow: 0 0 0 4px rgba(233, 69, 96, 0.08) !important;
        outline: none !important;
    }
    .stTextInput label, .stNumberInput label {
        color: #1a1a2e !important;
        font-weight: 600 !important;
        font-size: 13px !important;
    }
    
    .stButton button {
        border-radius: 10px !important;
        font-weight: 600 !important;
        border: none !important;
        transition: all 0.3s !important;
    }
    .stButton button[kind="primary"] {
        background: linear-gradient(135deg, #e94560, #c0392b) !important;
        color: white !important;
        padding: 10px 28px !important;
        font-size: 14px !important;
    }
    .stButton button[kind="primary"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 24px rgba(233, 69, 96, 0.3) !important;
    }
    
    .stAlert { border-radius: 10px !important; border-left: 4px solid !important; }
    .stAlert > div { color: #1a1a2e !important; }
    .stSuccess { background: #e8f8f5 !important; border-left-color: #00b894 !important; }
    .stWarning { border-left-color: #f39c12 !important; }
    
    .stMarkdown, .stMarkdown p, .stMarkdown div, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
        color: #1a1a2e !important;
    }
</style>
""", unsafe_allow_html=True)

# --- Detect User Location ---
country = detect_country()
currency = get_currency(country)
pricing = get_pricing(country)

# --- Session State ---
if 'page' not in st.session_state:
    st.session_state.page = 'home'
if 'comments' not in st.session_state:
    st.session_state.comments = []
if 'replies' not in st.session_state:
    st.session_state.replies = []
if 'posted' not in st.session_state:
    st.session_state.posted = {}
if 'video_id' not in st.session_state:
    st.session_state.video_id = None
if 'processing' not in st.session_state:
    st.session_state.processing = False

# --- Helper Functions ---
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

def get_authenticated_youtube():
    creds = None
    token_file = 'token.pickle'
    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                '../custom-reply-youtube/credentials.json', SCOPES)
            creds = flow.run_local_server(port=8080, open_browser=True)
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)
    return build('youtube', 'v3', credentials=creds)

def extract_video_id(url):
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11})(?:[?&]|$)',
        r'(?:embed\/)([0-9A-Za-z_-]{11})',
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_comments(youtube, video_id, max_results=20):
    try:
        request = youtube.commentThreads().list(
            part='snippet',
            videoId=video_id,
            maxResults=max_results,
            textFormat='plainText'
        )
        response = request.execute()
        comments = []
        for item in response.get('items', []):
            comment_id = item['snippet']['topLevelComment']['id']
            comment_text = item['snippet']['topLevelComment']['snippet']['textDisplay']
            author = item['snippet']['topLevelComment']['snippet']['authorDisplayName']
            comments.append({'id': comment_id, 'author': author, 'text': comment_text})
        return comments
    except HttpError as e:
        st.error(f"❌ Error: {e}")
        return []

def get_price_id(price_inr, price_usd):
    """Return the appropriate price ID based on user's currency"""
    if currency['code'] == 'INR':
        return price_inr
    else:
        return price_usd


def create_checkout_session(price_id, reply_count, plan_name):
    """Create a Stripe Checkout Session and redirect the user"""
    try:
        user_id = get_user_id()
        base_url = "http://localhost:8501"
        
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    "price": price_id,
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=f"{base_url}/?session_id={{CHECKOUT_SESSION_ID}}&success=true&plan={plan_name}",
            cancel_url=f"{base_url}/?canceled=true",
            metadata={
                "user_id": user_id,
                "reply_count": str(reply_count),
                "plan_name": plan_name
            }
            # Remove "payment_method_types" - let Stripe handle it dynamically
        )
        
        st.markdown(f'<meta http-equiv="refresh" content="0;url={checkout_session.url}">', unsafe_allow_html=True)
        st.info(f"🔄 Redirecting to Stripe Checkout... [Click here if not redirected]({checkout_session.url})")
        
    except Exception as e:
        st.error(f"❌ Failed to create checkout session: {e}")
        st.error(f"Error details: {str(e)}")


def generate_reply(comment_text):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a friendly YouTube creator replying to your audience. Keep replies short, personal, and engaging. Use emojis occasionally."},
                {"role": "user", "content": f"Comment: {comment_text}\n\nGenerate a short, friendly reply:"}
            ],
            max_tokens=60,
            temperature=0.8
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return "Thanks for your comment! 🙌"

def post_reply(youtube, comment_id, reply_text):
    try:
        request = youtube.comments().insert(
            part='snippet',
            body={'snippet': {'parentId': comment_id, 'textOriginal': reply_text}}
        )
        response = request.execute()
        return response
    except HttpError as e:
        st.error(f"❌ Error posting: {e}")
        return None

# --- Main Container ---
st.markdown('<div class="main-container">', unsafe_allow_html=True)

# --- Geolocation Banner with Manual Override ---
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    st.info(f"📍 Detected: {country} | Currency: {currency['symbol']} {currency['code']}")
with col2:
    if st.button("🇮🇳 India (₹)", use_container_width=True):
        st.query_params['country'] = 'IN'
        st.rerun()
with col3:
    if st.button("🌍 Global ($)", use_container_width=True):
        st.query_params['country'] = 'US'
        st.rerun()

# Also add a "Reset" option if there's an override
query_params = st.query_params
if query_params.get('country'):
    st.caption(f"🔧 Manual override active: {query_params.get('country')}")
    if st.button("🔄 Reset to Auto-Detect"):
        st.query_params.clear()
        st.rerun()

# --- NAVIGATION ---
is_logged_in = os.path.exists('token.pickle')

nav_col1, nav_col2 = st.columns([1, 2])
with nav_col1:
    st.markdown('<div class="logo">💬 Reply<span>Wala</span></div>', unsafe_allow_html=True)

with nav_col2:
    col_a, col_b, col_c, col_d, col_e = st.columns([1, 1, 1, 1, 1.2])
    with col_a:
        if st.button("🏠 Home", use_container_width=True):
            st.session_state.page = 'home'
            st.rerun()
    with col_b:
        if st.button("✨ Features", use_container_width=True):
            st.session_state.page = 'features'
            st.rerun()
    with col_c:
        if st.button("💰 Pricing", use_container_width=True):
            st.session_state.page = 'pricing'
            st.rerun()
    with col_d:
        if st.button("📊 Dashboard", use_container_width=True):
            st.session_state.page = 'dashboard'
            st.rerun()
    with col_e:
        if is_logged_in:
            st.markdown('<span class="badge-success">✅ Connected</span>', unsafe_allow_html=True)
        else:
            if st.button("🔗 Connect", use_container_width=True):
                with st.spinner("Opening browser..."):
                    try:
                        youtube = get_authenticated_youtube()
                        st.success("✅ Connected!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed: {e}")

# --- PAGE ROUTING ---
page = st.session_state.page
user_id = get_user_id()
usage = get_usage(user_id)
remaining_free = get_remaining_free(usage)

# ==================== HOME PAGE ====================
if page == 'home':
    st.markdown("""
    <div class="hero">
        <h1>AI-Powered YouTube <span>Comment Management</span></h1>
        <p>Auto-reply to your YouTube comments in under 2 minutes. Review before posting. Full control.</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Usage Banner
    if is_logged_in:
        free_pct = ((pricing['free']['replies'] - remaining_free) / pricing['free']['replies']) * 100
        st.markdown(f"""
        <div style="background: #f8f9fc; border-radius: 12px; padding: 16px 20px; margin-bottom: 16px; border: 1px solid #eef2f7;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                <span style="font-size: 14px; color: #1a1a2e;">
                    🎁 <strong>Free Tier:</strong> {remaining_free} of {pricing['free']['replies']} free replies remaining this month
                </span>
                <span style="font-size: 13px; color: #636e72;">
                    💰 Paid replies: {get_remaining_paid(usage)}
                </span>
            </div>
            <div class="usage-bar">
                <div class="usage-bar-fill" style="width: {min(free_pct, 100)}%;"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="steps">
        <div class="step-card">
            <span class="step-number">1</span>
            <div class="step-title">Connect Your Channel</div>
            <p class="step-desc">Paste any YouTube link — we'll find your channel automatically</p>
        </div>
        <div class="step-card">
            <span class="step-number">2</span>
            <div class="step-title">Review & Edit</div>
            <p class="step-desc">See every reply before it goes live. Edit, approve, or skip</p>
        </div>
        <div class="step-card">
            <span class="step-number">3</span>
            <div class="step-title">Post Approved</div>
            <p class="step-desc">Only the replies YOU approve get posted to YouTube</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="main-card">', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        video_url = st.text_input(
            "YouTube Video URL",
            placeholder="https://www.youtube.com/watch?v=...",
            label_visibility="collapsed"
        )
    with col2:
        num_comments = st.number_input(
            "Replies",
            min_value=1,
            max_value=20,
            value=min(5, remaining_free + 5),
            step=1,
            label_visibility="collapsed"
        )
    with col3:
        st.write("")
        if st.button("🚀 Generate", type="primary", use_container_width=True):
            if not os.path.exists('token.pickle'):
                st.error("❌ Please connect your YouTube account first")
            elif not video_url:
                st.error("❌ Please enter a YouTube URL")
            else:
                # Check if user has enough replies (free + paid)
                if num_comments > remaining_free:
                    st.warning(f"⚠️ You have {remaining_free} free replies left. Additional replies will use paid credits.")
                
                video_id = extract_video_id(video_url)
                if not video_id:
                    st.error("❌ Invalid YouTube URL")
                else:
                    st.session_state.video_id = video_id
                    st.session_state.processing = True
                    st.session_state.comments = []
                    st.session_state.replies = []
                    st.session_state.posted = {}
                    st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    if st.session_state.processing and st.session_state.video_id:
        youtube = get_authenticated_youtube()
        with st.spinner("Fetching comments and generating AI replies..."):
            comments = get_comments(youtube, st.session_state.video_id, num_comments)
            if not comments:
                st.warning("No comments found on this video")
                st.session_state.processing = False
            else:
                st.session_state.comments = comments
                for comment in comments:
                    reply = generate_reply(comment['text'])
                    st.session_state.replies.append(reply)
                    st.session_state.posted[comment['id']] = False
                st.session_state.processing = False
                st.rerun()
    
    if st.session_state.comments:
        st.markdown('<hr class="divider">', unsafe_allow_html=True)
        
        total = len(st.session_state.comments)
        posted = sum(1 for v in st.session_state.posted.values() if v)
        
        st.markdown("""
        <div class="stats-row">
            <div class="stat-item"><div class="number">{}</div><div class="label">Comments</div></div>
            <div class="stat-item"><div class="number">{}</div><div class="label">Replied</div></div>
            <div class="stat-item"><div class="number">{}</div><div class="label">Remaining</div></div>
            <div class="stat-item"><div class="number">🎁 {}</div><div class="label">Free Left</div></div>
        </div>
        """.format(total, posted, total - posted, remaining_free), unsafe_allow_html=True)
        
        if posted < total:
            if st.button("📤 Post All Remaining", use_container_width=True):
                youtube = get_authenticated_youtube()
                for idx, comment in enumerate(st.session_state.comments):
                    if not st.session_state.posted.get(comment['id'], False):
                        reply = st.session_state.replies[idx]
                        result = post_reply(youtube, comment['id'], reply)
                        if result:
                            st.session_state.posted[comment['id']] = True
                            # Track usage
                            track_reply_used(user_id)
                        time.sleep(0.5)
                st.rerun()
        
        st.markdown('<hr class="divider">', unsafe_allow_html=True)
        
        youtube = get_authenticated_youtube()
        for idx, comment in enumerate(st.session_state.comments):
            with st.container():
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"""
                    <div class="comment-box">
                        <div class="author">@{comment['author']}</div>
                        <div class="text">{comment['text'][:300]}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    if idx < len(st.session_state.replies):
                        reply = st.session_state.replies[idx]
                        st.markdown(f"""
                        <div class="reply-box">
                            <div class="label">🤖 AI Reply</div>
                            <div class="text">{reply}</div>
                        </div>
                        """, unsafe_allow_html=True)
                with col2:
                    st.write("")
                    if not st.session_state.posted.get(comment['id'], False):
                        # Check if user has free replies left before allowing post
                        usage_check = get_usage(user_id)
                        if can_use_free(usage_check) or get_remaining_paid(usage_check) != "0":
                            if st.button(f"📤 Post", key=f"post_{comment['id']}", use_container_width=True):
                                with st.spinner("Posting..."):
                                    result = post_reply(youtube, comment['id'], reply)
                                    if result:
                                        st.session_state.posted[comment['id']] = True
                                        track_reply_used(user_id)
                                        st.success("✅")
                                        time.sleep(0.3)
                                        st.rerun()
                                    else:
                                        st.error("❌")
                        else:
                            st.warning("No credits left")
                    else:
                        st.markdown('<span style="color: #00b894; font-weight: 600;">✅ Posted</span>', unsafe_allow_html=True)
                st.markdown('<hr class="divider">', unsafe_allow_html=True)

# ==================== FEATURES PAGE ====================
elif page == 'features':
    st.markdown("""
    <div class="hero">
        <h1>✨ Powerful Features for <span>Creators</span></h1>
        <p>Everything you need to manage YouTube comments at scale</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="features-grid">
        <div class="feature-item">
            <div class="icon">🤖</div>
            <div class="title">AI-Powered Replies</div>
            <div class="desc">Generate human-like replies using advanced AI. Each reply is personalized to the comment.</div>
        </div>
        <div class="feature-item">
            <div class="icon">📤</div>
            <div class="title">Auto-Posting</div>
            <div class="desc">Post replies directly to YouTube with one click. Save hours of manual work.</div>
        </div>
        <div class="feature-item">
            <div class="icon">✏️</div>
            <div class="title">Review Before Posting</div>
            <div class="desc">See every reply before it goes live. Edit, approve, or skip any reply.</div>
        </div>
        <div class="feature-item">
            <div class="icon">🎯</div>
            <div class="title">Smart Filtering</div>
            <div class="desc">Reply only to comments that matter. Filter by keywords, sentiment, or questions.</div>
        </div>
        <div class="feature-item">
            <div class="icon">🌍</div>
            <div class="title">Multi-Language Support</div>
            <div class="desc">Reply in Hindi, English, and more. Auto-detect comment language.</div>
        </div>
        <div class="feature-item">
            <div class="icon">📊</div>
            <div class="title">Analytics Dashboard</div>
            <div class="desc">Track engagement, reply performance, and audience sentiment over time.</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# ==================== PRICING PAGE ====================
elif page == 'pricing':
    st.markdown("""
    <div class="hero">
        <h1>Simple, Transparent <span>Pricing</span></h1>
        <p>Pay only for what you use. No hidden fees.</p>
    </div>
    """, unsafe_allow_html=True)
    
    p = pricing
    symbol = currency['symbol']
    
    # Check if Stripe is configured
    if not STARTER_INR or not STARTER_USD:
        st.warning("⚠️ Stripe Price IDs not fully configured. Please check your .env file.")
    
    # Display pricing cards with Buy buttons
    col1, col2, col3, col4 = st.columns(4)
    
    # Free Plan
    with col1:
        st.markdown(f"""
        <div class="pricing-card free-card">
            <div class="badge-free">🎁 Free</div>
            <div class="plan-name">Free</div>
            <div class="plan-price">{symbol}0 <span>/ month</span></div>
            <ul class="plan-features">
                <li>{p['free']['replies']} free replies/month</li>
                <li>Review before posting</li>
                <li>Basic analytics</li>
                <li>Email support</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    # Starter Plan
    with col2:
        st.markdown(f"""
        <div class="pricing-card">
            <div class="plan-name">{p['starter']['label']}</div>
            <div class="plan-price">{symbol}{p['starter']['price']} <span>/ {p['starter']['replies']} replies</span></div>
            <ul class="plan-features">
                <li>{p['starter']['replies']} AI replies</li>
                <li>Review before posting</li>
                <li>Basic analytics</li>
                <li>Email support</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        # Buy button
        price_id = get_price_id(STARTER_INR, STARTER_USD)
        if price_id:
            if st.button(f"Buy {p['starter']['label']} - {symbol}{p['starter']['price']}", key="buy_starter", use_container_width=True):
                create_checkout_session(price_id, p['starter']['replies'], p['starter']['label'])
        else:
            st.warning("⚠️ No Price ID")
    
    # Popular Plan
    with col3:
        st.markdown(f"""
        <div class="pricing-card popular">
            <div class="badge-popular">🔥 Most Popular</div>
            <div class="plan-name">{p['popular']['label']}</div>
            <div class="plan-price">{symbol}{p['popular']['price']} <span>/ {p['popular']['replies']} replies</span></div>
            <ul class="plan-features">
                <li>{p['popular']['replies']} AI replies</li>
                <li>Review before posting</li>
                <li>Advanced analytics</li>
                <li>Priority support</li>
                <li>Smart filtering</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        # Buy button
        price_id = get_price_id(POPULAR_INR, POPULAR_USD)
        if price_id:
            if st.button(f"Buy {p['popular']['label']} - {symbol}{p['popular']['price']}", key="buy_popular", use_container_width=True):
                create_checkout_session(price_id, p['popular']['replies'], p['popular']['label'])
        else:
            st.warning("⚠️ No Price ID")
    
    # Pro Plan
    with col4:
        st.markdown(f"""
        <div class="pricing-card">
            <div class="plan-name">{p['pro']['label']}</div>
            <div class="plan-price">{symbol}{p['pro']['price']} <span>/ {p['pro']['replies']} replies</span></div>
            <ul class="plan-features">
                <li>{p['pro']['replies']} AI replies</li>
                <li>Review before posting</li>
                <li>Advanced analytics</li>
                <li>Priority support</li>
                <li>Smart filtering</li>
                <li>Bulk processing</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        # Buy button
        price_id = get_price_id(PRO_INR, PRO_USD)
        if price_id:
            if st.button(f"Buy {p['pro']['label']} - {symbol}{p['pro']['price']}", key="buy_pro", use_container_width=True):
                create_checkout_session(price_id, p['pro']['replies'], p['pro']['label'])
        else:
            st.warning("⚠️ No Price ID")
    
    st.markdown(f"""
    <div style="text-align: center; padding: 8px 0;">
        <p style="color: #636e72; font-size: 14px;">💳 India: UPI, Credit Card, Netbanking | Global: Credit Cards, PayPal</p>
        <p style="color: #636e72; font-size: 14px;">🌍 Prices shown in {currency['symbol']} {currency['code']} based on your location ({country})</p>
        <p style="color: #636e72; font-size: 13px;">🎁 Everyone gets {p['free']['replies']} free replies every month!</p>
    </div>
    """, unsafe_allow_html=True)

# ==================== DASHBOARD PAGE ====================
elif page == 'dashboard':
    st.markdown("""
    <div class="hero">
        <h1>📊 Your <span>Dashboard</span></h1>
        <p>Track your reply performance and usage</p>
    </div>
    """, unsafe_allow_html=True)
    
    if not os.path.exists('token.pickle'):
        st.warning("🔐 Please connect your YouTube account to view dashboard")
    else:
        total_comments = len(st.session_state.comments)
        total_replies = sum(1 for v in st.session_state.posted.values() if v)
        free_used = usage.get('free_used', 0)
        paid_used = usage.get('paid_used', 0)
        total_used = free_used + paid_used
        
        st.markdown("""
        <div class="stats-row">
            <div class="stat-item"><div class="number">{}</div><div class="label">Comments Processed</div></div>
            <div class="stat-item"><div class="number">{}</div><div class="label">Replies Posted</div></div>
            <div class="stat-item"><div class="number">🎁 {}/{}</div><div class="label">Free Used / Quota</div></div>
            <div class="stat-item"><div class="number">💰 {}</div><div class="label">Paid Used</div></div>
        </div>
        """.format(total_comments, total_replies, free_used, pricing['free']['replies'], paid_used), unsafe_allow_html=True)
        
        # Free tier progress
        free_pct = (free_used / pricing['free']['replies']) * 100 if pricing['free']['replies'] > 0 else 0
        st.markdown(f"""
        <div style="background: #f8f9fc; border-radius: 12px; padding: 16px 20px; margin-top: 12px; border: 1px solid #eef2f7;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                <span style="font-size: 14px; font-weight: 600; color: #1a1a2e;">🎁 Free Tier Usage</span>
                <span style="font-size: 14px; color: #636e72;">{free_used} / {pricing['free']['replies']} used</span>
            </div>
            <div class="usage-bar">
                <div class="usage-bar-fill" style="width: {min(free_pct, 100)}%;"></div>
            </div>
            <p style="font-size: 13px; color: #636e72; margin: 6px 0 0 0;">
                {pricing['free']['replies'] - free_used} free replies remaining this month
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
        <div style="background: #f8f9fc; border-radius: 12px; padding: 20px; margin-top: 16px; border: 1px solid #eef2f7;">
            <p style="color: #636e72; font-size: 14px; margin: 0;">
                💡 <strong>Tip:</strong> Go to the <strong>Home</strong> page to process more videos and grow your engagement!
            </p>
        </div>
        """, unsafe_allow_html=True)

# --- Footer ---
st.markdown("""
<div class="footer-text">
    <strong>ReplyWala</strong> — AI-powered YouTube comment replies · Built for creators
</div>
""", unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

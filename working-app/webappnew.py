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
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- Load Environment ---
load_dotenv()
YOUTUBE_API_KEY = os.getenv("API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# Stripe Keys
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")

# Price IDs (for Stripe products)
STARTER_INR = os.getenv("STRIPE_STARTER_INR")
STARTER_USD = os.getenv("STRIPE_STARTER_USD")
POPULAR_INR = os.getenv("STRIPE_POPULAR_INR")
POPULAR_USD = os.getenv("STRIPE_POPULAR_USD")
PRO_INR = os.getenv("STRIPE_PRO_INR")
PRO_USD = os.getenv("STRIPE_PRO_USD")

# --- Geolocation ---
def detect_country():
    """Detect user's country from IP address with manual override"""
    # Check for manual override via URL parameter
    query_params = st.query_params
    override = query_params.get('country', None)
    
    if override:
        if override.upper() == 'IN':
            return 'IN'
        elif override.upper() == 'US':
            return 'US'
        else:
            return override.upper()
    
    # If no override, detect via IP
    try:
        response = requests.get('https://ipapi.co/json/', timeout=5)
        if response.status_code == 200:
            data = response.json()
            country = data.get('country_code', 'US')
            return country
    except:
        pass
    
    # Default to US if detection fails
    return 'US'

def get_currency(country_code):
    if country_code == 'IN':
        return {'symbol': '₹', 'code': 'INR', 'is_india': True}
    else:
        return {'symbol': '$', 'code': 'USD', 'is_india': False}

def get_pricing(country_code):
    """Correct pricing from our plan - ₹49, ₹149, ₹399 | $4.99, $14.99, $39.99"""
    if country_code == 'IN':
        return {
            'free': {'replies': 10, 'label': 'Free'},
            'starter': {'replies': 100, 'price': 49, 'display': '49', 'label': 'Starter'},
            'popular': {'replies': 500, 'price': 149, 'display': '149', 'label': 'Popular'},
            'pro': {'replies': 1500, 'price': 399, 'display': '399', 'label': 'Pro'}
        }
    else:
        return {
            'free': {'replies': 10, 'label': 'Free'},
            'starter': {'replies': 100, 'price': 499, 'display': '4.99', 'label': 'Starter'},
            'popular': {'replies': 500, 'price': 1499, 'display': '14.99', 'label': 'Popular'},
            'pro': {'replies': 1500, 'price': 3999, 'display': '39.99', 'label': 'Pro'}
        }

country = detect_country()
currency = get_currency(country)
pricing = get_pricing(country)

def get_price_id(price_inr, price_usd):
    if currency['code'] == 'INR':
        return price_inr
    else:
        return price_usd

def create_checkout_session(price_id, reply_count, plan_name):
    try:
        user_id = get_user_id()
        base_url = "http://localhost:8501"
        payment_methods = ["card"]
        if currency['code'] == 'INR':
            payment_methods = ["card", "upi"]
        
        checkout_session = stripe.checkout.Session.create(
            line_items=[{"price": price_id, "quantity": 1}],
            mode="payment",
            success_url=f"{base_url}/?session_id={{CHECKOUT_SESSION_ID}}&success=true&plan={plan_name}",
            cancel_url=f"{base_url}/?canceled=true",
            metadata={"user_id": user_id, "reply_count": str(reply_count), "plan_name": plan_name},
            payment_method_types=payment_methods,
        )
        st.markdown(f'<meta http-equiv="refresh" content="0;url={checkout_session.url}">', unsafe_allow_html=True)
        st.info(f"🔄 Redirecting to Stripe Checkout... [Click here if not redirected]({checkout_session.url})")
    except Exception as e:
        st.error(f"❌ Failed to create checkout session: {e}")

# --- Usage Tracking ---
USAGE_FILE = 'usage.json'

def get_user_id():
    return 'default_user'

def load_usage(user_id):
    if os.path.exists(USAGE_FILE):
        with open(USAGE_FILE, 'r') as f:
            data = json.load(f)
            return data.get(user_id, {})
    return {}

def save_usage(user_id, usage_data):
    data = {}
    if os.path.exists(USAGE_FILE):
        with open(USAGE_FILE, 'r') as f:
            data = json.load(f)
    data[user_id] = usage_data
    with open(USAGE_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def get_usage(user_id):
    usage = load_usage(user_id)
    today = datetime.now().date().isoformat()
    if not usage:
        usage = {'free_used': 0, 'free_quota': 10, 'paid_used': 0, 'last_reset': today, 'total_replies': 0}
    if usage.get('last_reset') != today:
        last_reset = datetime.strptime(usage['last_reset'], '%Y-%m-%d')
        if last_reset.month != datetime.now().month:
            usage['free_used'] = 0
            usage['last_reset'] = today
    return usage

def can_use_free(usage):
    return usage['free_used'] < usage['free_quota']

def get_remaining_free(usage):
    return usage['free_quota'] - usage['free_used']

def track_reply_used(user_id):
    usage = get_usage(user_id)
    if can_use_free(usage):
        usage['free_used'] += 1
    else:
        usage['paid_used'] += 1
    usage['total_replies'] += 1
    save_usage(user_id, usage)
    return usage

# --- YouTube Functions ---
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

def filter_comments(comment_text):
    """Filter out hate comments, negative comments, and unrelated questions"""
    
    # Keywords that indicate hate or negative comments
    hate_keywords = [
        'hate', 'stupid', 'idiot', 'dumb', 'useless', 'waste', 'boring', 
        'terrible', 'awful', 'garbage', 'trash', 'dislike', 'worst',
        'pathetic', 'ridiculous', 'nonsense', 'pointless', 'annoying',
        'irritating', 'fool', 'moron', 'jerk', 'scam', 'fake'
    ]
    
    # Keywords that indicate questions that are open-ended or unrelated
    unrelated_keywords = [
        'how to', 'tutorial', 'where can I', 'how do I', 'what is',
        'explain', 'meaning', 'definition', 'difference between',
        'vs', 'compare', 'why is', 'when does', 'who is', 'which is'
    ]
    
    # Check for hate/negative comments
    text_lower = comment_text.lower()
    for word in hate_keywords:
        if word in text_lower:
            return {'filter': True, 'reason': 'hate_or_negative', 'message': 'Skipped: Hate or negative comment'}
    
    # For long comments, check if they're asking unrelated questions
    if len(comment_text) > 50:
        word_count = len(text_lower.split())
        # If it's a long comment with question marks, likely unrelated
        if '?' in text_lower:
            for word in unrelated_keywords:
                if word in text_lower:
                    return {'filter': True, 'reason': 'unrelated_question', 'message': 'Skipped: Unrelated question'}
    
    # If comment is very short (like "nice" or "good"), keep it
    if len(text_lower.split()) <= 3:
        return {'filter': False, 'reason': None, 'message': None}
    
    return {'filter': False, 'reason': None, 'message': None}


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

def generate_reply(comment_text, tone="friendly"):
    tone_prompts = {
        "friendly": "You are a friendly YouTube creator. Keep replies warm, appreciative, and engaging. Use emojis occasionally.",
        "professional": "You are a professional YouTube creator. Keep replies polished, respectful, and informative.",
        "funny": "You are a witty YouTube creator. Keep replies humorous, clever, and entertaining.",
        "short": "You are a direct YouTube creator. Keep replies brief, concise, and to the point. Under 20 words."
    }
    system_prompt = tone_prompts.get(tone, tone_prompts["friendly"])
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Comment: {comment_text}\n\nGenerate a short reply:"}
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
if 'user_email' not in st.session_state:
    st.session_state.user_email = ""
if 'tone' not in st.session_state:
    st.session_state.tone = "friendly"

# --- Professional CSS (Mobile-Responsive) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    
    * { font-family: 'Inter', sans-serif; }
    
    .stApp {
        background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 50%, #16213e 100%) !important;
    }
    .stApp > div { background: transparent !important; }
    
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;}
    
    /* Mobile-first responsive design */
    .hero-section {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem 1rem;
        border-radius: 16px;
        margin-bottom: 1rem;
        text-align: center;
        box-shadow: 0 20px 60px rgba(102, 126, 234, 0.3);
    }
    .hero-title {
        font-size: 1.8rem;
        font-weight: 800;
        color: white;
        letter-spacing: -1px;
    }
    .hero-tagline {
        font-size: 0.9rem;
        color: rgba(255,255,255,0.9);
        font-weight: 300;
    }
    
    .card {
        background: linear-gradient(145deg, #1e1e3f 0%, #252550 100%);
        border-radius: 12px;
        padding: 1rem;
        border: 1px solid rgba(255,255,255,0.1);
        box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        margin-bottom: 0.8rem;
    }
    .card-title {
        font-size: 1.1rem;
        font-weight: 700;
        color: #fff;
        margin-bottom: 0.3rem;
    }
    .card-subtitle {
        font-size: 0.8rem;
        color: rgba(255,255,255,0.6);
        margin-bottom: 0.8rem;
    }
    
    .stat-box {
        background: linear-gradient(145deg, #1e1e3f 0%, #252550 100%);
        border-radius: 10px;
        padding: 0.8rem;
        text-align: center;
        border: 1px solid rgba(255,255,255,0.1);
    }
    .stat-number {
        font-size: 1.5rem;
        font-weight: 800;
        color: #667eea;
        line-height: 1;
    }
    .stat-label {
        font-size: 0.7rem;
        color: rgba(255,255,255,0.6);
        margin-top: 0.2rem;
    }
    
    .comment-box {
        background: rgba(255,255,255,0.05);
        border-radius: 8px;
        padding: 0.8rem;
        margin-bottom: 0.5rem;
        border-left: 3px solid #667eea;
        color: white;
        font-size: 0.9rem;
    }
    .reply-box {
        background: rgba(102, 126, 234, 0.15);
        border-radius: 8px;
        padding: 0.8rem;
        margin-bottom: 0.5rem;
        border-left: 3px solid #38ef7d;
        color: white;
        font-size: 0.9rem;
    }
    
    /* Mobile-friendly tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.3rem;
        background: rgba(255,255,255,0.05);
        border-radius: 10px;
        padding: 0.3rem;
        flex-wrap: wrap;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px;
        color: rgba(255,255,255,0.7);
        font-weight: 600;
        font-size: 0.75rem;
        padding: 0.3rem 0.6rem !important;
        white-space: nowrap;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white !important;
    }
    
    .stTextInput input, .stTextArea textarea, .stSelectbox select {
        background: rgba(255,255,255,0.05) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        border-radius: 10px !important;
        color: white !important;
        font-size: 0.9rem !important;
        padding: 0.5rem 0.8rem !important;
    }
    
    .stButton button {
        border-radius: 10px !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        padding: 0.4rem 0.8rem !important;
        transition: all 0.3s ease !important;
    }
    .stButton button[kind="primary"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        color: white !important;
    }
    
    .divider {
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.15), transparent);
        margin: 1rem 0;
    }
    
    .footer-text {
        text-align: center;
        color: rgba(255,255,255,0.4);
        font-size: 0.7rem;
        padding: 1rem 0 0.5rem 0;
        border-top: 1px solid rgba(255,255,255,0.05);
    }
    .footer-text strong { color: rgba(255,255,255,0.7); }
    
    /* Pricing cards - mobile responsive */
    .pricing-grid {
        display: grid;
        grid-template-columns: 1fr;
        gap: 0.8rem;
    }
    @media (min-width: 768px) {
        .pricing-grid {
            grid-template-columns: repeat(3, 1fr);
        }
        .hero-title { font-size: 2.5rem; }
    }
    
    .pricing-card {
        background: linear-gradient(145deg, #1e1e3f 0%, #252550 100%);
        border-radius: 12px;
        padding: 1rem;
        text-align: center;
        border: 1px solid rgba(255,255,255,0.1);
        transition: all 0.3s ease;
    }
    .pricing-card.popular {
        border: 2px solid #FFD700;
    }
    .pricing-card .plan-price {
        font-size: 1.8rem;
        font-weight: 800;
        color: white;
        margin: 0.3rem 0;
    }
    .pricing-card .plan-price span {
        font-size: 0.8rem;
        font-weight: 400;
        color: rgba(255,255,255,0.5);
    }
    .pricing-card .plan-features {
        list-style: none;
        padding: 0;
        text-align: left;
        color: rgba(255,255,255,0.7);
        font-size: 0.8rem;
        line-height: 1.8;
    }
    .pricing-card .plan-features li::before {
        content: "✅ ";
        color: #38ef7d;
    }
    .badge-popular {
        background: #FFD700;
        color: #1a1a2e;
        padding: 2px 10px;
        border-radius: 20px;
        font-size: 0.7rem;
        font-weight: 700;
        display: inline-block;
        margin-bottom: 0.3rem;
    }
    .badge-free {
        background: #667eea;
        color: white;
        padding: 2px 10px;
        border-radius: 20px;
        font-size: 0.7rem;
        font-weight: 700;
        display: inline-block;
        margin-bottom: 0.3rem;
    }
    
    .step-container {
        display: grid;
        grid-template-columns: 1fr;
        gap: 0.5rem;
        margin: 0.5rem 0;
    }
    @media (min-width: 768px) {
        .step-container {
            grid-template-columns: repeat(4, 1fr);
        }
    }
    .step-item {
        background: rgba(255,255,255,0.05);
        border-radius: 10px;
        padding: 0.8rem;
        text-align: center;
        border: 1px solid rgba(255,255,255,0.05);
    }
    .step-number {
        font-size: 1.2rem;
        font-weight: 800;
        color: #667eea;
    }
    .step-title {
        font-weight: 600;
        color: white;
        font-size: 0.85rem;
        margin: 0.2rem 0;
    }
    .step-desc {
        font-size: 0.7rem;
        color: rgba(255,255,255,0.5);
    }
    
    .stAlert { border-radius: 10px !important; font-size: 0.85rem !important; }
    .stSuccess { background: rgba(56, 239, 125, 0.15) !important; border-left: 4px solid #38ef7d !important; }
    .stError { background: rgba(235, 51, 73, 0.15) !important; border-left: 4px solid #eb3349 !important; }
    .stWarning { background: rgba(255, 215, 0, 0.15) !important; border-left: 4px solid #FFD700 !important; }
    .stInfo { background: rgba(102, 126, 234, 0.15) !important; border-left: 4px solid #667eea !important; }
    
    .stSlider > div > div > div > div {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    }
    
    /* Mobile stats row */
    .stats-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 0.5rem;
    }
    @media (min-width: 768px) {
        .stats-grid {
            grid-template-columns: repeat(4, 1fr);
        }
    }
</style>
""", unsafe_allow_html=True)

# --- HEADER ---
st.markdown(f"""
<div class="hero-section">
    <div class="hero-title">🤖 ReplyWala</div>
    <div class="hero-tagline">AI-Powered YouTube Comment Management for Serious Creators</div>
</div>
""", unsafe_allow_html=True)

# Show filtering status
if hasattr(st.session_state, 'filtered_count') and st.session_state.filtered_count > 0:
    st.success(f"🛡️ Filtered out {st.session_state.filtered_count} hate/negative or unrelated comments")

# --- Currency Override ---
query_params = st.query_params
if query_params.get('country'):
    st.caption(f"🔧 Manual override active: Showing prices for {query_params.get('country')}")

# --- Navigation Tabs ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🚀 Home", "✨ Features", "💰 Pricing", "📊 Dashboard", "❓ Help"])

# ==================== TAB 1: HOME ====================
with tab1:
    is_logged_in = os.path.exists('token.pickle')
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.markdown("""
        <div class="card">
            <div class="card-title">🚀 Get Started</div>
            <div class="card-subtitle">Start auto-replying in under 2 minutes</div>
        </div>
        """, unsafe_allow_html=True)
        
        if not is_logged_in:
            if st.button("🔗 Connect YouTube Channel", type="primary", use_container_width=True):
                with st.spinner("Opening browser for login..."):
                    try:
                        youtube = get_authenticated_youtube()
                        st.success("✅ Connected successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Connection failed: {e}")
        else:
            st.success("✅ YouTube account connected")
            
            video_url = st.text_input(
                "YouTube Video URL",
                placeholder="https://www.youtube.com/watch?v=...",
                label_visibility="collapsed"
            )
            
            tone = st.selectbox(
                "🎭 AI Personality",
                ["friendly", "professional", "funny", "short"],
                format_func=lambda x: {
                    "friendly": "😊 Friendly - Warm & Appreciative",
                    "professional": "👔 Professional - Expert & Polite",
                    "funny": "😂 Funny - Witty & Humorous",
                    "short": "⚡ Short & Sweet - Brief & Direct"
                }[x]
            )
            st.session_state.tone = tone
            
            num_comments = st.slider(
                "📊 How many comments to process?",
                min_value=5,
                max_value=50,
                value=10,
                step=5
            )
            
            user_id = get_user_id()
            usage = get_usage(user_id)
            remaining_free = get_remaining_free(usage)
            
            st.markdown(f"""
            <div style="background: rgba(255,255,255,0.05); border-radius: 10px; padding: 0.6rem; text-align: center; margin: 0.3rem 0;">
                <div style="font-size: 0.75rem; color: rgba(255,255,255,0.5);">🎁 Free replies remaining</div>
                <div style="font-size: 1.2rem; font-weight: 700; color: #667eea;">{remaining_free} / {pricing['free']['replies']}</div>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("🚀 Generate Replies", type="primary", use_container_width=True):
                if not video_url:
                    st.error("❌ Please enter a YouTube URL")
                else:
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
    
    with col2:
        st.markdown("""
        <div class="card">
            <div class="card-title">How It Works</div>
            <div class="card-subtitle">Review before posting - full control</div>
        </div>
        """, unsafe_allow_html=True)
        
        steps = [
            ("1️⃣", "Connect", "Paste any YouTube link - we'll find your channel automatically"),
            ("2️⃣", "Fetch Comments", "AI reads your latest comments and generates replies"),
            ("3️⃣", "Review & Edit", "YOU see every reply before it goes live. Edit, approve, or skip"),
            ("4️⃣", "Post Approved", "Only the replies YOU approve get posted to YouTube")
        ]
        
        for emoji, title, desc in steps:
            st.markdown(f"""
            <div style="display: flex; align-items: start; margin-bottom: 1rem;">
                <div style="font-size: 1.3rem; margin-right: 0.8rem;">{emoji}</div>
                <div>
                    <div style="font-weight: 600; color: white; font-size: 0.9rem;">{title}</div>
                    <div style="color: rgba(255,255,255,0.5); font-size: 0.8rem; line-height: 1.4;">{desc}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

   # ---- Processing & Results ----
if st.session_state.processing and st.session_state.video_id:
    youtube = get_authenticated_youtube()
    with st.spinner(f"Fetching {num_comments} comments and generating AI replies..."):
        comments = get_comments(youtube, st.session_state.video_id, num_comments * 2)  # Fetch more to allow filtering
        
        if not comments:
            st.warning("No comments found on this video")
            st.session_state.processing = False
        else:
            # Filter comments
            filtered_comments = []
            filtered_count = 0
            
            for comment in comments:
                filter_result = filter_comments(comment['text'])
                if not filter_result['filter']:
                    filtered_comments.append(comment)
                else:
                    filtered_count += 1
                    # Store filtered count for display
                    if 'filtered_count' not in st.session_state:
                        st.session_state.filtered_count = 0
                    st.session_state.filtered_count += 1
            
            # Limit to the number requested
            filtered_comments = filtered_comments[:num_comments]
            
            if filtered_count > 0:
                st.info(f"🛡️ Filtered out {filtered_count} hate/negative or unrelated comments")
            
            if not filtered_comments:
                st.warning("All comments were filtered out. Try a different video or increase the limit.")
                st.session_state.processing = False
            else:
                st.session_state.comments = filtered_comments
                st.session_state.filtered_count = filtered_count
                for comment in filtered_comments:
                    reply = generate_reply(comment['text'], st.session_state.tone)
                    st.session_state.replies.append(reply)
                    st.session_state.posted[comment['id']] = False
                st.session_state.processing = False
                st.rerun()    
    if st.session_state.comments:
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
        st.markdown("""
        <div style="text-align: center; margin-bottom: 0.8rem;">
            <span style="font-size: 1.1rem; font-weight: 600; color: white;">📝 Review AI Replies</span>
            <span style="color: rgba(255,255,255,0.5); font-size: 0.8rem; margin-left: 0.3rem;">— Approve, edit, or skip each one</span>
        </div>
        """, unsafe_allow_html=True)
        
        total = len(st.session_state.comments)
        posted = sum(1 for v in st.session_state.posted.values() if v)
        
        st.markdown(f"""
        <div class="stats-grid" style="margin-bottom: 0.8rem;">
            <div class="stat-box"><div class="stat-number">{total}</div><div class="stat-label">Comments</div></div>
            <div class="stat-box"><div class="stat-number">{posted}</div><div class="stat-label">Approved</div></div>
            <div class="stat-box"><div class="stat-number">{total - posted}</div><div class="stat-label">Remaining</div></div>
            <div class="stat-box"><div class="stat-number">🎁 {remaining_free}</div><div class="stat-label">Free Left</div></div>
        </div>
        """, unsafe_allow_html=True)
        
        if posted < total:
            if st.button("📤 Post All Approved", use_container_width=True):
                youtube = get_authenticated_youtube()
                for idx, comment in enumerate(st.session_state.comments):
                    if st.session_state.posted.get(comment['id'], False):
                        reply = st.session_state.replies[idx]
                        result = post_reply(youtube, comment['id'], reply)
                        if result:
                            track_reply_used(user_id)
                        time.sleep(0.5)
                st.rerun()
        
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
        
        youtube = get_authenticated_youtube()
        for idx, comment in enumerate(st.session_state.comments):
            with st.container():
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"""
                    <div class="comment-box">
                        <div style="font-size: 0.7rem; color: rgba(255,255,255,0.5);">@{comment['author']}</div>
                        <div style="color: white; font-size: 0.85rem;">{comment['text'][:300]}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    if idx < len(st.session_state.replies):
                        reply = st.session_state.replies[idx]
                        st.markdown(f"""
                        <div class="reply-box">
                            <div style="font-size: 0.7rem; color: #38ef7d;">🤖 AI Reply</div>
                            <div style="color: white; font-size: 0.85rem;">{reply}</div>
                        </div>
                        """, unsafe_allow_html=True)
                with col2:
                    st.write("")
                    if not st.session_state.posted.get(comment['id'], False):
                        # Check if user has free replies left
                        usage_check = get_usage(user_id)
                        if can_use_free(usage_check) or usage_check.get('paid_used', 0) > 0:
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
                                        st.error("❌ Failed")
                        else:
                            st.warning("No credits left")
                    else:
                        st.markdown('<span style="color: #38ef7d; font-weight: 600; font-size: 0.85rem;">✅ Posted</span>', unsafe_allow_html=True)
                st.markdown('<div style="height: 1px; background: rgba(255,255,255,0.05); margin: 0.2rem 0;"></div>', unsafe_allow_html=True)

# ==================== TAB 2: FEATURES ====================
with tab2:
    st.markdown("""
    <div style="text-align: center; margin-bottom: 1rem;">
        <div style="font-size: 1.5rem; font-weight: 700; color: white;">✨ Powerful Features</div>
        <div style="color: rgba(255,255,255,0.6); font-size: 0.9rem;">Everything you need to manage YouTube comments at scale</div>
    </div>
    """, unsafe_allow_html=True)
    
    features = [
        ("🤖", "AI-Powered Replies", "Generate human-like replies using advanced AI."),
        ("📤", "Auto-Posting", "Post replies directly to YouTube with one click."),
        ("✏️", "Review Before Posting", "See every reply before it goes live. Edit, approve, or skip."),
        ("🎭", "AI Personalities", "Choose from Friendly, Professional, Funny, or Short tones."),
        ("📊", "Analytics Dashboard", "Track engagement and reply performance."),
        ("🛡️", "Full Control", "You approve every reply. No AI posting without your permission.")
    ]
    
    col1, col2 = st.columns(2)
    for i, (icon, title, desc) in enumerate(features):
        with col1 if i % 2 == 0 else col2:
            st.markdown(f"""
            <div class="card">
                <div style="font-size: 1.5rem; margin-bottom: 0.3rem;">{icon}</div>
                <div style="font-weight: 600; color: white; font-size: 1rem; margin-bottom: 0.2rem;">{title}</div>
                <div style="color: rgba(255,255,255,0.6); font-size: 0.8rem; line-height: 1.5;">{desc}</div>
            </div>
            """, unsafe_allow_html=True)

## ==================== TAB 3: PRICING ====================
# ==================== TAB 3: PRICING ====================
with tab3:
    st.markdown("""
    <div style="text-align: center; margin-bottom: 1.5rem;">
        <div style="font-size: 1.8rem; font-weight: 700; color: white;">Simple, Transparent Pricing</div>
        <div style="color: rgba(255,255,255,0.6);">Pay only for what you use. No hidden fees.</div>
    </div>
    """, unsafe_allow_html=True)
    
    p = pricing
    symbol = currency['symbol']
    
    # Display pricing cards with Buy buttons
    col1, col2, col3 = st.columns(3)
    
    # Starter Plan
    with col1:
        st.markdown(f"""
        <div class="pricing-card">
            <div class="plan-name" style="font-weight: 600; color: white; font-size: 1.1rem;">Starter</div>
            <div class="plan-price">{symbol}{p['starter']['display']} <span>/ {p['starter']['replies']} replies</span></div>
            <ul class="plan-features">
                <li>{p['starter']['replies']} AI replies</li>
                <li>Review before posting</li>
                <li>Basic analytics</li>
                <li>Email support</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        price_id = get_price_id(STARTER_INR, STARTER_USD)
        if price_id:
            if st.button(f"Buy Starter - {symbol}{p['starter']['display']}", key="buy_starter", type="primary", use_container_width=True):
                create_checkout_session(price_id, p['starter']['replies'], "Starter")
    
    # Popular Plan (Most Popular)
    with col2:
        st.markdown(f"""
        <div class="pricing-card popular">
            <div class="badge-popular">🔥 Most Popular</div>
            <div class="plan-name" style="font-weight: 600; color: white; font-size: 1.1rem;">Popular</div>
            <div class="plan-price">{symbol}{p['popular']['display']} <span>/ {p['popular']['replies']} replies</span></div>
            <ul class="plan-features">
                <li>{p['popular']['replies']} AI replies</li>
                <li>Review before posting</li>
                <li>Advanced analytics</li>
                <li>Priority support</li>
                <li>Smart filtering</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        price_id = get_price_id(POPULAR_INR, POPULAR_USD)
        if price_id:
            if st.button(f"Buy Popular - {symbol}{p['popular']['display']}", key="buy_popular", type="primary", use_container_width=True):
                create_checkout_session(price_id, p['popular']['replies'], "Popular")
    
    # Pro Plan
    with col3:
        st.markdown(f"""
        <div class="pricing-card">
            <div class="plan-name" style="font-weight: 600; color: white; font-size: 1.1rem;">Pro</div>
            <div class="plan-price">{symbol}{p['pro']['display']} <span>/ {p['pro']['replies']} replies</span></div>
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
        price_id = get_price_id(PRO_INR, PRO_USD)
        if price_id:
            if st.button(f"Buy Pro - {symbol}{p['pro']['display']}", key="buy_pro", type="primary", use_container_width=True):
                create_checkout_session(price_id, p['pro']['replies'], "Pro")
    
    st.markdown(f"""
    <div style="text-align: center; padding: 1rem 0; color: rgba(255,255,255,0.5); font-size: 0.85rem;">
        💳 India: UPI, Credit Card, Netbanking | Global: Credit Cards, PayPal<br>
        🌍 Prices shown in {currency['symbol']} {currency['code']} based on your location ({country})
    </div>
    """, unsafe_allow_html=True)
# ==================== TAB 4: DASHBOARD ====================
with tab4:
    if not os.path.exists('token.pickle'):
        st.markdown("""
        <div style="text-align: center; padding: 2rem;">
            <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">🔒</div>
            <div style="font-size: 1.1rem; font-weight: 600; color: white;">Connect Your YouTube Channel</div>
            <div style="color: rgba(255,255,255,0.6); font-size: 0.85rem;">Sign in to view your dashboard and manage replies</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        user_id = get_user_id()
        usage = get_usage(user_id)
        remaining_free = get_remaining_free(usage)
        total_comments = len(st.session_state.comments)
        total_replies = sum(1 for v in st.session_state.posted.values() if v)
        
        st.markdown(f"""
        <div class="stats-grid" style="margin-bottom: 1rem;">
            <div class="stat-box"><div class="stat-number">{remaining_free}</div><div class="stat-label">Free Replies Left</div></div>
            <div class="stat-box"><div class="stat-number">{usage.get('total_replies', 0)}</div><div class="stat-label">Total Replies</div></div>
            <div class="stat-box"><div class="stat-number">{total_comments}</div><div class="stat-label">Comments Fetched</div></div>
            <div class="stat-box"><div class="stat-number">{total_replies}</div><div class="stat-label">Replies Posted</div></div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
        <div class="card">
            <div class="card-title">📝 Pending Replies</div>
            <div class="card-subtitle">Review and approve AI-generated replies before they go live</div>
        </div>
        """, unsafe_allow_html=True)
        
        if not st.session_state.comments:
            st.info("💡 No comments processed yet. Go to the Home tab to fetch comments!")
        else:
            st.info(f"📊 {len(st.session_state.comments)} comments fetched. Use the Home tab to review and approve them.")

# ==================== TAB 5: HELP ====================
with tab5:
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div class="card">
            <div class="card-title">❓ What is ReplyWala?</div>
            <div style="color: rgba(255,255,255,0.8); font-size: 0.85rem; line-height: 1.7;">
                ReplyWala reads comments on your YouTube videos and generates AI replies in your voice. 
                <strong>You review every reply before it goes live</strong> — full control.
                <br><br>
                <strong>Perfect for:</strong>
                <ul style="color: rgba(255,255,255,0.7); font-size: 0.8rem; padding-left: 1.2rem;">
                    <li>Creators getting 50+ comments per video</li>
                    <li>Busy YouTubers who value audience interaction</li>
                    <li>Anyone who wants to save 2+ hours daily</li>
                </ul>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="card">
            <div class="card-title">💰 Pricing Explained</div>
            <div style="color: rgba(255,255,255,0.8); font-size: 0.85rem; line-height: 1.7;">
                <strong>Free Tier:</strong>
                <div style="color: rgba(255,255,255,0.6); font-size: 0.8rem;">10 AI replies/month. Perfect for testing.</div>
                <br>
                <strong>Creator Plan (₹149/month):</strong>
                <div style="color: rgba(255,255,255,0.6); font-size: 0.8rem;">500 replies, all AI personalities, priority support.</div>
                <br>
                <strong>Flex (Pay-As-You-Go):</strong>
                <div style="color: rgba(255,255,255,0.6); font-size: 0.8rem;">₹49 for 100 replies, ₹149 for 500, ₹399 for 1500. Never expires.</div>
                <br>
                <strong>Built for Indian creators.</strong>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
        <div class="card" style="margin-top: 0.5rem;">
            <div class="card-title">📞 Support</div>
            <div style="color: rgba(255,255,255,0.8); font-size: 0.85rem;">
                <div>📧 replywala03@gmail.com</div>
                <div>⏰ Response: Within 24 hours</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

# --- FOOTER ---
st.markdown(f"""
<div class="footer-text">
    <strong>ReplyWala</strong> — AI-powered YouTube comment replies · Built for creators<br>
    © 2026 ReplyWala. Made with ❤️ | Support: replywala03@gmail.com
</div>
""", unsafe_allow_html=True)

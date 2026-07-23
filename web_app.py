#!/usr/bin/env python3
"""
ReplyWala - Production Ready SaaS
YouTube Comment AI with OAuth, AI Replies, Stripe Payments, and more
"""

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

# ============================================================================
# PAGE CONFIGURATION
# ============================================================================
st.set_page_config(
    page_title="ReplyWala - YouTube Comment AI",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ============================================================================
# ENVIRONMENT & API KEYS
# ============================================================================
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
YOUTUBE_API_KEY = os.getenv("API_KEY")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)
stripe.api_key = STRIPE_SECRET_KEY

# Stripe Price IDs
STARTER_INR = os.getenv("STRIPE_STARTER_INR")
STARTER_USD = os.getenv("STRIPE_STARTER_USD")
POPULAR_INR = os.getenv("STRIPE_POPULAR_INR")
POPULAR_USD = os.getenv("STRIPE_POPULAR_USD")
PRO_INR = os.getenv("STRIPE_PRO_INR")
PRO_USD = os.getenv("STRIPE_PRO_USD")

# ============================================================================
# GEOLOCATION & PRICING
# ============================================================================
def detect_country():
    query_params = st.query_params
    override = query_params.get('country', None)
    if override:
        return override.upper()
    try:
        response = requests.get('https://ipapi.co/json/', timeout=5)
        if response.status_code == 200:
            return response.json().get('country_code', 'US')
    except:
        pass
    return 'US'

def get_currency(country_code):
    if country_code == 'IN':
        return {'symbol': '₹', 'code': 'INR'}
    else:
        return {'symbol': '$', 'code': 'USD'}

def get_pricing(country_code):
    if country_code == 'IN':
        return {
            'starter': {'replies': 100, 'display': '49', 'label': 'Starter'},
            'popular': {'replies': 500, 'display': '149', 'label': 'Popular'},
            'pro': {'replies': 1500, 'display': '399', 'label': 'Pro'}
        }
    else:
        return {
            'starter': {'replies': 100, 'display': '4.99', 'label': 'Starter'},
            'popular': {'replies': 500, 'display': '14.99', 'label': 'Popular'},
            'pro': {'replies': 1500, 'display': '39.99', 'label': 'Pro'}
        }

country = detect_country()
currency = get_currency(country)
pricing = get_pricing(country)

def get_price_id(price_inr, price_usd):
    return price_inr if currency['code'] == 'INR' else price_usd

def create_checkout_session(price_id, reply_count, plan_name):
    try:
        session = stripe.checkout.Session.create(
            line_items=[{"price": price_id, "quantity": 1}],
            mode="payment",
            success_url="https://replywala.onrender.com/?success=true",
            cancel_url="https://replywala.onrender.com/?canceled=true",
            payment_method_types=["card", "upi"] if currency['code'] == 'INR' else ["card"],
        )
        st.markdown(f'<meta http-equiv="refresh" content="0;url={session.url}">', unsafe_allow_html=True)
        st.info(f"🔄 Redirecting to Stripe... [Click here]({session.url})")
    except Exception as e:
        st.error(f"❌ Failed to create session: {e}")

# ============================================================================
# USAGE TRACKING (Free Tier)
# ============================================================================
USAGE_FILE = 'usage.json'

def get_user_id():
    return 'default_user'

def get_usage(user_id):
    if os.path.exists(USAGE_FILE):
        with open(USAGE_FILE, 'r') as f:
            data = json.load(f)
            return data.get(user_id, {})
    return {}

def save_usage(user_id, data):
    all_data = {}
    if os.path.exists(USAGE_FILE):
        with open(USAGE_FILE, 'r') as f:
            all_data = json.load(f)
    all_data[user_id] = data
    with open(USAGE_FILE, 'w') as f:
        json.dump(all_data, f, indent=2)

def get_remaining_free():
    usage = get_usage(get_user_id())
    today = datetime.now().date().isoformat()
    if not usage:
        usage = {'free_used': 0, 'last_reset': today}
    if usage.get('last_reset') != today:
        last_reset = datetime.strptime(usage['last_reset'], '%Y-%m-%d')
        if last_reset.month != datetime.now().month:
            usage['free_used'] = 0
            usage['last_reset'] = today
            save_usage(get_user_id(), usage)
    return max(0, 10 - usage.get('free_used', 0))

def track_reply_used():
    user_id = get_user_id()
    usage = get_usage(user_id)
    today = datetime.now().date().isoformat()
    if not usage:
        usage = {'free_used': 0, 'last_reset': today}
    usage['free_used'] = usage.get('free_used', 0) + 1
    save_usage(user_id, usage)

# ============================================================================
# LANGUAGE DETECTION
# ============================================================================
def detect_language(text):
    if re.search(r'[\u0900-\u097F]', text):
        return 'hindi'
    if re.search(r'[\u0A80-\u0AFF]', text):
        return 'gujarati'
    if re.search(r'[\u0B80-\u0BFF]', text):
        return 'tamil'
    if re.search(r'[\u0C00-\u0C7F]', text):
        return 'telugu'
    if re.search(r'[\u0980-\u09FF]', text):
        return 'bengali'
    return 'english'

def get_language_prompt(lang):
    prompts = {
        'hindi': "Reply in HINDI. Keep it warm and engaging.",
        'gujarati': "Reply in GUJARATI. Keep it warm and engaging.",
        'tamil': "Reply in TAMIL. Keep it warm and engaging.",
        'telugu': "Reply in TELUGU. Keep it warm and engaging.",
        'bengali': "Reply in BENGALI. Keep it warm and engaging.",
        'english': "Reply in ENGLISH. Keep it warm and engaging."
    }
    return prompts.get(lang, prompts['english'])

# ============================================================================
# COMMENT DETECTION
# ============================================================================
def is_negative_comment(text):
    negative_words = [
        'hate', 'stupid', 'idiot', 'dumb', 'useless', 'waste', 'boring',
        'terrible', 'awful', 'garbage', 'trash', 'dislike', 'worst',
        'pathetic', 'ridiculous', 'nonsense', 'pointless', 'annoying',
        'irritating', 'fool', 'moron', 'jerk', 'scam', 'fake',
        'bekar', 'ganda', 'kharaab', 'बेकार', 'गंदा', 'खराब', 'bad'
    ]
    text_lower = text.lower()
    for word in negative_words:
        if word in text_lower:
            return True
    return False

def is_question(text):
    if '?' in text:
        return True
    question_words = ['what', 'when', 'where', 'why', 'how', 'who', 'which',
                      'kya', 'kaise', 'kahan', 'kyon', 'kaun', 'क्या', 'कैसे', 'कहाँ', 'क्यों']
    text_lower = text.lower()
    first_word = text_lower.split()[0] if text_lower.split() else ''
    if first_word in question_words:
        return True
    q_count = sum(1 for w in question_words if w in text_lower)
    if q_count >= 2:
        return True
    return False

# ============================================================================
# YOUTUBE API FUNCTIONS
# ============================================================================
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

def get_authenticated_youtube():
    """Authenticate and return YouTube API client - works on Render"""
    creds = None
    token_file = 'token.pickle'
    
    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            import json, base64
            
            creds_base64 = os.getenv('CREDENTIALS_JSON_BASE64')
            if not creds_base64:
                st.error("❌ CREDENTIALS_JSON_BASE64 environment variable not set!")
                return None
            
            creds_json_str = base64.b64decode(creds_base64).decode('utf-8')
            creds_data = json.loads(creds_json_str)
            
            temp_creds_path = '/tmp/credentials.json'
            with open(temp_creds_path, 'w') as f:
                json.dump(creds_data, f)
            
            flow = InstalledAppFlow.from_client_secrets_file(
                temp_creds_path, 
                scopes=SCOPES,
                redirect_uri='https://replywala.onrender.com/oauth2callback'
            )
            
            # Check if we have the code from the redirect
            query_params = st.query_params
            code_from_url = query_params.get('code', None)
            
            if code_from_url:
                try:
                    flow.fetch_token(code=code_from_url)
                    creds = flow.credentials
                    st.success("✅ Authentication successful!")
                    with open(token_file, 'wb') as token:
                        pickle.dump(creds, token)
                    st.query_params.clear()
                    st.rerun()
                    return build('youtube', 'v3', credentials=creds)
                except Exception as e:
                    st.error(f"❌ Authentication failed: {e}")
                    st.query_params.clear()
                    return None
            
            # No code yet - show authorization link
            auth_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true'
            )
            
            st.info("🔐 Please authorize the app:")
            st.markdown(f"[Click here to authorize]({auth_url})")
            st.markdown("After authorizing, you'll be redirected back. **The code will be captured automatically.**")
            
            # Manual fallback
            st.markdown("---")
            st.markdown("**Or paste the code manually:**")
            code = st.text_input("Enter the authorization code:")
            
            if code:
                try:
                    flow.fetch_token(code=code)
                    creds = flow.credentials
                    st.success("✅ Authentication successful!")
                    with open(token_file, 'wb') as token:
                        pickle.dump(creds, token)
                    st.rerun()
                    return build('youtube', 'v3', credentials=creds)
                except Exception as e:
                    st.error(f"❌ Authentication failed: {e}")
                    return None
            
            return None
    
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

def get_comments_with_reply_status(youtube, video_id, max_results=20):
    try:
        request = youtube.commentThreads().list(
            part='snippet,replies',
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
            total_reply_count = item['snippet'].get('totalReplyCount', 0)
            has_replies = total_reply_count > 0
            
            comments.append({
                'id': comment_id,
                'author': author,
                'text': comment_text,
                'has_replies': has_replies,
                'reply_count': total_reply_count
            })
        return comments
    except HttpError as e:
        st.error(f"❌ Error fetching comments: {e}")
        return []

def generate_positive_reply(comment_text, tone="friendly", is_negative=False):
    lang = detect_language(comment_text)
    lang_prompt = get_language_prompt(lang)
    
    if is_negative:
        system_prompt = f"""{lang_prompt} 
        This comment is negative or critical. Your reply should:
        1. Acknowledge their feedback politely
        2. Thank them for their input
        3. Stay positive and constructive
        4. NOT be defensive or argumentative
        5. Keep it warm and professional
        Use emojis occasionally."""
    else:
        tone_prompts = {
            "friendly": "Be warm, appreciative, and engaging. Use emojis.",
            "professional": "Be polished, respectful, and informative.",
            "funny": "Be humorous, clever, and entertaining.",
            "short": "Be brief and concise. Under 20 words."
        }
        system_prompt = f"{lang_prompt} {tone_prompts.get(tone, tone_prompts['friendly'])}"
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Comment: {comment_text}\n\nGenerate a short reply in the SAME LANGUAGE as the comment:"}
            ],
            max_tokens=80,
            temperature=0.8
        )
        return response.choices[0].message.content.strip()
    except:
        if is_negative:
            return "Thank you for your feedback! I appreciate all input and will keep it in mind for future content. 🙏"
        return "Thanks for your comment! 🙌"

def post_reply(youtube, comment_id, reply_text):
    try:
        request = youtube.comments().insert(
            part='snippet',
            body={'snippet': {'parentId': comment_id, 'textOriginal': reply_text}}
        )
        return request.execute()
    except HttpError as e:
        st.error(f"❌ Error posting: {e}")
        return None

# ============================================================================
# SESSION STATE
# ============================================================================
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
if 'tone' not in st.session_state:
    st.session_state.tone = "friendly"
if 'edited_replies' not in st.session_state:
    st.session_state.edited_replies = {}
if 'negative_count' not in st.session_state:
    st.session_state.negative_count = 0
if 'skipped_count' not in st.session_state:
    st.session_state.skipped_count = 0

# ============================================================================
# CSS STYLES
# ============================================================================
st.markdown("""
<style>
    .stApp { background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 50%, #16213e 100%) !important; }
    .stApp > div { background: transparent !important; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;}
    
    .hero-section {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem 1rem;
        border-radius: 16px;
        margin-bottom: 1rem;
        text-align: center;
    }
    .hero-title { font-size: 1.8rem; font-weight: 800; color: white; }
    .hero-tagline { font-size: 0.9rem; color: rgba(255,255,255,0.9); }
    
    .card {
        background: linear-gradient(145deg, #1e1e3f 0%, #252550 100%);
        border-radius: 12px;
        padding: 1rem;
        border: 1px solid rgba(255,255,255,0.1);
        margin-bottom: 0.8rem;
    }
    .card-title { font-size: 1.1rem; font-weight: 700; color: #fff; }
    .card-subtitle { font-size: 0.8rem; color: rgba(255,255,255,0.6); }
    
    .stat-box {
        background: linear-gradient(145deg, #1e1e3f 0%, #252550 100%);
        border-radius: 10px;
        padding: 0.8rem;
        text-align: center;
        border: 1px solid rgba(255,255,255,0.1);
    }
    .stat-number { font-size: 1.5rem; font-weight: 800; color: #667eea; }
    .stat-label { font-size: 0.7rem; color: rgba(255,255,255,0.6); }
    
    .comment-box {
        background: rgba(255,255,255,0.05);
        border-radius: 8px;
        padding: 0.8rem;
        margin-bottom: 0.5rem;
        border-left: 3px solid #667eea;
        color: white;
    }
    .comment-box.negative {
        border-left-color: #f39c12;
    }
    .reply-box {
        background: rgba(102, 126, 234, 0.15);
        border-radius: 8px;
        padding: 0.8rem;
        margin-bottom: 0.5rem;
        border-left: 3px solid #38ef7d;
        color: white;
    }
    
    .pricing-card {
        background: linear-gradient(145deg, #1e1e3f 0%, #252550 100%);
        border-radius: 12px;
        padding: 1rem;
        text-align: center;
        border: 1px solid rgba(255,255,255,0.1);
    }
    .pricing-card.popular { border: 2px solid #FFD700; }
    .pricing-card .plan-price { font-size: 1.8rem; font-weight: 800; color: white; }
    .pricing-card .plan-price span { font-size: 0.8rem; color: rgba(255,255,255,0.5); }
    .pricing-card .plan-features {
        list-style: none; padding: 0; text-align: left;
        color: rgba(255,255,255,0.7); font-size: 0.8rem; line-height: 1.8;
    }
    .pricing-card .plan-features li::before { content: "✅ "; color: #38ef7d; }
    .badge-popular {
        background: #FFD700; color: #1a1a2e;
        padding: 2px 10px; border-radius: 20px;
        font-size: 0.7rem; font-weight: 700;
        display: inline-block;
    }
    
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
    .stTextArea textarea {
        min-height: 60px !important;
    }
    
    .stButton button {
        border-radius: 10px !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
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
</style>
""", unsafe_allow_html=True)

# ============================================================================
# HEADER
# ============================================================================
st.markdown("""
<div class="hero-section">
    <div class="hero-title">🤖 ReplyWala</div>
    <div class="hero-tagline">AI-Powered YouTube Comment Management for Serious Creators</div>
</div>
""", unsafe_allow_html=True)

# ============================================================================
# CURRENCY OVERRIDE
# ============================================================================
col1, col2, col3 = st.columns([3, 1, 1])
with col2:
    if st.button("🇮🇳 India"):
        st.query_params['country'] = 'IN'
        st.rerun()
with col3:
    if st.button("🌍 Global"):
        st.query_params['country'] = 'US'
        st.rerun()

# ============================================================================
# TABS
# ============================================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🚀 Home", "✨ Features", "💰 Pricing", "📊 Dashboard", "❓ Help"])

# ============================================================================
# TAB 1: HOME
# ============================================================================
with tab1:
    is_logged_in = os.path.exists('token.pickle')
    remaining_free = get_remaining_free()
    
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
                with st.spinner("Initializing authentication..."):
                    try:
                        youtube = get_authenticated_youtube()
                        if youtube:
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
            
            st.markdown(f"""
            <div style="background: rgba(255,255,255,0.05); border-radius: 10px; padding: 0.6rem; text-align: center;">
                <span style="color: rgba(255,255,255,0.5);">🎁 Free replies left: </span>
                <span style="color: #667eea; font-weight: 700;">{remaining_free} / 10</span>
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
                        st.session_state.edited_replies = {}
                        st.session_state.negative_count = 0
                        st.session_state.skipped_count = 0
                        st.rerun()
    
    with col2:
        st.markdown("""
        <div class="card">
            <div class="card-title">How It Works</div>
            <div class="card-subtitle">Review before posting - full control</div>
        </div>
        """, unsafe_allow_html=True)
        
        steps = [
            ("1️⃣", "Connect", "Paste any YouTube link"),
            ("2️⃣", "Fetch", "AI reads comments and detects which have replies"),
            ("3️⃣", "Review & Edit", "Edit, skip, or approve each reply"),
            ("4️⃣", "Post", "Only approved replies go live")
        ]
        
        for emoji, title, desc in steps:
            st.markdown(f"""
            <div style="display: flex; align-items: start; margin-bottom: 0.8rem;">
                <div style="font-size: 1.3rem; margin-right: 0.8rem;">{emoji}</div>
                <div>
                    <div style="font-weight: 600; color: white; font-size: 0.9rem;">{title}</div>
                    <div style="color: rgba(255,255,255,0.5); font-size: 0.8rem;">{desc}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    # ---- Processing ----
    if st.session_state.processing and st.session_state.video_id:
        youtube = get_authenticated_youtube()
        if youtube:
            with st.spinner(f"Fetching {num_comments} comments..."):
                comments = get_comments_with_reply_status(youtube, st.session_state.video_id, num_comments * 2)
                if not comments:
                    st.warning("No comments found on this video")
                    st.session_state.processing = False
                else:
                    unreplied_comments = [c for c in comments if not c['has_replies']]
                    skipped_replied = len(comments) - len(unreplied_comments)
                    
                    if skipped_replied > 0:
                        st.info(f"⏭️ Skipped {skipped_replied} comments that already have replies")
                    
                    unreplied_comments = unreplied_comments[:num_comments]
                    
                    if not unreplied_comments:
                        st.warning("No unreplied comments found on this video")
                        st.session_state.processing = False
                    else:
                        st.session_state.comments = unreplied_comments
                        st.session_state.replies = []
                        st.session_state.posted = {}
                        st.session_state.edited_replies = {}
                        st.session_state.negative_count = 0
                        st.session_state.skipped_count = 0
                        
                        for comment in unreplied_comments:
                            is_neg = is_negative_comment(comment['text'])
                            if is_neg:
                                st.session_state.negative_count += 1
                            
                            reply = generate_positive_reply(
                                comment['text'], 
                                st.session_state.tone, 
                                is_neg
                            )
                            st.session_state.replies.append(reply)
                            st.session_state.posted[comment['id']] = False
                            st.session_state.edited_replies[comment['id']] = reply
                        
                        st.session_state.processing = False
                        st.rerun()
    
    # ---- Display Results ----
    if st.session_state.comments:
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
        
        total = len(st.session_state.comments)
        posted = sum(1 for v in st.session_state.posted.values() if v and v != 'skipped')
        negative_count = st.session_state.negative_count
        
        if negative_count > 0:
            st.info(f"💬 {negative_count} negative comments detected. AI will respond with positive, constructive replies.")
        
        st.markdown(f"""
        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.5rem; margin-bottom: 0.8rem;">
            <div class="stat-box"><div class="stat-number">{total}</div><div class="stat-label">Unreplied Comments</div></div>
            <div class="stat-box"><div class="stat-number">{posted}</div><div class="stat-label">Replies Posted</div></div>
            <div class="stat-box"><div class="stat-number">{total - posted}</div><div class="stat-label">Remaining</div></div>
            <div class="stat-box"><div class="stat-number">🎁 {remaining_free}</div><div class="stat-label">Free Left</div></div>
        </div>
        """, unsafe_allow_html=True)
        
        youtube = get_authenticated_youtube()
        if youtube:
            for idx, comment in enumerate(st.session_state.comments):
                with st.container():
                    is_neg = is_negative_comment(comment['text'])
                    neg_badge = "⚠️ Negative" if is_neg else ""
                    reply_status = f"💬 {comment['reply_count']} replies" if comment['has_replies'] else "🆕 No replies yet"
                    
                    st.markdown(f"""
                    <div class="comment-box {'negative' if is_neg else ''}">
                        <div style="display: flex; justify-content: space-between; font-size: 0.7rem; color: rgba(255,255,255,0.5);">
                            <span>@{comment['author']}</span>
                            <span>{reply_status}</span>
                        </div>
                        <div style="color: white; font-size: 0.85rem; margin-top: 0.2rem;">{comment['text']}</div>
                        {f'<div style="color: #f39c12; font-size: 0.7rem; margin-top: 0.2rem;">⚠️ {neg_badge}</div>' if is_neg else ''}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if idx < len(st.session_state.replies):
                        current_reply = st.session_state.edited_replies.get(comment['id'], st.session_state.replies[idx])
                        
                        edited_reply = st.text_area(
                            f"✏️ Reply #{idx+1}",
                            value=current_reply,
                            key=f"edit_{comment['id']}",
                            height=60
                        )
                        
                        if edited_reply != current_reply:
                            st.session_state.edited_replies[comment['id']] = edited_reply
                        
                        col1, col2 = st.columns([1, 1])
                        
                        with col1:
                            if not st.session_state.posted.get(comment['id'], False) or st.session_state.posted.get(comment['id']) == 'skipped':
                                if st.button(f"✅ Post Reply", key=f"post_{comment['id']}", use_container_width=True):
                                    if remaining_free > 0:
                                        reply_to_post = st.session_state.edited_replies.get(comment['id'], st.session_state.replies[idx])
                                        with st.spinner("Posting to YouTube..."):
                                            result = post_reply(youtube, comment['id'], reply_to_post)
                                            if result:
                                                st.session_state.posted[comment['id']] = True
                                                track_reply_used()
                                                st.success("✅ Posted!")
                                                time.sleep(0.3)
                                                st.rerun()
                                            else:
                                                st.error("❌ Failed to post")
                                    else:
                                        st.warning("⚠️ No free credits left")
                            else:
                                st.success("✅ Posted")
                        
                        with col2:
                            if not st.session_state.posted.get(comment['id'], False):
                                if st.button(f"⏭️ Skip", key=f"skip_{comment['id']}", use_container_width=True):
                                    st.session_state.posted[comment['id']] = 'skipped'
                                    st.session_state.skipped_count += 1
                                    st.success("⏭️ Skipped")
                                    st.rerun()
                            elif st.session_state.posted.get(comment['id']) == 'skipped':
                                st.info("⏭️ Skipped")
                        
                        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

# ============================================================================
# TAB 2: FEATURES
# ============================================================================
with tab2:
    st.markdown("""
    <div style="text-align: center; margin-bottom: 1rem;">
        <div style="font-size: 1.5rem; font-weight: 700; color: white;">✨ Features</div>
    </div>
    """, unsafe_allow_html=True)
    
    features = [
        ("🤖", "AI Replies", "Human-like replies in multiple languages"),
        ("🌍", "Multi-Language", "Hindi, Gujarati, Tamil, English, and more"),
        ("✏️", "Edit Before Post", "Edit any AI reply before it goes live"),
        ("💬", "Unreplied Only", "Only replies to comments without existing replies"),
        ("🎭", "AI Personalities", "Friendly, Professional, Funny, or Short"),
        ("🔄", "Positive Responses", "Turns negative comments into positive engagement"),
        ("🎁", "Free Tier", "10 free replies every month"),
        ("💰", "Global Pricing", "₹ for India, $ for the rest of the world")
    ]
    
    col1, col2 = st.columns(2)
    for i, (icon, title, desc) in enumerate(features):
        with col1 if i % 2 == 0 else col2:
            st.markdown(f"""
            <div class="card">
                <div style="font-size: 1.5rem;">{icon}</div>
                <div style="font-weight: 600; color: white;">{title}</div>
                <div style="color: rgba(255,255,255,0.6); font-size: 0.8rem;">{desc}</div>
            </div>
            """, unsafe_allow_html=True)

# ============================================================================
# TAB 3: PRICING
# ============================================================================
with tab3:
    st.markdown("""
    <div style="text-align: center; margin-bottom: 1rem;">
        <div style="font-size: 1.5rem; font-weight: 700; color: white;">Simple Pricing</div>
        <div style="color: rgba(255,255,255,0.6);">Pay only for what you use</div>
    </div>
    """, unsafe_allow_html=True)
    
    p = pricing
    symbol = currency['symbol']
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(f"""
        <div class="pricing-card">
            <div style="font-weight: 600; color: white;">Starter</div>
            <div class="plan-price">{symbol}{p['starter']['display']} <span>/ {p['starter']['replies']} replies</span></div>
            <ul class="plan-features">
                <li>{p['starter']['replies']} AI replies</li>
                <li>Review before posting</li>
                <li>Email support</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        price_id = get_price_id(STARTER_INR, STARTER_USD)
        if price_id and st.button(f"Buy - {symbol}{p['starter']['display']}", key="s", use_container_width=True):
            create_checkout_session(price_id, p['starter']['replies'], "Starter")
    
    with col2:
        st.markdown(f"""
        <div class="pricing-card popular">
            <div class="badge-popular">🔥 Most Popular</div>
            <div style="font-weight: 600; color: white;">Popular</div>
            <div class="plan-price">{symbol}{p['popular']['display']} <span>/ {p['popular']['replies']} replies</span></div>
            <ul class="plan-features">
                <li>{p['popular']['replies']} AI replies</li>
                <li>Review before posting</li>
                <li>Priority support</li>
                <li>Smart filtering</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        price_id = get_price_id(POPULAR_INR, POPULAR_USD)
        if price_id and st.button(f"Buy - {symbol}{p['popular']['display']}", key="p", use_container_width=True):
            create_checkout_session(price_id, p['popular']['replies'], "Popular")
    
    with col3:
        st.markdown(f"""
        <div class="pricing-card">
            <div style="font-weight: 600; color: white;">Pro</div>
            <div class="plan-price">{symbol}{p['pro']['display']} <span>/ {p['pro']['replies']} replies</span></div>
            <ul class="plan-features">
                <li>{p['pro']['replies']} AI replies</li>
                <li>Review before posting</li>
                <li>Priority support</li>
                <li>Smart filtering</li>
                <li>Bulk processing</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        price_id = get_price_id(PRO_INR, PRO_USD)
        if price_id and st.button(f"Buy - {symbol}{p['pro']['display']}", key="pr", use_container_width=True):
            create_checkout_session(price_id, p['pro']['replies'], "Pro")
    
    st.markdown(f"""
    <div style="text-align: center; padding: 0.5rem; color: rgba(255,255,255,0.5); font-size: 0.8rem;">
        💳 India: UPI, Credit Card | Global: Credit Cards<br>
        🌍 Prices in {currency['symbol']} {currency['code']} ({country})
    </div>
    """, unsafe_allow_html=True)

# ============================================================================
# TAB 4: DASHBOARD
# ============================================================================
with tab4:
    if not os.path.exists('token.pickle'):
        st.info("🔒 Connect your YouTube channel first")
    else:
        remaining_free = get_remaining_free()
        total_comments = len(st.session_state.comments)
        posted = sum(1 for v in st.session_state.posted.values() if v and v != 'skipped')
        skipped = sum(1 for v in st.session_state.posted.values() if v == 'skipped')
        negative_count = st.session_state.negative_count
        
        st.markdown(f"""
        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.5rem;">
            <div class="stat-box"><div class="stat-number">{remaining_free}</div><div class="stat-label">Free Left</div></div>
            <div class="stat-box"><div class="stat-number">{total_comments}</div><div class="stat-label">Unreplied</div></div>
            <div class="stat-box"><div class="stat-number">{posted}</div><div class="stat-label">Posted</div></div>
            <div class="stat-box"><div class="stat-number">{skipped}</div><div class="stat-label">Skipped</div></div>
            <div class="stat-box"><div class="stat-number">{negative_count}</div><div class="stat-label">Negative</div></div>
            <div class="stat-box"><div class="stat-number">{total_comments - posted - skipped}</div><div class="stat-label">Pending</div></div>
        </div>
        """, unsafe_allow_html=True)

# ============================================================================
# TAB 5: HELP
# ============================================================================
with tab5:
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div class="card">
            <div class="card-title">❓ What is ReplyWala?</div>
            <div style="color: rgba(255,255,255,0.8); font-size: 0.85rem; line-height: 1.8;">
                ReplyWala reads comments on your YouTube videos and generates AI replies in your voice. 
                <strong>You review every reply before it goes live</strong> — full control.
                <br><br>
                <strong>Key Features:</strong>
                <ul style="color: rgba(255,255,255,0.7); padding-left: 1.2rem;">
                    <li>Only replies to unreplied comments</li>
                    <li>Positive responses to negative comments</li>
                    <li>Multi-language support (Hindi, Gujarati, Tamil, English)</li>
                    <li>Edit, skip, or approve each reply</li>
                </ul>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="card">
            <div class="card-title">💰 Pricing</div>
            <div style="color: rgba(255,255,255,0.8); font-size: 0.85rem; line-height: 1.8;">
                <strong>Free:</strong> 10 replies/month<br>
                <strong>Starter:</strong> 100 replies<br>
                <strong>Popular:</strong> 500 replies (Best value)<br>
                <strong>Pro:</strong> 1500 replies (Power user)
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
        <div class="card" style="margin-top: 0.5rem;">
            <div class="card-title">📞 Support</div>
            <div style="color: rgba(255,255,255,0.8);">
                📧 replywala03@gmail.com
            </div>
        </div>
        """, unsafe_allow_html=True)

# ============================================================================
# FOOTER
# ============================================================================
st.markdown("""
<div class="footer-text">
    <strong>ReplyWala</strong> — AI-powered YouTube replies · Built for creators<br>
    © 2026 ReplyWala | Support: replywala03@gmail.com
</div>
""", unsafe_allow_html=True)

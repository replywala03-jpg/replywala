#!/usr/bin/env python3
"""
ReplyWala - Complete SaaS Application
Features: YouTube OAuth, AI Replies, Stripe Payments, Geolocation, Free Tier, Comment Filtering
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
# LOAD ENVIRONMENT
# ============================================================================
load_dotenv()

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")#!/usr/bin/env python3
"""
ReplyWala - Complete SaaS Application
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
# PAGE CONFIG
# ============================================================================
st.set_page_config(
    page_title="ReplyWala - YouTube Comment AI",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ============================================================================
# ENVIRONMENT
# ============================================================================
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

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
            'starter': {'replies': 100, 'price': 49, 'display': '49', 'label': 'Starter'},
            'popular': {'replies': 500, 'price': 149, 'display': '149', 'label': 'Popular'},
            'pro': {'replies': 1500, 'price': 399, 'display': '399', 'label': 'Pro'}
        }
    else:
        return {
            'starter': {'replies': 100, 'price': 499, 'display': '4.99', 'label': 'Starter'},
            'popular': {'replies': 500, 'price': 1499, 'display': '14.99', 'label': 'Popular'},
            'pro': {'replies': 1500, 'price': 3999, 'display': '39.99', 'label': 'Pro'}
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
            success_url="http://localhost:8501/?success=true",
            cancel_url="http://localhost:8501/?canceled=true",
            payment_method_types=["card", "upi"] if currency['code'] == 'INR' else ["card"],
        )
        st.markdown(f'<meta http-equiv="refresh" content="0;url={session.url}">', unsafe_allow_html=True)
        st.info(f"🔄 Redirecting to Stripe... [Click here]({session.url})")
    except Exception as e:
        st.error(f"❌ {e}")

# ============================================================================
# USAGE TRACKING
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
    """Detect language of the comment"""
    # Devanagari (Hindi, Marathi, etc.)
    if re.search(r'[\u0900-\u097F]', text):
        return 'hindi'
    # Gujarati
    if re.search(r'[\u0A80-\u0AFF]', text):
        return 'gujarati'
    # Tamil
    if re.search(r'[\u0B80-\u0BFF]', text):
        return 'tamil'
    # Telugu
    if re.search(r'[\u0C00-\u0C7F]', text):
        return 'telugu'
    # Bengali
    if re.search(r'[\u0980-\u09FF]', text):
        return 'bengali'
    # Default to English
    return 'english'

def get_language_prompt(lang):
    prompts = {
        'hindi': "Reply in HINDI. Keep it warm and engaging. Use emojis.",
        'gujarati': "Reply in GUJARATI. Keep it warm and engaging. Use emojis.",
        'tamil': "Reply in TAMIL. Keep it warm and engaging. Use emojis.",
        'telugu': "Reply in TELUGU. Keep it warm and engaging. Use emojis.",
        'bengali': "Reply in BENGALI. Keep it warm and engaging. Use emojis.",
        'english': "Reply in ENGLISH. Keep it warm and engaging. Use emojis."
    }
    return prompts.get(lang, prompts['english'])

# ============================================================================
# COMMENT FILTERING (FIXED)
# ============================================================================
def should_filter_comment(text):
    """Check if comment should be filtered out (negative or question)"""
    text_lower = text.lower()
    
    # === NEGATIVE KEYWORDS ===
    negative_words = [
        'hate', 'stupid', 'idiot', 'dumb', 'useless', 'waste', 'boring',
        'terrible', 'awful', 'garbage', 'trash', 'dislike', 'worst',
        'pathetic', 'ridiculous', 'nonsense', 'pointless', 'annoying',
        'irritating', 'fool', 'moron', 'jerk', 'scam', 'fake',
        'bekar', 'ganda', 'kharaab', 'बेकार', 'गंदा', 'खराब', 'bad', 'worst'
    ]
    
    for word in negative_words:
        if word in text_lower:
            return True, 'negative'
    
    # === QUESTIONS ===
    # Check for question marks
    if '?' in text:
        return True, 'question'
    
    # Check for question words
    question_words = ['what', 'when', 'where', 'why', 'how', 'who', 'which',
                      'kya', 'kaise', 'kahan', 'kyon', 'kaun', 'क्या', 'कैसे', 'कहाँ', 'क्यों']
    
    # Check if any question word is at the start
    first_word = text_lower.split()[0] if text_lower.split() else ''
    if first_word in question_words:
        return True, 'question'
    
    # Check if there are multiple question words
    q_count = sum(1 for w in question_words if w in text_lower)
    if q_count >= 2:
        return True, 'question'
    
    return False, None

# ============================================================================
# YOUTUBE FUNCTIONS
# ============================================================================
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

def generate_reply(comment_text, tone="friendly"):
    """Generate reply in the same language as the comment"""
    lang = detect_language(comment_text)
    lang_prompt = get_language_prompt(lang)
    
    tone_prompts = {
        "friendly": "Be warm, appreciative, and engaging.",
        "professional": "Be polished, respectful, and informative.",
        "funny": "Be humorous, clever, and entertaining.",
        "short": "Be brief and concise. Under 20 words."
    }
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"{lang_prompt} {tone_prompts.get(tone, tone_prompts['friendly'])}"},
                {"role": "user", "content": f"Comment: {comment_text}\n\nGenerate a short reply in the SAME LANGUAGE as the comment:"}
            ],
            max_tokens=80,
            temperature=0.8
        )
        return response.choices[0].message.content.strip()
    except:
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
if 'filtered_count' not in st.session_state:
    st.session_state.filtered_count = 0
if 'filtered_details' not in st.session_state:
    st.session_state.filtered_details = []

# ============================================================================
# CSS
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
                with st.spinner("Opening browser..."):
                    try:
                        youtube = get_authenticated_youtube()
                        st.success("✅ Connected!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ {e}")
        else:
            st.success("✅ YouTube connected")
            
            video_url = st.text_input(
                "YouTube Video URL",
                placeholder="https://www.youtube.com/watch?v=...",
                label_visibility="collapsed"
            )
            
            tone = st.selectbox(
                "🎭 AI Personality",
                ["friendly", "professional", "funny", "short"],
                format_func=lambda x: {
                    "friendly": "😊 Friendly",
                    "professional": "👔 Professional",
                    "funny": "😂 Funny",
                    "short": "⚡ Short & Sweet"
                }[x]
            )
            st.session_state.tone = tone
            
            num_comments = st.slider(
                "📊 How many comments?",
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
                        st.error("❌ Invalid URL")
                    else:
                        st.session_state.video_id = video_id
                        st.session_state.processing = True
                        st.session_state.comments = []
                        st.session_state.replies = []
                        st.session_state.posted = {}
                        st.session_state.edited_replies = {}
                        st.session_state.filtered_count = 0
                        st.session_state.filtered_details = []
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
            ("2️⃣", "Fetch", "AI reads comments"),
            ("3️⃣", "Review & Edit", "Edit or skip each reply"),
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
        with st.spinner(f"Fetching {num_comments} comments..."):
            comments = get_comments(youtube, st.session_state.video_id, num_comments * 2)
            if not comments:
                st.warning("No comments found")
                st.session_state.processing = False
            else:
                filtered_comments = []
                filtered_count = 0
                filtered_details = []
                
                for comment in comments:
                    should_filter, reason = should_filter_comment(comment['text'])
                    if should_filter:
                        filtered_count += 1
                        filtered_details.append(f"❌ '{comment['text'][:40]}...' ({reason})")
                    else:
                        filtered_comments.append(comment)
                
                filtered_comments = filtered_comments[:num_comments]
                st.session_state.filtered_count = filtered_count
                st.session_state.filtered_details = filtered_details
                
                if not filtered_comments:
                    st.warning("All comments filtered out")
                    st.session_state.processing = False
                else:
                    st.session_state.comments = filtered_comments
                    st.session_state.replies = []
                    st.session_state.posted = {}
                    st.session_state.edited_replies = {}
                    
                    for comment in filtered_comments:
                        reply = generate_reply(comment['text'], st.session_state.tone)
                        st.session_state.replies.append(reply)
                        st.session_state.posted[comment['id']] = False
                        st.session_state.edited_replies[comment['id']] = reply
                    
                    st.session_state.processing = False
                    st.rerun()
    
    # ---- Display Results ----
    if st.session_state.comments:
        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
        
        # Show filtered count
        if st.session_state.filtered_count > 0:
            with st.expander(f"🛡️ {st.session_state.filtered_count} comments filtered out"):
                for detail in st.session_state.filtered_details[:10]:
                    st.write(detail)
        
        st.markdown("""
        <div style="text-align: center; margin-bottom: 0.8rem;">
            <span style="font-size: 1.1rem; font-weight: 600; color: white;">📝 Review & Edit Replies</span>
            <span style="color: rgba(255,255,255,0.5); font-size: 0.8rem;">— Edit, approve, or skip</span>
        </div>
        """, unsafe_allow_html=True)
        
        total = len(st.session_state.comments)
        posted = sum(1 for v in st.session_state.posted.values() if v)
        
        st.markdown(f"""
        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.5rem; margin-bottom: 0.8rem;">
            <div class="stat-box"><div class="stat-number">{total}</div><div class="stat-label">Comments</div></div>
            <div class="stat-box"><div class="stat-number">{posted}</div><div class="stat-label">Approved</div></div>
            <div class="stat-box"><div class="stat-number">{total - posted}</div><div class="stat-label">Remaining</div></div>
            <div class="stat-box"><div class="stat-number">🎁 {remaining_free}</div><div class="stat-label">Free Left</div></div>
        </div>
        """, unsafe_allow_html=True)
        
        youtube = get_authenticated_youtube()
        
        for idx, comment in enumerate(st.session_state.comments):
            with st.container():
                st.markdown(f"""
                <div class="comment-box">
                    <div style="font-size: 0.7rem; color: rgba(255,255,255,0.5);">@{comment['author']}</div>
                    <div style="color: white; font-size: 0.85rem;">{comment['text']}</div>
                </div>
                """, unsafe_allow_html=True)
                
                if idx < len(st.session_state.replies):
                    current_reply = st.session_state.edited_replies.get(comment['id'], st.session_state.replies[idx])
                    
                    # Editable text area
                    edited_reply = st.text_area(
                        f"✏️ Reply #{idx+1}",
                        value=current_reply,
                        key=f"edit_{comment['id']}",
                        height=60
                    )
                    
                    # Save edit
                    if edited_reply != current_reply:
                        st.session_state.edited_replies[comment['id']] = edited_reply
                    
                    # Action buttons
                    col1, col2, col3 = st.columns([1, 1, 1])
                    
                    with col1:
                        if not st.session_state.posted.get(comment['id'], False):
                            if st.button(f"✅ Approve & Post", key=f"post_{comment['id']}", use_container_width=True):
                                if remaining_free > 0:
                                    reply_to_post = st.session_state.edited_replies.get(comment['id'], st.session_state.replies[idx])
                                    with st.spinner("Posting..."):
                                        result = post_reply(youtube, comment['id'], reply_to_post)
                                        if result:
                                            st.session_state.posted[comment['id']] = True
                                            track_reply_used()
                                            st.success("✅ Posted!")
                                            time.sleep(0.3)
                                            st.rerun()
                                        else:
                                            st.error("❌ Failed")
                                else:
                                    st.warning("⚠️ No free credits left")
                    
                    with col2:
                        if not st.session_state.posted.get(comment['id'], False):
                            if st.button(f"🔄 Regenerate", key=f"regen_{comment['id']}", use_container_width=True):
                                new_reply = generate_reply(comment['text'], st.session_state.tone)
                                st.session_state.replies[idx] = new_reply
                                st.session_state.edited_replies[comment['id']] = new_reply
                                st.rerun()
                    
                    with col3:
                        if not st.session_state.posted.get(comment['id'], False):
                            if st.button(f"❌ Skip", key=f"skip_{comment['id']}", use_container_width=True):
                                st.session_state.posted[comment['id']] = 'skipped'
                                st.success("⏭️ Skipped")
                                st.rerun()
                        else:
                            st.success("✅ Done")
                    
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
        ("🤖", "AI Replies", "Human-like replies"),
        ("🌍", "Multi-Language", "Hindi, Gujarati, Tamil, English"),
        ("✏️", "Edit Before Post", "Full control"),
        ("🛡️", "Smart Filtering", "Skip negatives & questions"),
        ("🎭", "AI Personalities", "Friendly, Professional, Funny, Short"),
        ("🎁", "Free Tier", "10 replies/month")
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
        if price_id and st.button(f"Buy - {symbol}{p['starter']['display']}", key="s"):
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
        if price_id and st.button(f"Buy - {symbol}{p['popular']['display']}", key="p"):
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
        if price_id and st.button(f"Buy - {symbol}{p['pro']['display']}", key="pr"):
            create_checkout_session(price_id, p['pro']['replies'], "Pro")
    
    st.markdown(f"""
    <div style="text-align: center; padding: 0.5rem; color: rgba(255,255,255,0.5); font-size: 0.8rem;">
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
        posted = sum(1 for v in st.session_state.posted.values() if v)
        
        st.markdown(f"""
        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.5rem;">
            <div class="stat-box"><div class="stat-number">{remaining_free}</div><div class="stat-label">Free Left</div></div>
            <div class="stat-box"><div class="stat-number">{total_comments}</div><div class="stat-label">Comments</div></div>
            <div class="stat-box"><div class="stat-number">{posted}</div><div class="stat-label">Posted</div></div>
            <div class="stat-box"><div class="stat-number">{total_comments - posted}</div><div class="stat-label">Pending</div></div>
        </div>
        """, unsafe_allow_html=True)

# ============================================================================
# TAB 5: HELP
# ============================================================================
with tab5:
    st.markdown("""
    <div class="card">
        <div class="card-title">❓ Help</div>
        <div style="color: rgba(255,255,255,0.8); font-size: 0.85rem; line-height: 1.8;">
            <strong>How it works:</strong><br>
            1. Connect YouTube → 2. Fetch comments → 3. Review & Edit → 4. Post
            <br><br>
            <strong>Filtering:</strong><br>
            🛡️ Negative comments and questions are automatically filtered out.
            <br><br>
            <strong>Editing:</strong><br>
            ✏️ You can edit any AI reply before posting.
            <br><br>
            <strong>Support:</strong><br>
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
client = OpenAI(api_key=OPENAI_API_KEY)

# YouTube
YOUTUBE_API_KEY = os.getenv("API_KEY")

# Stripe
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
stripe.api_key = STRIPE_SECRET_KEY

# Stripe Price IDs - One-Time Products
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
    """Detect user's country from IP address with manual override"""
    query_params = st.query_params
    override = query_params.get('country', None)
    if override:
        return override.upper()
    try:
        response = requests.get('https://ipapi.co/json/', timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get('country_code', 'US')
    except:
        pass
    return 'US'

def get_currency(country_code):
    if country_code == 'IN':
        return {'symbol': '₹', 'code': 'INR', 'is_india': True}
    else:
        return {'symbol': '$', 'code': 'USD', 'is_india': False}

def get_pricing(country_code):
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

# ============================================================================
# USAGE TRACKING
# ============================================================================
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

# ============================================================================
# YOUTUBE FUNCTIONS
# ============================================================================
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
        st.error(f"❌ Error fetching comments: {e}")
        return []

def filter_comment(comment_text):
    """Filter out hate/negative comments and unrelated questions"""
    hate_keywords = ['hate', 'stupid', 'idiot', 'dumb', 'useless', 'waste', 'boring', 
                     'terrible', 'awful', 'garbage', 'trash', 'dislike', 'worst',
                     'pathetic', 'ridiculous', 'nonsense', 'pointless', 'annoying',
                     'irritating', 'fool', 'moron', 'jerk', 'scam', 'fake']
    text_lower = comment_text.lower()
    for word in hate_keywords:
        if word in text_lower:
            return {'filter': True, 'reason': 'hate_or_negative'}
    if len(comment_text) > 50 and '?' in text_lower:
        return {'filter': True, 'reason': 'unrelated_question'}
    return {'filter': False, 'reason': None}

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
        st.error(f"❌ Error posting reply: {e}")
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
if 'filtered_count' not in st.session_state:
    st.session_state.filtered_count = 0

# ============================================================================
# CSS STYLES (Mobile Responsive)
# ============================================================================
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
    
    .hero-section {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem 1rem;
        border-radius: 16px;
        margin-bottom: 1rem;
        text-align: center;
        box-shadow: 0 20px 60px rgba(102, 126, 234, 0.3);
    }
    .hero-title { font-size: 1.8rem; font-weight: 800; color: white; letter-spacing: -1px; }
    .hero-tagline { font-size: 0.9rem; color: rgba(255,255,255,0.9); font-weight: 300; }
    
    .card {
        background: linear-gradient(145deg, #1e1e3f 0%, #252550 100%);
        border-radius: 12px;
        padding: 1rem;
        border: 1px solid rgba(255,255,255,0.1);
        box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        margin-bottom: 0.8rem;
    }
    .card-title { font-size: 1.1rem; font-weight: 700; color: #fff; margin-bottom: 0.3rem; }
    .card-subtitle { font-size: 0.8rem; color: rgba(255,255,255,0.6); margin-bottom: 0.8rem; }
    
    .stat-box {
        background: linear-gradient(145deg, #1e1e3f 0%, #252550 100%);
        border-radius: 10px;
        padding: 0.8rem;
        text-align: center;
        border: 1px solid rgba(255,255,255,0.1);
    }
    .stat-number { font-size: 1.5rem; font-weight: 800; color: #667eea; line-height: 1; }
    .stat-label { font-size: 0.7rem; color: rgba(255,255,255,0.6); margin-top: 0.2rem; }
    
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
    
    .pricing-grid {
        display: grid;
        grid-template-columns: 1fr;
        gap: 0.8rem;
    }
    @media (min-width: 768px) {
        .pricing-grid { grid-template-columns: repeat(3, 1fr); }
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
    .pricing-card:hover { transform: translateY(-4px); }
    .pricing-card.popular { border: 2px solid #FFD700; }
    .pricing-card .plan-price { font-size: 1.8rem; font-weight: 800; color: white; margin: 0.3rem 0; }
    .pricing-card .plan-price span { font-size: 0.8rem; font-weight: 400; color: rgba(255,255,255,0.5); }
    .pricing-card .plan-features {
        list-style: none; padding: 0; text-align: left;
        color: rgba(255,255,255,0.7); font-size: 0.8rem; line-height: 1.8;
    }
    .pricing-card .plan-features li::before { content: "✅ "; color: #38ef7d; }
    .badge-popular {
        background: #FFD700; color: #1a1a2e;
        padding: 2px 10px; border-radius: 20px;
        font-size: 0.7rem; font-weight: 700;
        display: inline-block; margin-bottom: 0.3rem;
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
    .stButton button {
        border-radius: 10px !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        padding: 0.4rem 0.8rem !important;
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
    if st.button("🇮🇳 India", use_container_width=True):
        st.query_params['country'] = 'IN'
        st.rerun()
with col3:
    if st.button("🌍 Global", use_container_width=True):
        st.query_params['country'] = 'US'
        st.rerun()

query_params = st.query_params
if query_params.get('country'):
    st.caption(f"🔧 Manual override: Showing prices for {query_params.get('country')}")

# ============================================================================
# TABS
# ============================================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🚀 Home", "✨ Features", "💰 Pricing", "📊 Dashboard", "❓ Help"])

# ============================================================================
# TAB 1: HOME
# ============================================================================
with tab1:
    is_logged_in = os.path.exists('token.pickle')
    user_id = get_user_id()
    usage = get_usage(user_id)
    remaining_free = get_remaining_free(usage)
    
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
                        st.session_state.filtered_count = 0
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
    
    # ---- Processing ----
    if st.session_state.processing and st.session_state.video_id:
        youtube = get_authenticated_youtube()
        with st.spinner(f"Fetching {num_comments} comments and generating AI replies..."):
            comments = get_comments(youtube, st.session_state.video_id, num_comments * 2)
            if not comments:
                st.warning("No comments found on this video")
                st.session_state.processing = False
            else:
                filtered_comments = []
                filtered_count = 0
                for comment in comments:
                    result = filter_comment(comment['text'])
                    if not result['filter']:
                        filtered_comments.append(comment)
                    else:
                        filtered_count += 1
                
                if filtered_count > 0:
                    st.info(f"🛡️ Filtered out {filtered_count} hate/negative or unrelated comments")
                
                filtered_comments = filtered_comments[:num_comments]
                if not filtered_comments:
                    st.warning("All comments were filtered out. Try a different video.")
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
    
    # ---- Display Results ----
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
        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.5rem; margin-bottom: 0.8rem;">
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

# ============================================================================
# TAB 2: FEATURES
# ============================================================================
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
        ("🛡️", "Comment Filtering", "Automatically skip hate, negative, and unrelated comments."),
        ("📊", "Analytics Dashboard", "Track engagement and reply performance."),
        ("🎁", "Free Tier", "10 free replies every month to get started."),
        ("🌍", "Global Pricing", "₹ for India, $ for the rest of the world.")
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

# ============================================================================
# TAB 3: PRICING
# ============================================================================
with tab3:
    st.markdown("""
    <div style="text-align: center; margin-bottom: 1.5rem;">
        <div style="font-size: 1.8rem; font-weight: 700; color: white;">Simple, Transparent Pricing</div>
        <div style="color: rgba(255,255,255,0.6);">Pay only for what you use. No hidden fees.</div>
    </div>
    """, unsafe_allow_html=True)
    
    p = pricing
    symbol = currency['symbol']
    
    col1, col2, col3 = st.columns(3)
    
    # Starter
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
    
    # Popular
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
    
    # Pro
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
        💳 India: UPI, Credit Card | Global: Credit Cards, PayPal<br>
        🌍 Prices shown in {currency['symbol']} {currency['code']} based on your location ({country})
    </div>
    """, unsafe_allow_html=True)

# ============================================================================
# TAB 4: DASHBOARD
# ============================================================================
with tab4:
    if not os.path.exists('token.pickle'):
        st.markdown("""
        <div style="text-align: center; padding: 2rem;">
            <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">🔒</div>
            <div style="font-size: 1.1rem; font-weight: 600; color: white;">Connect Your YouTube Channel</div>
            <div style="color: rgba(255,255,255,0.6); font-size: 0.85rem;">Sign in to view your dashboard</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        user_id = get_user_id()
        usage = get_usage(user_id)
        remaining_free = get_remaining_free(usage)
        total_comments = len(st.session_state.comments)
        total_replies = sum(1 for v in st.session_state.posted.values() if v)
        
        st.markdown(f"""
        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.5rem; margin-bottom: 1rem;">
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

# ============================================================================
# TAB 5: HELP
# ============================================================================
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
                <strong>Starter (₹49 / $4.99):</strong>
                <div style="color: rgba(255,255,255,0.6); font-size: 0.8rem;">100 replies. One-time purchase.</div>
                <br>
                <strong>Popular (₹149 / $14.99):</strong>
                <div style="color: rgba(255,255,255,0.6); font-size: 0.8rem;">500 replies. Best value.</div>
                <br>
                <strong>Pro (₹399 / $39.99):</strong>
                <div style="color: rgba(255,255,255,0.6); font-size: 0.8rem;">1500 replies. For power users.</div>
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

# ============================================================================
# FOOTER
# ============================================================================
st.markdown(f"""
<div class="footer-text">
    <strong>ReplyWala</strong> — AI-powered YouTube comment replies · Built for creators<br>
    © 2026 ReplyWala. Made with ❤️ | Support: replywala03@gmail.com
</div>
""", unsafe_allow_html=True)

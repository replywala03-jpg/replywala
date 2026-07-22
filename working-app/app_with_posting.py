import os
import re
import time
import pickle
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

YOUTUBE_API_KEY = os.getenv("API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
client = OpenAI(api_key=OPENAI_API_KEY)

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
            # Try different port
            try:
                creds = flow.run_local_server(port=8080, open_browser=True)
            except:
                creds = flow.run_local_server(port=8501, open_browser=True)
        
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
        print(f"❌ Error fetching comments: {e}")
        return []

def generate_reply(comment_text):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a friendly YouTube creator replying to your audience. Keep replies short, personal, and engaging. Use emojis occasionally."},
                {"role": "user", "content": f"Comment: {comment_text}\n\nGenerate a short reply:"}
            ],
            max_tokens=60,
            temperature=0.8
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ Error generating reply: {e}")
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
        print(f"❌ Error posting reply: {e}")
        return None

def main():
    print("🎬 YouTube Comment AI Reply Bot with Auto-Posting")
    print("-" * 60)
    
    print("🔐 Authenticating with YouTube...")
    try:
        youtube = get_authenticated_youtube()
        print("✅ Authentication successful!")
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        print("   Make sure credentials.json exists in ../custom-reply-youtube/")
        return
    
    video_url = input("\n📹 Enter YouTube Video URL: ").strip()
    video_id = extract_video_id(video_url)
    if not video_id:
        print("❌ Invalid YouTube URL.")
        return
    print(f"✅ Video ID: {video_id}")
    
    try:
        num_comments = int(input("How many comments to reply to? (max 20): ") or "5")
        num_comments = min(num_comments, 20)
    except:
        num_comments = 5
    
    print(f"\n📥 Fetching {num_comments} comments...")
    comments = get_comments(youtube, video_id, num_comments)
    if not comments:
        print("❌ No comments found.")
        return
    print(f"✅ Found {len(comments)} comments")
    
    confirm = input("\n⚠️ Post replies to YouTube? (yes/no): ").strip().lower()
    if confirm != 'yes':
        print("❌ Cancelled.")
        return
    
    print("\n🚀 Posting replies...")
    success_count = 0
    for i, comment in enumerate(comments, 1):
        print(f"\n💬 {i}/{len(comments)}: {comment['author']}")
        print(f"   \"{comment['text'][:80]}...\"")
        reply = generate_reply(comment['text'])
        print(f"   📝 Reply: {reply}")
        result = post_reply(youtube, comment['id'], reply)
        if result:
            print("   ✅ Posted!")
            success_count += 1
        else:
            print("   ❌ Failed")
        time.sleep(1)
    
    print(f"\n🎉 Done! Posted {success_count}/{len(comments)} replies.")

if __name__ == "__main__":
    main()

import os
import re
import time
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Get API keys
YOUTUBE_API_KEY = os.getenv("API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize OpenAI client (NEW syntax)
client = OpenAI(api_key=OPENAI_API_KEY)

# Initialize YouTube API
youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

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

def get_comments(video_id, max_results=20):
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
            comment = item['snippet']['topLevelComment']['snippet']['textDisplay']
            author = item['snippet']['topLevelComment']['snippet']['authorDisplayName']
            comments.append({
                'author': author,
                'text': comment
            })
        return comments
    except HttpError as e:
        print(f"❌ Error fetching comments: {e}")
        return []

def generate_reply(comment_text):
    """Generate AI reply using new OpenAI 1.0+ syntax"""
    try:
        response = client.chat.completions.create(  # NEW syntax
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a friendly YouTube creator replying to your audience. Keep replies short, personal, and engaging. Use emojis occasionally. Reply directly to what the comment says."},
                {"role": "user", "content": f"Comment: {comment_text}\n\nGenerate a short, friendly reply to this comment:"}
            ],
            max_tokens=60,
            temperature=0.8
        )
        return response.choices[0].message.content.strip()  # NEW syntax
    except Exception as e:
        print(f"❌ Error generating reply: {e}")
        return "Thanks for your comment! 🙌"

def main():
    print("🎬 YouTube Comment AI Reply Bot")
    print("-" * 50)
    
    video_url = input("Enter YouTube Video URL: ").strip()
    video_id = extract_video_id(video_url)
    
    if not video_id:
        print("❌ Invalid YouTube URL. Please try again.")
        return
    
    print(f"✅ Video ID: {video_id}")
    print("-" * 50)
    
    try:
        num_comments = int(input("How many comments to reply to? (max 50): ") or "10")
        num_comments = min(num_comments, 50)
    except:
        num_comments = 10
    
    print(f"\n📥 Fetching {num_comments} comments...")
    comments = get_comments(video_id, num_comments)
    
    if not comments:
        print("❌ No comments found or video has comments disabled.")
        return
    
    print(f"✅ Found {len(comments)} comments")
    print("-" * 50)
    
    for i, comment in enumerate(comments, 1):
        print(f"\n💬 Comment {i}: {comment['author']}")
        print(f"   \"{comment['text'][:100]}...\"")
        print("🤖 Generating reply...")
        
        reply = generate_reply(comment['text'])
        print(f"   📝 Reply: {reply}")
        print("-" * 30)
        time.sleep(0.5)
    
    print(f"\n🎉 Done! Generated {len(comments)} replies.")
    print("📝 Note: To post replies automatically, you need to set up OAuth 2.0.")
    print("   This script currently generates replies for review only.")

if __name__ == "__main__":
    main()

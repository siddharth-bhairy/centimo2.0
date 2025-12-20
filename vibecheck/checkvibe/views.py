import os
import re
import base64
from io import BytesIO
from collections import Counter

# Django Imports
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import ContactFeedback

# Analysis Library Imports
import pandas as pd
import googleapiclient.discovery
from langdetect import detect, LangDetectException
from wordcloud import WordCloud
from textblob import TextBlob

# Environment variables - Load dotenv for development
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import for pycountry
try:
    import pycountry
except ImportError:
    pass

# --- SIMPLIFIED ANALYSIS CLASS ---

class EmotionYouTubeAnalyzer:
    def __init__(self, api_key):
        if not api_key:
            raise ValueError("A YouTube API key must be provided.")
        self.api_key = api_key
        self.youtube = googleapiclient.discovery.build(
            'youtube', 'v3', developerKey=self.api_key
        )

    def generate_wordcloud_image(self, text):
        """Generates a word cloud image and returns it as a base64 string."""
        if not text or not text.strip():
            return None
        
        wordcloud = WordCloud(
            width=800, 
            height=400, 
            background_color='white',
            max_font_size=70,
            relative_scaling=0.5,
            colormap='viridis'
        ).generate(text)

        buffer = BytesIO()
        wordcloud.to_image().save(buffer, format='PNG')
        image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        return f"data:image/png;base64,{image_base64}"
    
    def extract_video_id(self, url):
        patterns = [
            r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
            r'(?:embed\/)([0-9A-Za-z_-]{11})',
            r'(?:v\/)([0-9A-Za-z_-]{11})'
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def get_video_info(self, video_id):
        request = self.youtube.videos().list(part='snippet,statistics', id=video_id)
        response = request.execute()
        if not response['items']:
            raise ValueError("Video not found.")
        video = response['items'][0]
        return {
            'title': video['snippet']['title'],
            'channel': video['snippet']['channelTitle'],
            'views': int(video['statistics'].get('viewCount', 0)),
            'likes': int(video['statistics'].get('likeCount', 0)),
            'comments': int(video['statistics'].get('commentCount', 0))
        }

    def get_comments(self, video_id, max_comments=800):
        comments = []
        next_page_token = None
        while len(comments) < max_comments:
            request = self.youtube.commentThreads().list(
                part='snippet', videoId=video_id,
                maxResults=min(100, max_comments - len(comments)),
                order='relevance', pageToken=next_page_token
            )
            response = request.execute()
            for item in response['items']:
                comment = item['snippet']['topLevelComment']['snippet']
                comments.append({'text': comment['textDisplay']})
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break
        return comments

    def analyze_sentiment(self, text):
        """Analyze sentiment using TextBlob"""
        polarity = TextBlob(text).sentiment.polarity
        if polarity > 0.1:
            sentiment = 'positive'
        elif polarity < -0.1:
            sentiment = 'negative'
        else:
            sentiment = 'neutral'
        
        return {
            'sentiment': sentiment,
            'polarity': polarity
        }

    def clean_text_for_wordcloud(self, text):
        text = re.sub(r'http\S+|www\S+|https\S+|<.*?>|@\w+|#\w+', '', text)
        text = re.sub(r'[^\w\s]', ' ', text).strip()
        stopwords_set = set(['the', 'is', 'at', 'on', 'and', 'a', 'to', 'in', 'of', 'for', 'with', 'this', 'that', 'it', 'from', 'we', 'have', 'had', 'do', 'if', 'will', 'up', 'out', 'so', 'some', 'would', 'like', 'has', 'more', 'what', 'know', 'just', 'get', 'your', 'can', 'see', 'time', 'one'])
        
        meaningful_words = [word.lower() for word, tag in TextBlob(text).tags
                            if (tag.startswith('NN') or tag.startswith('JJ') or tag.startswith('VB'))
                            and len(word) > 2 and word.lower() not in stopwords_set]
        return ' '.join(meaningful_words)

    def get_lang_full_name(self, code):
        if code == 'unknown':
            return 'Unknown'
        try:
            return pycountry.languages.get(alpha_2=code).name
        except (AttributeError, NameError):
            return code

    def get_sentiment_statistics(self, df):
        """Get sentiment statistics for pie chart"""
        sentiment_counts = df['sentiment'].value_counts().to_dict()
        total_comments = len(df)
        
        sentiment_stats = []
        for sentiment, count in sentiment_counts.items():
            percentage = (count / total_comments) * 100
            sentiment_stats.append({
                'name': sentiment,
                'count': count,
                'percentage': round(percentage, 1)
            })
        
        return sorted(sentiment_stats, key=lambda x: x['count'], reverse=True)

    def get_language_statistics(self, df):
        """Get language distribution statistics"""
        languages = []
        for text in df['text'].astype(str):
            try:
                if text.strip():
                    lang_code = detect(text)
                    lang_name = self.get_lang_full_name(lang_code)
                    languages.append(lang_name)
                else:
                    languages.append('Unknown')
            except LangDetectException:
                languages.append('Unknown')
        
        lang_counts = Counter(languages)
        total_comments = len(df)
        
        language_stats = []
        for language, count in lang_counts.items():
            percentage = (count / total_comments) * 100
            language_stats.append({
                'name': language,
                'count': count,
                'percentage': round(percentage, 1)
            })
        
        return sorted(language_stats, key=lambda x: x['count'], reverse=True)

    def analyze_video(self, video_url, max_comments=800):
        video_id = self.extract_video_id(video_url)
        if not video_id:
            raise ValueError("Invalid YouTube URL provided.")
        
        video_info = self.get_video_info(video_id)
        comments = self.get_comments(video_id, max_comments)
        if not comments:
            raise ValueError("No comments were found for this video or they are disabled.")
        
        # Analyze sentiment for each comment
        analyzed_comments = [{'text': c['text'], **self.analyze_sentiment(c['text'])} for c in comments]
        df = pd.DataFrame(analyzed_comments)
        
        # Get statistics
        sentiment_stats = self.get_sentiment_statistics(df)
        language_stats = self.get_language_statistics(df)
        
        # Generate word cloud
        all_text = ' '.join(df['text'].astype(str).tolist())
        cleaned_text = self.clean_text_for_wordcloud(all_text)
        wordcloud_image = self.generate_wordcloud_image(cleaned_text)
        
        return {
            'video_id': video_id,
            'video_info': video_info,
            'sentiment_stats': sentiment_stats,
            'language_stats': language_stats,
            'total_analyzed': len(df),
            'wordcloud_image': wordcloud_image
        }

# --- DJANGO VIEWS ---

def index(request):
    return render(request, "home.html") 

def about(request):
    return render(request, "about.html")

def is_valid_youtube_url(url):
    pattern = re.compile(r'^(https?\:\/\/)?(www\.youtube\.com|youtu\.?be)\/.+')
    return re.match(pattern, url)

def analyze(request):
    if request.method == "POST":
        url = request.POST.get("youtube_url", "").strip()
        max_comments_str = request.POST.get("max_comments", "800").strip()
        max_comments = int(max_comments_str) if max_comments_str.isdigit() else 800

        if not is_valid_youtube_url(url):
            messages.error(request, "Please enter a valid YouTube video URL.")
            return redirect("analyze")
        
        api_key = "enter api key here"
        if not api_key:
            messages.error(request, "Server configuration error: YouTube API key not found.")
            return redirect("analyze")

        try:
            analyzer = EmotionYouTubeAnalyzer(api_key=api_key)
            analysis_results = analyzer.analyze_video(url, max_comments)
                                                                            
            return render(request, "dashboard.html", context=analysis_results)

        except Exception as e:
            messages.error(request, f"An error occurred during analysis: {e}")
            return redirect("analyze")

    return render(request, "analyze.html")

def contact(request):
    msg = ""
    if request.method == "POST":
        email = request.POST.get("email")  
        feedback = request.POST.get("feedback")
        if email and feedback:
            ContactFeedback.objects.create(email=email, feedback=feedback)
            msg = "Thank you for your feedback!"
        else:
            msg = "Please fill out all fields."

    return render(request, "contact.html", {"msg": msg})  

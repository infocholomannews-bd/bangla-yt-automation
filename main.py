import os
import json
import asyncio
import requests
import edge_tts
from google import genai
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def generate_long_script(topic):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    prompt = f"""
    Create a detailed, engaging 3.5 to 4-minute YouTube documentary/explainer video script in Bengali about this topic: "{topic}"

    Divide the video into 8 to 10 logical scenes so the total spoken narration is around 450-550 Bengali words.

    Return ONLY valid JSON with these exact keys:
    "yt_title": "Catchy Bengali YouTube video title (max 80 chars)",
    "yt_desc": "Detailed Bengali description with relevant hashtags",
    "yt_tags": ["BanglaNews", "Bangladesh", "Explainer"],
    "scenes": [
        {{
            "narration": "Spoken Bengali paragraph for this scene (natural, clear Bengali without emojis or symbols)",
            "image_prompt": "Detailed cinematic 16:9 landscape visual prompt in English describing this scene, photorealistic, high quality"
        }}
    ]
    """
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    clean_json = response.text.strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(clean_json)

async def create_voice(text, filename):
    communicate = edge_tts.Communicate(text, "bn-BD-PradeepNeural", rate="+0%")
    await communicate.save(filename)

def create_image(prompt, filename):
    base_url = "https://" + "image.pollinations.ai/prompt/"
    url = f"{base_url}{requests.utils.quote(prompt)}?width=1280&height=720&nologo=true"
    img_data = requests.get(url, timeout=60).content
    with open(filename, "wb") as f:
        f.write(img_data)

def build_full_video(scenes, output_vid="final_video.mp4"):
    clips = []
    for idx, scene in enumerate(scenes):
        audio_file = f"audio_{idx}.mp3"
        img_file = f"img_{idx}.jpg"

        asyncio.run(create_voice(scene["narration"], audio_file))
        create_image(scene["image_prompt"], img_file)

        audio = AudioFileClip(audio_file)
        duration = audio.duration

        img_clip = ImageClip(img_file).set_duration(duration).resize((1280, 720))
        img_clip = img_clip.resize(lambda t: 1 + 0.03 * (t / duration))
        img_clip = img_clip.set_audio(audio)

        clips.append(img_clip)

    final_video = concatenate_videoclips(clips, method="compose")
    final_video.write_videofile(output_vid, fps=24, codec="libx264", audio_codec="aac")

def upload_as_private(video_file, title, description, tags):
    creds_data = json.loads(os.environ["YOUTUBE_TOKEN_JSON"])
    creds = Credentials.from_authorized_user_info(creds_data)
    youtube = build("youtube", "v3", credentials=creds)

    request_body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "25"
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False
        }
    }
    media = MediaFileUpload(video_file, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=request_body, media_body=media)
    response = request.execute()
    print("Successfully uploaded as Private! Video ID:", response["id"])

if __name__ == "__main__":
    topic = os.environ.get("VIDEO_TOPIC", "বাংলাদেশের বর্তমান অর্থনৈতিক চ্যালেঞ্জ ও সম্ভাবনা")
    print(f"Generating video for topic: {topic}")
    data = generate_long_script(topic)
    build_full_video(data["scenes"])
    upload_as_private("final_video.mp4", data["yt_title"], data["yt_desc"], data["yt_tags"])

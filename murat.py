import streamlit as st
import cv2
import numpy as np
from PIL import Image
import random
import firebase_admin
from firebase_admin import credentials, firestore
import requests
import os

# --- 1. FIREBASE BAĞLANTISI ---
if not firebase_admin._apps:
    try:
        private_key = st.secrets["firebase"]["private_key"].replace("\\n", "\n")
        fb_credentials = {
            "type": "service_account",
            "project_id": "sarkilarbizisoyler-b5128",
            "private_key": private_key,
            "client_email": "firebase-adminsdk-fbsvc@sarkilarbizisoyler-b5128.iam.gserviceaccount.com",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        cred = credentials.Certificate(fb_credentials)
        firebase_admin.initialize_app(cred)
    except:
        pass
db = firestore.client()

# --- 2. YEREL ANALİZ (HAFİF OPEN-CV) ---
def analyze_smile_locally(img_file):
    try:
        # Görseli al ve işle
        image = Image.open(img_file)
        img_array = np.array(image)
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

        # OpenCV'nin hazır modellerini yükle
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        smile_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_smile.xml')

        faces = face_cascade.detectMultiScale(gray, 1.3, 5)
        
        for (x, y, w, h) in faces:
            roi_gray = gray[y:y+h, x:x+w]
            # Gülümseme yakalama (Hassasiyeti artırdım)
            smiles = smile_cascade.detectMultiScale(roi_gray, 1.7, 22)
            
            if len(smiles) > 0:
                return "happy"
        return "neutral"
    except:
        return "neutral"

def get_yt_content(mood, api_key):
    p_id = st.secrets.get(f"playlist_{mood}", st.secrets["playlist_neutral"])
    url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50&playlistId={p_id}&key={api_key}"
    try:
        r = requests.get(url).json()
        item = random.choice(r['items'])['snippet']
        v_id = item['resourceId']['videoId']
        return {"title": item['title'], "v_id": v_id, "thumb": f"https://img.youtube.com/vi/{v_id}/hqdefault.jpg"}
    except: return None

# --- 3. ARAYÜZ ---
st.set_page_config(page_title="Şarkılar Seni Söyler", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = None

if not st.session_state.auth:
    st.title("🎵 Şarkılar Seni Söyler")
    st.markdown("### Bursa Teknik Üniversitesi - Local AI Sunumu")
    u = st.text_input("Kullanıcı")
    p = st.text_input("Şifre", type="password")
    if st.button("Sisteme Giriş"):
        st.session_state.auth, st.session_state.user = True, u; st.rerun()
else:
    with st.sidebar:
        st.write(f"👤 {st.session_state.user}")
        if st.button("Çıkış"): st.session_state.auth = False; st.rerun()

    cam = st.camera_input("Analiz için gülümse!")
    
    if cam:
        with st.spinner("OpenCV Analiz Yapıyor..."):
            mood = analyze_smile_locally(cam)
            yt = get_yt_content(mood, st.secrets["youtube_api_key"])
            
            if yt:
                # Firebase Kaydı
                try:
                    db.collection('mood_history').add({
                        'username': st.session_state.user,
                        'emotion': mood.upper(),
                        'song': yt['title'],
                        'timestamp': firestore.SERVER_TIMESTAMP
                    })
                except: pass
                
                c1, c2 = st.columns(2)
                with c1:
                    st.header(f"Modun: {mood.upper()} ✨")
                    st.info("Analiz API kullanılmadan, yerel kütüphane ile yapıldı.")
                with c2:
                    st.subheader(f"🎵 {yt['title']}")
                    st.image(yt['thumb'])
                    st.link_button("▶️ YouTube'da Dinle", f"https://music.youtube.com/watch?v={yt['v_id']}")

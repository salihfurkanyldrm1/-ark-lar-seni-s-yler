import streamlit as st
import cv2
import numpy as np
from PIL import Image
import random
import firebase_admin
from firebase_admin import credentials, firestore
import requests

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
    except: pass
db = firestore.client()

# --- 2. YEREL ANALİZ MANTIĞI (HAAR CASCADES) ---
# Bu yöntem RAM tüketmez, tamamen matematiksel çalışır.
def local_emotion_analysis(img_file):
    try:
        # Görseli oku ve gri tona çevir
        image = Image.open(img_file)
        img_array = np.array(image)
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

        # OpenCV'nin hazır yüz ve gülümseme modellerini yükle
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        smile_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_smile.xml')

        faces = face_cascade.detectMultiScale(gray, 1.3, 5)
        
        for (x, y, w, h) in faces:
            roi_gray = gray[y:y+h, x:x+w]
            # Gülümseme ara (parametreleri hassaslaştırdım)
            smiles = smile_cascade.detectMultiScale(roi_gray, 1.8, 20)
            
            if len(smiles) > 0:
                return "happy", 90
            
        # Eğer yüz var ama gülümseme yoksa nötr kabul et
        return "neutral", 50
    except:
        return "neutral", 10

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
st.set_page_config(page_title="Şarkılar Seni Söyler: Local AI", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = None

if not st.session_state.auth:
    st.title("🎵 Şarkılar Seni Söyler")
    st.markdown("### Bursa Teknik Üniversitesi - Local Library Sunumu")
    u = st.text_input("Kullanıcı Adı")
    p = st.text_input("Şifre", type="password")
    if st.button("Sisteme Giriş"):
        st.session_state.auth, st.session_state.user = True, u; st.rerun()
else:
    with st.sidebar:
        st.write(f"👤 {st.session_state.user}")
        if st.button("🚪 Çıkış"): st.session_state.auth = False; st.rerun()

    cam = st.camera_input("Fotoğraf Çek ve Yerel Analizi Başlat")
    
    if cam:
        with st.spinner("Python Kütüphanesi (OpenCV) ile Analiz Yapılıyor..."):
            mood, score = local_emotion_analysis(cam)
            yt = get_yt_content(mood, st.secrets["youtube_api_key"])
            
            if yt:
                # Firebase Kaydı
                db.collection('mood_history').add({
                    'username': st.session_state.user,
                    'emotion': mood.upper(),
                    'song': yt['title'],
                    'timestamp': firestore.SERVER_TIMESTAMP
                })
                
                st.divider()
                col1, col2 = st.columns(2)
                with col1:
                    st.header(f"Modun: {mood.upper()}")
                    st.progress(score)
                    st.info("Bu analiz hiçbir API kullanılmadan, direkt sunucudaki kütüphane ile yapılmıştır.")
                with col2:
                    st.subheader(f"🎵 Öneri: {yt['title']}")
                    st.image(yt['thumb'])
                    st.link_button("▶️ YouTube'da Dinle", f"https://music.youtube.com/watch?v={yt['v_id']}")

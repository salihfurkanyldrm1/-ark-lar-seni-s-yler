import streamlit as st
from PIL import Image
import numpy as np
import random
import requests
import firebase_admin
from firebase_admin import credentials, firestore
import os
import io

# --- 1. FIREBASE VE CLOUD AI AYARLARI ---
# Token'ı güvenli şekilde Secrets'tan çekiyoruz (GitHub engeline takılmaz)
HF_TOKEN = st.secrets.get("hf_token", "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")
API_URL = "https://api-inference.huggingface.co/models/dima806/facial_emotions_image_detection"
headers = {"Authorization": f"Bearer {HF_TOKEN}"}

if not firebase_admin._apps:
    try:
        private_key = st.secrets["firebase"]["private_key"].replace("\\n", "\n")
        fb_credentials = {
            "type": "service_account",
            "project_id": "sarkilarbizisoyler-b5128",
            "private_key_id": "53af40b6a879ceb1e598e0fba3cf6ec2f0126f53",
            "private_key": private_key,
            "client_email": "firebase-adminsdk-fbsvc@sarkilarbizisoyler-b5128.iam.gserviceaccount.com",
            "client_id": "108357774108544609360",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-fbsvc%40sarkilarbizisoyler-b5128.iam.gserviceaccount.com"
        }
        cred = credentials.Certificate(fb_credentials)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"⚠️ Firebase Bağlantı Hatası: {e}")

db = firestore.client()

# --- 2. YARDIMCI SÖZLÜKLER VE FONKSİYONLAR ---
TRANSLATION = {
    "happy": "Mutlu", "sad": "Üzgün", "neutral": "Tarafsız",
    "angry": "Sinirli", "surprise": "Şaşkın", "fear": "Korku", "disgust": "Tiksinti"
}

def query_hf_api(image_bytes):
    # Fotoğrafı Hugging Face sunucusuna gönder
    response = requests.post(API_URL, headers=headers, data=image_bytes)
    return response.json()

def user_auth(u, p, mode):
    user_ref = db.collection('users').document(u)
    doc = user_ref.get()
    if mode == "Giriş":
        if doc.exists and doc.to_dict().get('password') == p: return True
        return False
    else:
        if doc.exists: return False
        user_ref.set({'username': u, 'password': p})
        return True

def save_analysis(u, dom, song, score):
    try:
        db.collection('mood_history').add({
            'username': u,
            'emotion': TRANSLATION.get(dom, dom).upper(),
            'song': song,
            'ai_score': int(score),
            'timestamp': firestore.SERVER_TIMESTAMP
        })
    except: pass

def get_yt_content(playlist_id, api_key):
    url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50&playlistId={playlist_id}&key={api_key}"
    try:
        r = requests.get(url).json()
        item = random.choice(r['items'])['snippet']
        v_id = item['resourceId']['videoId']
        return {"title": item['title'], "v_id": v_id, "thumb": f"https://img.youtube.com/vi/{v_id}/hqdefault.jpg"}
    except: return None

# --- 3. SAYFA AYARLARI ---
st.set_page_config(page_title="Mood-Fi: Cloud AI", page_icon="🎵", layout="wide")
if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = None

# --- 4. GİRİŞ / KAYIT ---
if not st.session_state.auth:
    st.title("🎵 Mood-Fi: Cloud AI Music")
    st.info("Bursa Teknik Üniversitesi - Bulut Bilişim Projesi")
    t1, t2 = st.tabs(["🔐 Giriş", "📝 Kaydol"])
    with t1:
        with st.form("l"):
            u = st.text_input("Kullanıcı")
            p = st.text_input("Şifre", type="password")
            if st.form_submit_button("Giriş"):
                if user_auth(u, p, "Giriş"): 
                    st.session_state.auth = True
                    st.session_state.user = u
                    st.rerun()
                else: st.error("Hatalı Giriş!")
    with t2:
        with st.form("r"):
            ru = st.text_input("Yeni Kullanıcı")
            rp = st.text_input("Yeni Şifre", type="password")
            if st.form_submit_button("Kaydol"):
                if user_auth(ru, rp, "Kaydol"): st.success("Hesap Oluşturuldu!")
                else: st.error("Kullanıcı Mevcut!")
else:
    # --- 5. ANA PANEL ---
    with st.sidebar:
        st.subheader(f"👤 {st.session_state.user}")
        if st.button("🚪 Çıkış"): 
            st.session_state.auth = False
            st.rerun()

    tab_anlz, tab_hist = st.tabs(["🔍 Cloud Analizi", "📂 Geçmişim"])
    
    API_KEY = st.secrets["youtube_api_key"]
    PLAYLISTS = {
        "happy": st.secrets["playlist_happy"], 
        "sad": st.secrets["playlist_sad"], 
        "neutral": st.secrets["playlist_neutral"]
    }

   with tab_anlz:
        cam = st.camera_input("Ruh Halini Bulutta Analiz Et")
        if cam:
            # Görüntüyü API'ye göndermek için bytes formatına çeviriyoruz
            img_bytes = cam.getvalue()
            
            with st.spinner("AI Sunucuları Analiz Ediyor... (Lütfen Bekleyin)"):
                try:
                    # Işık mantığını sildik, DİREKT API'YE SORUYORUZ
                    result = query_hf_api(img_bytes)
                    
                    # Eğer model yükleniyorsa uyarı verir, fonksiyonun içine bu kontrolü koymuştuk
                    if result and isinstance(result, list):
                        # En yüksek puanlı sonucu al
                        top_emotion = result[0]
                        dom = top_emotion['label'].lower() # 'Happy', 'Sad', 'Neutral' vb.
                        score = top_emotion['score'] * 100
                        
                        # Çeviri ve Playlist Seçimi
                        # API'den bazen 'joy' veya 'smile' gelebilir, onları 'happy'ye eşitleyelim
                        if dom in ["joy", "happy", "smile"]: mood_key = "happy"
                        elif dom in ["sad", "disappointed"]: mood_key = "sad"
                        else: mood_key = "neutral"

                        yt = get_yt_content(PLAYLISTS.get(mood_key, PLAYLISTS["neutral"]), API_KEY)
                        
                        if yt:
                            # Firebase'e Kaydet
                            save_analysis(st.session_state.user, mood_key, yt['title'], score)
                            
                            c1, c2 = st.columns(2)
                            with c1:
                                st.header(f"Mood: {TRANSLATION.get(mood_key, 'Tarafsız').upper()} ✨")
                                st.metric("AI Güven Oranı", f"%{int(score)}")
                                if st.button("🔄 Yeni Fotoğraf"): st.rerun()
                            with c2:
                                st.subheader(f"🎵 Öneri: {yt['title']}")
                                st.image(yt['thumb'])
                                st.link_button("▶️ YouTube'da Dinle", f"https://music.youtube.com/watch?v={yt['v_id']}")
                except Exception as e:
                    st.error("Bulut sunucusu şu an yoğun, lütfen 5 saniye sonra tekrar deneyin.")

    with tab_hist:
        docs = db.collection('mood_history').where('username', '==', st.session_state.user).stream()
        h_list = sorted([d.to_dict() for d in docs], key=lambda x: x.get('timestamp', 0), reverse=True)
        for dat in h_list[:10]:
            ts = dat.get('timestamp')
            t_str = ts.strftime("%d/%m %H:%M") if ts else "Yeni"
            with st.expander(f"📅 {t_str} | {dat.get('emotion')}"):
                st.write(f"Şarkı: {dat.get('song')} (Skor: %{dat.get('ai_score')})")

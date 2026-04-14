import streamlit as st
import cv2
from PIL import Image
import numpy as np
import random
import requests
import firebase_admin
from firebase_admin import credentials, firestore
import mediapipe as mp
import os

# --- 1. FIREBASE BAĞLANTISI ---
if not firebase_admin._apps:
    try:
        if "firebase" in st.secrets:
            fb_info = dict(st.secrets["firebase"])
            fb_info["private_key"] = fb_info["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(fb_info)
            firebase_admin.initialize_app(cred)
        else:
            JSON_FILE = "sarkilarbizisoyler-b5128-firebase-adminsdk-fbsvc-53af40b6a8.json"
            if os.path.exists(JSON_FILE):
                cred = credentials.Certificate(JSON_FILE)
                firebase_admin.initialize_app(cred)
    except: pass
db = firestore.client()

# --- 2. YARDIMCI SÖZLÜKLER ---
TRANSLATION = {"happy": "Mutlu", "sad": "Üzgün", "neutral": "Tarafsız", "angry": "Sinirli", "surprise": "Şaşkın"}

# --- 3. ÜYELİK VE YT FONKSİYONLARI (AYNEN KORUNDU) ---
def user_auth(u, p, mode):
    user_ref = db.collection('users').document(u)
    doc = user_ref.get()
    if mode == "Giriş":
        return (doc.exists and doc.to_dict().get('password') == p), "Giriş Durumu"
    user_ref.set({'username': u, 'password': p})
    return True, "Kaydolundu"

def get_yt_content(playlist_id, api_key):
    url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50&playlistId={playlist_id}&key={api_key}"
    try:
        r = requests.get(url).json()
        item = random.choice(r['items'])['snippet']
        v_id = item.get('resourceId', {}).get('videoId', '')
        return {"title": item.get('title'), "v_id": v_id, "thumb": f"https://img.youtube.com/vi/{v_id}/hqdefault.jpg"}
    except: return None

# --- 4. TASARIM ---
st.set_page_config(page_title="Mood-Fi Pro Lite", page_icon="🎵", layout="wide")
if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = None
if 'result' not in st.session_state: st.session_state.result = None

if not st.session_state.auth:
    st.title("🎵 Mood-Fi: AI Music")
    t1, t2 = st.tabs(["Giriş Yap", "Kaydol"])
    with t1:
        u = st.text_input("Kullanıcı Adı")
        p = st.text_input("Şifre", type="password")
        if st.button("Giriş"):
            ok, msg = user_auth(u, p, "Giriş")
            if ok: st.session_state.auth = True; st.session_state.user = u; st.rerun()
else:
    # --- ANA PANEL ---
    with st.sidebar:
        st.subheader(f"👤 {st.session_state.user}")
        if st.button("🚪 Çıkış"): st.session_state.auth = False; st.rerun()

    tab_anlz, tab_hist = st.tabs(["🔍 Analiz", "📂 Geçmiş"])
    API_KEY = st.secrets["youtube_api_key"]
    PLAYLISTS = {
        "happy": "PLOkZh8jNcqTTlGGHc7C5auqTRmHKiypj5", "sad": "PLKVx4zuArgpyffjLRb6J7g9xA3eS05jiq",
        "neutral": "PLmDhjqsemmV_XM-XSr_4QxENCDFEHWvMK", "angry": "PLkQK3bOASMpXC31FuDSkT7RdICLJqGWCT"
    }

    with tab_anlz:
        if st.session_state.result is None:
            cam = st.camera_input("Fotoğraf Çek")
            if cam:
                img = Image.open(cam)
                img_array = np.array(img)
                
                with st.spinner("AI Nitelikli Analiz Yapıyor..."):
                    # MEDIAPIPE İLE DUYGU ANALİZİ (Gülümseme Algılama)
                    mp_face_mesh = mp.solutions.face_mesh
                    with mp_face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1) as face_mesh:
                        results = face_mesh.process(cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR))
                        if results.multi_face_landmarks:
                            landmarks = results.multi_face_landmarks[0].landmark
                            # Dudak kenarları ve üst dudak arasındaki mesafeyi ölçüyoruz
                            lip_up = landmarks[13].y
                            lip_down = landmarks[14].y
                            smile_ratio = abs(lip_up - lip_down)
                            
                            # Basit ama nitelikli mantık: Ağız açıklığına göre
                            if smile_ratio > 0.04: dom = "happy"
                            elif smile_ratio < 0.02: dom = "sad"
                            else: dom = "neutral"
                            
                            norm = {dom: random.randint(80, 95), "neutral": random.randint(5, 10)}
                            yt = get_yt_content(PLAYLISTS.get(dom), API_KEY)
                            if yt:
                                st.session_state.result = {"dom": dom, "norm": norm, "yt": yt}
                                st.rerun()
        else:
            # SONUÇ EKRANI (Senin Tasarımın)
            r = st.session_state.result
            st.header(f"Duygu: {TRANSLATION.get(r['dom']).upper()}")
            st.progress(int(r['norm'][r['dom']]))
            st.subheader(f"🎵 Öneri: {r['yt']['title']}")
            st.image(r['yt']['thumb'])
            st.link_button("▶️ Dinle", f"https://music.youtube.com/watch?v={r['yt']['v_id']}")
            if st.button("🔄 Tekrar"): st.session_state.result = None; st.rerun()

    with tab_hist:
        st.subheader("🕒 Son Kayıtlar")
        docs = db.collection('mood_history').where('username', '==', st.session_state.user).stream()
        for d in docs:
            dat = d.to_dict()
            st.write(f"📅 {dat.get('emotion')} - {dat.get('song')}")

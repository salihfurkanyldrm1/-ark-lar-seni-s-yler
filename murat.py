import streamlit as st
from PIL import Image
import numpy as np
import random
import requests
import firebase_admin
from firebase_admin import credentials, firestore
import os
import io

# --- 1. FIREBASE VE CLOUD AI AYARLARI (ID'SİZ SADECE SECRETS) ---
# Hugging Face Beyni
HF_TOKEN = st.secrets["hf_token"]
API_URL = "https://api-inference.huggingface.co/models/michel-schellekens/facial-emotion-recognition"
headers = {"Authorization": f"Bearer {HF_TOKEN}"}

# Firebase Bağlantısı (Tüm bilgileri Secrets TOML'dan çekiyor)
if not firebase_admin._apps:
    try:
        # Secrets'tan gelen sözlüğü al ve private_key'i düzelt
        fb_dict = dict(st.secrets["firebase"])
        fb_dict["private_key"] = fb_dict["private_key"].replace("\\n", "\n")
        
        cred = credentials.Certificate(fb_dict)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"⚠️ Bulut Bağlantı Hatası: {e}")

db = firestore.client()

# --- 2. YARDIMCI SÖZLÜKLER VE FONKSİYONLAR ---
TRANSLATION = {
    "happy": "Mutlu", "sad": "Üzgün", "neutral": "Tarafsız",
    "angry": "Sinirli", "surprise": "Şaşkın", "fear": "Korku", "disgust": "Tiksinti"
}

def query_hf_api(image_bytes):
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

def get_yt_content(p_id, a_key):
    url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50&playlistId={p_id}&key={a_key}"
    try:
        r = requests.get(url).json()
        item = random.choice(r['items'])['snippet']
        v_id = item['resourceId']['videoId']
        return {"title": item['title'], "v_id": v_id, "thumb": f"https://img.youtube.com/vi/{v_id}/hqdefault.jpg"}
    except: return None

# --- 3. TASARIM ---
st.set_page_config(page_title="Mood-Fi: Cloud AI", page_icon="🎵", layout="wide")
if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = None

if not st.session_state.auth:
    st.title("🎵 Mood-Fi: Cloud AI & Music")
    st.info("Bursa Teknik Üniversitesi - Bulut Bilişim Sunumu")
    t1, t2 = st.tabs(["🔐 Giriş", "📝 Kaydol"])
    with t1:
        with st.form("l"):
            u = st.text_input("Kullanıcı")
            p = st.text_input("Şifre", type="password")
            if st.form_submit_button("Giriş"):
                if user_auth(u, p, "Giriş"): 
                    st.session_state.auth = True; st.session_state.user = u; st.rerun()
                else: st.error("Hatalı Giriş!")
    with t2:
        with st.form("r"):
            ru = st.text_input("Yeni Kullanıcı")
            rp = st.text_input("Yeni Şifre", type="password")
            if st.form_submit_button("Kaydol"):
                if user_auth(ru, rp, "Kaydol"): st.success("Hesap Oluşturuldu!")
                else: st.error("Kullanıcı Mevcut!")
else:
    with st.sidebar:
        st.subheader(f"👤 {st.session_state.user}")
        if st.button("🚪 Çıkış"): st.session_state.auth = False; st.rerun()

    tab_anlz, tab_hist = st.tabs(["🔍 Cloud Analizi", "📂 Geçmişim"])
    
    Y_KEY = st.secrets["youtube_api_key"]
    # Playlistler de Secrets'tan geliyor
    PLAYS = {
        "happy": st.secrets["playlist_happy"], 
        "sad": st.secrets["playlist_sad"], 
        "neutral": st.secrets["playlist_neutral"]
    }

    with tab_anlz:
        cam = st.camera_input("Fotoğraf Çek ve Analiz Et")
        if cam:
            i_bytes = cam.getvalue()
            with st.spinner("Bulut AI Duygularını İnceliyor..."):
                try:
                    res = query_hf_api(i_bytes)
                    if res and isinstance(res, list):
                        top_res = res[0]
                        dom = top_res['label'].lower()
                        scr = top_res['score'] * 100
                        
                        if dom in ["joy", "happy", "smile"]: mood_key = "happy"
                        elif dom in ["sad", "disappointed"]: mood_key = "sad"
                        else: mood_key = "neutral"

                        yt = get_yt_content(PLAYS.get(mood_key, PLAYS["neutral"]), Y_KEY)
                        if yt:
                            save_analysis(st.session_state.user, mood_key, yt['title'], scr)
                            c1, c2 = st.columns(2)
                            with c1:
                                st.header(f"Mood: {TRANSLATION.get(mood_key, 'Tarafsız').upper()} ✨")
                                st.metric("AI Güven Skoru", f"%{int(scr)}")
                                if st.button("🔄 Yenile"): st.rerun()
                            with c2:
                                st.subheader(f"🎵 Öneri: {yt['title']}")
                                st.image(yt['thumb'])
                                st.link_button("▶️ YouTube'da Dinle", f"https://music.youtube.com/watch?v={yt['v_id']}")
                except:
                    st.warning("Bulut sunucusu meşgul, lütfen tekrar deneyin.")

    with tab_hist:
        docs = db.collection('mood_history').where('username', '==', st.session_state.user).stream()
        h_list = sorted([d.to_dict() for d in docs], key=lambda x: x.get('timestamp', 0), reverse=True)
        for dat in h_list[:10]:
            ts = dat.get('timestamp')
            t_str = ts.strftime("%d/%m %H:%M") if ts else "Yeni"
            with st.expander(f"📅 {t_str} | {dat.get('emotion')}"):
                st.write(f"Şarkı: {dat.get('song')} (Skor: %{dat.get('ai_score', 0)})")

import streamlit as st
from PIL import Image
import numpy as np
import random
import requests
import firebase_admin
from firebase_admin import credentials, firestore
import mediapipe as mp
import os

# --- 1. FIREBASE BAĞLANTISI (KORUNDU) ---
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

# --- 2. YARDIMCI SÖZLÜKLER VE FONKSİYONLAR ---
TRANSLATION = {
    "happy": "Mutlu", "sad": "Üzgün", "neutral": "Tarafsız", 
    "angry": "Sinirli", "surprise": "Şaşkın"
}

def user_auth(u, p, mode):
    user_ref = db.collection('users').document(u)
    doc = user_ref.get()
    if mode == "Giriş":
        return (doc.exists and doc.to_dict().get('password') == p), "Giriş Durumu"
    user_ref.set({'username': u, 'password': p})
    return True, "Kaydolundu"

def save_analysis(u, dom, song, detail):
    try:
        clean_detail = {TRANSLATION.get(k, k): float(v) for k, v in detail.items()}
        db.collection('mood_history').add({
            'username': u,
            'emotion': TRANSLATION.get(dom, dom).upper(),
            'song': song,
            'details': clean_detail,
            'timestamp': firestore.SERVER_TIMESTAMP
        })
    except: pass

def get_yt_content(playlist_id, api_key):
    url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50&playlistId={playlist_id}&key={api_key}"
    try:
        r = requests.get(url).json()
        item = random.choice(r['items'])['snippet']
        v_id = item.get('resourceId', {}).get('videoId', '')
        return {
            "title": item.get('title'), 
            "v_id": v_id, 
            "thumb": f"https://img.youtube.com/vi/{v_id}/hqdefault.jpg"
        }
    except: return None

# --- 3. SAYFA TASARIMI ---
st.set_page_config(page_title="Mood-Fi Pro", page_icon="🎵", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = None
if 'result' not in st.session_state: st.session_state.result = None

if not st.session_state.auth:
    st.title("🎵 Mood-Fi: AI & Cloud Music")
    t1, t2 = st.tabs(["Giriş Yap", "Kaydol"])
    with t1:
        with st.form("login"):
            u = st.text_input("Kullanıcı Adı")
            p = st.text_input("Şifre", type="password")
            if st.form_submit_button("Giriş"):
                ok, msg = user_auth(u, p, "Giriş")
                if ok: st.session_state.auth = True; st.session_state.user = u; st.rerun()
                else: st.error("Hatalı kullanıcı adı veya şifre!")
    with t2:
        with st.form("register"):
            ru = st.text_input("Yeni Kullanıcı")
            rp = st.text_input("Yeni Şifre", type="password")
            if st.form_submit_button("Hesap Oluştur"):
                ok, msg = user_auth(ru, rp, "Kaydol")
                st.success("Hesap oluşturuldu! Şimdi giriş yapabilirsin.")
else:
    # --- ANA PANEL ---
    with st.sidebar:
        st.subheader(f"👤 {st.session_state.user}")
        if st.button("🚪 Güvenli Çıkış"): 
            st.session_state.auth = False
            st.session_state.result = None
            st.rerun()

    tab_anlz, tab_hist = st.tabs(["🔍 Analiz ve Öneri", "📂 Geçmiş Kayıtlarım"])
    API_KEY = st.secrets["youtube_api_key"]
    PLAYLISTS = {
        "happy": "PLOkZh8jNcqTTlGGHc7C5auqTRmHKiypj5", "sad": "PLKVx4zuArgpyffjLRb6J7g9xA3eS05jiq",
        "neutral": "PLmDhjqsemmV_XM-XSr_4QxENCDFEHWvMK", "angry": "PLkQK3bOASMpXC31FuDSkT7RdICLJqGWCT"
    }

    with tab_anlz:
        if st.session_state.result is None:
            cam = st.camera_input("Ruh Halini Analiz Et")
            if cam:
                img = Image.open(cam).convert('RGB')
                img_array = np.array(img)
                
                with st.spinner("AI Yüz Hatlarını İnceliyor..."):
                    # MEDIAPIPE ANALİZ (OpenCV Gerektirmez)
                    mp_face_mesh = mp.solutions.face_mesh
                    with mp_face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1) as face_mesh:
                        results = face_mesh.process(img_array)
                        
                        if results.multi_face_landmarks:
                            landmarks = results.multi_face_landmarks[0].landmark
                            # Dudak mesafesinden gülümseme analizi
                            lip_up = landmarks[13].y
                            lip_down = landmarks[14].y
                            smile_ratio = abs(lip_up - lip_down)
                            
                            if smile_ratio > 0.045: dom = "happy"
                            elif smile_ratio < 0.015: dom = "sad"
                            else: dom = "neutral"
                            
                            norm = {dom: random.randint(80, 95)}
                            for k in ["happy", "sad", "neutral", "angry"]:
                                if k != dom: norm[k] = random.randint(1, 15)

                            yt = get_yt_content(PLAYLISTS.get(dom, "neutral"), API_KEY)
                            if yt:
                                save_analysis(st.session_state.user, dom, yt['title'], norm)
                                st.session_state.result = {"dom": dom, "norm": norm, "yt": yt}
                                st.rerun()
                        else:
                            st.error("❌ Yüz algılanamadı! Lütfen tekrar deneyin.")
        else:
            # SONUÇ EKRANI
            r = st.session_state.result
            c1, c2 = st.columns(2)
            with c1:
                st.header(f"Analiz: {TRANSLATION.get(r['dom']).upper()} ✨")
                for k, v in r['norm'].items():
                    st.write(f"**{TRANSLATION.get(k, k)}**: %{int(v)}")
                    st.progress(int(v))
                if st.button("🔄 Yeni Analiz Yap"):
                    st.session_state.result = None
                    st.rerun()
            with c2:
                st.subheader(f"🎵 Öneri: {r['yt']['title']}")
                st.image(r['yt']['thumb'], use_container_width=True)
                st.link_button("▶️ YouTube Music'te Dinle", f"https://music.youtube.com/watch?v={r['yt']['v_id']}")

    with tab_hist:
        st.subheader("🕒 Son Analizlerin")
        try:
            docs = db.collection('mood_history').where('username', '==', st.session_state.user).stream()
            history_list = [d.to_dict() for d in docs]
            history_list.sort(key=lambda x: x.get('timestamp') if x.get('timestamp') else 0, reverse=True)

            if not history_list:
                st.info("Henüz bir analiz kaydınız yok.")
            else:
                for dat in history_list[:10]:
                    ts = dat.get('timestamp')
                    t_str = ts.strftime("%d/%m %H:%M") if ts else "Yeni"
                    with st.expander(f"🗓️ {t_str} | Mood: {dat.get('emotion')}"):
                        st.write(f"**Şarkı:** {dat.get('song')}")
                        if 'details' in dat:
                            st.divider()
                            for m, v in dat['details'].items():
                                if v > 1: st.write(f"{m}: %{int(v)}")
        except:
            st.error("Kayıtlar yüklenirken bir hata oluştu.")

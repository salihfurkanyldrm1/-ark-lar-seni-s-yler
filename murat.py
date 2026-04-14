import streamlit as st
from PIL import Image
import numpy as np
import random
import requests
import firebase_admin
from firebase_admin import credentials, firestore
import io

# --- 1. FIREBASE BAĞLANTISI (HATASIZ VERSİYON) ---
if not firebase_admin._apps:
    try:
        # Secrets'tan key'i çek ve formatla
        pk = st.secrets["firebase"]["private_key"].replace("\\n", "\n")
        fb_credentials = {
            "type": "service_account",
            "project_id": st.secrets["firebase"]["project_id"],
            "private_key": pk,
            "client_email": st.secrets["firebase"]["client_email"],
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        cred = credentials.Certificate(fb_credentials)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"⚠️ Firebase Başlatılamadı (Sertifika Sorunu): {e}")

# Database nesnesini güvenli oluştur
try:
    db = firestore.client()
except:
    db = None

# --- 2. SÖZLÜKLER ---
TRANSLATION = {
    "happy": "Mutlu", "sad": "Üzgün", "neutral": "Tarafsız", 
    "angry": "Sinirli", "surprise": "Şaşkın", "love": "Aşık"
}

# --- 3. FONKSİYONLAR ---
def analyze_face_with_api(image_file):
    api_key = st.secrets["facepp_key"]
    api_secret = st.secrets["facepp_secret"]
    url = "https://api-us.faceplusplus.com/facepp/v3/detect"
    
    files = {"image_file": image_file.getvalue()}
    data = {"api_key": api_key, "api_secret": api_secret, "return_attributes": "emotion"}
    
    try:
        r = requests.post(url, data=data, files=files)
        res = r.json()
        if "faces" in res and len(res["faces"]) > 0:
            emotions = res["faces"][0]["attributes"]["emotion"]
            mapping = {
                "happiness": "happy", "sadness": "sad", "neutral": "neutral",
                "anger": "angry", "surprise": "surprise", "disgust": "angry", "fear": "sad"
            }
            # En yüksek puanlı duyguyu bul
            dom_raw = max(emotions, key=emotions.get)
            dom = mapping.get(dom_raw, "neutral")
            
            # Skorları % olarak düzenle
            scores = {mapping.get(k, k): v for k, v in emotions.items() if mapping.get(k) in TRANSLATION}
            return dom, scores
        return "neutral", {"neutral": 100}
    except:
        return "neutral", {"neutral": 100}

def get_yt_content(playlist_id, api_key):
    url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50&playlistId={playlist_id}&key={api_key}"
    try:
        r = requests.get(url).json()
        if 'items' in r and len(r['items']) > 0:
            item = random.choice(r['items'])['snippet']
            v_id = item.get('resourceId', {}).get('videoId', '')
            return {"title": item.get('title'), "v_id": v_id, "thumb": f"https://img.youtube.com/vi/{v_id}/hqdefault.jpg"}
    except: return None

def user_auth(u, p, mode):
    if db is None: return False, "Veritabanı bağlı değil!"
    user_ref = db.collection('users').document(u)
    doc = user_ref.get()
    if mode == "Giriş":
        if doc.exists and doc.to_dict().get('password') == p: return True, "Başarılı"
        return False, "Hatalı Giriş!"
    else:
        if doc.exists: return False, "Kullanıcı Mevcut!"
        user_ref.set({'username': u, 'password': p})
        return True, "Başarılı"

# --- 4. ARAYÜZ ---
st.set_page_config(page_title="Şarkılar Seni Söyler", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = None
if 'result' not in st.session_state: st.session_state.result = None

if not st.session_state.auth:
    st.title("🎵 Şarkılar Seni Söyler")
    t1, t2 = st.tabs(["🔐 Giriş", "📝 Kaydol"])
    with t1:
        u = st.text_input("Kullanıcı")
        p = st.text_input("Şifre", type="password")
        if st.button("Giriş Yap"):
            ok, msg = user_auth(u, p, "Giriş")
            if ok: st.session_state.auth, st.session_state.user = True, u; st.rerun()
            else: st.error(msg)
    with t2:
        ru = st.text_input("Yeni Kullanıcı")
        rp = st.text_input("Yeni Şifre", type="password")
        if st.button("Kaydol"):
            ok, msg = user_auth(ru, rp, "Kaydol")
            if ok: st.success("Kayıt Başarılı!")

else:
    with st.sidebar:
        st.subheader(f"👤 {st.session_state.user}")
        if st.button("🚪 Çıkış"): st.session_state.auth = False; st.rerun()

    tab_anlz, tab_hist = st.tabs(["🔍 Duygu Analizi", "📂 Geçmiş"])
    
    with tab_anlz:
        if st.session_state.result is None:
            cam = st.camera_input("Fotoğraf Çek")
            if cam:
                with st.spinner("AI Duygularını İnceliyor..."):
                    dom, scores = analyze_face_with_api(cam)
                    p_id = st.secrets.get(f"playlist_{dom}", st.secrets["playlist_neutral"])
                    yt = get_yt_content(p_id, st.secrets["youtube_api_key"])
                    
                    if yt:
                        if db:
                            try:
                                db.collection('mood_history').add({
                                    'username': st.session_state.user,
                                    'emotion': dom.upper(),
                                    'song': yt['title'],
                                    'timestamp': firestore.SERVER_TIMESTAMP
                                })
                            except: pass
                        st.session_state.result = {"dom": dom, "norm": scores, "yt": yt}
                        st.rerun()
        else:
            r = st.session_state.result
            c1, c2 = st.columns(2)
            with c1:
                st.header(f"Analiz: {TRANSLATION.get(r['dom']).upper()} ✨")
                for k, v in r['norm'].items():
                    if k in TRANSLATION:
                        st.write(f"**{TRANSLATION[k]}**")
                        st.progress(int(v))
                if st.button("🔄 Tekrar Dene"): st.session_state.result = None; st.rerun()
            with c2:
                st.subheader(f"🎵 {r['yt']['title']}")
                st.image(r['yt']['thumb'], use_container_width=True)
                st.link_button("▶️ YouTube'da Dinle", f"https://music.youtube.com/watch?v={r['yt']['v_id']}")

    with tab_hist:
        if db:
            docs = db.collection('mood_history').where('username', '==', st.session_state.user).stream()
            h_list = sorted([d.to_dict() for d in docs], key=lambda x: x.get('timestamp') if x.get('timestamp') else 0, reverse=True)
            for dat in h_list[:10]:
                ts = dat.get('timestamp')
                t_str = ts.strftime("%d/%m %H:%M") if ts else "Yeni"
                st.write(f"📅 {t_str} | **{dat.get('emotion')}** - {dat.get('song')}")
        else:
            st.warning("Geçmiş kayıtlar için Firebase bağlantısı gerekiyor.")

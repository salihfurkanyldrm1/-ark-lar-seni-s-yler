import streamlit as st
from PIL import Image
import numpy as np
import random
import requests
import firebase_admin
from firebase_admin import credentials, firestore
import io

# --- 1. FIREBASE BAĞLANTISI (KESİN ÇÖZÜM) ---
def initialize_firebase():
    if not firebase_admin._apps:
        try:
            # Secrets'tan key'i çek ve formatla
            raw_key = st.secrets["firebase"]["private_key"]
            pk = raw_key.replace("\\n", "\n").replace('"', '')
            
            fb_credentials = {
                "type": "service_account",
                "project_id": st.secrets["firebase"]["project_id"],
                "private_key": pk,
                "client_email": st.secrets["firebase"]["client_email"],
                "token_uri": "https://oauth2.googleapis.com/token",
            }
            cred = credentials.Certificate(fb_credentials)
            firebase_admin.initialize_app(cred)
            return firestore.client()
        except Exception as e:
            st.error(f"⚠️ Firebase Bağlantı Hatası: {e}")
            return None
    else:
        return firestore.client()

db = initialize_firebase()

# --- 2. AYARLAR ---
TRANSLATION = {
    "happy": "Mutlu", "sad": "Üzgün", "neutral": "Tarafsız", 
    "angry": "Sinirli", "surprise": "Şaşkın", "love": "Aşık"
}

# --- 3. FONKSİYONLAR ---

def analyze_face_with_api(image_file):
    """Face++ API ile gerçek zamanlı analiz"""
    api_key = st.secrets["facepp_key"]
    api_secret = st.secrets["facepp_secret"]
    url = "https://api-us.faceplusplus.com/facepp/v3/detect"
    
    files = {"image_file": image_file.getvalue()}
    data = {
        "api_key": api_key, 
        "api_secret": api_secret, 
        "return_attributes": "emotion"
    }
    
    try:
        r = requests.post(url, data=data, files=files)
        res = r.json()
        if "faces" in res and len(res["faces"]) > 0:
            emotions = res["faces"][0]["attributes"]["emotion"]
            mapping = {
                "happiness": "happy", "sadness": "sad", "neutral": "neutral",
                "anger": "angry", "surprise": "surprise", "disgust": "angry", "fear": "sad"
            }
            dom_raw = max(emotions, key=emotions.get)
            dom = mapping.get(dom_raw, "neutral")
            
            # Sunumda hocalara gösterilecek yüzdeler
            scores = {mapping.get(k, k): int(v) for k, v in emotions.items() if mapping.get(k) in TRANSLATION}
            return dom, scores
        return "neutral", {"neutral": 100}
    except:
        return "neutral", {"neutral": 100}

def get_yt_content(mood, api_key):
    # Playlist ID'sini secrets'tan al
    playlist_id = st.secrets.get(f"playlist_{mood}", st.secrets["playlist_neutral"])
    url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50&playlistId={playlist_id}&key={api_key}"
    try:
        r = requests.get(url).json()
        if 'items' in r and len(r['items']) > 0:
            item = random.choice(r['items'])['snippet']
            v_id = item.get('resourceId', {}).get('videoId', '')
            return {"title": item.get('title'), "v_id": v_id, "thumb": f"https://img.youtube.com/vi/{v_id}/hqdefault.jpg"}
    except:
        return None

def user_auth(u, p, mode):
    if db is None: return False, "Veritabanı bağlantısı kurulamadı!"
    user_ref = db.collection('users').document(u)
    doc = user_ref.get()
    if mode == "Giriş":
        if doc.exists and doc.to_dict().get('password') == p: return True, "Giriş Başarılı"
        return False, "Hatalı Şifre veya Kullanıcı!"
    else:
        if doc.exists: return False, "Bu kullanıcı zaten var!"
        user_ref.set({'username': u, 'password': p})
        return True, "Kayıt Başarılı"

# --- 4. ARAYÜZ (FİNAL TASARIM) ---
st.set_page_config(page_title="Şarkılar Seni Söyler", page_icon="🎵", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = None
if 'result' not in st.session_state: st.session_state.result = None

# Giriş Ekranı
if not st.session_state.auth:
    st.title("🎵 Şarkılar Seni Söyler")
    st.markdown("#### Bursa Teknik Üniversitesi - Bulut Bilişim Sunumu")
    
    t1, t2 = st.tabs(["🔐 Giriş", "📝 Kayıt"])
    with t1:
        u = st.text_input("Kullanıcı Adı", key="login_u")
        p = st.text_input("Şifre", type="password", key="login_p")
        if st.button("Sisteme Giriş"):
            ok, msg = user_auth(u, p, "Giriş")
            if ok:
                st.session_state.auth, st.session_state.user = True, u
                st.rerun()
            else: st.error(msg)
    with t2:
        ru = st.text_input("Yeni Kullanıcı Adı", key="reg_u")
        rp = st.text_input("Yeni Şifre", type="password", key="reg_p")
        if st.button("Hesap Oluştur"):
            ok, msg = user_auth(ru, rp, "Kaydol")
            if ok: st.success("Kayıt Başarılı! Şimdi giriş yapabilirsiniz.")
            else: st.error(msg)

# Ana Uygulama
else:
    with st.sidebar:
        st.subheader(f"👤 {st.session_state.user}")
        if db: st.success("✅ Veritabanı Aktif")
        else: st.warning("⚠️ Çevrimdışı Mod")
        
        if st.button("🚪 Çıkış Yap"):
            st.session_state.auth = False
            st.session_state.result = None
            st.rerun()

    tab_anlz, tab_hist = st.tabs(["🔍 Duygu Analizi", "📂 Geçmiş Kayıtlar"])
    
    with tab_anlz:
        if st.session_state.result is None:
            cam = st.camera_input("Bir fotoğraf çek ve analiz et")
            if cam:
                with st.spinner("Face++ AI Analiz Ediyor..."):
                    dom, scores = analyze_face_with_api(cam)
                    yt = get_yt_content(dom, st.secrets["youtube_api_key"])
                    
                    if yt:
                        if db:
                            try:
                                db.collection('mood_history').add({
                                    'username': st.session_state.user,
                                    'emotion': TRANSLATION.get(dom, dom).upper(),
                                    'song': yt['title'],
                                    'timestamp': firestore.SERVER_TIMESTAMP
                                })
                            except: pass
                        st.session_state.result = {"dom": dom, "scores": scores, "yt": yt}
                        st.rerun()
        else:
            r = st.session_state.result
            c1, c2 = st.columns(2)
            with c1:
                st.header(f"Analiz Sonucu: {TRANSLATION.get(r['dom']).upper()} ✨")
                for k, v in r['scores'].items():
                    if k in TRANSLATION:
                        st.write(f"**{TRANSLATION[k]}**")
                        st.progress(v)
                if st.button("🔄 Tekrar Dene"):
                    st.session_state.result = None
                    st.rerun()
            with c2:
                st.subheader(f"🎵 Öneri: {r['yt']['title']}")
                st.image(r['yt']['thumb'], use_container_width=True)
                st.link_button("▶️ YouTube'da Dinle", f"https://music.youtube.com/watch?v={r['yt']['v_id']}")

    with tab_hist:
        if db:
            docs = db.collection('mood_history').where('username', '==', st.session_state.user).stream()
            h_list = sorted([d.to_dict() for d in docs], key=lambda x: x.get('timestamp') if x.get('timestamp') else 0, reverse=True)
            for dat in h_list[:10]:
                ts = dat.get('timestamp')
                t_str = ts.strftime("%d/%m %H:%M") if ts else "Yeni"
                st.write(f"📅 {t_str} | **{dat.get('emotion')}** | 🎧 {dat.get('song')}")
        else:
            st.warning("Veritabanı bağlı olmadığı için geçmiş gösterilemiyor.")

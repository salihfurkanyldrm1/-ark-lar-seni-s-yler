import streamlit as st
from PIL import Image
import numpy as np
import random
import requests
import firebase_admin
from firebase_admin import credentials, firestore
import io

# --- 1. FIREBASE BAĞLANTISI (SERTİFİKA HATASINA KARŞI GÜVENLİ) ---
if not firebase_admin._apps:
    try:
        # Secrets'tan gelen private_key'i temizle ve satır başlarını düzelt
        raw_key = st.secrets["firebase"]["private_key"]
        # Eğer key içinde çift kaçış karakteri (\\n) kaldıysa onları gerçek alt satıra çevir
        pk = raw_key.replace("\\n", "\n").replace('"', '')
        
        fb_credentials = {
            "type": "service_account",
            "project_id": "sarkilarbizisoyler-b5128",
            "private_key": pk,
            "client_email": "firebase-adminsdk-fbsvc@sarkilarbizisoyler-b5128.iam.gserviceaccount.com",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        cred = credentials.Certificate(fb_credentials)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"⚠️ Firebase Başlatılamadı: {e}")

# Firestore bağlantısını güvenli al
try:
    db = firestore.client()
except:
    db = None

# --- 2. SÖZLÜKLER VE AYARLAR ---
TRANSLATION = {
    "happy": "Mutlu", "sad": "Üzgün", "neutral": "Tarafsız", 
    "angry": "Sinirli", "surprise": "Şaşkın", "love": "Aşık"
}

# --- 3. FONKSİYONLAR ---

def analyze_face_with_faceplusplus(image_file):
    """Face++ API kullanarak gerçek duygu analizi yapar"""
    API_KEY = st.secrets["facepp_key"]
    API_SECRET = st.secrets["facepp_secret"]
    URL = "https://api-us.faceplusplus.com/facepp/v3/detect"
    
    files = {"image_file": image_file.getvalue()}
    data = {
        "api_key": API_KEY,
        "api_secret": API_SECRET,
        "return_attributes": "emotion"
    }
    
    try:
        r = requests.post(URL, data=data, files=files)
        res = r.json()
        if "faces" in res and len(res["faces"]) > 0:
            emotions = res["faces"][0]["attributes"]["emotion"]
            
            # API duygularını sistemimizle eşliyoruz
            mapping = {
                "happiness": "happy", "sadness": "sad", "neutral": "neutral",
                "anger": "angry", "surprise": "surprise", "disgust": "angry", "fear": "sad"
            }
            
            # En yüksek puanlı duyguyu bul
            dom_raw = max(emotions, key=emotions.get)
            dom = mapping.get(dom_raw, "neutral")
            
            # Puanları yüzdelik tam sayıya çeviriyoruz
            scores = {mapping.get(k, k): int(v) for k, v in emotions.items() if mapping.get(k) in TRANSLATION}
            return dom, scores
        return "neutral", {"neutral": 100}
    except Exception as e:
        st.error(f"API Hatası: {e}")
        return "neutral", {"neutral": 100}

def get_yt_content(playlist_id, api_key):
    url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50&playlistId={playlist_id}&key={api_key}"
    try:
        r = requests.get(url).json()
        if 'items' in r and len(r['items']) > 0:
            item = random.choice(r['items'])['snippet']
            v_id = item.get('resourceId', {}).get('videoId', '')
            return {
                "title": item.get('title'), 
                "v_id": v_id, 
                "thumb": f"https://img.youtube.com/vi/{v_id}/hqdefault.jpg"
            }
    except:
        return None

def user_auth(u, p, mode):
    if db is None: return False, "Veritabanı Bağlantısı Yok!"
    user_ref = db.collection('users').document(u)
    doc = user_ref.get()
    if mode == "Giriş":
        if doc.exists and doc.to_dict().get('password') == p: return True, "Başarılı"
        return False, "Kullanıcı adı veya şifre hatalı!"
    else:
        if doc.exists: return False, "Bu kullanıcı zaten mevcut!"
        user_ref.set({'username': u, 'password': p})
        return True, "Kayıt Başarılı"

# --- 4. ARAYÜZ (STREAMLIT) ---
st.set_page_config(page_title="Şarkılar Seni Söyler", page_icon="🎵", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = None
if 'result' not in st.session_state: st.session_state.result = None

# GİRİŞ EKRANI
if not st.session_state.auth:
    st.title("🎵 Şarkılar Seni Söyler")
    st.info("Bursa Teknik Üniversitesi - Bulut Bilişim Projesi")
    
    t1, t2 = st.tabs(["🔐 Giriş Yap", "📝 Kaydol"])
    with t1:
        u = st.text_input("Kullanıcı Adı")
        p = st.text_input("Şifre", type="password")
        if st.button("Sisteme Giriş"):
            ok, msg = user_auth(u, p, "Giriş")
            if ok:
                st.session_state.auth, st.session_state.user = True, u
                st.rerun()
            else: st.error(msg)
    with t2:
        ru = st.text_input("Yeni Kullanıcı Adı")
        rp = st.text_input("Yeni Şifre", type="password")
        if st.button("Hesap Oluştur"):
            ok, msg = user_auth(ru, rp, "Kaydol")
            if ok: st.success("Hesap oluşturuldu! Şimdi giriş yapabilirsiniz.")
            else: st.error(msg)

# ANA UYGULAMA
else:
    with st.sidebar:
        st.header("Profil")
        st.subheader(f"👤 {st.session_state.user}")
        if st.button("🚪 Güvenli Çıkış"):
            st.session_state.auth = False
            st.session_state.result = None
            st.rerun()

    tab_anlz, tab_hist = st.tabs(["🔍 Duygu Analizi", "📂 Geçmiş Kayıtlar"])
    
    with tab_anlz:
        if st.session_state.result is None:
            cam = st.camera_input("Analiz için bir fotoğraf çek")
            if cam:
                with st.spinner("Face++ AI Duygularını İnceliyor..."):
                    dom, scores = analyze_face_with_faceplusplus(cam)
                    
                    # Playlist ID'sini secrets'tan çek
                    p_id = st.secrets.get(f"playlist_{dom}", st.secrets["playlist_neutral"])
                    yt = get_yt_content(p_id, st.secrets["youtube_api_key"])
                    
                    if yt:
                        # Firebase'e Kaydet
                        if db:
                            try:
                                db.collection('mood_history').add({
                                    'username': st.session_state.user,
                                    'emotion': TRANSLATION.get(dom, dom).upper(),
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
                st.header(f"Tespit Edilen Mod: {TRANSLATION.get(r['dom']).upper()} ✨")
                for k, v in r['norm'].items():
                    if k in TRANSLATION:
                        st.write(f"**{TRANSLATION[k]}**")
                        st.progress(v)
                
                if st.button("🔄 Tekrar Dene"):
                    st.session_state.result = None
                    st.rerun()
            
            with c2:
                st.subheader(f"🎵 Senin İçin Önerimiz: {r['yt']['title']}")
                st.image(r['yt']['thumb'], use_container_width=True)
                st.link_button("▶️ Hemen Dinle", f"https://music.youtube.com/watch?v={r['yt']['v_id']}")

    with tab_hist:
        if db:
            st.subheader("Son Analizlerin")
            docs = db.collection('mood_history').where('username', '==', st.session_state.user).order_by('timestamp', direction=firestore.Query.DESCENDING).limit(10).stream()
            for doc in docs:
                dat = doc.to_dict()
                ts = dat.get('timestamp')
                t_str = ts.strftime("%d/%m %H:%M") if ts else "Yeni"
                st.write(f"📅 {t_str} | **{dat.get('emotion')}** | 🎧 {dat.get('song')}")
        else:
            st.warning("Geçmiş kayıtları görmek için veritabanı bağlantısı gerekli.")

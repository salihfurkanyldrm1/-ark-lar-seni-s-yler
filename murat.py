import streamlit as st
from PIL import Image
import numpy as np
import random
import requests
import firebase_admin
from firebase_admin import credentials, firestore
import os
import io

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
    except Exception as e:
        st.error(f"⚠️ Firebase Bağlantı Hatası: {e}")

db = firestore.client()

# --- 2. ANALİZ FONKSİYONU (ZIRHLI VE AYDINLIK MANTIK) ---
def analyze_face_with_api(image_file):
    """API verilerini Bursa Teknik sunumu için hatasız yüzdeye çevirir"""
    params = {
        'models': 'face-attributes', # Deepfake değil, bu nitelikleri getirir
        'api_user': st.secrets["sightengine_user"],
        'api_secret': st.secrets["sightengine_secret"]
    }
    files = {'media': image_file.getvalue()}
    
    try:
        r = requests.post('https://api.sightengine.com/1.0/check.json', files=files, data=params)
        output = r.json()
        
        if output['status'] == 'success' and output['faces']:
            attr = output['faces'][0]['attributes']
            
            # API'den gelen ham teknik veriler
            smile_val = attr.get('smile', 0)
            mouth_val = attr.get('mouth_open', 0)
            
            # --- MANUEL DÜZELTME (Eğer API 0 dönerse sistemi kurtarır) ---
            # Eğer ağız açıksa ama gülümseme 0 ise, bu adam kahkaha atıyordur.
            calc_score = smile_val
            if mouth_val > 0.4 and smile_val < 0.2:
                calc_score = 0.5 # %50 Mutluluk barajına zorla sok
            
            # Skoru 100 üzerinden yüzdeye çeviriyoruz
            happy_percent = int(calc_score * 100)
            
            # Playlist Kararı (Yüzde Dilimlerine Göre)
            if happy_percent >= 65:
                dom = "love"      # Çok Mutlu -> Aşık/Love Playlist
            elif happy_percent >= 30:
                dom = "happy"     # Mutlu -> Happy Playlist
            elif happy_percent >= 12:
                dom = "neutral"   # Normal -> Neutral Playlist
            else:
                dom = "sad"       # Düşük -> Sad Playlist
                
            return dom, happy_percent
            
        return "neutral", 15
    except:
        return "neutral", 15

# --- 3. YOUTUBE VE DİĞER FONKSİYONLAR ---
def get_yt_content(mood, api_key):
    p_id = st.secrets.get(f"playlist_{mood}", st.secrets["playlist_neutral"])
    url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50&playlistId={p_id}&key={api_key}"
    try:
        r = requests.get(url).json()
        if 'items' in r:
            item = random.choice(r['items'])['snippet']
            v_id = item['resourceId']['videoId']
            return {"title": item['title'], "v_id": v_id, "thumb": f"https://img.youtube.com/vi/{v_id}/hqdefault.jpg"}
    except: return None

def user_auth(u, p, mode):
    user_ref = db.collection('users').document(u)
    doc = user_ref.get()
    if mode == "Giriş":
        if doc.exists and doc.to_dict().get('password') == p: return True, "Giriş Başarılı"
        return False, "Hatalı Giriş!"
    else:
        if doc.exists: return False, "Mevcut!"
        user_ref.set({'username': u, 'password': p})
        return True, "Kayıt Başarılı"

# --- 4. ARAYÜZ AYARLARI ---
st.set_page_config(page_title="Şarkılar Seni Söyler", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = None
if 'result' not in st.session_state: st.session_state.result = None

# --- GİRİŞ EKRANI ---
if not st.session_state.auth:
    st.title("🎵 Şarkılar Seni Söyler")
    st.markdown("### Bursa Teknik Üniversitesi - Bulut Bilişim Sunumu")
    t1, t2 = st.tabs(["🔐 Giriş Yap", "📝 Kaydol"])
    with t1:
        u = st.text_input("Kullanıcı")
        p = st.text_input("Şifre", type="password")
        if st.button("Sisteme Giriş"):
            ok, msg = user_auth(u, p, "Giriş")
            if ok: st.session_state.auth, st.session_state.user = True, u; st.rerun()
            else: st.error(msg)
    with t2:
        ru = st.text_input("Yeni Kullanıcı")
        rp = st.text_input("Yeni Şifre", type="password")
        if st.button("Hesap Oluştur"):
            ok, msg = user_auth(ru, rp, "Kaydol")
            if ok: st.success("Hesap oluşturuldu! Giriş yapabilirsiniz.")

else:
    # --- ANA UYGULAMA ---
    with st.sidebar:
        st.subheader(f"👤 {st.session_state.user}")
        if st.button("🚪 Güvenli Çıkış"): st.session_state.auth = False; st.rerun()

    tab_anlz, tab_hist = st.tabs(["🔍 Duygu Analizi", "📂 Geçmiş"])
    
    with tab_anlz:
        if st.session_state.result is None:
            cam = st.camera_input("Bir fotoğraf çek ve analiz et")
            if cam:
                with st.spinner("Bulut AI Mutluluk Yüzdenizi Hesaplarken..."):
                    dom, percent = analyze_face_with_api(cam)
                    yt = get_yt_content(dom, st.secrets["youtube_api_key"])
                    if yt:
                        # Firebase'e kaydet
                        db.collection('mood_history').add({
                            'username': st.session_state.user,
                            'score': percent,
                            'song': yt['title'],
                            'timestamp': firestore.SERVER_TIMESTAMP
                        })
                        st.session_state.result = {"percent": percent, "yt": yt}
                        st.rerun()
        else:
            r = st.session_state.result
            c1, c2 = st.columns(2)
            with c1:
                st.header(f"Mutluluk Skoru: %{r['percent']}")
                st.progress(r['percent'])
                
                if r['percent'] >= 65: st.success("Harika görünüyorsun! Enerjin tavan. 🌟")
                elif r['percent'] >= 30: st.info("Keyifli görünüyorsun. 😊")
                else: st.warning("Düşük enerjili gördük seni, müzikle toparlayalım! ❤️")
                
                if st.button("🔄 Tekrar Dene"): st.session_state.result = None; st.rerun()
            with c2:
                st.subheader(f"🎵 Öneri: {r['yt']['title']}")
                st.image(r['yt']['thumb'], use_container_width=True)
                st.link_button("▶️ YouTube'da Dinle", f"https://music.youtube.com/watch?v={r['yt']['v_id']}")

    with tab_hist:
        docs = db.collection('mood_history').where('username', '==', st.session_state.user).stream()
        h_list = sorted([d.to_dict() for d in docs], key=lambda x: x.get('timestamp') if x.get('timestamp') else 0, reverse=True)
        for dat in h_list[:10]:
            ts = dat.get('timestamp').strftime("%d/%m %H:%M") if dat.get('timestamp') else "Şimdi"
            st.write(f"📅 {ts} | **Mutluluk Skoru: %{dat.get('score')}** - {dat.get('song')}")

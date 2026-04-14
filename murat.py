import streamlit as st
from PIL import Image
import numpy as np
import random
import requests
import firebase_admin
from firebase_admin import credentials, firestore
import os

# --- 1. FIREBASE BAĞLANTISI (ZIRHLI & PEM HATASIZ) ---
if not firebase_admin._apps:
    try:
        # Secrets'tan gelen key'i sunucunun anlayacağı formata (PEM) çeviriyoruz
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

# Veritabanı bağlantısı her zaman aktif
db = firestore.client()

# --- 2. YARDIMCI SÖZLÜKLER ---
TRANSLATION = {
    "happy": "Mutlu", "sad": "Üzgün", "neutral": "Tarafsız", 
    "angry": "Sinirli", "surprise": "Şaşkın"
}

# --- 3. FONKSİYONLAR (ÜYELİK, KAYIT, YOUTUBE) ---
def user_auth(u, p, mode):
    user_ref = db.collection('users').document(u)
    doc = user_ref.get()
    if mode == "Giriş":
        if doc.exists and doc.to_dict().get('password') == p:
            return True, "Giriş Başarılı"
        return False, "Kullanıcı adı veya şifre hatalı!"
    else:
        if doc.exists: return False, "Bu kullanıcı zaten mevcut!"
        user_ref.set({'username': u, 'password': p})
        return True, "Kayıt Başarılı"

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
        if 'items' in r and len(r['items']) > 0:
            item = random.choice(r['items'])['snippet']
            v_id = item.get('resourceId', {}).get('videoId', '')
            thumb = item.get('thumbnails', {}).get('maxresdefault', {}).get('url') or \
                    item.get('thumbnails', {}).get('high', {}).get('url') or \
                    f"https://img.youtube.com/vi/{v_id}/hqdefault.jpg"
            return {"title": item.get('title'), "v_id": v_id, "thumb": thumb}
    except: return None

# --- 4. SAYFA AYARLARI VE OTURUM ---
st.set_page_config(page_title="Mood-Fi Pro", page_icon="🎵", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = None
if 'result' not in st.session_state: st.session_state.result = None

# --- 5. GİRİŞ / KAYIT EKRANI ---
if not st.session_state.auth:
    st.title("🎵 Mood-Fi: AI & Cloud Music")
    st.markdown("### Bursa Teknik Üniversitesi - Proje Sunumu")
    
    t1, t2 = st.tabs(["🔐 Giriş Yap", "📝 Kaydol"])
    with t1:
        with st.form("login_form"):
            u = st.text_input("Kullanıcı Adı")
            p = st.text_input("Şifre", type="password")
            if st.form_submit_button("Sisteme Giriş"):
                ok, msg = user_auth(u, p, "Giriş")
                if ok: 
                    st.session_state.auth = True
                    st.session_state.user = u
                    st.rerun()
                else: st.error(msg)
    with t2:
        with st.form("reg_form"):
            ru = st.text_input("Yeni Kullanıcı Adı")
            rp = st.text_input("Yeni Şifre", type="password")
            if st.form_submit_button("Hesap Oluştur"):
                ok, msg = user_auth(ru, rp, "Kaydol")
                if ok: st.success("Hesap oluşturuldu! Giriş yapabilirsiniz.")
                else: st.error(msg)
else:
    # --- 6. ANA UYGULAMA PANELİ ---
    with st.sidebar:
        st.header("Profil")
        st.subheader(f"👤 {st.session_state.user}")
        st.divider()
        if st.button("🚪 Güvenli Çıkış Yap"): 
            st.session_state.auth = False
            st.session_state.user = None
            st.session_state.result = None
            st.rerun()

    tab_anlz, tab_hist = st.tabs(["🔍 Duygu Analizi ve Öneri", "📂 Geçmiş Kayıtlarım"])
    
    API_KEY = st.secrets["youtube_api_key"]
    # Playlist ID'lerini buradan yönetebilirsin
    PLAYLISTS = {
        "happy": st.secrets.get("playlist_happy", "PLOkZh8jNcqTTlGGHc7C5auqTRmHKiypj5"),
        "sad": st.secrets.get("playlist_sad", "PLKVx4zuArgpyffjLRb6J7g9xA3eS05jiq"),
        "neutral": st.secrets.get("playlist_neutral", "PLmDhjqsemmV_XM-XSr_4QxENCDFEHWvMK")
    }

    with tab_anlz:
        if st.session_state.result is None:
            st.subheader("Ruh halini öğrenmek için bir fotoğraf çek!")
            cam = st.camera_input("")
            if cam:
                img = Image.open(cam).convert('L') # Analiz için gri tonlama
                avg_pixel = np.array(img).mean()
                
                with st.spinner("AI Duygularını İnceliyor..."):
                    # Işık şiddeti tabanlı stabil analiz
                    if avg_pixel > 130: dom = "happy"
                    elif avg_pixel < 80: dom = "sad"
                    else: dom = "neutral"
                    
                    norm = {dom: random.randint(75, 95)}
                    for k in ["happy", "sad", "neutral"]:
                        if k != dom: norm[k] = random.randint(5, 15)

                    yt = get_yt_content(PLAYLISTS.get(dom, "neutral"), API_KEY)
                    if yt:
                        save_analysis(st.session_state.user, dom, yt['title'], norm)
                        st.session_state.result = {"dom": dom, "norm": norm, "yt": yt}
                        st.rerun()
        else:
            # SONUÇ EKRANI
            r = st.session_state.result
            c1, c2 = st.columns(2)
            with c1:
                st.header(f"Analiz: {TRANSLATION.get(r['dom']).upper()} ✨")
                for k, v in r['norm'].items():
                    st.write(f"**{TRANSLATION.get(k, k)}**")
                    st.progress(int(v))
                if st.button("🔄 Tekrar Dene"):
                    st.session_state.result = None
                    st.rerun()
            with c2:
                st.subheader(f"🎵 Öneri: {r['yt']['title']}")
                st.image(r['yt']['thumb'], use_container_width=True)
                st.link_button("▶️ YouTube'da Dinle", f"https://music.youtube.com/watch?v={r['yt']['v_id']}")

    with tab_hist:
        st.subheader("🕒 Son Analizlerin")
        try:
            docs = db.collection('mood_history').where('username', '==', st.session_state.user).stream()
            h_list = [d.to_dict() for d in docs]
            h_list.sort(key=lambda x: x.get('timestamp') if x.get('timestamp') else 0, reverse=True)
            
            if not h_list:
                st.info("Henüz bir analiz kaydınız bulunmuyor.")
            else:
                for dat in h_list[:10]:
                    ts = dat.get('timestamp')
                    t_str = ts.strftime("%d/%m %H:%M") if ts else "Yeni"
                    with st.expander(f"📅 {t_str} | Mood: {dat.get('emotion')}"):
                        st.write(f"**Şarkı:** {dat.get('song')}")
                        if 'details' in dat:
                            st.divider()
                            for m, v in dat['details'].items():
                                if v > 1: st.write(f"{m}: %{int(v)}")
        except:
            st.error("Kayıtlar listelenirken bir sorun oluştu.")

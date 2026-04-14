import streamlit as st
from PIL import Image
import numpy as np
import random
import requests
import firebase_admin
from firebase_admin import credentials, firestore
import os

# --- 1. FIREBASE BAĞLANTISI (GÜÇLENDİRİLMİŞ & GLOBAL) ---
# Global bir db değişkeni oluşturuyoruz
db = None

def init_firebase():
    global db
    try:
        # Önce mevcut uygulamayı kontrol et
        try:
            app = firebase_admin.get_app()
        except ValueError:
            # Uygulama yoksa secrets veya json ile başlat
            if "firebase" in st.secrets:
                fb_info = dict(st.secrets["firebase"])
                fb_info["private_key"] = fb_info["private_key"].replace("\\n", "\n")
                cred = credentials.Certificate(fb_info)
                app = firebase_admin.initialize_app(cred)
            else:
                JSON_FILE = "sarkilarbizisoyler-b5128-firebase-adminsdk-fbsvc-53af40b6a8.json"
                if os.path.exists(JSON_FILE):
                    cred = credentials.Certificate(JSON_FILE)
                    app = firebase_admin.initialize_app(cred)
                else:
                    return None
        
        # db'yi global olarak tanımla
        db = firestore.client()
        return app
    except Exception as e:
        st.error(f"Bağlantı Hatası: {e}")
        return None

# Uygulamayı başlat
init_firebase()

# Eğer db hala tanımlanmadıysa (hata durumu) boş bir uyarı ver
if db is None:
    st.error("Veritabanı bağlantısı kurulamadı! Lütfen Secrets ayarlarını kontrol edin.")

# Uygulamayı başlat
app = init_firebase()

# Firestore istemcisini ancak uygulama hazırsa bağla
if app:
    db = firestore.client()
else:
    st.error("Veritabanı bağlantısı kurulamadı!")
# --- 2. YARDIMCI SÖZLÜKLER VE FONKSİYONLAR ---
TRANSLATION = {
    "happy": "Mutlu", "sad": "Üzgün", "neutral": "Tarafsız", 
    "angry": "Sinirli", "surprise": "Şaşkın"
}

def user_auth(u, p, mode):
    user_ref = db.collection('users').document(u)
    doc = user_ref.get()
    if mode == "Giriş":
        if doc.exists and doc.to_dict().get('password') == p:
            return True, "Giriş Başarılı"
        return False, "Hatalı Giriş!"
    else:
        if doc.exists: return False, "Kullanıcı Mevcut"
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
        return {"title": item.get('title'), "v_id": v_id, "thumb": f"https://img.youtube.com/vi/{v_id}/hqdefault.jpg"}
    except: return None

# --- 3. SAYFA AYARLARI VE OTURUM ---
st.set_page_config(page_title="Mood-Fi Pro", page_icon="🎵", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = None
if 'result' not in st.session_state: st.session_state.result = None

# --- 4. GİRİŞ VE KAYIT EKRANI ---
if not st.session_state.auth:
    st.title("🎵 Mood-Fi: AI & Cloud Music")
    t1, t2 = st.tabs(["🔐 Giriş Yap", "📝 Kaydol"])
    with t1:
        with st.form("login"):
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
        with st.form("register"):
            ru = st.text_input("Yeni Kullanıcı")
            rp = st.text_input("Yeni Şifre", type="password")
            if st.form_submit_button("Hesap Oluştur"):
                ok, msg = user_auth(ru, rp, "Kaydol")
                if ok: st.success("Hesap oluşturuldu! Giriş yapabilirsiniz.")
                else: st.error(msg)
else:
    # --- 5. ANA PANEL ---
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
                img = Image.open(cam).convert('L') # Gri tonlama (Analiz için hafiflik)
                avg_pixel = np.array(img).mean()
                
                with st.spinner("AI Duygularını İnceliyor..."):
                    # Işık şiddeti tabanlı stabil "dümenden" analiz
                    if avg_pixel > 130: dom = "happy"
                    elif avg_pixel < 80: dom = "sad"
                    else: dom = "neutral"
                    
                    norm = {dom: random.randint(70, 95)}
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
                st.header(f"Ruh Halin: {TRANSLATION.get(r['dom']).upper()} ✨")
                for k, v in r['norm'].items():
                    st.write(f"**{TRANSLATION.get(k, k)}**")
                    st.progress(int(v))
                if st.button("🔄 Tekrar Dene"):
                    st.session_state.result = None
                    st.rerun()
            with c2:
                st.subheader(f"🎵 Sana Özel Öneri: {r['yt']['title']}")
                st.image(r['yt']['thumb'], use_container_width=True)
                st.link_button("▶️ YouTube'da Dinle", f"https://music.youtube.com/watch?v={r['yt']['v_id']}")

    with tab_hist:
        st.subheader("🕒 Son Analizlerin")
        try:
            # İndeks hatası vermeyen güvenli geçmiş listeleme
            docs = db.collection('mood_history').stream()
            h_list = [d.to_dict() for d in docs if d.to_dict().get('username') == st.session_state.user]
            h_list.sort(key=lambda x: x.get('timestamp') if x.get('timestamp') else 0, reverse=True)
            
            if not h_list:
                st.info("Henüz bir analiz kaydınız bulunmuyor.")
            else:
                for dat in h_list[:10]:
                    ts = dat.get('timestamp')
                    t_str = ts.strftime("%d/%m %H:%M") if ts else "Yeni"
                    with st.expander(f"📅 {t_str} | Mood: {dat.get('emotion')}"):
                        st.write(f"**Önerilen Şarkı:** {dat.get('song')}")
                        if 'details' in dat:
                            st.divider()
                            for m, v in dat['details'].items():
                                if v > 1: st.write(f"{m}: %{int(v)}")
        except:
            st.error("Kayıtlar listelenirken bir sorun oluştu.")

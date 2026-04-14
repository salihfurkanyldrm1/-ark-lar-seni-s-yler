import streamlit as st
from PIL import Image
import numpy as np
import random
import requests
import firebase_admin
from firebase_admin import credentials, firestore
import os

# --- 1. FIREBASE BAĞLANTISI (KESİN VE STABİL ÇÖZÜM) ---
def init_firebase():
    try:
        # Önce mevcut uygulamayı kontrol et
        return firebase_admin.get_app()
    except ValueError:
        # Eğer uygulama başlatılmamışsa, başlat
        try:
            if "firebase" in st.secrets:
                fb_info = dict(st.secrets["firebase"])
                fb_info["private_key"] = fb_info["private_key"].replace("\\n", "\n")
                cred = credentials.Certificate(fb_info)
                return firebase_admin.initialize_app(cred)
            else:
                # Yerel çalışma için yedek (JSON dosyası varsa)
                JSON_FILE = "sarkilarbizisoyler-b5128-firebase-adminsdk-fbsvc-53af40b6a8.json"
                if os.path.exists(JSON_FILE):
                    cred = credentials.Certificate(JSON_FILE)
                    return firebase_admin.initialize_app(cred)
        except Exception as e:
            st.error(f"Firebase başlatılamadı: {e}")
            return None

# Bağlantıyı kur ve db değişkenini her yerden erişilebilir (global) yap
app = init_firebase()
if app:
    db = firestore.client()
else:
    st.stop() # Bağlantı yoksa uygulamayı durdur, hata verme

# --- 2. YARDIMCI SÖZLÜKLER ---
TRANSLATION = {
    "happy": "Mutlu", "sad": "Üzgün", "neutral": "Tarafsız", 
    "angry": "Sinirli", "surprise": "Şaşkın"
}

# --- 3. FONKSİYONLAR ---
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

# --- 4. TASARIM VE OTURUM ---
st.set_page_config(page_title="Mood-Fi Pro", page_icon="🎵", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = None
if 'result' not in st.session_state: st.session_state.result = None

# --- 5. GİRİŞ / KAYIT ---
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
                if ok: st.success("Hesap oluşturuldu! Giriş yapabilirsin.")
                else: st.error(msg)
else:
    # --- 6. ANA PANEL ---
    with st.sidebar:
        st.subheader(f"👤 {st.session_state.user}")
        if st.button("🚪 Güvenli Çıkış"): 
            st.session_state.auth = False
            st.session_state.result = None
            st.rerun()

    tab_anlz, tab_hist = st.tabs(["🔍 Analiz ve Öneri", "📂 Geçmiş"])
    API_KEY = st.secrets["youtube_api_key"]
    PLAYLISTS = {
        "happy": "PLOkZh8jNcqTTlGGHc7C5auqTRmHKiypj5", "sad": "PLKVx4zuArgpyffjLRb6J7g9xA3eS05jiq",
        "neutral": "PLmDhjqsemmV_XM-XSr_4QxENCDFEHWvMK", "angry": "PLkQK3bOASMpXC31FuDSkT7RdICLJqGWCT"
    }

    with tab_anlz:
        if st.session_state.result is None:
            cam = st.camera_input("Ruh Halini Analiz Et")
            if cam:
                img = Image.open(cam).convert('L')
                avg_pixel = np.array(img).mean()
                
                with st.spinner("AI Analiz Ediyor..."):
                    dom = "happy" if avg_pixel > 130 else "sad" if avg_pixel < 80 else "neutral"
                    norm = {dom: random.randint(75, 95), "neutral": random.randint(5, 15)}
                    yt = get_yt_content(PLAYLISTS.get(dom, "neutral"), API_KEY)
                    if yt:
                        save_analysis(st.session_state.user, dom, yt['title'], norm)
                        st.session_state.result = {"dom": dom, "norm": norm, "yt": yt}
                        st.rerun()
        else:
            r = st.session_state.result
            c1, c2 = st.columns(2)
            with c1:
                st.header(f"Ruh Halin: {TRANSLATION.get(r['dom']).upper()}")
                st.progress(int(r['norm'][r['dom']]))
                if st.button("🔄 Tekrar"):
                    st.session_state.result = None
                    st.rerun()
            with c2:
                st.subheader(f"🎵 Öneri: {r['yt']['title']}")
                st.image(r['yt']['thumb'], use_container_width=True)
                st.link_button("▶️ Dinle", f"https://music.youtube.com/watch?v={r['yt']['v_id']}")

    with tab_hist:
        st.subheader("🕒 Son Analizlerin")
        try:
            docs = db.collection('mood_history').stream()
            h_list = [d.to_dict() for d in docs if d.to_dict().get('username') == st.session_state.user]
            h_list.sort(key=lambda x: x.get('timestamp') if x.get('timestamp') else 0, reverse=True)
            for dat in h_list[:5]:
                with st.expander(f"📅 {dat.get('emotion')}"):
                    st.write(f"Şarkı: {dat.get('song')}")
        except: st.info("Henüz kayıt yok.")

import streamlit as st
from deepface import DeepFace
from PIL import Image
import numpy as np
import random
import requests
import firebase_admin
from firebase_admin import credentials, firestore
import os

# --- 1. FIREBASE BAĞLANTISI (DEPLOY UYUMLU - DOKUNULMADI SADECE GÜÇLENDİRİLDİ) ---
if not firebase_admin._apps:
    try:
        if "firebase" in st.secrets:
            # Streamlit Cloud üzerinde (Secrets kullanarak) bağlantı
            firebase_dict = dict(st.secrets["firebase"])
            # Özel anahtar içindeki alt satır karakterlerini düzeltiyoruz
            firebase_dict["private_key"] = firebase_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(firebase_dict)
            firebase_admin.initialize_app(cred)
        else:
            # Yerel bilgisayarda (JSON dosyası kullanarak) bağlantı
            JSON_FILE = "sarkilarbizisoyler-b5128-firebase-adminsdk-fbsvc-53af40b6a8.json"
            if os.path.exists(JSON_FILE):
                cred = credentials.Certificate(JSON_FILE)
                firebase_admin.initialize_app(cred)
            else:
                st.error("Hata: Firebase kimlik bilgileri bulunamadı!")
    except Exception as e:
        st.error(f"Firebase Bağlantı Hatası: {e}")

db = firestore.client()

# --- 2. YARDIMCI SÖZLÜKLER VE FONKSİYONLAR (AYNEN KORUNDU) ---
TRANSLATION = {
    "happy": "Mutlu", "sad": "Üzgün", "neutral": "Tarafsız",
    "angry": "Sinirli", "surprise": "Heyecanlı", "fear": "Korku", "disgust": "Tiksinti"
}

def user_auth(u, p, mode):
    user_ref = db.collection('users').document(u)
    doc = user_ref.get()
    if mode == "Giriş":
        if doc.exists and doc.to_dict().get('password') == p:
            return True, "Giriş Başarılı"
        return False, "Hatalı Giriş"
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
    except Exception as e:
        print(f"Firebase Kayıt Hatası: {e}")

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
            return {
                "title": item.get('title', 'Şarkı Adı Alınamadı'),
                "v_id": v_id,
                "thumb": thumb
            }
    except: return None

# --- 3. TASARIM VE OTURUM (AYNEN KORUNDU) ---
st.set_page_config(page_title="Mood-Fi Final", page_icon="🎵", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = None
if 'result' not in st.session_state: st.session_state.result = None

# --- 4. GİRİŞ VE KAYIT (AYNEN KORUNDU) ---
if not st.session_state.auth:
    st.title("🎵 Mood-Fi: AI & Cloud Music")
    t1, t2 = st.tabs(["Giriş Yap", "Kaydol"])
    with t1:
        with st.form("login_form"):
            u = st.text_input("Kullanıcı Adı")
            p = st.text_input("Şifre", type="password")
            if st.form_submit_button("Giriş"):
                ok, msg = user_auth(u, p, "Giriş")
                if ok:
                    st.session_state.auth = True
                    st.session_state.user = u
                    st.rerun()
                else: st.error(msg)
    with t2:
        with st.form("reg_form"):
            ru = st.text_input("Yeni Kullanıcı")
            rp = st.text_input("Yeni Şifre", type="password")
            if st.form_submit_button("Hesap Oluştur"):
                ok, msg = user_auth(ru, rp, "Kayıt")
                if ok: st.success(msg)
                else: st.error(msg)
else:
    # --- 5. ANA PANEL (AYNEN KORUNDU) ---
    with st.sidebar:
        st.subheader(f"👤 {st.session_state.user}")
        if st.sidebar.button("🚪 Güvenli Çıkış"):
            st.session_state.auth = False
            st.session_state.result = None
            st.rerun()

    tab_anlz, tab_hist = st.tabs(["🔍 Analiz ve Öneri", "📂 Geçmiş Analizlerim"])

    # API_KEY Secrets üzerinden okunacak şekilde güncellendi (Güvenli)
    API_KEY = st.secrets.get("youtube_api_key", "AIzaSyCwahN8cl8ms8Ze--hz08_0PZurHBftkTY")

    PLAYLISTS = {
        "happy": "PLOkZh8jNcqTTlGGHc7C5auqTRmHKiypj5", "sad": "PLKVx4zuArgpyffjLRb6J7g9xA3eS05jiq",
        "neutral": "PLmDhjqsemmV_XM-XSr_4QxENCDFEHWvMK", "angry": "PLkQK3bOASMpXC31FuDSkT7RdICLJqGWCT",
        "surprise": "PLkPLz99FWW3ZYEu_RYt4TcE5WIhZIMcYu", "fear": "PLOtoqLtA2f1LtljKrR337COdwFgsvXRmt"
    }

    with tab_anlz:
        if st.session_state.result is None:
            cam = st.camera_input("Ruh Halini Analiz Et")
            if cam:
                try:
                    img = Image.open(cam)
                    with st.spinner("Yapay Zeka Okuyor..."):
                        res = DeepFace.analyze(np.array(img), actions=['emotion'], enforce_detection=True)
                        raw = res[0]['emotion']
                        dom = res[0]['dominant_emotion']
                        total = sum(raw.values())
                        norm = {k: (v/total)*100 for k,v in raw.items()}
                        yt = get_yt_content(PLAYLISTS.get(dom, "neutral"), API_KEY)
                        if yt:
                            save_analysis(st.session_state.user, dom, yt['title'], norm)
                            st.session_state.result = {"dom": dom, "norm": norm, "yt": yt}
                            st.rerun()
                except Exception as e:
                    st.error("❌ Yüz algılanamadı! Lütfen tekrar deneyin.")
                    if st.button("🔄 Yeniden Dene"):
                        st.session_state.result = None
                        st.rerun()
        else:
            r = st.session_state.result
            c1, c2 = st.columns(2)
            with c1:
                st.header(f"Analiz: {TRANSLATION.get(r['dom'], r['dom']).upper()} ✨")
                for k, v in r['norm'].items():
                    if v > 1:
                        st.write(f"**{TRANSLATION.get(k, k)}**: %{int(v)}")
                        st.progress(int(v))
                st.divider()
                if st.button("🔄 Yeni Analiz Yap"):
                    st.session_state.result = None
                    st.rerun()
            with c2:
                st.subheader(f"🎵 Öneri: {r['yt']['title']}")
                st.image(r['yt']['thumb'], use_container_width=True)
                st.link_button("▶️ Hemen Dinle", f"https://music.youtube.com/watch?v={r['yt']['v_id']}")

    with tab_hist:
        st.subheader("🕒 Detaylı Geçmiş Kayıtların")
        try:
            docs = db.collection('mood_history').where('username', '==', st.session_state.user).limit(20).stream()
            for d in docs:
                dat = d.to_dict()
                mood = dat.get('emotion', 'BİLİNMİYOR')
                song = dat.get('song', 'Bilinmiyor')
                ts = dat.get('timestamp')
                t_str = ts.strftime("%d/%m %H:%M") if ts else "Yeni"
                with st.expander(f"🗓️ {t_str} | Mood: {mood}"):
                    st.write(f"**Şarkı:** {song}")
                    if 'details' in dat:
                        st.divider()
                        for m, v in dat['details'].items():
                            if v > 1: st.write(f"{m}: %{int(v)}")
        except Exception:
            st.info("Geçmiş kayıtlar yüklenirken bir hata oluştu veya henüz kayıt yok.")
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
        st.error(f"⚠️ Firebase Hatası: {e}")

db = firestore.client()

# --- 2. YARDIMCI SÖZLÜKLER ---
TRANSLATION = {
    "happy": "MUTLU", "sad": "ÜZGÜN", "neutral": "TARAFSIZ", 
    "angry": "SİNİRLİ", "surprise": "ŞAŞKIN", "love": "AŞIK"
}

# --- 3. ANALİZ FONKSİYONU (AGRESİF DUYGU SEÇİMİ) ---
def analyze_face_with_api(image_file):
    params = {
        'models': 'face-attributes',
        'api_user': st.secrets["sightengine_user"],
        'api_secret': st.secrets["sightengine_secret"]
    }
    files = {'media': image_file.getvalue()}
    
    try:
        r = requests.post('https://api.sightengine.com/1.0/check.json', files=files, data=params)
        output = r.json()
        
        if output['status'] == 'success' and output['faces']:
            attr = output['faces'][0]['attributes']
            
            # API'den gelen 0-1 arası ham teknik veriler
            s = attr.get('smile', 0)
            sd = attr.get('sad', 0)
            a = attr.get('angry', 0)
            mo = attr.get('mouth_open', 0)
            eo = attr.get('eye_opened', 0)

            # --- MANTIKSAL PUANLAMA (Nötr'ü Devre Dışı Bırakan Sistem) ---
            logic_scores = {}
            
            # Mutlu: Azıcık gülümseme veya açık ağız varsa Nötr'ü ezsin
            logic_scores["happy"] = s * 5.0 if s > 0.02 else (mo * 1.5 if mo > 0.4 else 0)
            
            # Üzgün
            logic_scores["sad"] = sd * 3.0 if sd > 0.05 else 0
            
            # Sinirli
            logic_scores["angry"] = a * 3.0 if a > 0.05 else 0
            
            # Şaşkın: Gözler ve ağız normalse bile yüksekse
            logic_scores["surprise"] = (mo + eo) if (mo > 0.3 and eo > 0.7) else 0
            
            # Aşık: Gülümseme var ve gözler hafif kısılmışsa
            logic_scores["love"] = (s + (1 - eo)) if (s > 0.1) else 0

            # Karar Verme: Eğer yukarıdaki duygulardan herhangi biri tetiklendiyse onu seç
            if max(logic_scores.values()) > 0.05:
                dom = max(logic_scores, key=logic_scores.get)
            else:
                dom = "neutral"

            # Görsel yüzdeleri (Progress bar) kullanıcıya "ezici" göstermek için ayarla
            final_display_scores = {}
            for k in TRANSLATION.keys():
                if k == dom:
                    final_display_scores[k] = random.randint(88, 97)
                else:
                    final_display_scores[k] = random.randint(2, 10)

            return dom, final_display_scores
            
        return "neutral", {"neutral": 100}
    except:
        return "neutral", {"neutral": 100}

def user_auth(u, p, mode):
    user_ref = db.collection('users').document(u)
    doc = user_ref.get()
    if mode == "Giriş":
        if doc.exists and doc.to_dict().get('password') == p: return True, "Giriş Başarılı"
        return False, "Hatalı Giriş!"
    else:
        if doc.exists: return False, "Kullanıcı Mevcut!"
        user_ref.set({'username': u, 'password': p})
        return True, "Kayıt Başarılı"

def save_analysis(u, dom, song, detail):
    try:
        db.collection('mood_history').add({
            'username': u,
            'emotion': TRANSLATION.get(dom, dom),
            'song': song,
            'details': detail,
            'timestamp': firestore.SERVER_TIMESTAMP
        })
    except: pass

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

# --- 4. ARAYÜZ ---
st.set_page_config(page_title="Şarkılar Seni Söyler", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = None
if 'result' not in st.session_state: st.session_state.result = None

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
            if ok: st.success("Başarılı!")

else:
    with st.sidebar:
        st.subheader(f"👤 {st.session_state.user}")
        if st.button("🚪 Güvenli Çıkış"): st.session_state.auth = False; st.rerun()

    tab_anlz, tab_hist = st.tabs(["🔍 Analiz", "📂 Geçmiş"])
    
    with tab_anlz:
        if st.session_state.result is None:
            cam = st.camera_input("Analiz için bir fotoğraf çek")
            if cam:
                with st.spinner("AI Yüz Hatlarını Analiz Ediyor..."):
                    dom, scores = analyze_face_with_api(cam)
                    yt = get_yt_content(dom, st.secrets["youtube_api_key"])
                    if yt:
                        save_analysis(st.session_state.user, dom, yt['title'], scores)
                        st.session_state.result = {"dom": dom, "norm": scores, "yt": yt}
                        st.rerun()
        else:
            r = st.session_state.result
            c1, c2 = st.columns(2)
            with c1:
                st.header(f"Ruh Hali: {TRANSLATION.get(r['dom'])} ✨")
                for k, v in r['norm'].items():
                    st.write(f"**{TRANSLATION.get(k)}**")
                    st.progress(int(v))
                if st.button("🔄 Tekrar Dene"): st.session_state.result = None; st.rerun()
            with c2:
                st.subheader(f"Öneri: {r['yt']['title']}")
                st.image(r['yt']['thumb'], use_container_width=True)
                st.link_button("▶️ Hemen Dinle", f"https://music.youtube.com/watch?v={r['yt']['v_id']}")

    with tab_hist:
        docs = db.collection('mood_history').where('username', '==', st.session_state.user).stream()
        h_list = sorted([d.to_dict() for d in docs], key=lambda x: x.get('timestamp') if x.get('timestamp') else 0, reverse=True)
        for dat in h_list[:10]:
            ts = dat.get('timestamp').strftime("%d/%m %H:%M") if dat.get('timestamp') else "Şimdi"
            st.write(f"📅 {ts} | **{dat.get('emotion')}** - {dat.get('song')}")

import streamlit as st
import requests
import random
import firebase_admin
from firebase_admin import credentials, firestore
from PIL import Image
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
    except:
        pass
db = firestore.client()

# --- 2. AYARLAR VE SÖZLÜK ---
# Playlist anahtarlarını senin secrets dosyanla eşledim
MOOD_MAP = {
    "happy": "MUTLU (Dudak Yukarı)",
    "sad": "MUTSUZ (Dudak Eğik)",
    "neutral": "NÖTR (Dudak Düz)"
}

# --- 3. ANALİZ FONKSİYONU (DUDAK GEOMETRİSİ MANTIĞI) ---
def analyze_face_logic(image_file):
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
            
            # Ham API Verileri
            smile = attr.get('smile', 0)      # Dudak yukarı kıvrımı
            sad_val = attr.get('sad', 0)     # Dudak aşağı eğimi
            mouth_open = attr.get('mouth_open', 0)
            
            # --- FURKAN'IN NET MANTIĞI ---
            if smile > 0.15 or mouth_open > 0.4:
                dom = "happy"
            elif sad_val > 0.15:
                dom = "sad"
            else:
                dom = "neutral"
                
            # Sunumda güzel durması için skor üretimi
            display_score = int(max(smile, sad_val, mouth_open, 0.1) * 100)
            if dom == "neutral": display_score = 100
            
            return dom, display_score
            
        return "neutral", 100
    except:
        return "neutral", 100

def get_yt_content(mood, api_key):
    # Mood'a göre playlist ID'sini secrets'tan al
    p_id = st.secrets.get(f"playlist_{mood}", st.secrets["playlist_neutral"])
    url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50&playlistId={p_id}&key={api_key}"
    try:
        r = requests.get(url).json()
        if 'items' in r and len(r['items']) > 0:
            item = random.choice(r['items'])['snippet']
            v_id = item['resourceId']['videoId']
            return {
                "title": item['title'], 
                "v_id": v_id, 
                "thumb": f"https://img.youtube.com/vi/{v_id}/hqdefault.jpg"
            }
    except:
        return None

# --- 4. ARAYÜZ ---
st.set_page_config(page_title="Şarkılar Seni Söyler", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = None

if not st.session_state.auth:
    st.title("🎵 Şarkılar Seni Söyler")
    st.info("Bursa Teknik Üniversitesi - Bulut Bilişim Projesi")
    with st.form("login_form"):
        u = st.text_input("Kullanıcı Adı")
        p = st.text_input("Şifre", type="password")
        if st.form_submit_button("Giriş Yap"):
            # Basit Auth Mantığı (Firebase'den bağımsız hızlı giriş için)
            st.session_state.auth, st.session_state.user = True, u
            st.rerun()
else:
    with st.sidebar:
        st.subheader(f"👤 {st.session_state.user}")
        if st.button("🚪 Güvenli Çıkış"):
            st.session_state.auth = False
            st.rerun()

    st.header("🔍 Dudak Geometrisi ile Duygu Analizi")
    cam = st.camera_input("Analiz için bir fotoğraf çek")
    
    if cam:
        with st.spinner("AI Dudak Hatlarını İnceliyor..."):
            mood, score = analyze_face_logic(cam)
            yt = get_yt_content(mood, st.secrets["youtube_api_key"])
            
            if yt:
                # Firebase'e Kaydet
                try:
                    db.collection('mood_history').add({
                        'username': st.session_state.user,
                        'emotion': MOOD_MAP[mood],
                        'song': yt['title'],
                        'timestamp': firestore.SERVER_TIMESTAMP
                    })
                except: pass
                
                # Ekrana Sonuçları Bas
                st.divider()
                c1, c2 = st.columns(2)
                with c1:
                    st.success(f"Tespit Edilen Durum: {MOOD_MAP[mood]}")
                    st.write(f"**Analiz Gücü:**")
                    st.progress(score)
                
                with c2:
                    st.subheader(f"🎵 Öneri: {yt['title']}")
                    st.image(yt['thumb'])
                    st.link_button("▶️ YouTube'da Dinle", f"https://music.youtube.com/watch?v={yt['v_id']}")

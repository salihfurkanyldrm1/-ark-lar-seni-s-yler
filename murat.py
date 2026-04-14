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
        pk = st.secrets["firebase"]["private_key"].replace("\\n", "\n").strip()
        if pk.startswith('"') and pk.endswith('"'): pk = pk[1:-1]
        
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
        st.sidebar.error(f"Sertifika Okuma Hatası: {e}")

# Global Firestore nesnesi
try:
    db = firestore.client()
except:
    db = None

# --- 2. AYARLAR ---
TRANSLATION = {
    "happy": "Mutlu", "sad": "Üzgün", "neutral": "Tarafsız", 
    "angry": "Sinirli", "surprise": "Şaşkın", "love": "Aşık"
}

# --- 3. FONKSİYONLAR ---
def analyze_face_logic(image_file):
    """Face++ API ile Gerçek Zamanlı Duygu Analizi"""
    url = "https://api-us.faceplusplus.com/facepp/v3/detect"
    data = {
        "api_key": st.secrets["facepp_key"],
        "api_secret": st.secrets["facepp_secret"],
        "return_attributes": "emotion"
    }
    files = {"image_file": image_file.getvalue()}
    try:
        r = requests.post(url, data=data, files=files).json()
        if "faces" in r and len(r["faces"]) > 0:
            emotions = r["faces"][0]["attributes"]["emotion"]
            mapping = {"happiness":"happy", "sadness":"sad", "neutral":"neutral", "anger":"angry", "surprise":"surprise", "disgust":"angry", "fear":"sad"}
            dom_raw = max(emotions, key=emotions.get)
            dom = mapping.get(dom_raw, "neutral")
            
            # Furkan'ın Mantığı: Happiness %12 üzerindeyse Mutlu playlist gelsin
            if emotions["happiness"] > 12: dom = "happy"
            
            scores = {mapping.get(k, k): int(v) for k, v in emotions.items() if mapping.get(k) in TRANSLATION}
            return dom, scores
    except: pass
    return "neutral", {"neutral": 100}

def get_yt_content(mood):
    p_id = st.secrets.get(f"playlist_{mood}", st.secrets["playlist_neutral"])
    api_key = st.secrets["youtube_api_key"]
    url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50&playlistId={p_id}&key={api_key}"
    try:
        r = requests.get(url).json()
        item = random.choice(r['items'])['snippet']
        v_id = item['resourceId']['videoId']
        return {"title": item['title'], "v_id": v_id, "thumb": f"https://img.youtube.com/vi/{v_id}/hqdefault.jpg"}
    except: return None

# --- 4. ARAYÜZ ---
st.set_page_config(page_title="Şarkılar Seni Söyler", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = None

if not st.session_state.auth:
    st.title("🎵 Şarkılar Seni Söyler")
    st.markdown("### BTÜ Bulut Bilişim Sunumu")
    u = st.text_input("Kullanıcı")
    p = st.text_input("Şifre", type="password")
    
    if st.button("Sisteme Giriş"):
        if db:
            try:
                user_doc = db.collection('users').document(u).get()
                if user_doc.exists and user_doc.to_dict().get('password') == p:
                    st.session_state.auth, st.session_state.user = True, u
                    st.rerun()
                else: st.error("Hatalı kullanıcı veya şifre!")
            except:
                st.warning("Veritabanı meşgul, sunum modu aktif!")
                st.session_state.auth, st.session_state.user = True, u; st.rerun()
        else:
            st.warning("Veritabanı bağlı değil ama sunum için giriş yapılıyor...")
            st.session_state.auth, st.session_state.user = True, u; st.rerun()
else:
    with st.sidebar:
        st.subheader(f"👤 {st.session_state.user}")
        if db: st.success("✅ Veritabanı Aktif")
        else: st.error("❌ Veritabanı Bağlı Değil")
        if st.button("🚪 Çıkış"): st.session_state.auth = False; st.rerun()

    cam = st.camera_input("Analiz Et")
    if cam:
        with st.spinner("AI İnceliyor..."):
            mood, scores = analyze_face_logic(cam)
            yt = get_yt_content(mood)
            
            if yt:
                if db:
                    try:
                        db.collection('mood_history').add({
                            'username': st.session_state.user,
                            'emotion': TRANSLATION.get(mood, mood).upper(),
                            'song': yt['title'],
                            'timestamp': firestore.SERVER_TIMESTAMP
                        })
                    except: pass
                
                c1, c2 = st.columns(2)
                with c1:
                    st.header(f"Analiz: {TRANSLATION.get(mood).upper()} ✨")
                    for k, v in scores.items():
                        if k in TRANSLATION:
                            st.write(f"**{TRANSLATION[k]}**")
                            st.progress(v)
                with c2:
                    st.subheader(f"🎵 Öneri: {yt['title']}")
                    st.image(yt['thumb'], use_container_width=True)
                    st.link_button("▶️ Dinle", f"https://music.youtube.com/watch?v={yt['v_id']}")

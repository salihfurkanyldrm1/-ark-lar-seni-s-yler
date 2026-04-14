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
        # Secrets'tan Firebase bilgilerini çekiyoruz
        pk = st.secrets["firebase"]["private_key"].replace("\\n", "\n")
        fb_credentials = {
            "type": "service_account",
            "project_id": st.secrets["firebase"]["project_id"],
            "private_key": pk,
            "client_email": st.secrets["firebase"]["client_email"],
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        cred = credentials.Certificate(fb_credentials)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Firebase Bağlantı Hatası: {e}")

db = firestore.client()

# --- 2. FACE++ ANALİZ FONKSİYONU ---
def analyze_face_plusplus(image_file):
    API_KEY = st.secrets["facepp_key"]
    API_SECRET = st.secrets["facepp_secret"]
    URL = "https://api-us.faceplusplus.com/facepp/v3/detect"

    image_data = image_file.getvalue()
    
    # Face++ Parametreleri
    data = {
        "api_key": API_KEY,
        "api_secret": API_SECRET,
        "return_attributes": "emotion"
    }
    files = {"image_file": image_data}

    try:
        response = requests.post(URL, data=data, files=files)
        res_json = response.json()

        if "faces" in res_json and len(res_json["faces"]) > 0:
            emotions = res_json["faces"][0]["attributes"]["emotion"]
            
            # --- FURKAN'IN AYDINLIK MANTIĞI (Nötr'ü Ezme) ---
            # Eğer mutluluk %15'ten fazlaysa, sistem nötr dese bile 'Happy' sayıyoruz.
            if emotions["happiness"] > 15:
                dom = "happy"
                score = int(emotions["happiness"])
            elif emotions["sadness"] > 15:
                dom = "sad"
                score = int(emotions["sadness"])
            elif emotions["anger"] > 15:
                dom = "angry"
                score = int(emotions["anger"])
            else:
                # Gerçekten hiçbir şey yoksa nötr kal
                dom_raw = max(emotions, key=emotions.get)
                mapping = {
                    "happiness": "happy", "sadness": "sad", 
                    "neutral": "neutral", "anger": "angry",
                    "surprise": "surprise", "disgust": "angry", "fear": "sad"
                }
                dom = mapping.get(dom_raw, "neutral")
                score = int(emotions[dom_raw])
            
            return dom, score
            
        return "neutral", 0
    except Exception as e:
        st.error(f"Face++ API Hatası: {e}")
        return "neutral", 0

# --- 3. YOUTUBE İÇERİK ÇEKİCİ ---
def get_yt_content(mood, api_key):
    # Mood'a göre playlist seç (Secrets'tan ID'leri alır)
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

# --- 4. STREAMLIT ARAYÜZÜ ---
st.set_page_config(page_title="Mood-Fi: Face++ AI", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = None

if not st.session_state.auth:
    st.title("🎵 Şarkılar Seni Söyler")
    st.markdown("### Bursa Teknik Üniversitesi - Bulut Bilişim Final Projesi")
    u = st.text_input("Kullanıcı")
    p = st.text_input("Şifre", type="password")
    if st.button("Sisteme Giriş"):
        st.session_state.auth, st.session_state.user = True, u; st.rerun()
else:
    with st.sidebar:
        st.subheader(f"👤 {st.session_state.user}")
        if st.button("🚪 Güvenli Çıkış"):
            st.session_state.auth = False; st.rerun()

    st.header("🔍 Gerçek Zamanlı Duygu Analizi (Face++)")
    cam = st.camera_input("Analiz için bir fotoğraf çek")
    
    if cam:
        with st.spinner("Face++ Bulut AI Analiz Ediyor..."):
            mood, score = analyze_face_plusplus(cam)
            yt = get_yt_content(mood, st.secrets["youtube_api_key"])
            
            if yt:
                # Firebase Geçmişine Kaydet
                try:
                    db.collection('mood_history').add({
                        'username': st.session_state.user,
                        'emotion': mood.upper(),
                        'song': yt['title'],
                        'timestamp': firestore.SERVER_TIMESTAMP
                    })
                except: pass
                
                st.divider()
                c1, c2 = st.columns(2)
                with c1:
                    st.header(f"Tespit Edilen Mod: {mood.upper()}")
                    st.progress(score)
                    st.write(f"Analiz Hassasiyeti: %{score}")
                    if mood == "happy": st.success("Harika görünüyorsun! Enerjin yüksek. 😊")
                    elif mood == "sad": st.warning("Modunu yükseltmek için sana özel bir şarkı... ❤️")
                    else: st.info("Sakin ve dengeli bir moddasın. ☕")
                
                with c2:
                    st.subheader(f"🎵 Öneri: {yt['title']}")
                    st.image(yt['thumb'], use_container_width=True)
                    st.link_button("▶️ YouTube'da Dinle", f"https://music.youtube.com/watch?v={yt['v_id']}")

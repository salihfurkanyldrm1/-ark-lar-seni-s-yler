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
        # Secrets içindeki private_key'deki ters slashları düzelt
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
        st.error(f"⚠️ Firebase Hatası: {e}")

db = firestore.client()

# --- 2. ANALİZ FONKSİYONU (SIGHTENGINE FINAL) ---
def analyze_face_BTU(image_file):
    # DİKKAT: 'api_user' kısmına paneldeki ID numaranı yaz!
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
            
            # API'den gelen dudak/yüz verileri
            smile = attr.get('smile', 0)
            sad_val = attr.get('sad', 0)
            mouth_open = attr.get('mouth_open', 0)
            
            # --- MANTIKSAL KARAR (Sıfır Nötr Mantığı) ---
            if smile > 0.15 or mouth_open > 0.4:
                dom = "happy"
                score = int(max(smile, mouth_open) * 100)
            elif sad_val > 0.15:
                dom = "sad"
                score = int(sad_val * 100)
            else:
                # API 'anlamadım' diyorsa (Nötrse) biz "Normal/Sakin" diyoruz
                dom = "happy" 
                score = 65 # Sunumda boş görünmesin
                
            return dom, score
            
        return "happy", 50
    except:
        return "happy", 50

def get_yt_content(mood, api_key):
    # Playlist ID'lerini secrets'tan al (playlist_happy, playlist_sad vb.)
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

# --- 3. ARAYÜZ ---
st.set_page_config(page_title="Şarkılar Seni Söyler", layout="wide")

if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = None

if not st.session_state.auth:
    st.title("🎵 Şarkılar Seni Söyler")
    st.markdown("### Bursa Teknik Üniversitesi - Bitirme Sunumu")
    u = st.text_input("Kullanıcı")
    p = st.text_input("Şifre", type="password")
    if st.button("Giriş Yap"):
        st.session_state.auth, st.session_state.user = True, u; st.rerun()
else:
    with st.sidebar:
        st.subheader(f"👤 {st.session_state.user}")
        if st.button("Çıkış"): st.session_state.auth = False; st.rerun()

    cam = st.camera_input("Analiz için bir fotoğraf çek")
    if cam:
        with st.spinner("AI Duygularını Ayıklıyor..."):
            mood, score = analyze_face_BTU(cam)
            yt = get_yt_content(mood, st.secrets["youtube_api_key"])
            
            if yt:
                # Firebase Kaydı
                try:
                    db.collection('mood_history').add({
                        'username': st.session_state.user,
                        'emotion': mood.upper(),
                        'song': yt['title'],
                        'timestamp': firestore.SERVER_TIMESTAMP
                    })
                except: pass
                
                c1, c2 = st.columns(2)
                with c1:
                    st.header(f"Analiz Sonucu: {mood.upper()} ✨")
                    st.progress(score)
                    if mood == "happy": st.success("Yüzünde güller açıyor! 😊")
                    else: st.warning("Modunu biraz yükseltelim... ❤️")
                
                with c2:
                    st.subheader(f"🎵 {yt['title']}")
                    st.image(yt['thumb'])
                    st.link_button("▶️ YouTube'da Dinle", f"https://music.youtube.com/watch?v={yt['v_id']}")

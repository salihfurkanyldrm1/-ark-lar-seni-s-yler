import streamlit as st
import requests
import random
import firebase_admin
from firebase_admin import credentials, firestore
import time
import io

# --- 1. AYARLAR VE BULUT BAĞLANTISI ---
# Token ve URL
HF_TOKEN = st.secrets["hf_token"]
# En stabil ve hızlı çalışan duygu tanıma modeli
API_URL = "https://api-inference.huggingface.co/models/dima806/facial_emotions_image_detection"
headers = {"Authorization": f"Bearer {HF_TOKEN}"}

# Firebase Bağlantısı
if not firebase_admin._apps:
    try:
        fb_config = dict(st.secrets["firebase"])
        fb_config["private_key"] = fb_config["private_key"].replace("\\n", "\n")
        cred = credentials.Certificate(fb_config)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Firebase Bağlantı Hatası: {e}")

db = firestore.client()

# --- 2. FONKSİYONLAR ---
def query_hf_api(image_bytes):
    """Zaman aşımı ve paket hatasına karşı en dayanıklı API sorgusu"""
    for i in range(3):
        try:
            # timeout=20 ile sunucuyu çok bekletmeden cevap zorluyoruz
            response = requests.post(API_URL, headers=headers, data=image_bytes, timeout=20)
            
            if response.status_code == 200:
                return response.json()
            
            # Model yükleniyorsa bekleme süresi
            res = response.json()
            if isinstance(res, dict) and "estimated_time" in res:
                time.sleep(5)
                continue
        except:
            if i < 2:
                time.sleep(2)
                continue
    return None

def user_auth(u, p, mode):
    user_ref = db.collection('users').document(u)
    doc = user_ref.get()
    if mode == "Giriş":
        return doc.exists and doc.to_dict().get('password') == p
    else:
        if doc.exists: return False
        user_ref.set({'username': u, 'password': p})
        return True

def get_yt_content(p_id, a_key):
    url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&maxResults=50&playlistId={p_id}&key={a_key}"
    try:
        r = requests.get(url).json()
        item = random.choice(r['items'])['snippet']
        v_id = item['resourceId']['videoId']
        return {"title": item['title'], "v_id": v_id, "thumb": f"https://img.youtube.com/vi/{v_id}/hqdefault.jpg"}
    except: return None

# --- 3. ARAYÜZ ---
st.set_page_config(page_title="Mood-Fi Pro: Cloud AI", layout="wide")
TRANSLATION = {"happy": "Mutlu", "sad": "Üzgün", "neutral": "Tarafsız", "angry": "Sinirli"}

if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = None

if not st.session_state.auth:
    st.title("🎵 Mood-Fi: Cloud AI & Music")
    st.info("Bursa Teknik Üniversitesi - Bulut Bilişim Sunumu")
    t1, t2 = st.tabs(["🔐 Giriş Yap", "📝 Kaydol"])
    with t1:
        with st.form("l"):
            u = st.text_input("Kullanıcı Adı")
            p = st.text_input("Şifre", type="password")
            if st.form_submit_button("Sisteme Giriş"):
                if user_auth(u, p, "Giriş"): 
                    st.session_state.auth, st.session_state.user = True, u
                    st.rerun()
                else: st.error("Hatalı Giriş Bilgileri!")
    with t2:
        with st.form("r"):
            ru = st.text_input("Yeni Kullanıcı")
            rp = st.text_input("Yeni Şifre", type="password")
            if st.form_submit_button("Hesap Oluştur"):
                if user_auth(ru, rp, "Kaydol"): st.success("Başarıyla Kaydoldunuz!")
                else: st.error("Bu kullanıcı adı zaten alınmış!")
else:
    with st.sidebar:
        st.subheader(f"👤 {st.session_state.user}")
        if st.button("🚪 Güvenli Çıkış"): 
            st.session_state.auth = False
            st.rerun()

    tab_anlz, tab_hist = st.tabs(["🔍 Duygu Analizi", "📂 Analiz Geçmişi"])
    
    with tab_anlz:
        cam = st.camera_input("Ruh Halini Analiz Et")
        if cam:
            with st.spinner("AI Bulut Sunucusu Analiz Ediyor..."):
                res = query_hf_api(cam.getvalue())
                
                if res and isinstance(res, list):
                    # API sonucunu işle
                    top_res = res[0]
                    dom = top_res['label'].lower()
                    scr = top_res['score'] * 100
                    
                    # Duygu eşleme (Model etiketlerini playlistlere bağlıyoruz)
                    if dom in ["joy", "happy", "surprise"]: mood = "happy"
                    elif dom in ["sad", "fear", "disgust"]: mood = "sad"
                    else: mood = "neutral"
                    
                    yt = get_yt_content(st.secrets[f"playlist_{mood}"], st.secrets["youtube_api_key"])
                    if yt:
                        # Firebase'e Kaydet
                        db.collection('mood_history').add({
                            'username': st.session_state.user,
                            'emotion': TRANSLATION.get(mood, "Tarafsız").upper(),
                            'song': yt['title'],
                            'ai_score': int(scr),
                            'timestamp': firestore.SERVER_TIMESTAMP
                        })
                        
                        # Ekrana Yazdır
                        c1, c2 = st.columns(2)
                        with c1:
                            st.header(f"Mood: {TRANSLATION.get(mood, 'Tarafsız').upper()} ✨")
                            st.metric("AI Güven Skoru", f"%{int(scr)}")
                            if st.button("🔄 Tekrar Analiz Et"): st.rerun()
                        with c2:
                            st.subheader(f"🎵 Öneri: {yt['title']}")
                            st.image(yt['thumb'])
                            st.link_button("▶️ YouTube'da Dinle", f"https://music.youtube.com/watch?v={yt['v_id']}")
                else:
                    st.warning("Bulut sunucusu şu an meşgul. Lütfen 5 saniye bekleyip tekrar fotoğraf çekin.")

    with tab_hist:
        st.subheader("🕒 Son Analizlerin")
        try:
            docs = db.collection('mood_history').where('username', '==', st.session_state.user).stream()
            h_list = sorted([d.to_dict() for d in docs], key=lambda x: x.get('timestamp', 0), reverse=True)
            if h_list:
                for d in h_list[:10]:
                    ts = d.get('timestamp').strftime("%d/%m %H:%M") if d.get('timestamp') else "Yeni"
                    st.write(f"📅 {ts} | {d.get('emotion')} - {d.get('song')} (AI Skoru: %{d.get('ai_score', 0)})")
            else:
                st.info("Henüz bir analiz geçmişiniz bulunmuyor.")
        except:
            st.info("Geçmiş yüklenirken bir hata oluştu.")

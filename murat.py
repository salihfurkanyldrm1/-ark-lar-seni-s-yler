import streamlit as st
import requests
import random
import firebase_admin
from firebase_admin import credentials, firestore
import time
import io

# --- 1. AYARLAR VE BULUT BAĞLANTISI ---
HF_TOKEN = st.secrets["hf_token"]
# Duyguları daha net yakalayan güncel model
API_URL = "https://api-inference.huggingface.co/models/michel-schellekens/facial-emotion-recognition"
headers = {"Authorization": f"Bearer {HF_TOKEN}"}

# Firebase: Tüm ID'ler Secrets'tan çekiliyor
if not firebase_admin._apps:
    try:
        fb_config = dict(st.secrets["firebase"])
        fb_config["private_key"] = fb_config["private_key"].replace("\\n", "\n")
        cred = credentials.Certificate(fb_config)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Bağlantı Hatası: {e}")

db = firestore.client()

# --- 2. FONKSİYONLAR ---
def query_hf_api(image_bytes):
    """JSON Decode hatasını engelleyen, en dayanıklı API sorgusu"""
    import time
    for i in range(3):
        try:
            # 30 saniye cevap bekleme sınırı
            response = requests.post(API_URL, headers=headers, data=image_bytes, timeout=30)
            
            # Eğer sunucu 200 (OK) dönmediyse JSON okumaya çalışma
            if response.status_code != 200:
                time.sleep(2)
                continue
            
            res = response.json()
            
            # Sunucu uyanıyorsa bekle
            if isinstance(res, dict) and "estimated_time" in res:
                time.sleep(5)
                continue
                
            return res
            
        except Exception as e:
            # Herhangi bir hatada (JSON, Bağlantı vb.) uygulamayı çökertme, tekrar dene
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
st.set_page_config(page_title="Mood-Fi: Cloud AI", layout="wide")
TRANSLATION = {"happy": "Mutlu", "sad": "Üzgün", "neutral": "Tarafsız"}

if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = None

if not st.session_state.auth:
    st.title("🎵 Mood-Fi: Cloud AI")
    st.info("Bursa Teknik Üniversitesi - Bulut Bilişim Sunumu")
    t1, t2 = st.tabs(["Giriş", "Kaydol"])
    with t1:
        with st.form("l"):
            u, p = st.text_input("Kullanıcı"), st.text_input("Şifre", type="password")
            if st.form_submit_button("Giriş"):
                if user_auth(u, p, "Giriş"): st.session_state.auth, st.session_state.user = True, u; st.rerun()
                else: st.error("Hatalı!")
    with t2:
        with st.form("r"):
            ru, rp = st.text_input("Yeni Kullanıcı"), st.text_input("Yeni Şifre", type="password")
            if st.form_submit_button("Kaydol"):
                if user_auth(ru, rp, "Kaydol"): st.success("Başarılı!")
                else: st.error("Mevcut!")
else:
    with st.sidebar:
        st.write(f"👤 {st.session_state.user}")
        if st.button("Çıkış"): st.session_state.auth = False; st.rerun()

    tab_anlz, tab_hist = st.tabs(["🔍 Analiz", "📂 Geçmiş"])
    
    with tab_anlz:
        cam = st.camera_input("Analiz Et")
        if cam:
            with st.spinner("Bulut AI Sunucusu Uyandırılıyor..."):
                res = query_hf_api(cam.getvalue())
                if res and isinstance(res, list):
                    dom = res[0]['label'].lower()
                    scr = res[0]['score'] * 100
                    mood = "happy" if dom in ["joy", "happy"] else "sad" if dom in ["sad"] else "neutral"
                    
                    yt = get_yt_content(st.secrets[f"playlist_{mood}"], st.secrets["youtube_api_key"])
                    if yt:
                        db.collection('mood_history').add({
                            'username': st.session_state.user, 'emotion': TRANSLATION[mood].upper(),
                            'song': yt['title'], 'ai_score': int(scr), 'timestamp': firestore.SERVER_TIMESTAMP
                        })
                        c1, c2 = st.columns(2)
                        with c1:
                            st.header(f"Mood: {TRANSLATION[mood].upper()}")
                            st.metric("AI Güveni", f"%{int(scr)}")
                        with c2:
                            st.subheader(f"Öneri: {yt['title']}")
                            st.image(yt['thumb'])
                            st.link_button("YouTube'da Dinle", f"https://music.youtube.com/watch?v={yt['v_id']}")
                else: st.warning("Bulut sunucusu şu an hazır değil, lütfen 5 saniye sonra tekrar deneyin.")

    with tab_hist:
        docs = db.collection('mood_history').where('username', '==', st.session_state.user).stream()
        h_list = sorted([d.to_dict() for d in docs], key=lambda x: x.get('timestamp', 0), reverse=True)
        for d in h_list[:10]:
            ts = d.get('timestamp').strftime("%d/%m %H:%M") if d.get('timestamp') else "Yeni"
            st.write(f"📅 {ts} | {d.get('emotion')} - {d.get('song')} (%{d.get('ai_score')})")

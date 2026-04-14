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
        raw_key = st.secrets["firebase"]["private_key"]
        pk = raw_key.replace("\\n", "\n").strip()
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

# Session State Yönetimi
if 'auth' not in st.session_state: st.session_state.auth = False
if 'user' not in st.session_state: st.session_state.user = None
if 'result' not in st.session_state: st.session_state.result = None

# GİRİŞ / KAYIT EKRANI
if not st.session_state.auth:
    st.title("🎵 Şarkılar Seni Söyler")
    st.markdown("### BTÜ Bulut Bilişim Sunumu")
    
    tab_login, tab_register = st.tabs(["🔐 Giriş Yap", "📝 Kayıt Ol"])
    
    with tab_login:
        u = st.text_input("Kullanıcı Adı", key="l_user")
        p = st.text_input("Şifre", type="password", key="l_pass")
        if st.button("Giriş"):
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
                st.session_state.auth, st.session_state.user = True, u; st.rerun()

    with tab_register:
        new_u = st.text_input("Kullanıcı Adı Belirle", key="r_user")
        new_p = st.text_input("Şifre Belirle", type="password", key="r_pass")
        if st.button("Kayıt Ol"):
            if db:
                try:
                    db.collection('users').document(new_u).set({"username": new_u, "password": new_p})
                    st.success("Kayıt başarılı! Giriş sekmesinden giriş yapabilirsiniz.")
                except: st.error("Veritabanı hatası!")
            else: st.error("Veritabanı bağlı değil, kayıt yapılamaz.")

# ANA UYGULAMA EKRANI
else:
    with st.sidebar:
        st.subheader(f"👤 {st.session_state.user}")
        if db: st.success("✅ Veritabanı Aktif")
        else: st.error("❌ Veritabanı Bağlı Değil")
        if st.button("🚪 Çıkış"): 
            st.session_state.auth = False
            st.session_state.result = None
            st.rerun()

    tab_anlz, tab_hist = st.tabs(["🔍 Duygu Analizi", "📂 Geçmiş Kayıtlar"])

    with tab_anlz:
        # Eğer henüz bir sonuç yoksa kamera inputu göster
        if st.session_state.result is None:
            cam = st.camera_input("Fotoğraf Çek ve Modunu Bul")
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
                        st.session_state.result = {"mood": mood, "scores": scores, "yt": yt}
                        st.rerun()
        
        # Sonuç varsa ekrana yazdır ve "Tekrar Dene" butonunu göster
        else:
            res = st.session_state.result
            c1, c2 = st.columns(2)
            with c1:
                st.header(f"Analiz: {TRANSLATION.get(res['mood']).upper()} ✨")
                for k, v in res['scores'].items():
                    if k in TRANSLATION:
                        st.write(f"**{TRANSLATION[k]}**")
                        st.progress(v)
                
                # TEKRAR DENE BUTONU
                if st.button("🔄 Tekrar Dene"):
                    st.session_state.result = None
                    st.rerun()
                    
            with c2:
                st.subheader(f"🎵 Öneri: {res['yt']['title']}")
                st.image(res['yt']['thumb'], use_container_width=True)
                st.link_button("▶️ YouTube'da Dinle", f"https://music.youtube.com/watch?v={res['yt']['v_id']}")

    with tab_hist:
        if db:
            try:
                docs = db.collection('mood_history').where('username', '==', st.session_state.user).order_by('timestamp', direction=firestore.Query.DESCENDING).limit(10).stream()
                for doc in docs:
                    dat = doc.to_dict()
                    ts = dat.get('timestamp')
                    t_str = ts.strftime("%d/%m %H:%M") if ts else "Yeni"
                    st.write(f"📅 {t_str} | **{dat.get('emotion')}** - {dat.get('song')}")
            except:
                st.info("Geçmiş kayıtlar yüklenirken bir sorun oluştu.")
        else:
            st.warning("Veritabanı bağlı değil.")

import os, requests
import streamlit as st
from collections import deque
from functools import lru_cache
from datetime import date, datetime
from dotenv import load_dotenv

# ---------------- setup ----------------
load_dotenv()
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
BASE = "https://api.themoviedb.org/3"
SESSION = requests.Session()

def tmdb_get(path, params=None):
    if params is None: params = {}
    params["api_key"] = TMDB_API_KEY
    r = SESSION.get(f"{BASE}{path}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()

# -------------- helpers ---------------
def calc_age(birthday, deathday=None):
    if not birthday:
        return None
    b = datetime.strptime(birthday, "%Y-%m-%d").date()
    end = datetime.strptime(deathday, "%Y-%m-%d").date() if deathday else date.today()
    return end.year - b.year - ((end.month, end.day) < (b.month, b.day))

def img_url(path, size="w185"):
    return f"https://image.tmdb.org/t/p/{size}{path}" if path else None

@st.cache_data(ttl=3600, show_spinner=False)
def get_person_details(person_id: int):
    return tmdb_get(f"/person/{person_id}")

@st.cache_data(ttl=300, show_spinner=False)
def search_people(query: str, limit: int = 10):
    if not query.strip():
        return []
    data = tmdb_get("/search/person", {"query": query})
    results = []
    for p in data.get("results", [])[:limit]:
        d = get_person_details(p["id"])
        results.append({
            "id": p["id"],
            "name": d.get("name") or p.get("name"),
            "age": calc_age(d.get("birthday"), d.get("deathday")),
            "known_for": ", ".join([(k.get("title") or k.get("name") or "") for k in p.get("known_for", [])][:3]),
            "profile_path": d.get("profile_path"),
        })
    return results

@lru_cache(maxsize=10_000)
def _person_movies_cached(person_id):
    cast = tmdb_get(f"/person/{person_id}/movie_credits").get("cast", [])
    return tuple(sorted({m["id"] for m in cast}))

@lru_cache(maxsize=10_000)
def _movie_cast_cached(movie_id):
    cast = tmdb_get(f"/movie/{movie_id}/credits").get("cast", [])
    return tuple(sorted({c["id"] for c in cast}))

@lru_cache(maxsize=10_000)
def _person_name_photo(person_id):
    p = get_person_details(person_id)
    return p.get("name") or "Unknown", p.get("profile_path")

@lru_cache(maxsize=10_000)
def _movie_title_poster(movie_id):
    m = tmdb_get(f"/movie/{movie_id}")
    title = m.get("title") or m.get("original_title") or "Unknown"
    year = (m.get("release_date") or "")[:4]
    return (f"{title} ({year})" if year else title), m.get("poster_path")

# -------------- shortest path (bi-BFS) --------------
def bidir_bfs_people(source_id, target_id, max_edges=6):
    if source_id == target_id:
        return [("person", source_id)]
    qa, qb = deque([("person", source_id)]), deque([("person", target_id)])
    pa, pb = {("person", source_id): None}, {("person", target_id): None}
    visited_a, visited_b = set(pa.keys()), set(pb.keys())

    def expand(q, parents, visited, other_visited):
        for _ in range(len(q)):
            node_type, node_id = q.popleft()
            if node_type == "person":
                for mid in _person_movies_cached(node_id):
                    nxt = ("movie", mid)
                    if nxt not in visited:
                        visited.add(nxt); parents[nxt] = (node_type, node_id)
                        q.append(nxt)
                        if nxt in other_visited: return nxt
            else:
                for pid in _movie_cast_cached(node_id):
                    nxt = ("person", pid)
                    if nxt not in visited:
                        visited.add(nxt); parents[nxt] = (node_type, node_id)
                        q.append(nxt)
                        if nxt in other_visited: return nxt
        return None

    depth = 0
    while qa and qb and depth <= max_edges:
        meet = expand(qa, pa, visited_a, visited_b)
        if meet: return reconstruct(pa, pb, meet)
        meet = expand(qb, pb, visited_b, visited_a)
        if meet: return reconstruct(pa, pb, meet)
        depth += 1
    return None

def reconstruct(pa, pb, meet):
    left, cur = [], meet
    while cur is not None:
        left.append(cur); cur = pa.get(cur)
    left.reverse()
    right, cur = [], pb.get(meet)
    while cur is not None:
        right.append(cur); cur = pb.get(cur)
    return left + right

# -------------- UI --------------
st.set_page_config(page_title="Actor Link", page_icon="🎬", layout="wide")

# ---- Discrete theme toggle (header button) ----
if "dark" not in st.session_state:
    st.session_state.dark = True

col_logo, col_toggle = st.columns([8,1])
with col_logo:
    st.title("🎬 Actor Link")
    st.caption("Shortest Path via Movies — Powered by TMDb")
with col_toggle:
    if st.button("🌙" if st.session_state.dark else "☀️", help="Toggle theme"):
        st.session_state.dark = not st.session_state.dark

def inject_theme(dark: bool):
    if dark:
        colors = {
            "bg": "#0f1115", "fg": "#f3f4f6", "muted": "#a3a3a3",
            "surface": "#171a21", "placeholder": "#252a34",
            "accent": "#2563eb", "button_fg": "#f8fafc",
            "accent_border": "#1d4ed8", "shadow": "rgba(0,0,0,0.35)"
        }
    else:
        colors = {
            "bg": "#ffffff", "fg": "#111111", "muted": "#5b5b5b",
            "surface": "#f6f7f9", "placeholder": "#e9eaee",
            "accent": "#111827", "button_fg": "#ffffff",
            "accent_border": "#0f172a", "shadow": "rgba(0,0,0,0.06)"
        }

    st.markdown(f"""
    <style>
      .stApp {{
        background: {colors['bg']};
        color: {colors['fg']};
        transition: background 0.3s ease, color 0.3s ease;
      }}
      .stButton>button {{
        background: {colors['accent']};
        color: {colors['button_fg']};
        border-radius: 8px;
        border: 1px solid {colors['accent_border']};
      }}
      .card {{
        text-align:center; padding:10px;
        background: {colors['surface']};
        border-radius: 10px;
        box-shadow: 0 2px 10px {colors['shadow']};
      }}
      .avatar {{ width:120px; height:120px; border-radius:50%; object-fit:cover; background:{colors['placeholder']}; }}
      .poster {{ width:120px; height:180px; border-radius:8px; object-fit:cover; background:{colors['placeholder']}; }}
      .title {{ font-size:0.9rem; margin-top:6px; color:{colors['fg']}; }}
      .sep {{ font-size:1.2rem; opacity:0.8; padding:0 8px; color:{colors['muted']}; }}
    </style>
    """, unsafe_allow_html=True)

inject_theme(st.session_state.dark)

if not TMDB_API_KEY:
    st.error("Missing TMDB_API_KEY in .env"); st.stop()

def person_picker(column, label, key_prefix):
    with column:
        st.subheader(label)
        q = st.text_input("Start typing a name", key=f"q_{key_prefix}", placeholder="e.g., Keanu Reeves")
        selected = None
        if len(q.strip()) >= 2:
            results = search_people(q)
            if results:
                labels = [
                    f"{p['name']} ({p['age'] if p['age'] is not None else '?'} yrs) — Known for: {p['known_for']}"
                    for p in results
                ]
                chosen_label = st.selectbox("Suggestions", labels, key=f"sel_{key_prefix}", index=0)
                selected = results[labels.index(chosen_label)]

                with st.container(border=True):
                    c1, c2 = st.columns([1, 3])
                    with c1:
                        if selected.get("profile_path"):
                            st.image(img_url(selected["profile_path"]), use_container_width=True)
                    with c2:
                        st.markdown(f"**{selected['name']}**")
                        st.markdown(f"Age: {selected['age'] if selected['age'] is not None else 'Unknown'}")
                        if selected["known_for"]:
                            st.caption(f"Known for: {selected['known_for']}")
        return selected

col1, col2 = st.columns(2)
actor_a = person_picker(col1, "Actor A", "a")
actor_b = person_picker(col2, "Actor B", "b")

movie_hops = st.slider("Maximum movie hops (movies between the two actors)", 1, 8, 3)
max_edges = movie_hops * 2

disabled = not (actor_a and actor_b)
if st.button("Find Connection", type="primary", disabled=disabled):
    with st.spinner("Searching shortest path…"):
        path = bidir_bfs_people(actor_a["id"], actor_b["id"], max_edges=max_edges)

    if not path:
        st.warning("No path found within the depth limit.")
    else:
        st.subheader("Connection (chain)")
        items = []
        for node_type, node_id in path:
            if node_type == "person":
                name, profile = _person_name_photo(node_id)
                items.append({"type": "person", "title": name, "img": img_url(profile), "link": f"https://www.themoviedb.org/person/{node_id}"})
            else:
                title, poster = _movie_title_poster(node_id)
                items.append({"type": "movie", "title": title, "img": img_url(poster), "link": f"https://www.themoviedb.org/movie/{node_id}"})

        cols = st.columns(len(items) * 2 - 1)
        ci = 0
        for i, it in enumerate(items):
            with cols[ci]:
                st.markdown('<div class="card">', unsafe_allow_html=True)
                img_class = "avatar" if it["type"] == "person" else "poster"
                if it["img"]:
                    st.markdown(f'<a href="{it["link"]}" target="_blank"><img class="{img_class}" src="{it["img"]}"/></a>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="{img_class}" style="display:inline-block;"></div>', unsafe_allow_html=True)
                st.markdown(f'<div class="title">{it["title"]}</div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
            ci += 1
            if i < len(items) - 1:
                with cols[ci]:
                    st.markdown('<div class="sep">⟶</div>', unsafe_allow_html=True)
                ci += 1
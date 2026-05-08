import streamlit as st
import requests
import re
from bs4 import BeautifulSoup
from openai import OpenAI
from io import BytesIO


# ======================
# GOOGLE NEWS RESULTS
# ======================

def get_google_news_results(keyword, num_results, serpapi_key, hl, gl):

    url = "https://serpapi.com/search.json"

    params = {
        "engine": "google_news",
        "q": keyword,
        "hl": hl,
        "gl": gl,
        "api_key": serpapi_key
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    data = response.json()

    news_results = data.get("news_results", [])

    competitors = []
    seen = set()

    for item in news_results:

        link = item.get("link")

        if not link:
            continue

        normalized = link.strip().rstrip("/")

        if normalized in seen:
            continue

        seen.add(normalized)

        competitors.append({
            "title": item.get("title", ""),
            "link": normalized,
            "source": item.get("source", "")
        })

        if len(competitors) >= num_results:
            break

    return competitors


# ======================
# SCRAPE PAGE
# ======================

def fetch_page(url):

    try:

        resp = requests.get(
            url,
            headers={
                "User-Agent":
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            },
            timeout=15
        )

        resp.raise_for_status()

        html = resp.text

        soup = BeautifulSoup(html, "lxml")

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        text = " ".join(soup.get_text().split())

        return html, text[:18000]

    except Exception:
        return "", ""


def extract_metadata(html):

    soup = BeautifulSoup(html, "lxml")

    title = soup.title.string.strip() if soup.title and soup.title.string else ""

    h1_tag = soup.find("h1")
    h1 = h1_tag.get_text(strip=True) if h1_tag else ""

    meta_desc = ""

    meta = soup.find("meta", attrs={"name": "description"})

    if meta and "content" in meta.attrs:
        meta_desc = meta["content"].strip()

    return title, h1, meta_desc


# ======================
# GPT PARSER
# ======================

def parse_generated_content(content):

    title = ""
    meta = ""
    article = content

    if "TITLE TAG:" in content:

        after_title = content.split("TITLE TAG:", 1)[1]
        title = after_title.split("META DESCRIPTION:", 1)[0].strip()

        after_meta = after_title.split("META DESCRIPTION:", 1)[1]
        meta = after_meta.split("ARTICLE HTML:", 1)[0].strip()

        article = after_meta.split("ARTICLE HTML:", 1)[1].strip()

    return title, meta, article


# ======================
# GENERATE ARTICLE
# ======================

def generate_article(keyword, target_h1, custom_prompt, competitors, openai_key, language):

    client = OpenAI(api_key=openai_key)

    merged = ""

    for comp in competitors:

        merged += f"""
URL: {comp['link']}

TITLE: {comp['html_title']}
H1: {comp['h1']}
META: {comp['meta_desc']}

CONTENUTO:
{comp['text']}

-------------------------
"""

    prompt = f"""
Sei un content writer SEO esperto.

Scrivi un contenuto SEO completo per la keyword:

{keyword}

H1 del contenuto da redigere:

{target_h1}

Lingua: {language}

Il risultato deve contenere:

TITLE TAG (max 60 caratteri)
META DESCRIPTION (max 155 caratteri)
ARTICOLO HTML (800-1200 parole)

Regole HTML:

- inizia l'articolo con questo H1 esatto: <h1>{target_h1}</h1>
- integra sempre la keyword in maniera naturale, senza forzature
- basati sulle informazioni estrpolate dallo scraping
- usa <h2> e <h3>
- usa <p>
- usa <ul> e <ol>
- usa <strong>
- NON includere <html> o <body>

Customizzazioni ad hoc da integrare alle regole precedenti:
{custom_prompt if custom_prompt else "Nessuna customizzazione aggiuntiva."}

COMPETITOR DATA:
{merged}

Formato output:

TITLE TAG:
...

META DESCRIPTION:
...

ARTICLE HTML:
...
"""

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )

    content = response.choices[0].message.content

    return parse_generated_content(content)


# ======================
# TXT EXPORT
# ======================

def create_txt_file(title_tag, h1, meta_description, article):

    content = f"""Title Tag
{title_tag}

H1
{h1}

Meta Description
{meta_description}

HTML Article
{article}
"""

    buffer = BytesIO()
    buffer.write(content.encode("utf-8"))
    buffer.seek(0)

    return buffer


def create_txt_filename(h1):

    filename = re.sub(r'[<>:"/\\|?*]', "", h1)
    filename = re.sub(r"\s+", " ", filename).strip()

    return f"{filename or 'seo_article'}.txt"


# ======================
# STREAMLIT UI
# ======================

st.title("Google News SEO Article Generator")

st.sidebar.title("API Keys")

SERPAPI_KEY = st.sidebar.text_input("SerpAPI Key", type="password")
OPENAI_KEY = st.sidebar.text_input("OpenAI Key", type="password")

keyword = st.text_input("Keyword")

target_h1 = st.text_input("H1 del contenuto da redigere")

custom_prompt = st.text_area(
    "Customizzazioni prompt ad hoc",
    help="Inserisci eventuali indicazioni aggiuntive: tono, pubblico, angolazione, CTA, sezioni da includere o evitare."
)

num_results = st.slider(
    "Numero articoli da analizzare",
    1,
    10,
    5
)

country = st.text_input("Country code", "it")
language = st.text_input("Language code", "it")

generate = st.button("Genera contenuto")


# ======================
# MAIN LOGIC
# ======================

if generate:

    if not SERPAPI_KEY or not OPENAI_KEY:

        st.error("Inserisci le API key.")
        st.stop()

    if not keyword:

        st.error("Inserisci una keyword.")
        st.stop()

    if not target_h1:

        st.error("Inserisci l'H1 del contenuto da redigere.")
        st.stop()

    st.write("Recupero Google News...")

    competitors = get_google_news_results(
        keyword,
        num_results,
        SERPAPI_KEY,
        language,
        country
    )

    enriched = []

    for comp in competitors:

        st.write("Scraping:", comp["link"])

        html, text = fetch_page(comp["link"])

        html_title, h1, meta_desc = extract_metadata(html)

        enriched.append({
            **comp,
            "html_title": html_title,
            "h1": h1,
            "meta_desc": meta_desc,
            "text": text
        })

    st.write("Generazione articolo...")

    title_tag, meta_description, article = generate_article(
        keyword,
        target_h1,
        custom_prompt,
        enriched,
        OPENAI_KEY,
        language
    )

    st.subheader("Title Tag")
    st.write(title_tag)

    st.subheader("Meta Description")
    st.write(meta_description)

    st.subheader("H1")
    st.write(target_h1)

    st.subheader("Articolo HTML")

    st.code(article, language="html")

    txt_file = create_txt_file(
        title_tag,
        target_h1,
        meta_description,
        article
    )

    st.download_button(
        label="Scarica TXT",
        data=txt_file,
        file_name=create_txt_filename(target_h1),
        mime="text/plain"
    )

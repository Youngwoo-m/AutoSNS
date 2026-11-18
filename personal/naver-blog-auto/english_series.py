"""English GeoAI series - one post a day to https://geoai-safety.blogspot.com/ (2026-11-18 user request).

The topic list is fixed below (title + angle); the body is written by the main model
(public post body -> claude CLI, per the credit-saving rule). Checks before publishing:
format (4+ <h2>, 800-1800 words), only allow-listed link domains, no statistics.

Usage:
    python english_series.py --plan   # list topics and what is next (no API calls)
    python english_series.py --dry    # write today's post to english/drafts/ (no publishing)
    python english_series.py --go     # write and publish (run_personal.py english-daily)
"""
import json
import os
import re
import sys
from datetime import datetime

from common import BASE_DIR, load_config, log

STATE_PATH = os.path.join(BASE_DIR, "english_state.json")
DRAFT_DIR = os.path.join(BASE_DIR, "english", "drafts")
BLOG_ID = "3154612862980198700"          # GeoAI for Disaster Safety (geoai-safety.blogspot.com)
SITE_EN = "https://geoai-na.web.app/en/"

# (slug, title, angle, labels). Titles start with the words people search for.
TOPICS = [
    # 2026-11-18: the blog already had 44 translated GeoAI posts (2026-11-15) plus a daily Whitebox practice post
    # from another job. Topics that overlapped them (CRS, QGIS start, GeoPandas, Earth Engine, flood/landslide/
    # wildfire maps, shelters, DEM, open data, drones, generative AI coding, heat island) were removed.
    # Check the blog's titles before adding a topic here.
    ("what-is-geoai", "What Is GeoAI, and How Does It Help Disaster Safety?",
     "Already published by hand on 2026-11-15.", ["GeoAI basics"]),
    ("gis-vs-geoai", "GIS vs GeoAI: What Changes When Maps Start Learning",
     "Rule-based GIS analysis vs learned models; what each is good at; how they are combined in practice.",
     ["GeoAI basics", "GIS"]),
    ("risk-equation", "Hazard, Exposure and Vulnerability: The Risk Equation Behind Disaster Maps",
     "What each term means, how each becomes a map layer, why a hazard map alone is not a risk map, simple overlay logic.",
     ["Disaster safety", "GeoAI basics"]),
    ("satellite-basics", "Satellite Imagery Basics: Resolution, Bands and Revisit Time",
     "Spatial, temporal and spectral resolution; how to read a band list; matching image choice to the question. Do not go deep into SAR flood mapping (covered elsewhere).",
     ["Remote sensing", "GeoAI basics"]),
    ("ndvi-ndwi", "NDVI and NDWI: What Spectral Indices Actually Show",
     "Reflectance idea behind indices; NDVI and NDWI; reading vegetation stress and surface water; common mistakes. Mention dNBR only in one line (covered elsewhere).",
     ["Remote sensing", "GeoAI basics"]),
    ("training-data", "Training Data for GeoAI: Labeling Imagery Without Fooling Yourself",
     "Points vs polygons vs masks, class imbalance, regional bias, label noise, documenting how labels were made.",
     ["GeoAI basics", "Machine learning"]),
    ("spatial-validation", "Spatial Cross-Validation: Why Random Splits Overstate Accuracy",
     "Nearby samples leak information, block or region splits, honest error reporting for maps used in decisions. Do not re-explain the confusion matrix (covered elsewhere).",
     ["Machine learning", "GeoAI basics"]),
    ("map-uncertainty", "Showing Uncertainty on Risk Maps: What We Don't Know Matters",
     "Sources of uncertainty (data, model, scale), ways to show it (classes, hatching, confidence layers, notes), how readers misread precise-looking maps.",
     ["Cartography", "Disaster safety"]),
    ("maps-that-communicate", "Making Risk Maps People Can Read in an Emergency",
     "Clear legends, colorblind-safe palettes, data date and limits on the map, one message per map, print and phone checks.",
     ["Cartography", "Disaster safety"]),
    ("building-footprints", "Building Footprints From Imagery: How AI Maps Exposure",
     "Why building outlines matter for exposure, segmentation idea in plain words, open footprint datasets in general terms, checking errors in dense or rural areas.",
     ["GeoAI basics", "Exposure data"]),
    ("critical-infrastructure", "Mapping Critical Infrastructure: Hospitals, Power and Water in a Disaster",
     "Which facilities count, dependencies between networks, mapping service areas, keeping sensitive locations appropriately general.",
     ["Disaster safety", "GIS"]),
    ("tsunami-maps", "Tsunami Inundation Maps: How Coastal Hazard Zones Are Drawn",
     "Scenario-based modeling in plain words, run-up vs inundation, evacuation zones and signs, limits of a single scenario.",
     ["Tsunamis", "Disaster safety"]),
    ("storm-surge", "Storm Surge Explained: How Typhoon Winds Push Water Ashore",
     "Surge vs tide vs waves, coastal shape and elevation, how surge maps are read, combining with evacuation planning. Avoid repeating typhoon damage prediction (covered elsewhere).",
     ["Typhoons", "Floods"]),
    ("drought-from-space", "Drought Monitoring From Space: Soil Moisture and Vegetation Signals",
     "Types of drought, satellite soil moisture and vegetation anomalies, comparing with a long-term baseline, why one image is not enough.",
     ["Drought", "Remote sensing"]),
    ("sea-level-scenarios", "Sea-Level Rise Maps: How to Read the Scenarios Without Panic",
     "What a scenario is, bathtub maps vs modeled maps, elevation accuracy limits, using these maps for long-term planning only.",
     ["Climate", "Floods"]),
    ("volcanic-hazards", "Volcanic Hazard Maps: Lava, Ash and Evacuation Zones",
     "Different volcanic hazards and their reach, zone maps, ash fall and wind, monitoring with satellites in general terms.",
     ["Volcanoes", "Disaster safety"]),
    ("crowdsourced-reports", "Crowdsourced Disaster Reports: Turning Public Posts Into Map Points",
     "Volunteer reports and social posts as data, location errors, verification steps, privacy and consent, never mapping individuals.",
     ["Disaster safety", "Open data"]),
    ("early-warning", "Early Warning Systems: From Sensor Reading to Public Alert",
     "Monitor, decide, warn, respond; where maps fit in each step; false alarms vs missed events; testing the chain with drills.",
     ["Disaster safety", "GeoAI basics"]),
]

ALLOWED_LINK_DOMAINS = (
    "qgis.org", "docs.qgis.org", "openstreetmap.org", "wiki.openstreetmap.org", "dataspace.copernicus.eu",
    "browser.dataspace.copernicus.eu", "sentinels.copernicus.eu", "earthengine.google.com",
    "developers.google.com", "geopandas.org", "usgs.gov", "earthexplorer.usgs.gov", "nasa.gov",
    "earthdata.nasa.gov", "epsg.io", "python.org", "geoai-na.web.app", "geoai-safety.blogspot.com",
)

SYSTEM = """You write for the English blog "GeoAI for Disaster Safety", run by an educator in Korea.
Readers: students, teachers and practitioners new to GIS and GeoAI, worldwide.

Style
- Plain, natural English. Short paragraphs. Active voice. Concrete examples.
- No hype, no filler openers ("In today's world..."), no closing clichés ("In conclusion...").
- Explain terms the first time they appear.

Accuracy (strict)
- Do NOT invent statistics, percentages, dates of events, study results, quotes or named case studies.
- Use numbers only for definitions or well-known technical facts (for example a 10 m Sentinel-2 band).
- If you are not sure a fact is true, leave it out.
- Links only to official tool or data sites (QGIS, OpenStreetMap, Copernicus, USGS, NASA Earthdata,
  Google Earth Engine, GeoPandas, epsg.io). Do not link anything else.

Output format (exactly these markers, nothing before or after)
===DESCRIPTION===
one sentence, max 150 characters, for search results
===LABELS===
2-4 short labels, comma separated
===BODY===
HTML only: <p>, <h2>, <h3>, <ul>, <ol>, <li>, <strong>, <em>, <code>, <pre>, <a>.
No <h1>, no title, no inline styles, no images.
800-1500 words, at least 4 <h2> sections, end with a short "What to try next" section."""

USER = """Write post {n} of the series.

Title (already set, do not repeat it in the body): {title}
Angle and must-cover points: {angle}

Posts already on the blog (do not re-explain these topics; a one-line mention is fine):
{recent}

Next post in the series (if you mention what comes next, use only this): {next_title}"""


def state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"posted": {}}


def save_state(s):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def service():
    from geoai_blogger import service as svc   # same Google account and token as the Korean blog
    return svc()


def blog_titles(svc):
    from geoai_blogger import posted_titles
    return posted_titles(svc, BLOG_ID)


def next_topic(done_titles=()):
    done = set(state().get("posted", {}))
    for i, t in enumerate(TOPICS, start=1):
        if t[0] not in done and t[1] not in done_titles:
            return i, t
    return None, None


def _client(cfg):
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    from shared.llm import client
    return client(cfg)          # public body text -> main model (no low-cost task tag)


def _parse(text):
    parts = dict(re.findall(r"===(DESCRIPTION|LABELS|BODY)===\s*(.*?)(?=\n===[A-Z]+===|\Z)", text, re.S))
    return {k.lower(): v.strip() for k, v in parts.items()}


def _clean_links(body):
    """Drop links to domains outside the allow list (keep the link text)."""
    def fix(m):
        href = m.group(1)
        host = re.sub(r"^https?://", "", href).split("/")[0].lower()
        if any(host == d or host.endswith("." + d) for d in ALLOWED_LINK_DOMAINS):
            return f'<a href="{href}" rel="noopener" target="_blank">'
        return "<a>"
    body = re.sub(r'<a\s[^>]*href="([^"]+)"[^>]*>', fix, body)
    return re.sub(r"<a>(.*?)</a>", r"\1", body, flags=re.S)


def check(data):
    """Return a list of problems (empty = OK)."""
    body = data.get("body", "")
    words = len(re.sub(r"<[^>]+>", " ", body).split())
    problems = []
    if body.count("<h2") < 4:
        problems.append(f"only {body.count('<h2')} <h2> sections")
    if not 800 <= words <= 1800:
        problems.append(f"{words} words")
    if re.search(r"<h1|<img|style=", body, re.I):
        problems.append("forbidden tag or inline style")
    if re.search(r"\d+(\.\d+)?\s?%|\bpercent\b|according to (a|one) (study|survey|report)", body, re.I):
        problems.append("looks like a statistic or unnamed study")
    if not data.get("description"):
        problems.append("no description")
    return problems, words


def generate(idx, topic, cfg, recent=()):
    slug, title, angle, labels = topic
    client = _client(cfg)
    user = USER.format(n=idx, title=title, angle=angle,
                       recent="\n".join(f"- {t}" for t in list(recent)[-60:]) or "(none)",
                       next_title=TOPICS[idx][1] if idx < len(TOPICS) else "(not decided yet - do not announce a topic)")
    feedback = ""
    for attempt in range(1, 4):
        msg = client.messages.create(
            model=cfg.get("model", "claude-sonnet-4-6"), max_tokens=8000, system=SYSTEM,
            messages=[{"role": "user", "content": SYSTEM + "\n\n" + user + feedback}])
        data = _parse(msg.content[0].text.strip())
        data["body"] = _clean_links(data.get("body", ""))
        problems, words = check(data)
        if not problems:
            log(f"English post generated: {words} words")
            data.update(slug=slug, title=title,
                        labels=list(dict.fromkeys([*labels, *[l.strip() for l in data.get("labels", "").split(",") if l.strip()]]))[:5])
            return data
        log(f"English post check failed (try {attempt}/3): {', '.join(problems)}")
        feedback = "\n\nYour previous draft had these problems, fix them: " + "; ".join(problems)
    raise RuntimeError("English post failed the checks 3 times: " + ", ".join(problems))


def build_html(data):
    footer = (f'<p>More materials (some in Korean) are on <a href="{SITE_EN}" rel="noopener" target="_blank">'
              'GeoAI for Disaster Safety</a>.</p>\n'
              '<p style="font-size:13px;color:#666">This post was drafted with the help of AI tools and '
              'checked before publishing. Tool features and data portals change over time, so check the '
              'official documentation when you practice.</p>')
    return data["body"] + "\n" + footer


def run(go=False, cfg=None):
    cfg = cfg or load_config()
    svc = service() if go else None
    have = set()
    if go:
        # Only this series counts: another job posts a daily "Whitebox QGIS Practice" to the same blog.
        today = f"{datetime.now():%Y-%m-%d}"
        mine = [v["title"] for v in state().get("posted", {}).values() if v.get("date") == today]
        if mine:
            log(f"English series already posted today ({mine[0]}), skipping.")
            return {"status": "skipped", "reason": "already posted today"}
        have = blog_titles(svc)
    idx, topic = next_topic(have)
    if topic is None:
        log("English series: no topics left (add more to TOPICS).")
        return {"status": "exhausted"}
    log(f"English series {idx}/{len(TOPICS)}: {topic[1]}")
    recent = [t[1] for t in TOPICS[:idx - 1]] + sorted(t for t in have if "Whitebox" not in t and t not in {x[1] for x in TOPICS})
    data = generate(idx, topic, cfg, recent)
    html = build_html(data)
    if not go:
        os.makedirs(DRAFT_DIR, exist_ok=True)
        path = os.path.join(DRAFT_DIR, f"{datetime.now():%Y%m%d}-{topic[0]}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"<!-- title: {data['title']} -->\n<!-- description: {data['description']} -->\n"
                    f"<!-- labels: {', '.join(data['labels'])} -->\n{html}\n")
        return {"status": "dry", "title": data["title"], "file": path}
    post = svc.posts().insert(blogId=BLOG_ID, isDraft=False,
                              body={"title": data["title"], "content": html, "labels": data["labels"]}).execute()
    s = state()
    s.setdefault("posted", {})[topic[0]] = {"title": data["title"], "url": post.get("url", ""),
                                            "date": f"{datetime.now():%Y-%m-%d}"}
    save_state(s)
    log(f"English post published: {post.get('url')}")
    return {"status": "published", "title": data["title"], "url": post.get("url", "")}


if __name__ == "__main__":
    if "--plan" in sys.argv:
        done = set(state().get("posted", {}))
        for i, t in enumerate(TOPICS, start=1):
            print(("[done] " if t[0] in done else "[todo] ") + f"{i:2d}. {t[1]}")
        raise SystemExit(0)
    print(json.dumps(run(go="--go" in sys.argv), ensure_ascii=False, indent=2))

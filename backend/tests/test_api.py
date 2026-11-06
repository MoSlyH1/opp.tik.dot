import pytest

from app import create_app
from app.classifier import classify
from app.extensions import db
from app.models import Item


@pytest.fixture()
def client():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SQLALCHEMY_ENGINE_OPTIONS": {},
        "DEV_LOGIN": True,
        "ADMIN_EMAILS": {"admin@local.test"},
        "YOUTUBE_API_KEY": "",
    })
    with app.app_context():
        db.create_all()
        for n, (era, cat) in enumerate([("90s", "music"), ("00s", "style"), ("classic", "ads"),
                                        ("90s", "movies"), ("00s", "music")] * 4):
            db.session.add(Item(source="youtube", external_id=f"vid{n}", url=f"https://y/{n}",
                                title=f"Item {n} {cat}", era=era, category=cat, score=0.6,
                                thumbnail=f"https://img/{n}.jpg"))
        db.session.commit()
        yield app.test_client()


def login(c, email="me@local.test"):
    assert c.post("/api/auth/dev", json={"email": email}).status_code == 200


def test_classifier_basics():
    assert classify("Backstreet Boys - I Want It That Way (1999)")["era"] == "90s"
    assert classify("Y2K fashion lookbook throwback")["era"] == "00s"
    assert classify("Nokia 3310 commercial 2001")["category"] in ("tech", "ads")
    assert not classify("iPhone 16 review 2024")["accepted"]
    assert classify("Windows 98 launch", year=1998)["accepted"]


def test_auth_required(client):
    assert client.get("/api/feed").status_code == 401
    assert client.get("/api/auth/me").get_json()["user"] is None


def test_feed_filters_and_paging(client):
    login(client)
    r = client.get("/api/feed?era=90s&limit=5&seed=a").get_json()
    assert len(r["items"]) == 5 and all(i["era"] == "90s" for i in r["items"])
    r2 = client.get(f"/api/feed?era=90s&limit=5&seed=a&cursor={r['next_cursor']}").get_json()
    ids = {i["id"] for i in r["items"]} | {i["id"] for i in r2["items"]}
    assert len(ids) == 8  # 8 '90s items, no duplicates across pages
    assert r2["next_cursor"] is None


def test_interactions_and_collection(client):
    login(client)
    item = client.get("/api/feed?limit=1").get_json()["items"][0]
    r = client.post(f"/api/items/{item['id']}/interact", json={"action": "like"}).get_json()
    assert r["item"]["liked"] and r["item"]["likes"] == 1
    client.post(f"/api/items/{item['id']}/interact", json={"action": "like"})  # idempotent
    assert client.get("/api/me/collection?type=like").get_json()["items"][0]["likes"] == 1
    client.post(f"/api/items/{item['id']}/interact", json={"action": "hide"})
    feed_ids = {i["id"] for i in client.get("/api/feed?limit=20").get_json()["items"]}
    assert item["id"] not in feed_ids


def test_search_db_only(client):
    login(client)
    r = client.get("/api/search?q=style&live=0").get_json()
    assert r["items"] and all("style" in i["title"] for i in r["items"])


def test_admin_guard_and_prefs(client):
    login(client)
    assert client.post("/api/admin/ingest").status_code == 403
    r = client.put("/api/me/prefs", json={"era": ["90s", "bogus"], "reverse": True}).get_json()
    assert r["user"]["prefs"] == {"era": ["90s"], "category": [], "reverse": True}
    login(client, "admin@local.test")
    assert client.get("/api/admin/stats").get_json()["total"] == 20


def test_cron_requires_secret(client):
    assert client.get("/api/cron/ingest").status_code == 401

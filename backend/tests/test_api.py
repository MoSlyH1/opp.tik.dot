import pytest

from app import create_app
from app.classifier import classify
from app.extensions import db
from app.models import Item
from app.providers.archive import pick_file
from app.ranking import engagement


@pytest.fixture()
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SQLALCHEMY_ENGINE_OPTIONS": {},
        "DEV_LOGIN": True,
        "ADMIN_EMAILS": {"admin@local.test"},
        "YOUTUBE_API_KEY": "",
        "DAILYMOTION": False,
    })
    with app.app_context():
        db.create_all()
        specs = [("90s", "|t:music|r:american|"), ("00s", "|t:style|"), ("80s", "|t:ads|r:arabic|r:lebanese|"),
                 ("90s", "|t:movies|t:scifi|"), ("00s", "|t:music|r:latin|"), ("90s", "|t:football|r:arabic|"),
                 ("80s", "|t:kids|c:spacetoon|r:arabic|"), ("90s", "|t:docs|c:natgeo|")]
        for n in range(24):
            era, labels = specs[n % len(specs)]
            cat = labels.split("|")[1][2:]
            db.session.add(Item(source="youtube", external_id=f"vid{n}", url=f"https://y/{n}",
                                title=f"Item {n} {cat}", era=era, category=cat, labels=labels, score=0.6,
                                thumbnail=f"https://img/{n}.jpg", author=f"chan{n % 5}", tax_v=99))
        # An archive item whose file is known to be missing must never reach the feed.
        db.session.add(Item(source="archive", external_id="gone", url="https://a/gone", title="gone 1990",
                            era="90s", category="ads", labels="|t:ads|", media_url="", tax_v=99))
        db.session.commit()
        yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def login(c, email="me@local.test"):
    assert c.post("/api/auth/dev", json={"email": email}).status_code == 200


def test_classifier_basics():
    assert classify("Backstreet Boys - I Want It That Way (1999)")["era"] == "90s"
    assert classify("Y2K fashion lookbook throwback")["era"] == "00s"
    assert classify("Nokia 3310 commercial 2001")["category"] in ("tech", "ads")
    assert not classify("iPhone 16 review 2024")["accepted"]
    assert classify("Windows 98 launch", year=1998)["accepted"]
    assert classify("Thriller 1983")["era"] == "80s"


def test_classifier_cultures_and_topics():
    c = classify("شارة كرتون سبيستون كابتن ماجد 1995")
    assert "kids" in c["topics"] and "arabic" in c["regions"] and "spacetoon" in c["channels"]
    c = classify("Fairuz live in Beirut 1970s")
    assert {"lebanese", "arabic"} <= set(c["regions"]) and c["era"] == "70s"
    c = classify("Zidane goals World Cup 1998")
    assert c["topics"][0] == "football"
    assert "sports" in classify("NFL Super Bowl 1996 highlights")["topics"]
    assert "football" not in classify("NFL Super Bowl 1996 highlights")["topics"]
    assert "cars" in classify("Ferrari F40 commercial 1988")["topics"]
    assert "scifi" in classify("The X-Files opening 1993")["topics"]
    assert "japanese" in classify("Dragon Ball opening 1989 anime")["regions"]
    assert "french" in classify("pub années 80", lang="fr")["regions"]


def test_engagement_signal():
    assert engagement(800, 30) < 0                     # swiped away
    assert engagement(25000, 30) > engagement(8000, 30)  # watched more
    assert engagement(20000, 30, unmuted=True) > engagement(20000, 30)
    # duration debiasing: 3 min of a 10 min film is a good view, not a failure
    assert engagement(180000, 600) > 0.3


def test_archive_pick_file_prefers_short_mp4():
    files = [{"name": "reel.mp4", "format": "h.264", "length": "5400", "size": "900000000"},
             {"name": "ad1.mp4", "format": "h.264", "length": "31.2", "size": "4000000"},
             {"name": "ad1.ogv", "format": "Ogg Video", "length": "31.2"},
             {"name": "orig.avi", "format": "Cinepack"}]
    assert pick_file(files)["name"] == "ad1.mp4"
    assert pick_file([{"name": "x.ogv", "format": "Ogg Video"}]) is None


def test_auth_required(client):
    assert client.get("/api/feed").status_code == 401
    assert client.get("/api/auth/me").get_json()["user"] is None


def test_meta_has_taxonomy(client):
    m = client.get("/api/meta").get_json()
    assert len(m["eras"]) == 6 and any(t["id"] == "football" for t in m["topics"])
    assert any(r["id"] == "lebanese" and r["parent"] == "arabic" for r in m["regions"])
    assert m["quick"] and m["channels"]


def test_feed_filters_and_session_paging(client):
    login(client)
    r = client.post("/api/feed", json={"era": ["90s"], "limit": 5, "seed": "a"}).get_json()
    assert len(r["items"]) == 5 and all(i["era"] == "90s" for i in r["items"])
    seen = [i["id"] for i in r["items"]]
    r2 = client.post("/api/feed", json={"era": ["90s"], "limit": 5, "seed": "a", "exclude": seen}).get_json()
    ids = seen + [i["id"] for i in r2["items"]]
    assert len(ids) == len(set(ids))  # no duplicates inside a session
    # 90s items in the fixture: specs 0, 3, 5, 7 -> 12 of 24
    assert len(set(ids)) == 10
    r3 = client.post("/api/feed", json={"era": ["90s"], "limit": 5, "exclude": ids}).get_json()
    assert len(r3["items"]) == 2 and r3["done"]


def test_feed_multi_dimension_filters(client):
    login(client)
    r = client.post("/api/feed", json={"region": ["arabic"], "limit": 20}).get_json()
    assert r["items"] and all(any(x["id"] == "arabic" for x in i["regions"]) for i in r["items"])
    r = client.post("/api/feed", json={"region": ["arabic"], "topic": ["kids"], "limit": 20}).get_json()
    assert r["items"] and all(i["category"] == "kids" for i in r["items"])
    r = client.get("/api/feed?category=football&limit=20").get_json()  # v3 parameter name
    assert r["items"] and all(i["category"] == "football" for i in r["items"])
    assert client.get("/api/feed/count?region=lebanese").get_json()["count"] == 3
    assert client.get("/api/feed?era=classic&limit=20").get_json()["items"]  # v3 era name


def test_unplayable_archive_never_served(client):
    login(client)
    r = client.post("/api/feed", json={"topic": ["ads"], "limit": 20}).get_json()
    assert all(i["external_id"] != "gone" for i in r["items"])


def test_events_learn_taste(client, app):
    login(client)
    first = client.post("/api/feed", json={"limit": 20, "seed": "x"}).get_json()["items"]
    football = [i for i in first if i["category"] == "football"]
    others = [i for i in first if i["category"] != "football"]
    evs = [{"type": "impression", "item_id": i["id"], "watch_ms": 45000, "duration_ms": 30000, "loops": 1,
            "unmuted": True} for i in football]
    evs += [{"type": "impression", "item_id": i["id"], "watch_ms": 600, "duration_ms": 30000} for i in others]
    assert client.post("/api/events", json={"events": evs}).get_json()["n"] == len(evs)
    # fresh session: football should now lead the feed
    nxt = client.post("/api/feed", json={"limit": 6, "seed": "y"}).get_json()["items"]
    lead = [i for i in nxt[:3] if i["category"] == "football"]
    assert lead, [i["category"] for i in nxt]
    with app.app_context():
        it = db.session.get(Item, football[0]["id"])
        assert it.impressions == 1 and it.engagement > 0 and it.duration == 30


def test_broken_reports_hide_dead_videos(client):
    login(client)
    item = client.post("/api/feed", json={"limit": 1}).get_json()["items"][0]
    client.post("/api/events", json={"events": [{"type": "broken", "item_id": item["id"], "code": "yt:150"}]})
    ids = {i["id"] for i in client.post("/api/feed", json={"limit": 20}).get_json()["items"]}
    assert item["id"] not in ids


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
    r = client.get("/api/search?q=Item&live=0&region=latin").get_json()
    assert r["items"] and all(i["category"] == "music" for i in r["items"])


def test_admin_guard_and_prefs(client):
    login(client)
    assert client.post("/api/admin/ingest").status_code == 403
    r = client.put("/api/me/prefs", json={"era": ["90s", "bogus"], "region": ["arabic"], "reverse": True}).get_json()
    p = r["user"]["prefs"]
    assert p["era"] == ["90s"] and p["region"] == ["arabic"] and p["topic"] == []
    login(client, "admin@local.test")
    assert client.get("/api/admin/stats").get_json()["total"] == 25


def test_reclassify_upgrades_old_rows(client, app):
    with app.app_context():
        db.session.add(Item(source="youtube", external_id="old", url="u", title="Spacetoon intro 1996",
                            era="classic", category="tv", tax_v=0))
        db.session.commit()
        from app.store import reclassify
        assert reclassify() == 1
        it = Item.query.filter_by(external_id="old").first()
        assert it.era == "90s" and "|c:spacetoon|" in it.labels and "|t:kids|" in it.labels


def test_cron_requires_secret(client):
    assert client.get("/api/cron/ingest").status_code == 401


def test_archive_renditions_grouped_by_original():
    files = [{"name": "ad.mpeg", "format": "MPEG2", "source": "original"},
             {"name": "ad.mp4", "format": "h.264", "source": "derivative", "original": "ad.mpeg",
              "length": "30", "size": "3000000", "height": "480"},
             {"name": "ad_512kb.mp4", "format": "512Kb MPEG4", "source": "derivative", "original": "ad.mpeg",
              "length": "30", "size": "1200000", "height": "240"},
             {"name": "long.mp4", "format": "h.264", "source": "derivative", "original": "long.mpeg",
              "length": "4000", "size": "400000000"}]
    f = pick_file(files)
    assert f["name"] == "ad.mp4" and f["duration"] == 30
    assert [r[0] for r in f["renditions"]] == ["ad_512kb.mp4", "ad.mp4"]   # lowest bitrate first
    assert f["renditions"][0][1] == 320 and f["renditions"][1][1] == 800


def test_feed_serves_renditions_and_skips_unresolved(client, app):
    with app.app_context():
        db.session.add(Item(source="archive", external_id="clip1", url="https://a/clip1", title="ad 1991",
                            era="90s", category="ads", labels="|t:ads|", tax_v=99, score=0.9,
                            media_url="https://archive.org/download/clip1/a.mp4",
                            media_info={"node": "ia800.us.archive.org/1/items/clip1",
                                        "r": [["a_512kb.mp4", 320, 240], ["a.mp4", 800, 480]]}))
        db.session.add(Item(source="archive", external_id="unknown1", url="https://a/u", title="ad 1992",
                            era="90s", category="ads", labels="|t:ads|", tax_v=99, score=0.9))
        db.session.commit()
    login(client)
    from unittest.mock import patch
    with patch("app.providers.archive.resolve", side_effect=TimeoutError):
        items = client.post("/api/feed", json={"source": ["archive"], "limit": 10}).get_json()["items"]
    assert [i["external_id"] for i in items] == ["clip1"]
    r = items[0]["renditions"]
    assert r[0]["url"] == "https://ia800.us.archive.org/1/items/clip1/a_512kb.mp4"
    assert r[0]["fallback"] == "https://archive.org/download/clip1/a_512kb.mp4" and r[1]["kbps"] == 800


def test_meta_is_edge_cached(client):
    assert "s-maxage" in client.get("/api/meta").headers["Cache-Control"]


def test_follow_boosts_creator_and_survives_prefs(client):
    login(client)
    r = client.post("/api/me/follow", json={"source": "youtube", "author": "Chan3"}).get_json()
    assert r["following"] and r["user"]["prefs"]["follows"] == ["youtube|chan3"]
    client.put("/api/me/prefs", json={"era": ["90s"]})
    assert client.get("/api/auth/me").get_json()["user"]["prefs"]["follows"] == ["youtube|chan3"]
    items = client.post("/api/feed", json={"limit": 8, "seed": "x"}).get_json()["items"]
    assert sum(i["author"] == "chan3" for i in items) >= 2
    assert any("you follow" in (i.get("reason") or "") for i in items)
    r = client.post("/api/me/follow", json={"source": "youtube", "author": "chan3", "on": False}).get_json()
    assert r["user"]["prefs"]["follows"] == []
    assert client.post("/api/me/follow", json={"author": "x"}).status_code == 400


# ---------- v11: hosted clips ----------

def _archive_item(app, **kw):
    with app.app_context():
        it = Item(source="archive", external_id=kw.pop("ext", "hosted1"), url="https://a/h", title="Ad 1991", era="90s",
                  category="ads", labels="|t:ads|", media_url="https://archive.org/download/hosted1/a.mp4",
                  duration=kw.pop("duration", 600), tax_v=99, **kw)
        db.session.add(it)
        db.session.commit()
        return it.id


def test_hosted_clip_is_served_only_when_clips_base_is_set(app):
    iid = _archive_item(app, media_info={"clip": {"v": 1, "from": 48, "s": 60.0, "whole": False}})
    with app.app_context():
        it = db.session.get(Item, iid)
        app.config["CLIPS_BASE"] = ""
        assert it.to_dict()["clip"] is None
        app.config["CLIPS_BASE"] = "http://insecure.example"          # https only
        assert it.to_dict()["clip"] is None
        app.config["CLIPS_BASE"] = "https://opp-clips.pages.dev"
        c = it.to_dict()["clip"]
        assert c == {"url": f"https://opp-clips.pages.dev/c/{iid}.mp4?v=1", "s": 60.0, "from": 48, "whole": False}
        plain = Item(source="archive", external_id="p", url="u", title="t", era="90s", category="ads", tax_v=99)
        assert plain.to_dict()["clip"] is None                        # no clip made yet


def test_hosted_clip_does_not_overwrite_the_videos_real_length(app, client):
    iid = _archive_item(app, ext="nolen", duration=None, media_info={"clip": {"v": 1, "from": 0, "s": 60.0, "whole": False}})
    login(client)
    client.post("/api/events", json={"events": [{"type": "impression", "item_id": iid, "watch_ms": 9000,
                                                  "duration_ms": 60000, "clip_ms": 30000}]})
    with app.app_context():
        assert db.session.get(Item, iid).duration is None


def test_clips_job_picks_start_encodes_and_applies(app, tmp_path, monkeypatch):
    from app import clips
    with app.app_context():
        mk = lambda ext, **kw: Item(source="archive", external_id=ext, url="u", title=ext, era="90s", category=kw.pop("category", "ads"),
                                    labels=kw.pop("labels", "|t:ads|"), media_url=f"https://archive.org/download/{ext}/a.mp4", tax_v=99, **kw)
        song = mk("song", category="music", labels="|t:music|", duration=240, engagement=2.0)
        film = mk("film", duration=7200, engagement=1.0)
        short = mk("short", duration=40, engagement=0.5)
        done = mk("done", duration=100, media_info={"clip": {"v": clips.ENCODE_V, "from": 0, "s": 60, "whole": False}})
        hid = mk("hid", duration=100, hidden=True)
        db.session.add_all([song, film, short, done, hid])
        db.session.commit()
        assert clips.clip_from(song) == 62            # music: first chorus, ~26 %
        assert clips.clip_from(film) == 180           # long film: server start point (past logos)
        assert clips.clip_from(short) == 0
        calls = []

        def fake_encode(src, dst, start, seconds=60):
            calls.append((src.split("/")[4], start))
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(b"x" * 1000)
            return 40.0 if "short" in src else 60.0
        monkeypatch.setattr(clips, "encode", fake_encode)
        out = tmp_path / "c"
        res = clips.run(10, out)
        assert [c[0] for c in calls] == ["song", "film", "short"]   # most engaging first; done/hidden skipped
        assert {r["id"]: r["whole"] for r in res} == {song.id: False, film.id: False, short.id: True}
        assert (out / f"{song.id}.mp4").exists()
        assert clips.apply(res) == 3
        assert db.session.get(Item, song.id).media_info["clip"] == {"v": clips.ENCODE_V, "from": 62, "s": 60.0, "whole": False}
        assert clips.run(10, tmp_path / "again") == []                # everything is done now

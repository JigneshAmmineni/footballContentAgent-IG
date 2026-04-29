"""Fetcher contract tests — mock HTTP so no live API calls."""
from unittest.mock import MagicMock, patch
from pathlib import Path
import json

from app.models.raw_idea import RawIdea


def test_football_data_fetcher_returns_raw_ideas():
    from app.tools.fetchers.football_data import FootballDataFetcher

    mock_matches = {
        "matches": [{
            "id": 1,
            "status": "FINISHED",
            "homeTeam": {"name": "Arsenal"},
            "awayTeam": {"name": "Chelsea"},
            "score": {"fullTime": {"home": 2, "away": 1}},
        }]
    }
    mock_standings = {"standings": [{"table": [
        {"team": {"name": "Arsenal"}, "position": 1},
        {"team": {"name": "Chelsea"}, "position": 2},
        {"team": {"name": "Man City"}, "position": 3},
        {"team": {"name": "Luton"}, "position": 18},
        {"team": {"name": "Burnley"}, "position": 19},
        {"team": {"name": "Sheffield"}, "position": 20},
    ]}]}
    mock_scorers = {"scorers": [{
        "player": {"name": "Erling Haaland"},
        "team": {"name": "Man City"},
        "goals": 30,
    }]}

    responses = [mock_matches, mock_standings, mock_scorers]

    with patch("app.tools.fetchers.football_data.requests.get") as mock_get, \
         patch("app.tools.fetchers.football_data.time.sleep"):
        mock_get.return_value.json.side_effect = responses * 5  # 5 competitions
        mock_get.return_value.raise_for_status = MagicMock()

        fetcher = FootballDataFetcher("fake_token", ["PL"])
        ideas = fetcher.fetch()

    assert len(ideas) > 0
    assert all(isinstance(i, RawIdea) for i in ideas)


def test_reddit_fetcher_returns_raw_ideas():
    from app.tools.fetchers.reddit import RedditFetcher

    mock_response = {
        "data": {
            "children": [
                {"data": {"id": "abc", "title": "Haaland hat-trick", "url": "https://example.com", "permalink": "/r/soccer/abc", "ups": 5000, "link_flair_text": "News"}},
                {"data": {"id": "def", "title": "Transfer deadline", "url": "https://example2.com", "permalink": "/r/soccer/def", "ups": 2000, "link_flair_text": "Transfer"}},
            ]
        }
    }

    with patch("app.tools.fetchers.reddit.requests.get") as mock_get:
        mock_get.return_value.json.return_value = mock_response
        mock_get.return_value.raise_for_status = MagicMock()

        fetcher = RedditFetcher()
        ideas = fetcher.fetch()

    assert len(ideas) > 0
    assert all(isinstance(i, RawIdea) for i in ideas)
    assert all(i.source == "reddit" for i in ideas)


def test_rss_fetcher_returns_raw_ideas():
    from app.tools.fetchers.rss import RssFetcher
    from app.config import RssFeedConfig

    mock_entry = MagicMock()
    mock_entry.get = lambda k, default="": {
        "title": "Arsenal beat Chelsea 2-1",
        "link": "https://bbc.co.uk/sport/football/123",
        "summary": "Arsenal won 2-1",
        "published": "Mon, 27 Apr 2026 12:00:00 GMT",
    }.get(k, default)
    mock_entry.configure_mock(**{
        "media_thumbnail": [],
        "media_content": [],
        "enclosures": [],
    })

    mock_parsed = MagicMock()
    mock_parsed.entries = [mock_entry]

    with patch("app.tools.fetchers.rss.feedparser.parse", return_value=mock_parsed):
        feeds = [RssFeedConfig("bbc", "https://fake.url/rss")]
        fetcher = RssFetcher(feeds)
        ideas = fetcher.fetch()

    assert len(ideas) == 1
    assert ideas[0].source == "rss:bbc"


def test_newsapi_fetcher_returns_raw_ideas():
    from app.tools.fetchers.newsapi import NewsApiFetcher

    mock_response = {
        "articles": [
            {
                "title": "Bellingham on fire in La Liga",
                "description": "Real Madrid star scores again",
                "publishedAt": "2026-04-27T10:00:00Z",
                "source": {"name": "BBC Sport"},
                "url": "https://bbc.co.uk/sport/football/456",
            }
        ]
    }
    with patch("app.tools.fetchers.newsapi.requests.get") as mock_get:
        mock_get.return_value.json.return_value = mock_response
        mock_get.return_value.raise_for_status = MagicMock()
        fetcher = NewsApiFetcher("fake_key")
        ideas = fetcher.fetch()

    assert len(ideas) == 1
    assert ideas[0].source == "newsapi"
    assert ideas[0].source_url == "https://bbc.co.uk/sport/football/456"

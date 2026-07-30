from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import commands


class TestCommands:
    @patch("utils.say_hello", return_value="howdy.")
    def test_handle_hello(self, mock_say_hello):
        result = commands.handle_hello("hello")
        assert result == "howdy."

    def test_handle_date_returns_formatted_when_keyword_present(self):
        result = commands.handle_date("what is the date today")
        assert "Today is" in result

    def test_handle_date_returns_empty_when_no_keyword(self):
        result = commands.handle_date("what is the weather")
        assert result == ""

    def test_handle_date_with_day(self):
        result = commands.handle_date("what day is it")
        assert result.startswith(" ")

    def test_handle_time_returns_formatted_when_keyword_present(self):
        result = commands.handle_time("what time is it")
        assert "It is" in result

    def test_handle_time_returns_empty_when_no_keyword(self):
        result = commands.handle_time("hello")
        assert result == ""

    @patch("pyjokes.get_joke", return_value="Why did the chicken cross the road?")
    def test_handle_joke(self, mock_joke):
        result = commands.handle_joke("tell me a joke")
        assert "chicken" in result

    def test_handle_joke_no_keyword(self):
        result = commands.handle_joke("hello")
        assert result == ""

    def test_handle_about_who_are_you(self):
        result = commands.handle_about("who are you")
        assert "Hollali" in result

    def test_handle_about_your_name(self):
        result = commands.handle_about("what is your name")
        assert "Hollali" in result

    def test_handle_about_made_you(self):
        result = commands.handle_about("who made you")
        assert "Deon" in result

    def test_handle_about_how_are_you(self):
        result = commands.handle_about("how are you")
        assert "awesome" in result

    def test_handle_about_no_match(self):
        result = commands.handle_about("hello world")
        assert result == ""

    def test_handle_pizza(self):
        result = commands.handle_pizza("order pizza")
        assert "no longer supported" in result

    def test_handle_pizza_no_keyword(self):
        result = commands.handle_pizza("hello")
        assert result == ""

    @patch("webbrowser.open")
    def test_handle_open_youtube(self, mock_web):
        result = commands.handle_open("open youtube")
        assert "Youtube" in result
        mock_web.assert_called_with("https://youtube.com/")

    @patch("webbrowser.open")
    def test_handle_open_google(self, mock_web):
        result = commands.handle_open("open google")
        assert "Google" in result
        mock_web.assert_called_with("https://google.com/")

    @patch("webbrowser.open")
    def test_handle_open_no_keyword(self, mock_web):
        result = commands.handle_open("hello")
        assert result == ""
        mock_web.assert_not_called()

    def test_handle_exit_raises_system_exit(self):
        with pytest.raises(SystemExit):
            commands.handle_exit("exit")

    def test_handle_exit_with_quit(self):
        with pytest.raises(SystemExit):
            commands.handle_exit("quit")

    def test_handle_exit_no_keyword(self):
        result = commands.handle_exit("hello")
        assert result is None

    @patch("webbrowser.open")
    def test_handle_youtube_search(self, mock_web):
        result = commands.handle_youtube_search("youtube never gonna give you up")
        assert "never gonna give you up" in result
        mock_web.assert_called_once()

    def test_handle_youtube_search_no_keyword(self):
        result = commands.handle_youtube_search("hello")
        assert result == ""

    @patch("webbrowser.open")
    def test_handle_google_search(self, mock_web):
        result = commands.handle_google_search("search python tutorials")
        assert "python tutorials" in result
        mock_web.assert_called_once()

    def test_handle_google_search_no_keyword(self):
        result = commands.handle_google_search("hello")
        assert result == ""

    @patch("webbrowser.open")
    def test_handle_where_is(self, mock_web):
        result = commands.handle_where_is("where is Paris")
        assert "Paris" in result
        mock_web.assert_called_once()

    def test_handle_where_is_no_keyword(self):
        result = commands.handle_where_is("hello")
        assert result == ""

    @patch("utils.talk")
    def test_handle_sleep_no_keyword(self, mock_talk):
        result = commands.handle_sleep("hello")
        assert result == ""
        mock_talk.assert_not_called()

    @patch("utils.talk")
    def test_handle_change_background_no_keyword(self, mock_talk):
        result = commands.handle_change_background("hello")
        assert result == ""
        mock_talk.assert_not_called()

    @patch("requests.get")
    def test_handle_weather_missing_api_key(self, mock_get):
        with patch("config.WEATHER_API_KEY", ""):
            result = commands.handle_weather("weather in London")
            assert "not configured" in result
            mock_get.assert_not_called()

    def test_handle_weather_no_keyword(self):
        result = commands.handle_weather("hello")
        assert result == ""

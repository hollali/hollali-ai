from __future__ import annotations

from unittest.mock import patch

import utils


class TestUtils:
    def test_today_date_format(self):
        date_str = utils.today_date()
        assert date_str.startswith("Today is")
        assert "the" in date_str

    def test_say_hello_matches(self):
        result = utils.say_hello("hello there")
        assert result.endswith(".")
        assert result[:-1] in ("howdy", "whats good", "hello", "hey there")

    def test_say_hello_nomatch(self):
        assert utils.say_hello("goodbye") == ""

    def test_say_hello_case_insensitive(self):
        result = utils.say_hello("HELLO world")
        assert result != ""

    def test_say_hello_hola(self):
        result = utils.say_hello("hola amigo")
        assert result.endswith(".")

    def test_say_hello_greetings(self):
        result = utils.say_hello("greetings")
        assert result.endswith(".")

    def test_wiki_person_extracts_name(self):
        result = utils.wiki_person("who is Albert Einstein")
        assert result == "Albert Einstein"

    def test_wiki_person_two_words(self):
        result = utils.wiki_person("who is John F Kennedy")
        assert result == "John F"

    def test_wiki_person_no_match(self):
        assert utils.wiki_person("what is the weather") is None

    def test_wiki_person_edge_case(self):
        assert utils.wiki_person("who") is None

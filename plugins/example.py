from __future__ import annotations


class ExamplePlugin:
    name = "Example"
    keywords = ["example", "test plugin"]

    def handle(self, text: str) -> str | None:
        return "This is an example plugin. It works!"

from erbs_plugin.models import CardPayload
from erbs_plugin.rendering import TextRenderer


def test_text_renderer() -> None:
    result = TextRenderer().render(CardPayload(kind="player", title="Kanami"))
    assert '"title": "Kanami"' in result

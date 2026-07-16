import pytest

from src.api.post import translation
from src.api.post.translation import PostTranslator, TranslationOutput, TranslationUnavailableError
from src.core.config import Settings


class FakeStructuredModel:
    def __init__(self, output: TranslationOutput) -> None:
        self.output = output
        self.messages = []

    async def ainvoke(self, messages):
        self.messages = messages
        return self.output


class FakeChatOpenAI:
    structured_model = FakeStructuredModel(TranslationOutput(title="Translated title", content="Translated content"))

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def with_structured_output(self, schema, method: str, strict: bool):
        assert schema is TranslationOutput
        assert method == "json_schema"
        assert strict is True
        return self.structured_model


@pytest.mark.asyncio
async def test_post_translator_preserves_original_and_translates_target_language(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(translation, "ChatOpenAI", FakeChatOpenAI)
    translator = PostTranslator(Settings(openai_api_key="openai-test", openai_model="gpt-test"))

    korean = await translator.translate("부산 야경", "광안대교가 아름다워요")
    english = await translator.translate("Busan night view", "The bridge is beautiful")

    assert korean.title_kr == "부산 야경"
    assert korean.title_en == "Translated title"
    assert korean.content_kr == "광안대교가 아름다워요"
    assert korean.content_en == "Translated content"
    assert english.title_en == "Busan night view"
    assert english.title_kr == "Translated title"
    assert english.content_en == "The bridge is beautiful"
    assert english.content_kr == "Translated content"
    assert "Do not summarize" in FakeChatOpenAI.structured_model.messages[0].content


@pytest.mark.asyncio
async def test_post_translator_requires_openai_configuration() -> None:
    translator = PostTranslator(Settings(openai_api_key=None, openai_model=None))

    with pytest.raises(TranslationUnavailableError):
        await translator.translate("제목", "본문")

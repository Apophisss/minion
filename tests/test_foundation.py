from minion.models import ServerSpec, slugify
from minion.secrets import MissingSecret


async def test_db_and_secrets(services):
    await services.secrets.set("TOKEN_X", "abcdef123")
    resolved = await services.secrets.resolve({"h": "Bearer ${secret:TOKEN_X}"})
    assert resolved == {"h": "Bearer abcdef123"}
    assert services.secrets.referenced(["${secret:A}", {"x": "${secret:B}"}]) == ["A", "B"]
    try:
        await services.secrets.resolve("${secret:MISSING_ONE}")
    except MissingSecret as exc:
        assert exc.names == ["MISSING_ONE"]
    else:
        raise AssertionError("expected MissingSecret")
    assert "***" in await services.secrets.redact("key=abcdef123")
    await services.db.kv_set("a", {"b": 1})
    assert await services.db.kv_get("a") == {"b": 1}


def test_models():
    assert ServerSpec(name="github", command="npx").transport == "stdio"
    assert slugify("My Cool Tool!") == "my-cool-tool"


def test_settings(settings):
    assert settings.catalog_dir.name == "catalog"
    assert settings.gateway_url.endswith("/mcp")

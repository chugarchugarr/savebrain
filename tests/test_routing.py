from tro_frontier.routing import ModelRouter


def test_luna_terra_sol_route(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_LUNA", "luna-test")
    monkeypatch.setenv("MODEL_TERRA", "terra-test")
    monkeypatch.setenv("MODEL_SOL", "sol-test")
    router = ModelRouter.from_manifest(
        {
            "default_model": "sol-default",
            "route": [
                {"name": "luna", "model_env": "MODEL_LUNA", "default_model": "luna", "start_repair": 0},
                {"name": "terra", "model_env": "MODEL_TERRA", "default_model": "terra", "start_repair": 1},
                {"name": "sol", "model_env": "MODEL_SOL", "default_model": "sol", "start_repair": 2},
            ],
        }
    )
    assert router.select(0).model == "luna-test"
    assert router.select(1).model == "terra-test"
    assert router.select(2).model == "sol-test"
    assert [event["tier"] for event in router.history] == ["luna", "terra", "sol"]

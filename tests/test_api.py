from fastapi.testclient import TestClient

from heatwin.api import app

client = TestClient(app)


def test_run_returns_real_simulation_and_twin():
    response = client.post(
        "/api/run",
        json={"duration": 90, "setpoint": 57, "fault": "sensor_bias", "fault_time": 50},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["runs"]["PID"]["samples"]) == 91
    before = body["runs"]["PID"]["samples"][49]
    after = body["runs"]["PID"]["samples"][50]
    assert after["measurement"] - after["tc"] == 2
    assert before["valve"] != after["valve"]
    assert "twin" in after and "alarm" in after


def test_compare_runs_share_time_and_initial_conditions():
    response = client.post("/api/run", json={"duration": 90, "compare": True})
    assert response.status_code == 200
    runs = response.json()["runs"]
    assert set(runs) == {"P", "PI", "PID"}
    assert len({run["samples"][0]["tc"] for run in runs.values()}) == 1
    assert len({run["samples"][-1]["time"] for run in runs.values()}) == 1


def test_api_rejects_invalid_parameters():
    assert client.post("/api/run", json={"duration": -1}).status_code == 422


def test_noise_is_injected_only_after_configured_time():
    samples = client.post(
        "/api/run", json={"duration": 90, "fault": "noise", "fault_time": 50}
    ).json()["runs"]["PID"]["samples"]
    assert samples[49]["measurement"] == samples[49]["tc"]
    assert samples[50]["measurement"] != samples[50]["tc"]


def test_configurable_initial_state_is_used_and_validated():
    body = client.post(
        "/api/run", json={"duration": 90, "initial_state": [45, 70, 0.5]}
    ).json()
    initial = body["runs"]["PID"]["samples"][0]
    assert [initial["tc"], initial["th"], initial["valve"]] == [45, 70, 0.5]
    assert (
        client.post("/api/run", json={"initial_state": [45, 70, 2]}).status_code == 422
    )

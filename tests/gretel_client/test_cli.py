import os

from typing import Callable
from unittest.mock import MagicMock, patch

import pytest

from click.testing import CliRunner

from gretel_client.cli.cli import cli
from gretel_client.cli.common import ModelObjectReader
from gretel_client.config import (
    ClientConfig,
    configure_session,
    get_session_config,
    GRETEL_API_KEY,
    GRETEL_CONFIG_FILE,
    GRETEL_ENDPOINT,
    GRETEL_PROJECT,
)
from gretel_client.projects.exceptions import DockerEnvironmentError
from gretel_client.projects.jobs import Status


@pytest.fixture
def runner() -> CliRunner:
    """Returns a CliRunner that can be used to invoke the CLI from
    unit tests.
    """
    return CliRunner()


@patch("gretel_client.cli.cli.write_config")
def test_configure_env(write_config: MagicMock, runner: CliRunner):
    orig_api, orig_proj, orig_endpoint = "orig_api", "orig_proj", "orig_endpoint"
    new_api, new_proj, new_endpoint = "new_api", "new_proj", "http:/new_endpoint"

    with patch.dict(
        os.environ,
        {
            GRETEL_API_KEY: orig_api,
            GRETEL_ENDPOINT: orig_endpoint,
            GRETEL_PROJECT: orig_proj,
            GRETEL_CONFIG_FILE: "none",
        },
    ):
        configure_session(ClientConfig())
        assert get_session_config().api_key == orig_api
        assert get_session_config().endpoint == orig_endpoint
        assert get_session_config().default_project_name == orig_proj
        cmd = runner.invoke(
            cli,
            [
                "configure",
                "--api-key",
                new_api,
                "--endpoint",
                new_endpoint,
                "--project",
                new_proj,
            ],
        )

    assert get_session_config().api_key == new_api
    assert get_session_config().endpoint == "https://new_endpoint"
    assert get_session_config().default_project_name == new_proj
    assert not get_session_config().preview_features_enabled
    assert cmd.exit_code == 0


@pytest.fixture
def get_project() -> MagicMock:
    with patch("gretel_client.cli.common.get_project") as get_project:
        get_project_mock = get_project.return_value.create_model_obj.return_value
        get_project_mock._submit.return_value = {"model_key": ""}
        get_project_mock.print_obj = {}
        get_project_mock.billing_details = {}
        get_project_mock.peek_report.return_value = {}
        get_project_mock.status = Status.COMPLETED
        get_project_mock._data = {}

        model = get_project.return_value.create_model_obj.return_value
        model._submit.return_value = model

        yield get_project


@pytest.fixture
def container_run() -> MagicMock:
    with patch("gretel_client.cli.models.ContainerRun") as container_run:
        yield container_run


def test_local_model_upload_flag(
    container_run: MagicMock, get_project: MagicMock, runner: CliRunner
):
    cmd = runner.invoke(
        cli,
        [
            "models",
            "create",
            "--upload-model",
            "--runner",
            "local",
            "--config",
            "synthetics/default",
            "--output",
            "tmp",
            "--project",
            "mocked",
        ],
    )
    assert cmd.exit_code == 0
    assert container_run.from_job.return_value.start.call_count == 1
    assert container_run.from_job.return_value.enable_cloud_uploads.call_count == 1


def test_local_model_upload_disabled_by_default(
    container_run: MagicMock, get_project: MagicMock, runner: CliRunner
):
    cmd = runner.invoke(
        cli,
        [
            "models",
            "create",
            "--runner",
            "local",
            "--config",
            "synthetics/default",
            "--output",
            "tmp",
            "--project",
            "mocked",
        ],
    )
    assert cmd.exit_code == 0
    assert container_run.from_job.return_value.start.call_count == 1
    assert container_run.from_job.return_value.enable_cloud_uploads.call_count == 0


def test_does_read_model_json(runner: CliRunner, get_fixture: Callable):
    output = get_fixture("xf_model_create_output.json")
    sc = MagicMock()
    sc.model.data_source = "test.csv"
    model_obj = ModelObjectReader(output)
    model_obj.apply(sc)
    sc.in_data == "test.csv"
    sc.runner == "local"
    sc.set_project.assert_called_once_with("60b9a37000f67523d00b944c")
    sc.set_model.assert_called_once_with("60dca3d09c03f7c6edadee91")


def test_does_read_model_object_id():
    sc = MagicMock()
    model_obj = ModelObjectReader("test_id")
    model_obj.apply(sc)
    sc.set_model.assert_called_once_with("test_id")
    sc.data_source = None
    sc.runner = None


def test_does_read_model_object_str(get_fixture: Callable):
    output = get_fixture("xf_model_create_output.json")
    model_obj = ModelObjectReader(output.read_text())
    assert model_obj.model.get("uid") == "60dca3d09c03f7c6edadee91"


@patch("gretel_client.cli.common.check_docker_env")
def test_does_gracefully_handler_docker_errors(
    check_docker_env: MagicMock, runner: CliRunner
):
    check_docker_env.side_effect = DockerEnvironmentError()
    cmd = runner.invoke(
        cli,
        [
            "models",
            "create",
            "--runner",
            "local",
            "--config",
            "synthetics/default",
            "--output",
            "tmp",
            "--project",
            "mocked",
        ],
    )
    check_docker_env.assert_called_once()
    assert cmd.exit_code == 1
    assert "docker is not running" in cmd.output


def test_can_name_model(get_project: MagicMock, runner: CliRunner):
    cmd = runner.invoke(
        cli,
        [
            "models",
            "create",
            "--config",
            "synthetics/default",
            "--name",
            "test-project",
        ],
    )
    assert cmd.exit_code == 0
    assert get_project.return_value.create_model_obj.return_value.name == "test-project"

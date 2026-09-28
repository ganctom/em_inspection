from pathlib import Path

import pytest

from em_inspection.experiment_configs import (
    ExpConfig,
    ExperimentRegistry,
    ExperimentRegistryError,
    get_experiments_yaml_path,
    get_purge_command_variants,
)
from em_inspection.interactive_inspector.data_service import DataService


@pytest.fixture
def temp_registry_env(tmp_path, monkeypatch):
    """Provides an isolated registry pointing to a temporary YAML file."""
    yaml_file = tmp_path / "experiments.yaml"
    monkeypatch.setenv("EM_INSPECTION_CONFIG", str(yaml_file))

    # Seed with sample experiments
    registry = ExperimentRegistry()
    acq1 = tmp_path / "acq1"
    proc1 = tmp_path / "proc1"
    proc1.mkdir(parents=True, exist_ok=True)

    exp1 = ExpConfig(
        name="test_exp_1",
        acq_dir=str(acq1),
        proc_dir=str(proc1),
        grid_num=0,
        grid_shape=[10, 10],
        first_sec=1,
        last_sec=10,
        pixel_size=10.0,
        cut_thickness=25.0,
    )
    registry.add(exp1)
    registry.save_user_experiments()

    return registry, tmp_path, exp1


def test_delete_experiment_registry_only(temp_registry_env):
    registry, tmp_path, exp1 = temp_registry_env

    assert "test_exp_1" in registry.get_all()
    proc_path = Path(exp1.proc_dir)
    assert proc_path.exists()

    success, trashed, proc_existed = registry.delete(
        "test_exp_1", quarantine_proc_dir=False
    )
    assert success is True
    assert trashed is None
    assert proc_existed is True
    assert "test_exp_1" not in registry.get_all()

    # Disk directory should remain untouched
    assert proc_path.exists()

    # Verify disk persistence
    new_reg = ExperimentRegistry()
    assert "test_exp_1" not in new_reg.get_all()


def test_delete_experiment_with_quarantine(temp_registry_env):
    registry, tmp_path, exp1 = temp_registry_env
    proc_path = Path(exp1.proc_dir)
    sample_file = proc_path / "section.yaml"
    sample_file.write_text("hello: world")

    success, trashed, proc_existed = registry.delete(
        "test_exp_1", quarantine_proc_dir=True
    )
    assert success is True
    assert trashed is not None
    assert proc_existed is True
    assert ".trash_test_exp_1" in trashed

    # Original proc_path should be gone, renamed to trashed
    assert not proc_path.exists()
    trashed_path = Path(trashed)
    assert trashed_path.exists()
    assert (trashed_path / "section.yaml").read_text() == "hello: world"


def test_delete_experiment_quarantine_proc_dir_not_found(temp_registry_env):
    registry, tmp_path, _ = temp_registry_env

    missing_proc = tmp_path / "does_not_exist_dir"
    exp_missing = ExpConfig(
        name="missing_proc_exp",
        acq_dir=str(tmp_path / "acq"),
        proc_dir=str(missing_proc),
        grid_num=0,
        grid_shape=[5, 5],
        first_sec=1,
        last_sec=5,
        pixel_size=10.0,
        cut_thickness=25.0,
    )
    registry.add(exp_missing)

    assert not missing_proc.exists()
    success, trashed, proc_existed = registry.delete(
        "missing_proc_exp", quarantine_proc_dir=True
    )
    assert success is True
    assert trashed is None
    assert proc_existed is False
    assert "missing_proc_exp" not in registry.get_all()


def test_delete_nonexistent_raises(temp_registry_env):
    registry, _, _ = temp_registry_env
    with pytest.raises(ExperimentRegistryError, match="does not exist in registry"):
        registry.delete("non_existent_exp")


def test_safety_check_acq_dir_equals_proc_dir(tmp_path, monkeypatch):
    yaml_file = tmp_path / "experiments.yaml"
    monkeypatch.setenv("EM_INSPECTION_CONFIG", str(yaml_file))

    same_dir = tmp_path / "shared_folder"
    same_dir.mkdir(parents=True, exist_ok=True)

    registry = ExperimentRegistry()
    exp = ExpConfig(
        name="unsafe_exp",
        acq_dir=str(same_dir),
        proc_dir=str(same_dir),
        grid_num=0,
        grid_shape=[5, 5],
        first_sec=1,
        last_sec=5,
        pixel_size=10.0,
        cut_thickness=25.0,
    )
    registry.add(exp)

    with pytest.raises(ExperimentRegistryError, match="identical to acq_dir"):
        registry.delete("unsafe_exp", quarantine_proc_dir=True)


def test_safety_check_root_or_home(tmp_path, monkeypatch):
    yaml_file = tmp_path / "experiments.yaml"
    monkeypatch.setenv("EM_INSPECTION_CONFIG", str(yaml_file))

    registry = ExperimentRegistry()
    exp = ExpConfig(
        name="root_exp",
        acq_dir=str(tmp_path / "acq"),
        proc_dir=str(Path.home()),
        grid_num=0,
        grid_shape=[5, 5],
        first_sec=1,
        last_sec=5,
        pixel_size=10.0,
        cut_thickness=25.0,
    )
    registry.add(exp)

    with pytest.raises(
        ExperimentRegistryError, match="Refusing to quarantine root or home"
    ):
        registry.delete("root_exp", quarantine_proc_dir=True)


def test_data_service_delete_resets_session(temp_registry_env):
    registry, tmp_path, exp1 = temp_registry_env

    service = DataService()
    service.exp_config = exp1
    service.service_initialized = True

    success, trashed, proc_existed = service.delete_experiment(
        "test_exp_1", quarantine_proc_dir=False
    )
    assert success is True
    assert trashed is None
    assert proc_existed is True
    assert service.exp_config is None
    assert service.service_initialized is False


def test_purge_commands_with_volumes_prefix():
    path = "/Volumes/tungstenfs/scratch/data/.trash_exp_123"
    variants = get_purge_command_variants(path)

    assert len(variants) == 2

    # Variant 1: macOS / Client mount
    assert variants[0].label == "macOS / Client Mount"
    assert variants[0].path == path
    assert variants[0].command == f"rm -rf '{path}'"
    assert "apple" in variants[0].icon

    # Variant 2: Linux server / cluster
    assert variants[1].label == "Linux Server / Cluster (SSH)"
    assert variants[1].path == "/tungstenfs/scratch/data/.trash_exp_123"
    assert variants[1].command == "rm -rf '/tungstenfs/scratch/data/.trash_exp_123'"
    assert "terminal" in variants[1].icon


def test_purge_commands_without_volumes_prefix():
    path = "/Users/testuser/experiments/.trash_exp_123"
    variants = get_purge_command_variants(path)

    # Should gracefully collapse to 1 single canonical command
    assert len(variants) == 1
    assert variants[0].label == "Terminal Purge Command"
    assert variants[0].path == path
    assert variants[0].command == f"rm -rf '{path}'"


def test_purge_commands_custom_mapping(monkeypatch):
    monkeypatch.setenv(
        "EM_REMOTE_MOUNT_MAP",
        '{"/Volumes/my_storage": "/mnt/cluster_storage"}',
    )
    path = "/Volumes/my_storage/dataset/.trash_exp_123"
    variants = get_purge_command_variants(path)

    assert len(variants) == 2
    assert variants[0].path == "/Volumes/my_storage/dataset/.trash_exp_123"
    assert variants[1].path == "/mnt/cluster_storage/dataset/.trash_exp_123"
    assert variants[1].command == "rm -rf '/mnt/cluster_storage/dataset/.trash_exp_123'"


def test_purge_commands_safe_quote_escaping():
    path = "/Volumes/share/alice's_exp/.trash_exp_123"
    variants = get_purge_command_variants(path)

    assert len(variants) == 2
    # Ensure single quote is safely escaped for shell
    assert (
        variants[0].command == "rm -rf '/Volumes/share/alice'\\''s_exp/.trash_exp_123'"
    )
    assert variants[1].command == "rm -rf '/share/alice'\\''s_exp/.trash_exp_123'"


def test_purge_commands_empty():
    assert get_purge_command_variants("") == []
    assert get_purge_command_variants("   ") == []


def test_get_experiments_yaml_path_default(monkeypatch):
    monkeypatch.delenv("EM_INSPECTION_CONFIG", raising=False)
    path = get_experiments_yaml_path()
    assert isinstance(path, Path)
    assert path.name == "experiments.yaml"
    assert ".em_inspection" in str(path)


def test_get_experiments_yaml_path_custom_env(tmp_path, monkeypatch):
    custom_yaml = tmp_path / "custom_dir" / "my_experiments.yaml"
    monkeypatch.setenv("EM_INSPECTION_CONFIG", str(custom_yaml))

    path = get_experiments_yaml_path()
    assert path == custom_yaml

    reg = ExperimentRegistry()
    assert reg.config_path == custom_yaml

    svc = DataService()
    assert svc.config_path == custom_yaml

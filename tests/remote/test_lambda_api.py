import pytest

from saage.remote.lambda_api import LambdaError, pick_instance_type


def _avail(**types):
    """types: name=(cents_per_hour, [regions])"""
    return {
        name: {
            "instance_type": {"price_cents_per_hour": cents},
            "regions_with_capacity_available": [{"name": r} for r in regions],
        }
        for name, (cents, regions) in types.items()
    }


def test_auto_picks_cheapest_with_capacity():
    avail = _avail(gpu_1x_h100_pcie=(249, ["us-east-1"]),
                   gpu_1x_a10=(75, ["us-west-1"]),
                   gpu_1x_a100=(129, []))           # no capacity -> skipped
    assert pick_instance_type(avail, "auto") == ("gpu_1x_a10", "us-west-1", 0.75)


def test_gpu_class_preference_order():
    avail = _avail(gpu_1x_a100_sxm4=(129, []),       # preferred but no capacity
                   gpu_1x_a100=(110, ["us-east-1"]))
    assert pick_instance_type(avail, "a100") == ("gpu_1x_a100", "us-east-1", 1.10)


def test_exact_type_name_works():
    avail = _avail(gpu_1x_gh200=(149, ["us-east-3"]))
    assert pick_instance_type(avail, "gpu_1x_gh200") == ("gpu_1x_gh200", "us-east-3", 1.49)


def test_no_capacity_error_lists_alternatives():
    avail = _avail(gpu_1x_a10=(75, []), gpu_1x_h100_pcie=(249, ["us-east-1"]))
    with pytest.raises(LambdaError, match="gpu_1x_h100_pcie"):
        pick_instance_type(avail, "a10")

"""Recursive masking of sensitive personal fields in log output."""

from __future__ import annotations

from pet_hospital_mcp.logging_config import mask_recursive


def test_masks_sensitive_fields():
    sample = {
        "tool_name": "list_pets",
        "params": {
            "ownerName": "张三",
            "ownerPhone": "13800001111",
            "ownerAddr": "成都市武侯区",
            "chipNo": "CHIP-123",
            "owner_phone": "13900000000",
            "owner_addr": "某地",
            "chip_no": "CHIP-456",
            "name": "旺财",
            "species": "犬",
        },
        "status": "ok",
    }
    masked = mask_recursive(sample)
    assert masked["params"]["ownerPhone"] == "***"
    assert masked["params"]["ownerAddr"] == "***"
    assert masked["params"]["chipNo"] == "***"
    assert masked["params"]["owner_phone"] == "***"
    assert masked["params"]["owner_addr"] == "***"
    assert masked["params"]["chip_no"] == "***"
    # Non-sensitive values are untouched
    assert masked["params"]["name"] == "旺财"
    assert masked["params"]["species"] == "犬"
    assert masked["params"]["ownerName"] == "张三"
    assert masked["tool_name"] == "list_pets"


def test_masking_handles_lists_and_primitives():
    masked = mask_recursive(
        {"items": [{"ownerPhone": "138", "chipNo": "C1"}, "plain", 42, None]}
    )
    assert masked["items"][0]["ownerPhone"] == "***"
    assert masked["items"][0]["chipNo"] == "***"
    assert masked["items"][1] == "plain"
    assert masked["items"][2] == 42
    assert masked["items"][3] is None

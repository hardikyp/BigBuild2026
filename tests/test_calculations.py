from app.services.shear_wall_calculation import calculate_average_shear_stress
from tests.conftest import create_assessment


def calculation_inputs():
    return {
        "direction": "X",
        "units": "ksf",
        "building_system": "Shear wall (S4, S5, C2, C3, PC1a, PC2, RM2, URMa)",
        "story_band": "2",
        "spectral_acceleration": "0.2",
        "seismic_weight": "1000",
        "period": "0.5",
        "use_six_story_simplification": False,
        "levels": [
            {"level": "1", "weight": "1000", "height": "10"},
            {"level": "2", "weight": "1000", "height": "20"},
        ],
        "story_level": "1",
        "wall_category": "Reinforced concrete / precast concrete / wood / reinforced masonry / cold-formed steel",
        "performance": "Collapse Prevention (CP)",
        "material": "Concrete / reinforced masonry / cold-formed steel",
        "walls": [{"name": "W1", "length": "10", "thickness": "8"}],
        "notes": "Two-level sample",
    }


def test_guided_calculation_matches_reference_formula():
    result = calculate_average_shear_stress(calculation_inputs())

    assert result["modification_factor_C"] == 1.2
    assert result["base_shear_V_kips"] == 240.0
    assert result["story_shear_Vj_kips"] == 240.0
    assert result["modifier_Ms"] == 4.5
    assert result["effective_wall_measure"] == 6.666666666666667
    assert round(result["average_shear_stress"], 4) == 8.0


def test_shear_calculation_window_saves_explicit_determination_and_exports(client):
    assessment_id = create_assessment(client, performance="IO", building_type="C2", seismicity="high")
    item_id = "17-12io-typec2-item-003"
    page = client.get(f"/assessments/{assessment_id}/calculations/shear-wall?item_id={item_id}")

    assert page.status_code == 200
    assert b"Average shear stress check" in page.data
    assert b"new window" not in page.data.lower()

    data = calculation_inputs()
    data.update({
        "item_id": item_id,
        "engineer_determination": "NC",
        "level_number_1": "1",
        "level_weight_1": "1000",
        "level_height_1": "10",
        "level_number_2": "2",
        "level_weight_2": "1000",
        "level_height_2": "20",
        "wall_name_1": "W1",
        "wall_length_1": "10",
        "wall_thickness_1": "8",
    })
    # The route consumes the flattened form fields rather than the service's
    # nested test input shape.
    response = client.post(
        f"/assessments/{assessment_id}/calculations/shear-wall?item_id={item_id}",
        data={
            "item_id": item_id,
            "direction": "X",
            "units": "ksf",
            "building_system": data["building_system"],
            "story_band": "2",
            "spectral_acceleration": "0.2",
            "seismic_weight": "1000",
            "period": "0.5",
            "story_level": "1",
            "wall_category": data["wall_category"],
            "performance": data["performance"],
            "material": data["material"],
            "level_number_1": "1",
            "level_weight_1": "1000",
            "level_height_1": "10",
            "level_number_2": "2",
            "level_weight_2": "1000",
            "level_height_2": "20",
            "wall_name_1": "W1",
            "wall_length_1": "10",
            "wall_thickness_1": "8",
            "engineer_determination": "NC",
            "notes": "Review wall line W1.",
        },
    )
    assert response.status_code == 302

    payload = client.get(f"/assessments/{assessment_id}/export.json").get_json()
    assert len(payload["calculations"]) == 1
    record = payload["calculations"][0]
    assert record["engineer_determination"] == "NC"
    assert record["result"]["average_shear_stress"] == 8.0
    assert record["source_reference"].endswith("asce41_4433_shear_wall_app_TABLE47_FIXED.py")

    summary = client.get(f"/assessments/{assessment_id}/summary")
    assert b"Average shear stress records" in summary.data
    pdf = client.get(f"/assessments/{assessment_id}/export.pdf")
    assert pdf.status_code == 200
    assert b"%PDF" == pdf.data[:4]

#!/usr/bin/env python3
"""Validate the structural contract of a photo-deconstruct-svg output."""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


SVG_NS = "{http://www.w3.org/2000/svg}"


def numeric_dimension(value: str | None) -> int | None:
    if value is None:
        return None
    match = re.fullmatch(r"([0-9]+)(?:px)?", value.strip())
    return int(match.group(1)) if match else None


def path_coordinate_bounds(path_data: str) -> tuple[float, float, float, float] | None:
    numbers = [
        float(value)
        for value in re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", path_data)
    ]
    if len(numbers) < 2 or len(numbers) % 2:
        return None
    x_values = numbers[0::2]
    y_values = numbers[1::2]
    return min(x_values), min(y_values), max(x_values), max(y_values)


def path_bleeds_past_edges(
    bounds: tuple[float, float, float, float] | None,
    edges: list[str],
    width: int | None,
    height: int | None,
) -> bool:
    if bounds is None or width is None or height is None:
        return not edges
    minimum_x, minimum_y, maximum_x, maximum_y = bounds
    return all(
        {
            "left": minimum_x < 0.0,
            "right": maximum_x > width,
            "top": minimum_y < 0.0,
            "bottom": maximum_y > height,
        }.get(edge, False)
        for edge in edges
    )


def nested_json_keys(value: object) -> list[str]:
    """Collect JSON object keys without treating source filenames as metadata."""
    if isinstance(value, dict):
        keys = [str(key).lower() for key in value]
        for child in value.values():
            keys.extend(nested_json_keys(child))
        return keys
    if isinstance(value, list):
        keys: list[str] = []
        for child in value:
            keys.extend(nested_json_keys(child))
        return keys
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("svg", type=Path)
    parser.add_argument("--analysis", type=Path)
    args = parser.parse_args()

    if not args.svg.is_file():
        raise SystemExit(f"SVG not found: {args.svg}")
    try:
        root = ET.parse(args.svg).getroot()
    except ET.ParseError as exc:
        raise SystemExit(f"Invalid XML: {exc}") from exc

    width = numeric_dimension(root.get("width"))
    height = numeric_dimension(root.get("height"))
    view_box = root.get("viewBox", "").split()
    tags = [element.tag.rsplit("}", 1)[-1].lower() for element in root.iter()]
    paths = root.findall(f".//{SVG_NS}path")
    rendered_paths = root.findall(f".//{SVG_NS}g[@id='source-derived-fields']/{SVG_NS}path")
    rendered_by_id = {path.get("id", ""): path for path in rendered_paths}
    rendered_bounds_by_id = {
        path_id: path_coordinate_bounds(path.get("d", ""))
        for path_id, path in rendered_by_id.items()
    }
    highlight_group = root.findall(f"./{SVG_NS}g[@id='point-highlights']")
    circles = (
        highlight_group[0].findall(f"./{SVG_NS}circle") if len(highlight_group) == 1 else []
    )
    turbulence = root.findall(f".//{SVG_NS}feTurbulence")
    gaussian_blurs = root.findall(f".//{SVG_NS}feGaussianBlur")
    patterns = root.findall(f".//{SVG_NS}pattern")
    pattern_ids = {pattern.get("id", "") for pattern in patterns}
    pattern_ellipses = root.findall(f".//{SVG_NS}pattern//{SVG_NS}ellipse")
    pattern_paths = root.findall(f".//{SVG_NS}pattern//{SVG_NS}path")
    gradients = root.findall(f".//{SVG_NS}linearGradient")
    gradient_ids = [gradient.get("id", "") for gradient in gradients]
    surface_noise_rect = root.findall(f"./{SVG_NS}rect[@id='surface-noise-layer']")
    surface_noise_group = root.findall(f"./{SVG_NS}g[@id='surface-noise-layer']")
    surface_noise = surface_noise_rect + surface_noise_group
    traditional_grain_overlay = root.findall(
        f"./{SVG_NS}g[@id='surface-noise-layer']/{SVG_NS}rect[@id='traditional-grain-overlay']"
    )
    root_children = list(root)
    forbidden = sorted(set(tags) & {"image", "canvas", "foreignobject"})

    checks = {
        "root_is_svg": root.tag == f"{SVG_NS}svg",
        "positive_dimensions": bool(width and height and width > 0 and height > 0),
        "viewbox_matches_dimensions": bool(
            width
            and height
            and len(view_box) == 4
            and view_box[:2] == ["0", "0"]
            and [round(float(view_box[2])), round(float(view_box[3]))] == [width, height]
        ),
        "root_clips_frame_bleed": root.get("overflow") == "hidden",
        "has_source_derived_paths": 2 <= len(rendered_paths) <= 32,
        "point_highlights_are_restrained": len(circles) <= 64,
        "contains_no_embedded_or_canvas_content": not forbidden,
        "all_paths_have_geometry": all(bool(path.get("d", "").strip()) for path in paths),
        "structural_paths_use_cubic_curves": all("C " in path.get("d", "") for path in rendered_paths),
        "surface_noise_filter_is_vector_native": len(turbulence) <= 3,
        "surface_noise_layer_is_unique": len(surface_noise) <= 1,
        "surface_noise_layer_is_topmost": not surface_noise or root_children[-1] is surface_noise[0],
        "source_gradients_are_restrained": len(gradients) <= len(rendered_paths),
        "source_gradients_have_three_stops": all(
            len(gradient.findall(f"./{SVG_NS}stop")) == 3 for gradient in gradients
        ),
        "source_gradient_ids_are_unique": len(gradient_ids) == len(set(gradient_ids)),
    }

    if args.analysis:
        if not args.analysis.is_file():
            raise SystemExit(f"Analysis JSON not found: {args.analysis}")
        analysis_data = json.loads(args.analysis.read_text(encoding="utf-8"))
        analysis_keys = nested_json_keys(analysis_data)
        color_mode = analysis_data.get("color_mode")
        archetype = analysis_data.get("archetype")
        paper_style = analysis_data.get("paper_style")
        grain_overlay_strength = analysis_data.get("grain_overlay_strength")
        has_grain_overlay = isinstance(grain_overlay_strength, (int, float)) and grain_overlay_strength > 0
        night_curve_limits = {
            "foreground-silhouette": 132,
            "luminous-sky-field": 48,
            "foreground-light": 84,
        }
        night_curve_counts = {
            path_id: rendered_by_id[path_id].get("d", "").count("C ")
            for path_id in night_curve_limits
            if path_id in rendered_by_id
        }
        analysis_dimensions = analysis_data.get("analysis_dimensions")
        minimum_gap_fraction = analysis_data.get("min_negative_gap_fraction")
        expected_general_clearance = None
        expected_general_margin = None
        expected_general_overlap_kernel = None
        if (
            isinstance(analysis_dimensions, list)
            and len(analysis_dimensions) == 2
            and all(isinstance(value, int) and value > 0 for value in analysis_dimensions)
            and isinstance(minimum_gap_fraction, (int, float))
            and minimum_gap_fraction >= 0
        ):
            if minimum_gap_fraction == 0:
                expected_general_clearance = 0
                expected_general_margin = 0
                expected_general_overlap_kernel = 1
            else:
                expected_general_clearance = max(
                    1,
                    round(min(analysis_dimensions) * minimum_gap_fraction),
                )
                expected_general_margin = max(
                    3,
                    expected_general_clearance + 3,
                )
                expected_general_overlap_kernel = (
                    2 * (expected_general_clearance + expected_general_margin) + 1
                )
        checks.update(
            {
                "analysis_dimensions_match": analysis_data.get("output_dimensions") == [width, height],
                "analysis_omits_private_quadrant_confidence": all(
                    "confidence" not in key and "quadrant" not in key
                    for key in analysis_keys
                ),
                "analysis_declares_svg_renderer": analysis_data.get("renderer")
                == "SVG (no Canvas, no image generation model)",
                "analysis_records_clipped_frame_bleed": analysis_data.get("frame_bleed_policy")
                == "extend frame-touching masks outside a clipped viewBox before fitting"
                and isinstance(analysis_data.get("frame_bleed_analysis_pixels"), int)
                and analysis_data.get("frame_bleed_analysis_pixels", 0) >= 3,
                "analysis_shape_count_matches": analysis_data.get("large_shape_count") == len(rendered_paths),
                "analysis_point_count_matches": analysis_data.get("point_highlight_count") == len(circles),
                "analysis_color_mode_is_valid": color_mode in {"source", "balanced", "curated-night"},
                "analysis_archetype_is_valid": archetype
                in {
                    "general-color-fields",
                    "night-landscape",
                    "reflective-horizontal-fields",
                },
                "analysis_records_curve_smoothing": isinstance(analysis_data.get("curve_smoothing"), (int, float)),
                "analysis_records_gradient_strength": isinstance(
                    analysis_data.get("gradient_strength"), (int, float)
                ),
                "analysis_records_negative_gap_floor": isinstance(
                    analysis_data.get("min_negative_gap_fraction"), (int, float)
                )
                and 0.0 <= analysis_data.get("min_negative_gap_fraction", -1.0) <= 0.08,
                "analysis_gradient_count_matches": analysis_data.get("gradient_layer_count")
                == len(gradients),
                "analysis_paper_style_is_valid": paper_style in {"grain", "rough"},
                "analysis_paper_density_is_valid": isinstance(
                    analysis_data.get("paper_density"), (int, float)
                )
                and 0.25 <= analysis_data.get("paper_density", 0.0) <= 4.0,
                "analysis_grain_overlay_is_valid": isinstance(grain_overlay_strength, (int, float))
                and 0.0 <= grain_overlay_strength <= 1.0,
                "traditional_grain_overlay_matches": len(traditional_grain_overlay)
                == (1 if paper_style == "rough" and has_grain_overlay and surface_noise else 0),
                "traditional_grain_overlay_is_topmost": not traditional_grain_overlay
                or list(surface_noise_group[0])[-1] is traditional_grain_overlay[0],
                "analysis_vector_particle_count_matches": analysis_data.get(
                    "paper_vector_particle_count"
                )
                == len(pattern_paths) + len(pattern_ellipses),
                "analysis_paper_texture_model_is_valid": analysis_data.get("paper_texture_model")
                in {
                    "none",
                    "continuous-fractal-grain",
                    "hybrid-vector-particles",
                    "hybrid-vector-particles+traditional-grain",
                },
                "analysis_noise_layer_matches": analysis_data.get("surface_noise_layer")
                == bool(surface_noise),
                "analysis_records_compact_salient_islands": (
                    analysis_data.get("compact_salient_island_policy")
                    in {
                        "retain at most one compact locally contrasted or rare-chromatic focal island",
                        "retain at most one compact locally contrasted, cross-field contrasted, or rare-chromatic focal island",
                    }
                    and isinstance(
                        analysis_data.get("compact_salient_island_count"),
                        int,
                    )
                    and 0
                    <= analysis_data.get("compact_salient_island_count", -1)
                    <= 1
                    and isinstance(
                        analysis_data.get("compact_salient_island_area_fractions"),
                        list,
                    )
                    and len(
                        analysis_data.get("compact_salient_island_area_fractions", [])
                    )
                    == analysis_data.get("compact_salient_island_count")
                    and all(
                        isinstance(value, (int, float))
                        and 0.0007 <= value <= 0.03
                        for value in analysis_data.get(
                            "compact_salient_island_area_fractions",
                            [],
                        )
                    )
                    and isinstance(
                        analysis_data.get("compact_salient_island_kinds"),
                        list,
                    )
                    and len(analysis_data.get("compact_salient_island_kinds", []))
                    == analysis_data.get("compact_salient_island_count")
                    and set(analysis_data.get("compact_salient_island_kinds", [])).issubset(
                        {
                            "local-contrast",
                            "cross-field-contrast",
                            "rare-chromatic",
                        }
                    )
                    and (
                        archetype != "night-landscape"
                        or analysis_data.get("compact_salient_island_count") == 0
                    )
                ),
                "analysis_records_focal_support_fields": (
                    analysis_data.get("focal_support_field_policy")
                    == "retain at most one row-relative luminous support field beneath a rare-chromatic focal island"
                    and isinstance(analysis_data.get("focal_support_field_count"), int)
                    and 0 <= analysis_data.get("focal_support_field_count", -1) <= 1
                    and isinstance(
                        analysis_data.get("focal_support_field_area_fractions"),
                        list,
                    )
                    and len(analysis_data.get("focal_support_field_area_fractions", []))
                    == analysis_data.get("focal_support_field_count")
                    and all(
                        isinstance(value, (int, float)) and 0.045 <= value <= 0.32
                        for value in analysis_data.get(
                            "focal_support_field_area_fractions",
                            [],
                        )
                    )
                    and (
                        analysis_data.get("focal_support_field_count") == 0
                        or analysis_data.get("compact_salient_island_kinds")
                        == ["rare-chromatic"]
                    )
                    and (
                        archetype != "night-landscape"
                        or analysis_data.get("focal_support_field_count") == 0
                    )
                ),
                "analysis_records_perspective_accent_lines": (
                    analysis_data.get("perspective_accent_line_policy")
                    == "retain at most one chromatic center-leading line with bottom contact and convergent evidence"
                    and isinstance(
                        analysis_data.get("perspective_accent_line_count"),
                        int,
                    )
                    and 0
                    <= analysis_data.get("perspective_accent_line_count", -1)
                    <= 1
                    and isinstance(
                        analysis_data.get("perspective_accent_line_area_fractions"),
                        list,
                    )
                    and len(
                        analysis_data.get("perspective_accent_line_area_fractions", [])
                    )
                    == analysis_data.get("perspective_accent_line_count")
                    and all(
                        isinstance(value, (int, float))
                        and 0.001 <= value <= 0.015
                        for value in analysis_data.get(
                            "perspective_accent_line_area_fractions",
                            [],
                        )
                    )
                    and (
                        archetype != "night-landscape"
                        or analysis_data.get("perspective_accent_line_count") == 0
                    )
                ),
                "reflective_fields_report_measured_pairing": archetype
                != "reflective-horizontal-fields"
                or (
                    analysis_data.get("reflection_detection_policy")
                    == "wide central axis with opposed lightness, chroma, and edge agreement"
                    and isinstance(
                        analysis_data.get("reflection_axis_analysis_row"),
                        int,
                    )
                    and isinstance(
                        analysis_data.get("reflection_axis_fraction"),
                        (int, float),
                    )
                    and 0.42
                    <= analysis_data.get("reflection_axis_fraction", 0.0)
                    <= 0.58
                    and isinstance(analysis_dimensions, list)
                    and len(analysis_dimensions) == 2
                    and analysis_dimensions[1] > 0
                    and abs(
                        analysis_data.get("reflection_axis_fraction")
                        - analysis_data.get("reflection_axis_analysis_row")
                        / analysis_dimensions[1]
                    )
                    <= 0.000001
                    and isinstance(
                        analysis_data.get("reflection_score"),
                        (int, float),
                    )
                    and analysis_data.get("reflection_score", 0.0) >= 0.72
                    and analysis_data.get(
                        "reflection_lightness_correlation",
                        0.0,
                    )
                    >= 0.80
                    and analysis_data.get(
                        "reflection_chroma_correlation",
                        0.0,
                    )
                    >= 0.55
                    and analysis_data.get(
                        "reflection_edge_correlation",
                        0.0,
                    )
                    >= 0.55
                    and isinstance(
                        analysis_data.get("reflection_axis_edge_strength"),
                        (int, float),
                    )
                    and analysis_data.get("reflection_axis_edge_strength", 0.0)
                    > 0.0
                    and analysis_data.get("reflection_shape_policy")
                    == "dynamic upper outer contour with vertically paired lower fields"
                    and analysis_data.get("reflection_contour_policy")
                    == "four-pass curved fitting after compact-valley envelope regularization"
                    and analysis_data.get("reflection_color_policy")
                    == "sample upper and lower roles independently from their source masks"
                    and isinstance(
                        analysis_data.get("reflection_role_count"),
                        int,
                    )
                    and 7
                    <= analysis_data.get("reflection_role_count", 0)
                    <= 10
                    and analysis_data.get("reflection_role_count")
                    == len(rendered_paths)
                    and analysis_data.get("reflection_role_ids")
                    == list(rendered_by_id)
                    and {
                        "sky-field",
                        "water-field",
                        "upper-terrain",
                        "reflected-terrain",
                        "shore-divider",
                    }.issubset(set(rendered_by_id))
                    and isinstance(
                        analysis_data.get(
                            "reflection_pair_vertical_area_delta_fraction"
                        ),
                        (int, float),
                    )
                    and 0.0
                    <= analysis_data.get(
                        "reflection_pair_vertical_area_delta_fraction",
                        -1.0,
                    )
                    <= 0.01
                    and isinstance(
                        analysis_data.get("reflection_frame_edges_touched"),
                        dict,
                    )
                    and set(
                        analysis_data.get(
                            "reflection_frame_edges_touched",
                            {},
                        )
                    )
                    == set(rendered_by_id)
                    and all(
                        isinstance(edges, list)
                        and set(edges).issubset(
                            {"left", "right", "top", "bottom"}
                        )
                        and path_bleeds_past_edges(
                            rendered_bounds_by_id.get(path_id),
                            edges,
                            width,
                            height,
                        )
                        for path_id, edges in analysis_data.get(
                            "reflection_frame_edges_touched",
                            {},
                        ).items()
                    )
                    and isinstance(
                        analysis_data.get("gradient_axes"),
                        dict,
                    )
                    and set(analysis_data.get("gradient_axes", {})).issubset(
                        set(rendered_by_id)
                    )
                    and analysis_data.get("point_highlight_count") == 0
                ),
                "rough_paper_uses_three_vector_scales": paper_style != "rough"
                or not surface_noise
                or (
                    len(turbulence) == (2 if has_grain_overlay else 1)
                    and len(surface_noise_group) == 1
                    and len(surface_noise_group[0].findall(f"./{SVG_NS}rect"))
                    == (4 if has_grain_overlay else 3)
                    and {"paper-fiber-pattern", "paper-pore-pattern"}.issubset(pattern_ids)
                    and bool(pattern_paths)
                    and bool(pattern_ellipses)
                    and not gaussian_blurs
                    and analysis_data.get("paper_texture_model")
                    == (
                        "hybrid-vector-particles+traditional-grain"
                        if has_grain_overlay
                        else "hybrid-vector-particles"
                    )
                ),
                "general_fields_report_seam_underlap": archetype != "general-color-fields"
                or (
                    analysis_data.get("general_boundary_policy")
                    == "curve-fit-safe render-order underlap between retained adjacent fields"
                    and analysis_data.get("general_seam_clearance_radius_analysis_pixels")
                    == expected_general_clearance
                    and analysis_data.get("general_seam_fitting_margin_analysis_pixels")
                    == expected_general_margin
                    and isinstance(analysis_data.get("general_seam_overlap_kernel"), int)
                    and analysis_data.get("general_seam_overlap_kernel")
                    == expected_general_overlap_kernel
                    and analysis_data.get("general_seam_expected_overlap_kernel")
                    == expected_general_overlap_kernel
                    and isinstance(analysis_data.get("general_seam_overlap_pixels"), dict)
                    and set(analysis_data.get("general_seam_overlap_pixels", {}))
                    == set(rendered_by_id)
                    and all(
                        isinstance(value, int) and value >= 0
                        for value in analysis_data.get("general_seam_overlap_pixels", {}).values()
                    )
                ),
                "general_fields_use_light_contour_low_pass": archetype
                != "general-color-fields"
                or (
                    analysis_data.get("general_contour_policy")
                    == "four-pass closed-loop low-pass before cubic Bezier fitting"
                    and analysis_data.get("general_contour_low_passes") == 4
                    and analysis_data.get("general_compact_contour_policy")
                    == "two-pass identity lock for protected compact roles"
                    and analysis_data.get("general_compact_contour_low_passes") == 2
                ),
                "general_fields_bleed_past_touched_frame_edges": archetype
                != "general-color-fields"
                or (
                    analysis_data.get("general_frame_boundary_policy")
                    == "extend touching paths beyond the clipped viewBox"
                    and analysis_data.get("general_frame_bleed_analysis_pixels")
                    == analysis_data.get("frame_bleed_analysis_pixels")
                    and isinstance(analysis_data.get("general_frame_edges_touched"), dict)
                    and set(analysis_data.get("general_frame_edges_touched", {}))
                    == set(rendered_by_id)
                    and all(
                        isinstance(edges, list)
                        and set(edges).issubset({"left", "right", "top", "bottom"})
                        and path_bleeds_past_edges(
                            rendered_bounds_by_id.get(path_id),
                            edges,
                            width,
                            height,
                        )
                        for path_id, edges in analysis_data.get(
                            "general_frame_edges_touched", {}
                        ).items()
                    )
                ),
                "general_fields_report_discarded_region_merge": archetype
                != "general-color-fields"
                or (
                    analysis_data.get("general_discarded_region_policy")
                    == "merge touching non-background components into retained fields"
                    and isinstance(analysis_data.get("general_discarded_components_merged"), dict)
                    and set(analysis_data.get("general_discarded_components_merged", {}))
                    == set(rendered_by_id)
                    and all(
                        isinstance(value, int) and value >= 0
                        for value in analysis_data.get(
                            "general_discarded_components_merged", {}
                        ).values()
                    )
                    and isinstance(analysis_data.get("general_discarded_pixels_merged"), dict)
                    and set(analysis_data.get("general_discarded_pixels_merged", {}))
                    == set(rendered_by_id)
                    and all(
                        isinstance(value, int) and value >= 0
                        for value in analysis_data.get(
                            "general_discarded_pixels_merged", {}
                        ).values()
                    )
                ),
                "general_fields_report_negative_space_consolidation": archetype
                != "general-color-fields"
                or (
                    analysis_data.get("general_negative_space_policy")
                    == "collapse sub-clearance background channels and micro-pockets before fitting"
                    and isinstance(
                        analysis_data.get("general_negative_space_close_kernel"),
                        int,
                    )
                    and analysis_data.get("general_negative_space_close_kernel", 0) % 2 == 1
                    and isinstance(
                        analysis_data.get("general_negative_space_hole_area_limit"),
                        int,
                    )
                    and analysis_data.get("general_negative_space_hole_area_limit", -1) >= 0
                    and isinstance(
                        analysis_data.get("general_negative_space_closed_pixels"),
                        int,
                    )
                    and analysis_data.get("general_negative_space_closed_pixels", -1) >= 0
                    and isinstance(
                        analysis_data.get("general_negative_space_holes_filled"),
                        int,
                    )
                    and analysis_data.get("general_negative_space_holes_filled", -1) >= 0
                    and isinstance(
                        analysis_data.get("general_negative_space_components_reassigned"),
                        dict,
                    )
                    and set(
                        analysis_data.get(
                            "general_negative_space_components_reassigned",
                            {},
                        )
                    )
                    == set(rendered_by_id)
                    and all(
                        isinstance(value, int) and value >= 0
                        for value in analysis_data.get(
                            "general_negative_space_components_reassigned",
                            {},
                        ).values()
                    )
                    and isinstance(
                        analysis_data.get("general_negative_space_pixels_reassigned"),
                        dict,
                    )
                    and set(
                        analysis_data.get(
                            "general_negative_space_pixels_reassigned",
                            {},
                        )
                    )
                    == set(rendered_by_id)
                    and all(
                        isinstance(value, int) and value >= 0
                        for value in analysis_data.get(
                            "general_negative_space_pixels_reassigned",
                            {},
                        ).values()
                    )
                ),
                "general_fields_report_micro_hole_cleanup": archetype != "general-color-fields"
                or (
                    analysis_data.get("general_micro_hole_policy")
                    == "fill enclosed holes up to the minimum-clearance area"
                    and isinstance(analysis_data.get("general_micro_hole_area_limit"), int)
                    and analysis_data.get("general_micro_hole_area_limit", 0) >= 0
                    and isinstance(analysis_data.get("general_micro_holes_filled"), dict)
                    and set(analysis_data.get("general_micro_holes_filled", {}))
                    == set(rendered_by_id)
                    and all(
                        isinstance(value, int) and value >= 0
                        for value in analysis_data.get("general_micro_holes_filled", {}).values()
                    )
                    and isinstance(analysis_data.get("general_micro_hole_pixels"), dict)
                    and set(analysis_data.get("general_micro_hole_pixels", {}))
                    == set(rendered_by_id)
                    and all(
                        isinstance(value, int) and value >= 0
                        for value in analysis_data.get("general_micro_hole_pixels", {}).values()
                    )
                ),
                "general_fields_report_unrepresented_hole_merge": archetype
                != "general-color-fields"
                or (
                    analysis_data.get("general_unrepresented_hole_policy")
                    == "merge discarded non-background islands"
                    and isinstance(analysis_data.get("general_unrepresented_holes_merged"), dict)
                    and set(analysis_data.get("general_unrepresented_holes_merged", {}))
                    == set(rendered_by_id)
                    and all(
                        isinstance(value, int) and value >= 0
                        for value in analysis_data.get(
                            "general_unrepresented_holes_merged", {}
                        ).values()
                    )
                    and isinstance(analysis_data.get("general_unrepresented_hole_pixels"), dict)
                    and set(analysis_data.get("general_unrepresented_hole_pixels", {}))
                    == set(rendered_by_id)
                    and all(
                        isinstance(value, int) and value >= 0
                        for value in analysis_data.get(
                            "general_unrepresented_hole_pixels", {}
                        ).values()
                    )
                ),
                "general_fields_report_chromatic_false_background_merge": archetype
                != "general-color-fields"
                or not any(
                    key in analysis_data
                    for key in {
                        "general_chromatic_false_background_policy",
                        "general_chromatic_false_background_holes_merged",
                        "general_chromatic_false_background_pixels_merged",
                    }
                )
                or (
                    all(
                        key in analysis_data
                        for key in {
                            "general_chromatic_false_background_policy",
                            "general_chromatic_false_background_holes_merged",
                            "general_chromatic_false_background_pixels_merged",
                        }
                    )
                    and analysis_data.get(
                        "general_chromatic_false_background_policy"
                    )
                    == "merge compact enclosed background labels whose source hue aligns with the enclosing field and opposes the background"
                    and isinstance(
                        analysis_data.get(
                            "general_chromatic_false_background_holes_merged"
                        ),
                        dict,
                    )
                    and set(
                        analysis_data.get(
                            "general_chromatic_false_background_holes_merged",
                            {},
                        )
                    )
                    == set(rendered_by_id)
                    and all(
                        isinstance(value, int) and value >= 0
                        for value in analysis_data.get(
                            "general_chromatic_false_background_holes_merged",
                            {},
                        ).values()
                    )
                    and sum(
                        analysis_data.get(
                            "general_chromatic_false_background_holes_merged",
                            {},
                        ).values()
                    )
                    >= 1
                    and isinstance(
                        analysis_data.get(
                            "general_chromatic_false_background_pixels_merged"
                        ),
                        dict,
                    )
                    and set(
                        analysis_data.get(
                            "general_chromatic_false_background_pixels_merged",
                            {},
                        )
                    )
                    == set(rendered_by_id)
                    and all(
                        isinstance(value, int) and value >= 0
                        for value in analysis_data.get(
                            "general_chromatic_false_background_pixels_merged",
                            {},
                        ).values()
                    )
                    and sum(
                        analysis_data.get(
                            "general_chromatic_false_background_pixels_merged",
                            {},
                        ).values()
                    )
                    >= 1
                ),
                "night_landscape_has_reduced_shape_budget": archetype != "night-landscape"
                or len(rendered_paths) <= 3,
                "night_landscape_declares_spline_fitter": archetype != "night-landscape"
                or analysis_data.get("curve_fitter") == "periodic cubic B-spline to Bezier",
                "night_landscape_curve_segments_are_minimal": archetype != "night-landscape"
                or all(
                    night_curve_counts.get(path_id, 0) <= segment_limit
                    for path_id, segment_limit in night_curve_limits.items()
                ),
                "night_landscape_reports_gap_closure": archetype != "night-landscape"
                or (
                    isinstance(analysis_data.get("negative_gap_closure_kernel"), int)
                    and analysis_data.get("negative_gap_closure_kernel", 0) % 2 == 1
                    and isinstance(analysis_data.get("negative_gap_pixels_closed"), int)
                ),
                "night_landscape_reports_seam_overlap": archetype != "night-landscape"
                or (
                    isinstance(analysis_data.get("luminous_seam_overlap_pixels"), dict)
                    and isinstance(analysis_data.get("luminous_seam_overlap_kernels"), dict)
                ),
                "night_landscape_regularizes_internal_contours": archetype != "night-landscape"
                or (
                    analysis_data.get("internal_contour_policy")
                    == "rounded positive tips + minimum-clearance edge snap inside foreground clip"
                    and isinstance(analysis_data.get("internal_rounding_kernels"), dict)
                    and isinstance(analysis_data.get("internal_edge_snap_pixels"), dict)
                ),
                "source_mode_preserves_sampled_palette": color_mode != "source"
                or analysis_data.get("palette_output") == analysis_data.get("palette_sampled"),
                "source_palette_reports_diverse_roles": color_mode != "source"
                or (
                    analysis_data.get("palette_selection_model")
                    == "source Oklab diverse-role quantization"
                    and isinstance(analysis_data.get("palette_candidate_count"), int)
                    and analysis_data.get("palette_candidate_count", 0)
                    >= len(analysis_data.get("palette_sampled", []))
                    and isinstance(analysis_data.get("palette_candidate_colors"), list)
                    and len(analysis_data.get("palette_candidate_colors", []))
                    == analysis_data.get("palette_candidate_count")
                    and isinstance(
                        analysis_data.get("palette_candidate_population_fractions"), list
                    )
                    and len(analysis_data.get("palette_candidate_population_fractions", []))
                    == analysis_data.get("palette_candidate_count")
                    and abs(
                        sum(analysis_data.get("palette_candidate_population_fractions", []))
                        - 1.0
                    )
                    <= 0.00001
                    and isinstance(analysis_data.get("palette_seed_colors"), list)
                    and 4
                    <= len(analysis_data.get("palette_seed_colors", []))
                    <= len(analysis_data.get("palette_sampled", []))
                    and len(analysis_data.get("palette_sampled", []))
                    - len(analysis_data.get("palette_seed_colors", []))
                    <= 6
                    and analysis_data.get("palette_dominant_seed_color")
                    in analysis_data.get("palette_seed_colors", [])
                    and (
                        analysis_data.get("palette_accent_seed_color") is None
                        or analysis_data.get("palette_accent_seed_color")
                        in analysis_data.get("palette_seed_colors", [])
                    )
                    and isinstance(analysis_data.get("palette_population_fractions"), list)
                    and len(analysis_data.get("palette_population_fractions", []))
                    == len(analysis_data.get("palette_sampled", []))
                    and abs(sum(analysis_data.get("palette_population_fractions", [])) - 1.0)
                    <= 0.00001
                ),
            }
        )

    passed = all(checks.values())
    report = {
        "svg": str(args.svg.resolve()),
        "dimensions": [width, height],
        "rendered_path_count": len(rendered_paths),
        "path_count_including_clip_geometry": len(paths),
        "point_count": len(circles),
        "gradient_count": len(gradients),
        "texture_particle_count": len(pattern_paths) + len(pattern_ellipses),
        "forbidden_elements": forbidden,
        "checks": checks,
        "result": "PASS" if passed else "FAIL",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

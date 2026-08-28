#!/usr/bin/env python3
"""Turn a photograph into a sparse, paper-textured SVG abstraction.

The script uses only deterministic image analysis and SVG generation. It does
not call an image model and does not draw through HTML Canvas.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape

import numpy as np
from PIL import Image, ImageFilter, ImageOps


@dataclass
class Region:
    label: int
    pixels: list[tuple[int, int]]
    area: int
    centroid_x: float
    centroid_y: float
    score: float


@dataclass
class SvgGradient:
    name: str
    x1: float
    y1: float
    x2: float
    y2: float
    axis: str
    stops: tuple[tuple[float, tuple[int, int, int]], ...]


@dataclass
class SvgLayer:
    name: str
    path: str
    color: tuple[int, int, int]
    clip: str | None = None
    opacity: float = 1.0
    gradient: SvgGradient | None = None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def rgb_hex(rgb: Iterable[int]) -> str:
    return "#" + "".join(f"{int(clamp(channel, 0, 255)):02X}" for channel in rgb)


def color_distance(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    # Weighted RGB is sufficient here because it is used only for region ranking.
    dr = (first[0] - second[0]) * 0.30
    dg = (first[1] - second[1]) * 0.59
    db = (first[2] - second[2]) * 0.11
    return math.sqrt(dr * dr + dg * dg + db * db) / 255.0


def source_gradient(
    array: np.ndarray,
    mask: np.ndarray,
    base_color: tuple[int, int, int],
    strength: float,
    name: str,
) -> SvgGradient | None:
    """Derive a restrained three-stop gradient from masked source variation."""
    if strength <= 0.0 or int(np.count_nonzero(mask)) < 64:
        return None
    y_values, x_values = np.nonzero(mask)
    pixels = array[mask].astype(np.float64)
    height, width = mask.shape
    x_normalized = x_values.astype(np.float64) / max(1, width - 1)
    y_normalized = y_values.astype(np.float64) / max(1, height - 1)
    candidates = (
        ("horizontal", 0.0, 0.5, 1.0, 0.5, x_normalized),
        ("vertical", 0.5, 0.0, 0.5, 1.0, y_normalized),
        ("diagonal-down", 0.0, 0.0, 1.0, 1.0, (x_normalized + y_normalized) * 0.5),
        ("diagonal-up", 0.0, 1.0, 1.0, 0.0, (x_normalized + 1.0 - y_normalized) * 0.5),
    )
    selected = candidates[0]
    selected_score = -1.0
    for candidate in candidates:
        parameter = candidate[-1]
        low_limit, high_limit = np.percentile(parameter, (18.0, 82.0))
        low_pixels = pixels[parameter <= low_limit]
        high_pixels = pixels[parameter >= high_limit]
        if len(low_pixels) < 16 or len(high_pixels) < 16:
            continue
        low_color = np.median(low_pixels, axis=0)
        high_color = np.median(high_pixels, axis=0)
        delta = high_color - low_color
        score = math.sqrt((0.30 * delta[0]) ** 2 + (0.59 * delta[1]) ** 2 + (0.11 * delta[2]) ** 2)
        if score > selected_score:
            selected = candidate
            selected_score = score

    axis, x1, y1, x2, y2, parameter = selected
    limits = np.percentile(parameter, (18.0, 46.0, 54.0, 82.0))
    samples = (
        pixels[parameter <= limits[0]],
        pixels[(parameter >= limits[1]) & (parameter <= limits[2])],
        pixels[parameter >= limits[3]],
    )
    source_center = np.median(pixels, axis=0)
    base = np.asarray(base_color, dtype=np.float64)
    stops: list[tuple[float, tuple[int, int, int]]] = []
    for offset, sample in zip((0.0, 0.5, 1.0), samples):
        sample_color = source_center if not len(sample) else np.median(sample, axis=0)
        delta = np.clip(sample_color - source_center, -48.0, 48.0)
        adjusted = np.clip(base + delta * strength, 0.0, 255.0)
        stops.append((offset, tuple(int(round(value)) for value in adjusted)))
    return SvgGradient(name, x1, y1, x2, y2, axis, tuple(stops))


CURATED_NIGHT = {
    "sky": (21, 25, 24),          # #151918
    "luminous-outer": (109, 93, 99),  # #6D5D63
    "luminous-inner": (150, 128, 135),  # #968087
    "foreground": (112, 72, 50),  # #704832
    "shadow": (59, 37, 31),       # #3B251F
    "light": (183, 125, 80),      # #B77D50
    "star": (232, 215, 207),      # #E8D7CF
}


def srgb_to_oklab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """Convert sRGB bytes to Oklab using the CSS Color 4 sample matrices."""
    srgb = np.asarray(rgb, dtype=np.float64) / 255.0
    linear = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    red, green, blue = linear
    l_value = 0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue
    m_value = 0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue
    s_value = 0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue
    l_root, m_root, s_root = np.cbrt((l_value, m_value, s_value))
    return (
        float(0.2104542553 * l_root + 0.7936177850 * m_root - 0.0040720468 * s_root),
        float(1.9779984951 * l_root - 2.4285922050 * m_root + 0.4505937099 * s_root),
        float(0.0259040371 * l_root + 0.7827717662 * m_root - 0.8086757660 * s_root),
    )


def srgb_array_to_oklab(rgb: np.ndarray) -> np.ndarray:
    """Vectorized sRGB-to-Oklab conversion for palette assignment."""
    srgb = rgb.astype(np.float64) / 255.0
    linear = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    red, green, blue = linear[..., 0], linear[..., 1], linear[..., 2]
    l_value = 0.4122214708 * red + 0.5363325363 * green + 0.0514459929 * blue
    m_value = 0.2119034982 * red + 0.6806995451 * green + 0.1073969566 * blue
    s_value = 0.0883024619 * red + 0.2817188376 * green + 0.6299787005 * blue
    l_root, m_root, s_root = np.cbrt((l_value, m_value, s_value))
    return np.stack(
        (
            0.2104542553 * l_root + 0.7936177850 * m_root - 0.0040720468 * s_root,
            1.9779984951 * l_root - 2.4285922050 * m_root + 0.4505937099 * s_root,
            0.0259040371 * l_root + 0.7827717662 * m_root - 0.8086757660 * s_root,
        ),
        axis=-1,
    )


def oklab_to_srgb(lab: tuple[float, float, float]) -> tuple[int, int, int] | None:
    lightness, axis_a, axis_b = lab
    l_root = lightness + 0.3963377774 * axis_a + 0.2158037573 * axis_b
    m_root = lightness - 0.1055613458 * axis_a - 0.0638541728 * axis_b
    s_root = lightness - 0.0894841775 * axis_a - 1.2914855480 * axis_b
    l_value, m_value, s_value = l_root**3, m_root**3, s_root**3
    linear = np.asarray(
        (
            4.0767416621 * l_value - 3.3077115913 * m_value + 0.2309699292 * s_value,
            -1.2684380046 * l_value + 2.6097574011 * m_value - 0.3413193965 * s_value,
            -0.0041960863 * l_value - 0.7034186147 * m_value + 1.7076147010 * s_value,
        ),
        dtype=np.float64,
    )
    if bool(np.any(linear < -1e-5) or np.any(linear > 1.00001)):
        return None
    linear = np.clip(linear, 0.0, 1.0)
    srgb = np.where(linear <= 0.0031308, 12.92 * linear, 1.055 * (linear ** (1.0 / 2.4)) - 0.055)
    return tuple(int(round(value * 255.0)) for value in srgb)


def balanced_color(rgb: tuple[int, int, int], light_shift: float = 0.0) -> tuple[int, int, int]:
    """Apply small perceptual guardrails without rotating the source hue."""
    lightness, axis_a, axis_b = srgb_to_oklab(rgb)
    chroma = math.hypot(axis_a, axis_b)
    hue = math.atan2(axis_b, axis_a)
    target_lightness = clamp(lightness + light_shift, 0.055, 0.94)
    target_chroma = min(chroma, 0.18)
    for _ in range(32):
        candidate = oklab_to_srgb(
            (target_lightness, target_chroma * math.cos(hue), target_chroma * math.sin(hue))
        )
        if candidate is not None:
            return candidate
        target_chroma *= 0.94
    return tuple(int(clamp(channel, 0, 255)) for channel in rgb)


def output_color(
    rgb: tuple[int, int, int],
    color_mode: str,
    role: str | None = None,
    light_shift: float = 0.0,
) -> tuple[int, int, int]:
    """Return source color by default; fixed palettes are explicit opt-ins."""
    if color_mode == "curated-night" and role in CURATED_NIGHT:
        return CURATED_NIGHT[role]
    if color_mode == "balanced" or abs(light_shift) > 1e-9:
        return balanced_color(rgb, light_shift=light_shift)
    return rgb


def analysis_image(image: Image.Image, longest_side: int) -> Image.Image:
    width, height = image.size
    scale = min(1.0, longest_side / max(width, height))
    size = (max(2, round(width * scale)), max(2, round(height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)


def private_label_coherence(labels: np.ndarray) -> float:
    """Measure how much of each local label belongs to its largest component."""
    height, width = labels.shape
    retained = 0
    for label in np.unique(labels):
        mask = labels == label
        visited = np.zeros_like(mask, dtype=bool)
        largest = 0
        for y_zero, x_zero in np.argwhere(mask):
            y_start = int(y_zero)
            x_start = int(x_zero)
            if visited[y_start, x_start]:
                continue
            queue: deque[tuple[int, int]] = deque([(y_start, x_start)])
            visited[y_start, x_start] = True
            count = 0
            while queue:
                y_value, x_value = queue.popleft()
                count += 1
                for delta_y, delta_x in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    next_y = y_value + delta_y
                    next_x = x_value + delta_x
                    if (
                        0 <= next_y < height
                        and 0 <= next_x < width
                        and mask[next_y, next_x]
                        and not visited[next_y, next_x]
                    ):
                        visited[next_y, next_x] = True
                        queue.append((next_y, next_x))
            largest = max(largest, count)
        retained += largest
    return retained / max(1, height * width)


def private_quadrant_confidences(
    softened_lab: np.ndarray,
    distances: np.ndarray,
    labels: np.ndarray,
) -> tuple[float, float, float, float]:
    """Score four quadrants without exposing the values in SVG or plan JSON."""
    ordered = np.sort(np.sqrt(distances), axis=-1)
    assignment_margin = (ordered[:, :, 1] - ordered[:, :, 0]) / np.maximum(
        ordered[:, :, 1],
        1e-6,
    )
    lightness = softened_lab[:, :, 0]
    gradient = np.hypot(
        np.gradient(lightness, axis=1),
        np.gradient(lightness, axis=0),
    )
    boundary = np.zeros_like(labels, dtype=bool)
    boundary[:, 1:] |= labels[:, 1:] != labels[:, :-1]
    boundary[1:, :] |= labels[1:, :] != labels[:-1, :]
    boundary_near = np.asarray(
        Image.fromarray(np.where(boundary, 255, 0).astype(np.uint8), mode="L").filter(
            ImageFilter.MaxFilter(5)
        ),
        dtype=np.uint8,
    ) >= 128
    height, width = labels.shape
    quadrants = (
        (slice(0, height // 2), slice(0, width // 2)),
        (slice(0, height // 2), slice(width // 2, width)),
        (slice(height // 2, height), slice(0, width // 2)),
        (slice(height // 2, height), slice(width // 2, width)),
    )
    confidences: list[float] = []
    label_count = max(2, int(np.max(labels)) + 1)
    for y_slice, x_slice in quadrants:
        local_gradient = gradient[y_slice, x_slice]
        strong_threshold = float(np.percentile(local_gradient, 72.0))
        strong_edges = local_gradient >= strong_threshold
        edge_recall = float(
            np.sum(local_gradient[strong_edges & boundary_near[y_slice, x_slice]])
            / max(float(np.sum(local_gradient[strong_edges])), 1e-9)
        )
        local_labels = labels[y_slice, x_slice]
        coherence = private_label_coherence(local_labels)
        counts = np.bincount(local_labels.ravel(), minlength=label_count)
        probabilities = counts[counts > 0] / max(1, counts.sum())
        entropy = float(
            -np.sum(probabilities * np.log(probabilities)) / math.log(label_count)
        )
        margin = float(np.mean(assignment_margin[y_slice, x_slice]))
        gradient_energy = float(np.mean(local_gradient))
        confidence = 0.45 * edge_recall + 0.30 * coherence + 0.25 * margin
        collapsed_edges = (
            edge_recall < 0.48
            and entropy < 0.55
            and gradient_energy > 0.0045
        )
        fragmented_assignment = (
            coherence < 0.80
            and margin < 0.58
            and edge_recall < 0.68
            and gradient_energy > 0.0040
        )
        if collapsed_edges or fragmented_assignment:
            confidence -= 0.16
        confidences.append(clamp(confidence, 0.0, 1.0))
    return tuple(confidences)  # type: ignore[return-value]


def private_binary_components(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    """Return four-connected components for internal structural measurements."""
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    components: list[list[tuple[int, int]]] = []
    for y_zero, x_zero in np.argwhere(mask):
        y_start = int(y_zero)
        x_start = int(x_zero)
        if visited[y_start, x_start]:
            continue
        queue: deque[tuple[int, int]] = deque([(y_start, x_start)])
        visited[y_start, x_start] = True
        component: list[tuple[int, int]] = []
        while queue:
            y_value, x_value = queue.popleft()
            component.append((y_value, x_value))
            for delta_y, delta_x in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                next_y = y_value + delta_y
                next_x = x_value + delta_x
                if (
                    0 <= next_y < height
                    and 0 <= next_x < width
                    and mask[next_y, next_x]
                    and not visited[next_y, next_x]
                ):
                    visited[next_y, next_x] = True
                    queue.append((next_y, next_x))
        components.append(component)
    return components


def private_line_mean(
    values: np.ndarray,
    x_zero: float,
    y_zero: float,
    x_one: float,
    y_one: float,
) -> float:
    steps = max(8, round(abs(y_one - y_zero)) + 1)
    x_values = np.rint(np.linspace(x_zero, x_one, steps)).astype(np.int32)
    y_values = np.rint(np.linspace(y_zero, y_one, steps)).astype(np.int32)
    x_values = np.clip(x_values, 0, values.shape[1] - 1)
    y_values = np.clip(y_values, 0, values.shape[0] - 1)
    return float(np.mean(values[y_values, x_values]))


def private_perspective_corridor_mask(source_lab: np.ndarray) -> np.ndarray | None:
    """Find a dark lower field bounded by two edges converging near the horizon."""
    lightness = source_lab[:, :, 0]
    gradient = np.hypot(
        np.gradient(lightness, axis=1),
        np.gradient(lightness, axis=0),
    )
    height, width = lightness.shape
    best: tuple[float, float, float, int, int, int, int] | None = None
    y_step = max(2, round(0.025 * height))
    x_step = max(5, round(0.035 * width))
    vanishing_step = max(4, round(0.025 * width))
    for vanishing_y in range(round(0.42 * height), round(0.63 * height), y_step):
        for vanishing_x in range(
            round(0.38 * width),
            round(0.63 * width),
            vanishing_step,
        ):
            center_prior = math.exp(
                -((vanishing_x - 0.5 * width) / max(1.0, 0.20 * width)) ** 2
            )
            left_candidates = [
                (
                    bottom_x,
                    private_line_mean(
                        gradient,
                        vanishing_x,
                        vanishing_y,
                        bottom_x,
                        height - 1,
                    ),
                )
                for bottom_x in range(round(0.02 * width), round(0.39 * width), x_step)
            ]
            right_candidates = [
                (
                    bottom_x,
                    private_line_mean(
                        gradient,
                        vanishing_x,
                        vanishing_y,
                        bottom_x,
                        height - 1,
                    ),
                )
                for bottom_x in range(round(0.61 * width), round(0.99 * width), x_step)
            ]
            for left_x, left_score in left_candidates:
                for right_x, right_score in right_candidates:
                    left_span = vanishing_x - left_x
                    right_span = right_x - vanishing_x
                    symmetry = min(left_span, right_span) / max(left_span, right_span)
                    score = (
                        math.sqrt(max(0.0, left_score * right_score))
                        * (0.78 + 0.22 * symmetry)
                        * center_prior
                    )
                    candidate = (
                        score,
                        left_score,
                        right_score,
                        vanishing_x,
                        vanishing_y,
                        left_x,
                        right_x,
                    )
                    if best is None or candidate > best:
                        best = candidate
    if best is None:
        return None
    _, left_score, right_score, vanishing_x, vanishing_y, left_x, right_x = best
    bottom_span = right_x - left_x
    if (
        vanishing_y > 0.56 * height
        or bottom_span < 0.72 * width
        or min(left_score, right_score) < 0.015
    ):
        return None

    corridor = np.zeros((height, width), dtype=bool)
    top_half_width = max(3, round(0.018 * width))
    for y_value in range(vanishing_y, height):
        progress = (y_value - vanishing_y) / max(1, height - 1 - vanishing_y)
        curved_progress = progress ** 0.88
        left_boundary = round(
            vanishing_x
            - top_half_width
            + (left_x - (vanishing_x - top_half_width)) * curved_progress
        )
        right_boundary = round(
            vanishing_x
            + top_half_width
            + (right_x - (vanishing_x + top_half_width)) * curved_progress
        )
        corridor[y_value, max(0, left_boundary) : min(width, right_boundary + 1)] = True
    inset = max(2, round(0.035 * width))
    core = corridor.copy()
    core[:, :inset] = False
    core[:, width - inset :] = False
    if not np.any(core) or float(np.median(lightness[core])) >= 0.42:
        return None
    return fill_enclosed_holes(corridor)


def private_isolated_silhouette_mask(source_lab: np.ndarray) -> np.ndarray | None:
    """Find a compact dark subject that differs from its horizontal context."""
    lightness = source_lab[:, :, 0]
    height, width = lightness.shape
    radius = max(4, round(0.12 * width))
    padded = np.pad(lightness, ((0, 0), (radius, radius)), mode="reflect")
    cumulative = np.pad(np.cumsum(padded, axis=1), ((0, 0), (1, 0)))
    local_average = (
        cumulative[:, 2 * radius + 1 :] - cumulative[:, : -(2 * radius + 1)]
    ) / (2 * radius + 1)
    local_contrast = local_average - lightness
    measured_band = local_contrast[round(0.28 * height) : round(0.90 * height)]
    threshold = max(0.045, float(np.percentile(measured_band, 88.0)))
    candidate_mask = local_contrast > threshold
    candidate_mask[: round(0.28 * height)] = False
    candidate_mask[round(0.92 * height) :] = False
    filtered = Image.fromarray(
        np.where(candidate_mask, 255, 0).astype(np.uint8),
        mode="L",
    )
    filtered = filtered.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.MinFilter(7))
    candidate_mask = np.asarray(filtered, dtype=np.uint8) >= 128
    best: tuple[float, list[tuple[int, int]]] | None = None
    total = height * width
    for component in private_binary_components(candidate_mask):
        area = len(component)
        if not 0.003 * total <= area <= 0.15 * total:
            continue
        y_values = np.fromiter((point[0] for point in component), dtype=np.int32)
        x_values = np.fromiter((point[1] for point in component), dtype=np.int32)
        component_width = int(x_values.max() - x_values.min() + 1)
        component_height = int(y_values.max() - y_values.min() + 1)
        if not (
            0.04 * width <= component_width <= 0.38 * width
            and 0.10 * height <= component_height <= 0.55 * height
            and int(y_values.min()) < 0.68 * height
            and int(y_values.max()) > 0.48 * height
        ):
            continue
        salience = (
            float(np.mean(local_contrast[y_values, x_values]))
            * math.sqrt(area)
            * (component_height / height)
        )
        if best is None or salience > best[0]:
            best = (salience, component)
    if best is None or best[0] < 2.0:
        return None
    result = np.zeros((height, width), dtype=bool)
    y_values = np.fromiter((point[0] for point in best[1]), dtype=np.int32)
    x_values = np.fromiter((point[1] for point in best[1]), dtype=np.int32)
    result[y_values, x_values] = True
    # A reflected subject can otherwise become one long vertical blob. Measure
    # the broad horizontal transition outside the subject, then retain a
    # tapering trunk while leaving the reflection to the existing lower field.
    x_right = min(width - 2, int(x_values.max()) + max(3, round(0.05 * width)))
    context = source_lab[:, x_right:, :]
    if context.shape[1] >= max(8, round(0.12 * width)):
        row_blue = np.median(context[:, :, 2], axis=1)
        row_lightness = np.median(context[:, :, 0], axis=1)
        transition = np.abs(np.gradient(row_blue)) + 0.5 * np.abs(
            np.gradient(row_lightness)
        )
        search_start = round(0.50 * height)
        search_end = round(0.72 * height)
        horizon = search_start + int(np.argmax(transition[search_start:search_end]))
        subject_bottom = min(height - 1, horizon + round(0.09 * height))
        if int(y_values.max()) - subject_bottom > 0.10 * height:
            lower_subject = result.copy()
            lower_subject[: max(0, horizon - round(0.03 * height))] = False
            dark_limit = float(
                np.percentile(lightness[lower_subject], 45.0)
            )
            center_pixels = np.argwhere(lower_subject & (lightness <= dark_limit))
            trunk_center = (
                int(round(float(np.median(center_pixels[:, 1]))))
                if len(center_pixels)
                else int(round(float(np.median(x_values))))
            )
            result[subject_bottom + 1 :] = False
            for y_value in range(horizon, subject_bottom + 1):
                progress = (y_value - horizon) / max(1, subject_bottom - horizon)
                half_width = round(
                    (0.12 * width) * (1.0 - progress) + (0.03 * width) * progress
                )
                result[y_value, : max(0, trunk_center - half_width)] = False
                result[y_value, min(width, trunk_center + half_width + 1) :] = False
    result, _, _, _ = fill_small_enclosed_holes(result, 0.040)
    result = smooth_binary_boundary(result, radius=max(1.2, min(height, width) * 0.006))
    return result


def private_cool_shore_mask(source_lab: np.ndarray) -> np.ndarray | None:
    """Find a cool horizontal field entering a warm lower foreground from an edge."""
    height, width = source_lab.shape[:2]
    blue_axis = source_lab[:, :, 2]
    warm_foreground = float(
        np.median(blue_axis[round(0.65 * height) :, : round(0.45 * width)])
    )
    cool_midfield = float(
        np.median(
            blue_axis[
                round(0.43 * height) : round(0.64 * height),
                round(0.55 * width) :,
            ]
        )
    )
    if not (
        warm_foreground > 0.015
        and cool_midfield < 0.0
        and warm_foreground - cool_midfield > 0.035
    ):
        return None
    row_blue = np.median(blue_axis[:, round(0.55 * width) :], axis=1)
    row_change = np.abs(np.gradient(row_blue))
    search_start = round(0.35 * height)
    search_end = round(0.58 * height)
    horizon = search_start + int(np.argmax(row_change[search_start:search_end]))
    color_threshold = 0.5 * (warm_foreground + cool_midfield)
    candidate_mask = blue_axis < color_threshold
    candidate_mask[:horizon] = False
    filtered = Image.fromarray(
        np.where(candidate_mask, 255, 0).astype(np.uint8),
        mode="L",
    )
    filtered = filtered.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(9))
    candidate_mask = np.asarray(filtered, dtype=np.uint8) >= 128
    best: list[tuple[int, int]] | None = None
    total = height * width
    for component in private_binary_components(candidate_mask):
        if len(component) < 0.04 * total:
            continue
        y_values = np.fromiter((point[0] for point in component), dtype=np.int32)
        x_values = np.fromiter((point[1] for point in component), dtype=np.int32)
        if (
            int(x_values.max()) < width - 3
            or int(x_values.max() - x_values.min()) < 0.45 * width
            or int(y_values.max()) < 0.85 * height
        ):
            continue
        if best is None or len(component) > len(best):
            best = component
    if best is None:
        return None
    result = np.zeros((height, width), dtype=bool)
    y_values = np.fromiter((point[0] for point in best), dtype=np.int32)
    x_values = np.fromiter((point[1] for point in best), dtype=np.int32)
    result[y_values, x_values] = True
    result = smooth_binary_boundary(result, radius=max(1.2, min(height, width) * 0.006))
    return fill_enclosed_holes(result)


def private_repair_spatial_roles(
    source: np.ndarray,
    labels: np.ndarray,
    base_label_count: int,
) -> tuple[np.ndarray, list[tuple[int, int, int]]]:
    """Add measured spatial roles only after the private confidence gate opens."""
    source_lab = srgb_array_to_oklab(source)
    corridor_mask = private_perspective_corridor_mask(source_lab)
    silhouette_mask = private_isolated_silhouette_mask(source_lab)
    shore_mask = private_cool_shore_mask(source_lab)
    silhouette_color_mask = silhouette_mask
    if silhouette_mask is not None:
        lightness_limit = float(np.percentile(source_lab[:, :, 0][silhouette_mask], 40.0))
        silhouette_color_mask = silhouette_mask & (source_lab[:, :, 0] <= lightness_limit)
    shore_color_mask = shore_mask
    if shore_mask is not None:
        blue_limit = float(np.percentile(source_lab[:, :, 2][shore_mask], 30.0))
        shore_color_mask = shore_mask & (source_lab[:, :, 2] <= blue_limit)
    spatial_roles = (
        (corridor_mask, corridor_mask),
        (silhouette_mask, silhouette_color_mask),
        (shore_mask, shore_color_mask),
    )
    repaired = labels.copy()
    role_colors: list[tuple[int, int, int]] = []
    claimed = np.zeros_like(labels, dtype=bool)
    next_label = base_label_count
    for role_mask, color_mask in spatial_roles:
        if role_mask is None:
            continue
        role_mask = role_mask & (~claimed)
        if int(np.count_nonzero(role_mask)) < max(16, round(0.003 * labels.size)):
            continue
        if color_mask is None:
            color_mask = role_mask
        else:
            color_mask = color_mask & role_mask
        pixels = source[color_mask if np.any(color_mask) else role_mask]
        color = tuple(int(round(value)) for value in np.median(pixels, axis=0))
        repaired[role_mask] = next_label
        role_colors.append(color)
        claimed |= role_mask
        next_label += 1
    return repaired, role_colors


def quantized_labels(
    image: Image.Image,
    colors: int,
    smoothing: int,
    preserve_compact_islands: bool = True,
    preserve_perspective_lines: bool = True,
) -> tuple[np.ndarray, list[tuple[int, int, int]], dict[str, object]]:
    """Quantize into source-faithful, perceptually distinct color roles.

    Extracting exactly the requested number of median-cut bins lets a large
    smooth sky consume most of the palette. We first extract twice as many
    robust source candidates, lock the dominant and strongest chromatic roles,
    then spend the remaining slots on frequency-weighted Oklab diversity.
    """
    radius = max(1.1, max(image.size) / 185.0)
    softened = image.filter(ImageFilter.GaussianBlur(radius=radius))
    candidate_count = min(24, max(colors * 2, colors + 4))
    candidate_image = softened.quantize(
        colors=candidate_count,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    candidate_labels = np.asarray(candidate_image, dtype=np.uint8)
    source = np.asarray(image, dtype=np.uint8)
    total_pixels = source.shape[0] * source.shape[1]
    candidates: list[dict[str, object]] = []
    for label in range(candidate_count):
        pixels = source[candidate_labels == label]
        if not len(pixels):
            continue
        color = tuple(int(round(value)) for value in np.median(pixels, axis=0))
        lab = np.asarray(srgb_to_oklab(color), dtype=np.float64)
        candidates.append(
            {
                "color": color,
                "lab": lab,
                "population": int(len(pixels)),
                "chroma": float(np.linalg.norm(lab[1:])),
            }
        )

    dominant_index = max(range(len(candidates)), key=lambda index: int(candidates[index]["population"]))
    selected_indices = [dominant_index]
    accent_candidates = [
        index
        for index, candidate in enumerate(candidates)
        if int(candidate["population"]) / total_pixels >= 0.004
    ]
    accent_index = max(accent_candidates, key=lambda index: float(candidates[index]["chroma"]))
    accent_seed_color: str | None = None
    if accent_index != dominant_index and float(candidates[accent_index]["chroma"]) >= 0.040:
        selected_indices.append(accent_index)
        accent_seed_color = rgb_hex(candidates[accent_index]["color"])

    maximum_population = max(int(candidate["population"]) for candidate in candidates)
    while len(selected_indices) < colors:
        remaining_indices = [index for index in range(len(candidates)) if index not in selected_indices]

        def diversity_score(index: int) -> float:
            lab = np.asarray(candidates[index]["lab"], dtype=np.float64)
            minimum_distance = min(
                float(np.linalg.norm(lab - np.asarray(candidates[selected]["lab"], dtype=np.float64)))
                for selected in selected_indices
            )
            frequency = math.sqrt(int(candidates[index]["population"]) / maximum_population)
            return minimum_distance * (0.35 + 0.65 * frequency)

        selected_indices.append(max(remaining_indices, key=diversity_score))

    seed_palette = [candidates[index]["color"] for index in selected_indices]
    softened_lab = srgb_array_to_oklab(np.asarray(softened, dtype=np.uint8))
    center_lab = np.asarray([srgb_to_oklab(color) for color in seed_palette], dtype=np.float64)
    distances = np.sum((softened_lab[:, :, None, :] - center_lab[None, None, :, :]) ** 2, axis=-1)
    labels = np.argmin(distances, axis=-1).astype(np.uint8)
    labels_image = Image.fromarray(labels, mode="L")
    for _ in range(smoothing):
        labels_image = labels_image.filter(ImageFilter.ModeFilter(size=7))
    labels = np.asarray(labels_image, dtype=np.uint8)
    private_confidences = private_quadrant_confidences(
        softened_lab,
        distances,
        labels,
    )
    role_colors: list[tuple[int, int, int]] = []
    if min(private_confidences) < 0.56:
        labels, role_colors = private_repair_spatial_roles(source, labels, colors)

    compact_colors: list[tuple[int, int, int]] = []
    compact_area_fractions: list[float] = []
    compact_kinds: list[str] = []
    focal_support_colors: list[tuple[int, int, int]] = []
    focal_support_area_fractions: list[float] = []
    if preserve_compact_islands:
        (
            labels,
            compact_colors,
            compact_area_fractions,
            compact_kinds,
        ) = preserve_compact_salient_islands(
            image,
            labels,
            first_new_label=colors + len(role_colors),
            protected_label_start=colors,
        )
        if compact_kinds == ["rare-chromatic"]:
            compact_label = colors + len(role_colors)
            compact_mask = labels == compact_label
            support = preserve_row_relative_luminous_support(
                image,
                compact_mask,
            )
            if support is not None:
                support_mask, support_color, support_fraction = support
                labels[compact_mask] = compact_label + 1
                labels[support_mask & (~compact_mask)] = compact_label
                focal_support_colors.append(support_color)
                focal_support_area_fractions.append(
                    round(support_fraction, 6)
                )
                role_colors.extend(focal_support_colors)
        role_colors.extend(compact_colors)

    perspective_line_colors: list[tuple[int, int, int]] = []
    perspective_line_area_fractions: list[float] = []
    if preserve_perspective_lines:
        (
            labels,
            perspective_line_colors,
            perspective_line_area_fractions,
        ) = preserve_perspective_accent_line(
            image,
            labels,
            first_new_label=colors + len(role_colors),
        )
        role_colors.extend(perspective_line_colors)

    palette: list[tuple[int, int, int]] = []
    population_fractions: list[float] = []
    for label in range(colors + len(role_colors)):
        pixels = source[labels == label]
        if label >= colors:
            palette.append(role_colors[label - colors])
        elif len(pixels):
            median = np.median(pixels, axis=0)
            palette.append(tuple(int(round(value)) for value in median))
        else:
            palette.append(seed_palette[label])
        population_fractions.append(round(float(len(pixels)) / total_pixels, 6))
    metadata = {
        "palette_selection_model": "source Oklab diverse-role quantization",
        "palette_candidate_count": len(candidates),
        "palette_candidate_colors": [rgb_hex(candidate["color"]) for candidate in candidates],
        "palette_candidate_population_fractions": [
            round(int(candidate["population"]) / total_pixels, 6) for candidate in candidates
        ],
        "palette_seed_colors": [rgb_hex(color) for color in seed_palette],
        "palette_dominant_seed_color": rgb_hex(candidates[dominant_index]["color"]),
        "palette_accent_seed_color": accent_seed_color,
        "palette_population_fractions": population_fractions,
        "compact_salient_island_policy": "retain at most one compact locally contrasted, cross-field contrasted, or rare-chromatic focal island",
        "compact_salient_island_count": len(compact_colors),
        "compact_salient_island_area_fractions": compact_area_fractions,
        "compact_salient_island_kinds": compact_kinds,
        "focal_support_field_policy": "retain at most one row-relative luminous support field beneath a rare-chromatic focal island",
        "focal_support_field_count": len(focal_support_colors),
        "focal_support_field_area_fractions": focal_support_area_fractions,
        "perspective_accent_line_policy": "retain at most one chromatic center-leading line with bottom contact and convergent evidence",
        "perspective_accent_line_count": len(perspective_line_colors),
        "perspective_accent_line_area_fractions": perspective_line_area_fractions,
    }
    return labels, palette, metadata


def normalized_array_correlation(
    first: np.ndarray,
    second: np.ndarray,
) -> float:
    """Return a stable correlation for two equally shaped measured fields."""
    first_values = first.astype(np.float64)
    second_values = second.astype(np.float64)
    first_values = (first_values - first_values.mean()) / max(
        1e-6,
        float(first_values.std()),
    )
    second_values = (second_values - second_values.mean()) / max(
        1e-6,
        float(second_values.std()),
    )
    return float(np.mean(first_values * second_values))


def horizontal_reflection_evidence(
    image: Image.Image,
) -> dict[str, float | int] | None:
    """Detect a strong horizontal source/reflection relationship.

    The detector is deliberately relational. A wide source must contain one
    central horizontal transition whose vertically opposed lightness, chroma,
    and edge fields all correlate after reflection. Flat horizons, symmetric
    color gradients, and portrait scenes fail at least one independent gate.
    """
    width, height = image.size
    if width / max(1, height) < 1.35:
        return None
    broad = image.filter(
        ImageFilter.GaussianBlur(radius=max(3.0, width / 70.0))
    )
    source_lab = srgb_array_to_oklab(np.asarray(broad, dtype=np.uint8))
    lightness = source_lab[:, :, 0]
    chroma = source_lab[:, :, 1:]
    vertical_delta = np.linalg.norm(source_lab[1:] - source_lab[:-1], axis=2)
    row_edge = np.percentile(vertical_delta, 72.0, axis=1)
    inner = slice(round(0.04 * width), round(0.96 * width))
    candidates: list[tuple[float, int, float, float, float, float]] = []
    for axis in range(round(0.38 * height), round(0.64 * height)):
        depth = min(axis, height - axis, round(0.34 * height))
        if depth < round(0.15 * height):
            continue
        upper_lightness = lightness[axis - depth : axis][::-1]
        lower_lightness = lightness[axis : axis + depth]
        upper_chroma = chroma[axis - depth : axis][::-1]
        lower_chroma = chroma[axis : axis + depth]
        lightness_correlation = normalized_array_correlation(
            upper_lightness[:, inner],
            lower_lightness[:, inner],
        )
        chroma_correlation = normalized_array_correlation(
            upper_chroma[:, inner],
            lower_chroma[:, inner],
        )
        upper_gradient = np.sqrt(
            np.gradient(upper_lightness, axis=0) ** 2
            + np.gradient(upper_lightness, axis=1) ** 2
        )
        lower_gradient = np.sqrt(
            np.gradient(lower_lightness, axis=0) ** 2
            + np.gradient(lower_lightness, axis=1) ** 2
        )
        edge_correlation = normalized_array_correlation(
            upper_gradient[:, inner],
            lower_gradient[:, inner],
        )
        axis_edge = float(row_edge[axis - 1])
        score = (
            0.42 * lightness_correlation
            + 0.23 * chroma_correlation
            + 0.35 * edge_correlation
            + 1.4 * axis_edge
        )
        candidates.append(
            (
                score,
                axis,
                lightness_correlation,
                chroma_correlation,
                edge_correlation,
                axis_edge,
            )
        )
    if not candidates:
        return None
    (
        score,
        axis,
        lightness_correlation,
        chroma_correlation,
        edge_correlation,
        axis_edge,
    ) = max(candidates, key=lambda item: item[0])
    if (
        score < 0.72
        or not 0.42 <= axis / height <= 0.58
        or lightness_correlation < 0.80
        or chroma_correlation < 0.55
        or edge_correlation < 0.55
    ):
        return None
    return {
        "axis": axis,
        "score": round(score, 6),
        "lightness_correlation": round(lightness_correlation, 6),
        "chroma_correlation": round(chroma_correlation, 6),
        "edge_correlation": round(edge_correlation, 6),
        "axis_edge": round(axis_edge, 6),
    }


def reflective_outer_contour(
    image: Image.Image,
    axis: int,
) -> np.ndarray:
    """Trace one restrained upper outer contour with dynamic programming."""
    width, height = image.size
    fine = image.filter(ImageFilter.GaussianBlur(radius=1.2))
    broad = image.filter(ImageFilter.GaussianBlur(radius=5.5))
    fine_lab = srgb_array_to_oklab(np.asarray(fine, dtype=np.uint8))
    broad_lab = srgb_array_to_oklab(np.asarray(broad, dtype=np.uint8))
    texture = np.linalg.norm(fine_lab - broad_lab, axis=2)
    minimum_y = max(4, round(0.015 * height))
    maximum_y = axis - 7
    score = np.full((height, width), -1e9, dtype=np.float64)
    for y_value in range(minimum_y, maximum_y + 1):
        upper = broad_lab[
            max(0, y_value - 7) : max(1, y_value - 2)
        ].mean(axis=0)
        lower = broad_lab[
            min(height - 1, y_value + 2) : min(height, y_value + 8)
        ].mean(axis=0)
        color_jump = np.linalg.norm(lower - upper, axis=1)
        edge = np.linalg.norm(
            broad_lab[min(height - 1, y_value + 1)]
            - broad_lab[max(0, y_value - 1)],
            axis=1,
        )
        upper_texture = texture[
            max(0, y_value - 8) : max(1, y_value - 2)
        ].mean(axis=0)
        lower_texture = texture[
            min(height - 1, y_value + 2) : min(height, y_value + 9)
        ].mean(axis=0)
        score[y_value] = (
            1.25 * color_jump
            + 1.8 * edge
            + 3.0 * (lower_texture - upper_texture)
            - 0.00110 * y_value
        )
    score[:, :3] *= 1.12
    score[:, -3:] *= 1.12
    positions = maximum_y - minimum_y + 1
    cost = np.full((positions, width), -1e9, dtype=np.float64)
    back = np.zeros((positions, width), dtype=np.int16)
    cost[:, 0] = score[minimum_y : maximum_y + 1, 0]
    max_step = max(4, round(0.028 * height))
    for x_value in range(1, width):
        for local_y in range(positions):
            low = max(0, local_y - max_step)
            high = min(positions, local_y + max_step + 1)
            previous = cost[low:high, x_value - 1]
            deltas = np.arange(low, high) - local_y
            candidate = (
                previous
                - 0.0045 * deltas * deltas
                - 0.0040 * np.abs(deltas)
            )
            best_index = int(np.argmax(candidate))
            back[local_y, x_value] = low + best_index
            cost[local_y, x_value] = (
                score[minimum_y + local_y, x_value]
                + candidate[best_index]
            )
    line = np.zeros(width, dtype=np.int32)
    endpoint_values = score[minimum_y : maximum_y + 1, -1]
    endpoint_threshold = 0.94 * float(endpoint_values.max())
    endpoint_candidates = np.flatnonzero(
        endpoint_values >= endpoint_threshold
    )
    line[-1] = minimum_y + int(endpoint_candidates[0])
    for x_value in range(width - 1, 0, -1):
        line[x_value - 1] = minimum_y + back[
            line[x_value] - minimum_y,
            x_value,
        ]
    kernel_radius = 12
    kernel_positions = np.arange(-kernel_radius, kernel_radius + 1)
    kernel = np.exp(-0.5 * (kernel_positions / 4.0) ** 2)
    kernel /= kernel.sum()
    line = np.rint(
        np.convolve(
            np.pad(line.astype(np.float64), kernel_radius, mode="edge"),
            kernel,
            mode="valid",
        )
    ).astype(np.int32)

    # Remove deep compact valleys caused by internal texture transitions, but
    # blend the envelope back with the measured contour so source-given bends
    # remain curved instead of collapsing into a geometric plateau.
    envelope_radius = max(9, round(0.085 * width))
    padded = np.pad(line, envelope_radius, mode="edge")
    eroded = np.minimum.reduce(
        [
            padded[offset : offset + width]
            for offset in range(2 * envelope_radius + 1)
        ]
    )
    padded_eroded = np.pad(eroded, envelope_radius, mode="edge")
    opened = np.maximum.reduce(
        [
            padded_eroded[offset : offset + width]
            for offset in range(2 * envelope_radius + 1)
        ]
    )
    line = np.rint(
        0.35 * line + 0.65 * np.minimum(line, opened)
    ).astype(np.int32)
    return np.clip(line, minimum_y, maximum_y)


def reflective_horizontal_layers(
    image: Image.Image,
    output_width: int,
    output_height: int,
    evidence: dict[str, float | int],
    color_mode: str,
    curve_smoothing: float,
    gradient_strength: float,
) -> tuple[
    tuple[int, int, int],
    list[SvgLayer],
    dict[str, str],
    np.ndarray,
    tuple[int, int, int],
    list[tuple[int, int, int]],
    list[tuple[int, int, int]],
    list[float],
    dict[str, object],
]:
    """Build a sparse paired composition around a measured reflection axis."""
    width, height = image.size
    axis = int(evidence["axis"])
    outer_contour = reflective_outer_contour(image, axis)
    y_grid = np.arange(height)[:, None]
    upper_terrain = (
        (y_grid >= outer_contour[None, :])
        & (y_grid < axis)
    )
    reflected_terrain = np.zeros((height, width), dtype=bool)
    for x_value, skyline_y in enumerate(outer_contour):
        reflected_bottom = min(
            height,
            axis + (axis - int(skyline_y)),
        )
        reflected_terrain[axis:reflected_bottom, x_value] = True
    water = np.broadcast_to(y_grid >= axis, (height, width)).copy()
    sky_field = np.broadcast_to(y_grid < axis, (height, width)).copy()
    sky_source = sky_field & (~upper_terrain)

    broad = image.filter(ImageFilter.GaussianBlur(radius=5.5))
    source_lab = srgb_array_to_oklab(np.asarray(broad, dtype=np.uint8))
    lightness = source_lab[:, :, 0]
    chroma = np.linalg.norm(source_lab[:, :, 1:], axis=2)
    rock_seed = (
        upper_terrain
        & (lightness >= np.percentile(lightness[upper_terrain], 57.0))
        & (chroma <= np.percentile(chroma[upper_terrain], 52.0))
    )
    upper_rock = smooth_binary_boundary(
        clean_binary_mask(rock_seed, closing_size=13, mode_size=11),
        radius=5.5,
    )
    upper_rock &= upper_terrain
    rock_components = components_from_mask(
        upper_rock,
        min_fraction=0.012,
        limit=2,
    )
    upper_rock = np.zeros_like(upper_terrain)
    for component in rock_components:
        for y_value, x_value in component:
            upper_rock[y_value, x_value] = True

    green_seed = (
        upper_terrain
        & (source_lab[:, :, 1] < -0.012)
        & (source_lab[:, :, 2] > 0.010)
        & (lightness < np.percentile(lightness[upper_terrain], 64.0))
    )
    vegetation = smooth_binary_boundary(
        clean_binary_mask(green_seed, closing_size=11, mode_size=9),
        radius=4.5,
    )
    vegetation &= upper_terrain
    vegetation_components = components_from_mask(
        vegetation,
        min_fraction=0.006,
        limit=2,
    )
    vegetation = np.zeros_like(upper_terrain)
    for component in vegetation_components:
        for y_value, x_value in component:
            vegetation[y_value, x_value] = True

    reflected_rock = np.zeros_like(upper_terrain)
    reflected_vegetation = np.zeros_like(upper_terrain)
    for y_value in range(axis):
        reflected_y = 2 * axis - 1 - y_value
        if reflected_y >= height:
            continue
        reflected_rock[reflected_y] = upper_rock[y_value]
        reflected_vegetation[reflected_y] = vegetation[y_value]
    reflected_rock &= reflected_terrain
    reflected_vegetation &= reflected_terrain
    shore = np.zeros_like(upper_terrain)
    shore[max(0, axis - 2) : min(height, axis + 4), :] = True

    array = np.asarray(image, dtype=np.uint8)
    role_specs: list[tuple[str, np.ndarray, np.ndarray, bool]] = [
        ("sky-field", sky_field, sky_source, True),
        ("water-field", water, water, True),
        ("upper-terrain", upper_terrain, upper_terrain, True),
        (
            "reflected-terrain",
            reflected_terrain,
            reflected_terrain,
            True,
        ),
    ]
    if np.any(vegetation):
        role_specs.append(
            ("upper-vegetation", vegetation, vegetation, True)
        )
    if np.any(reflected_vegetation):
        role_specs.append(
            (
                "reflected-vegetation",
                reflected_vegetation,
                reflected_vegetation,
                True,
            )
        )
    if np.any(upper_rock):
        role_specs.append(
            ("upper-rock-light", upper_rock, upper_rock, True)
        )
    if np.any(reflected_rock):
        role_specs.append(
            (
                "reflected-rock-light",
                reflected_rock,
                reflected_rock,
                True,
            )
        )
    role_specs.append(("shore-divider", shore, shore, False))

    source_colors = [
        median_color(array, source_mask)
        for _, _, source_mask, _ in role_specs
    ]
    output_colors = [
        output_color(color, color_mode) for color in source_colors
    ]
    background_color = output_colors[0]
    frame_bleed = frame_bleed_margin(width, height)
    layers: list[SvgLayer] = []
    gradient_axes: dict[str, str] = {}
    frame_edges: dict[str, list[str]] = {}
    for index, (name, mask, source_mask, allow_gradient) in enumerate(
        role_specs
    ):
        path = pixels_svg_path(
            [
                (int(y_value), int(x_value))
                for y_value, x_value in np.argwhere(mask)
            ],
            width,
            height,
            output_width,
            output_height,
            epsilon=2.25,
            curve_smoothing=min(0.92, curve_smoothing + 0.04),
            smoothing_passes=4,
            frame_bleed=frame_bleed,
        )
        color = output_colors[index]
        gradient = (
            source_gradient(
                array,
                source_mask,
                color,
                gradient_strength,
                f"gradient-{name}",
            )
            if allow_gradient
            else None
        )
        if gradient is not None:
            gradient_axes[name] = gradient.axis
        layers.append(SvgLayer(name, path, color, gradient=gradient))
        frame_edges[name] = touched_frame_edges(mask)

    role_areas = [
        int(np.count_nonzero(mask)) for _, mask, _, _ in role_specs
    ]
    role_total = sum(role_areas)
    population_fractions = [
        round(area / role_total, 6) for area in role_areas
    ]
    population_fractions[-1] = round(
        population_fractions[-1]
        + (1.0 - sum(population_fractions)),
        6,
    )
    reflected_area_delta = abs(
        int(np.count_nonzero(upper_terrain))
        - int(np.count_nonzero(reflected_terrain))
    ) / max(1, int(np.count_nonzero(upper_terrain)))
    metadata = {
        "archetype": "reflective-horizontal-fields",
        "reflection_detection_policy": "wide central axis with opposed lightness, chroma, and edge agreement",
        "reflection_axis_analysis_row": axis,
        "reflection_axis_fraction": round(axis / height, 6),
        "reflection_score": evidence["score"],
        "reflection_lightness_correlation": evidence[
            "lightness_correlation"
        ],
        "reflection_chroma_correlation": evidence["chroma_correlation"],
        "reflection_edge_correlation": evidence["edge_correlation"],
        "reflection_axis_edge_strength": evidence["axis_edge"],
        "reflection_shape_policy": "dynamic upper outer contour with vertically paired lower fields",
        "reflection_contour_policy": "four-pass curved fitting after compact-valley envelope regularization",
        "reflection_color_policy": "sample upper and lower roles independently from their source masks",
        "reflection_role_count": len(layers),
        "reflection_role_ids": [layer.name for layer in layers],
        "reflection_pair_vertical_area_delta_fraction": round(
            reflected_area_delta,
            6,
        ),
        "reflection_frame_edges_touched": frame_edges,
        "gradient_axes": gradient_axes,
    }
    point_mask = np.zeros((height, width), dtype=bool)
    highlight_color = max(output_colors, key=lambda color: sum(color))
    return (
        background_color,
        layers,
        {},
        point_mask,
        highlight_color,
        source_colors,
        output_colors,
        population_fractions,
        metadata,
    )


def preserve_compact_salient_islands(
    image: Image.Image,
    labels: np.ndarray,
    first_new_label: int,
    protected_label_start: int,
) -> tuple[
    np.ndarray,
    list[tuple[int, int, int]],
    list[float],
    list[str],
]:
    """Preserve one small source-defining island without restoring clutter.

    Ordinary region retention deliberately favors broad fields, so a compact
    object can disappear even when it is the only strong local interruption in
    a smooth background. Detect that relationship rather than an object class:
    use either a detached local-contrast island inside one stable field, one
    compact source-rare interruption across a junction of stable fields, or one
    coherent rare-chromatic focal cluster inside an otherwise hue-restrained
    scene.
    """
    width, height = image.size
    total = width * height
    fine = image.filter(
        ImageFilter.GaussianBlur(radius=max(1.0, max(image.size) / 260.0))
    )
    broad = image.filter(
        ImageFilter.GaussianBlur(radius=max(6.0, max(image.size) / 42.0))
    )
    fine_array = np.asarray(fine, dtype=np.uint8)
    fine_lab = srgb_array_to_oklab(fine_array)
    broad_lab = srgb_array_to_oklab(np.asarray(broad, dtype=np.uint8))
    local_delta = np.linalg.norm(fine_lab - broad_lab, axis=2)
    threshold = max(0.085, float(np.percentile(local_delta, 98.2)))
    seed_mask = local_delta >= threshold
    seed_mask[:2, :] = False
    seed_mask[-2:, :] = False
    seed_mask[:, :2] = False
    seed_mask[:, -2:] = False
    seed_image = Image.fromarray(
        np.where(seed_mask, 255, 0).astype(np.uint8),
        mode="L",
    )
    seed_image = seed_image.filter(ImageFilter.MaxFilter(5)).filter(
        ImageFilter.MinFilter(5)
    )
    seed_image = seed_image.filter(ImageFilter.ModeFilter(5))
    seed_mask = np.asarray(seed_image, dtype=np.uint8) >= 128

    candidates: list[
        tuple[
            float,
            np.ndarray,
            tuple[int, int, int],
            float,
            str,
        ]
    ] = []
    ring_size = max(7, round(min(width, height) * 0.035))
    if ring_size % 2 == 0:
        ring_size += 1
    for component in private_binary_components(seed_mask):
        area = len(component)
        area_fraction = area / total
        if not 0.0008 <= area_fraction <= 0.025:
            continue
        y_values = np.fromiter((point[0] for point in component), dtype=np.int32)
        x_values = np.fromiter((point[1] for point in component), dtype=np.int32)
        minimum_x = int(x_values.min())
        maximum_x = int(x_values.max())
        minimum_y = int(y_values.min())
        maximum_y = int(y_values.max())
        if (
            minimum_x <= 2
            or minimum_y <= 2
            or maximum_x >= width - 3
            or maximum_y >= height - 3
        ):
            continue
        component_width = maximum_x - minimum_x + 1
        component_height = maximum_y - minimum_y + 1
        if component_width > width * 0.34 or component_height > height * 0.30:
            continue
        compactness = area / (component_width * component_height)
        aspect = min(component_width, component_height) / max(
            component_width,
            component_height,
        )
        if compactness < 0.18 or aspect < 0.20:
            continue

        component_mask = np.zeros_like(labels, dtype=bool)
        component_mask[y_values, x_values] = True
        existing_labels = labels[component_mask]
        if np.mean(existing_labels >= protected_label_start) > 0.30:
            continue
        inner_band = dilate_binary_mask(component_mask, 3)
        ring_mask = dilate_binary_mask(component_mask, ring_size) & (~inner_band)
        if not np.any(ring_mask):
            continue
        _, ring_counts = np.unique(labels[ring_mask], return_counts=True)
        ring_purity = float(ring_counts.max() / ring_counts.sum())
        if ring_purity < 0.82:
            continue
        ring_lab = fine_lab[ring_mask]
        background_lab = np.median(ring_lab, axis=0)
        ring_spread = float(
            np.median(np.linalg.norm(ring_lab - background_lab, axis=1))
        )
        if ring_spread > 0.065:
            continue
        component_color_array = np.median(fine_array[component_mask], axis=0)
        background_color_array = np.median(fine_array[ring_mask], axis=0)
        component_color = tuple(int(round(value)) for value in component_color_array)
        background_color = tuple(int(round(value)) for value in background_color_array)
        local_contrast = color_distance(component_color, background_color)
        if local_contrast < 0.095:
            continue

        component_lab = np.median(fine_lab[component_mask], axis=0)
        lab_contrast = float(np.linalg.norm(component_lab - background_lab))
        growth_domain = (
            np.linalg.norm(fine_lab - background_lab, axis=2)
            >= max(0.045, lab_contrast * 0.33)
        ) & dilate_binary_mask(component_mask, 13)
        grown_mask = component_mask.copy()
        for _ in range(16):
            next_mask = (
                dilate_binary_mask(grown_mask, 3) & growth_domain
            ) | component_mask
            if np.array_equal(next_mask, grown_mask):
                break
            grown_mask = next_mask
        grown_mask = clean_binary_mask(
            grown_mask,
            closing_size=5,
            mode_size=3,
        ) | component_mask
        grown_mask |= enclosed_hole_mask(grown_mask)
        source_color_array = np.median(
            np.asarray(image, dtype=np.uint8)[grown_mask],
            axis=0,
        )
        source_color = tuple(int(round(value)) for value in source_color_array)
        grown_fraction = float(np.count_nonzero(grown_mask)) / total
        score = local_contrast * math.sqrt(area_fraction) * compactness
        candidates.append(
            (
                score,
                grown_mask,
                source_color,
                grown_fraction,
                "local-contrast",
            )
        )

    junction_fallback: (
        tuple[float, np.ndarray, tuple[int, int, int], float, str] | None
    ) = None

    # A compact subject may sit exactly on the junction between two or three
    # broad fields: a cabin on a horizon, a boat across water and sky, or a
    # figure crossing a ridge. The single-field ring test above deliberately
    # rejects such cases. When no simpler candidate survived, model the local
    # ring as a small set of stable roles and retain only the compact pixels
    # that remain unlike every role. Global color rarity and a vertical floor
    # keep this exception from restoring ordinary boundary texture.
    if not candidates:
        junction_candidates: list[
            tuple[float, np.ndarray, tuple[int, int, int], float, str]
        ] = []
        for component in private_binary_components(seed_mask):
            area = len(component)
            area_fraction = area / total
            if not 0.0008 <= area_fraction <= 0.025:
                continue
            y_values = np.fromiter(
                (point[0] for point in component),
                dtype=np.int32,
            )
            x_values = np.fromiter(
                (point[1] for point in component),
                dtype=np.int32,
            )
            minimum_x = int(x_values.min())
            maximum_x = int(x_values.max())
            minimum_y = int(y_values.min())
            maximum_y = int(y_values.max())
            if (
                minimum_x <= 2
                or minimum_y <= 2
                or maximum_x >= width - 3
                or maximum_y >= height - 3
            ):
                continue
            component_width = maximum_x - minimum_x + 1
            component_height = maximum_y - minimum_y + 1
            if (
                component_width > width * 0.34
                or component_height > height * 0.30
            ):
                continue
            compactness = area / (component_width * component_height)
            aspect = min(component_width, component_height) / max(
                component_width,
                component_height,
            )
            if compactness < 0.18 or aspect < 0.20:
                continue

            component_mask = np.zeros_like(labels, dtype=bool)
            component_mask[y_values, x_values] = True
            existing_labels = labels[component_mask]
            if np.mean(existing_labels >= protected_label_start) > 0.30:
                continue
            inner_band = dilate_binary_mask(component_mask, 3)
            ring_mask = (
                dilate_binary_mask(component_mask, ring_size) & (~inner_band)
            )
            if not np.any(ring_mask):
                continue
            ring_labels, ring_counts = np.unique(
                labels[ring_mask],
                return_counts=True,
            )
            order = np.argsort(ring_counts)[::-1]
            ring_shares = ring_counts[order] / ring_counts.sum()
            if float(ring_shares[0]) >= 0.82:
                continue
            role_indices = [
                int(ring_labels[order[index]])
                for index in range(min(3, len(order)))
                if float(ring_shares[index]) >= 0.10
            ]
            role_coverage = float(
                sum(
                    ring_shares[index]
                    for index in range(min(3, len(order)))
                    if float(ring_shares[index]) >= 0.10
                )
            )
            if not 2 <= len(role_indices) <= 3 or role_coverage < 0.88:
                continue
            role_labs = np.asarray(
                [
                    np.median(
                        fine_lab[ring_mask & (labels == label)],
                        axis=0,
                    )
                    for label in role_indices
                ],
                dtype=np.float64,
            )
            distance_to_roles = np.min(
                np.linalg.norm(
                    fine_lab[:, :, None, :] - role_labs[None, None, :, :],
                    axis=3,
                ),
                axis=2,
            )
            candidate_envelope = np.zeros_like(component_mask, dtype=bool)
            candidate_envelope[
                minimum_y : maximum_y + 1,
                minimum_x : maximum_x + 1,
            ] = True
            residual_mask = candidate_envelope & (distance_to_roles >= 0.075)
            residual_image = Image.fromarray(
                np.where(residual_mask, 255, 0).astype(np.uint8),
                mode="L",
            )
            residual_image = residual_image.filter(
                ImageFilter.MaxFilter(3)
            ).filter(ImageFilter.MinFilter(3))
            residual_image = residual_image.filter(
                ImageFilter.MinFilter(5)
            ).filter(ImageFilter.MaxFilter(5))
            residual_mask = np.asarray(residual_image, dtype=np.uint8) >= 128
            residual_mask = fill_enclosed_holes(residual_mask)

            for residual_component in private_binary_components(residual_mask):
                residual_area = len(residual_component)
                residual_fraction = residual_area / total
                if not 0.0007 <= residual_fraction <= 0.022:
                    continue
                residual_y = np.fromiter(
                    (point[0] for point in residual_component),
                    dtype=np.int32,
                )
                residual_x = np.fromiter(
                    (point[1] for point in residual_component),
                    dtype=np.int32,
                )
                residual_width = int(residual_x.max() - residual_x.min() + 1)
                residual_height = int(residual_y.max() - residual_y.min() + 1)
                residual_compactness = residual_area / (
                    residual_width * residual_height
                )
                residual_aspect = min(
                    residual_width,
                    residual_height,
                ) / max(residual_width, residual_height)
                if residual_compactness < 0.25 or residual_aspect < 0.16:
                    continue
                if float(np.mean(residual_y)) >= 0.80 * height:
                    continue
                selected_mask = np.zeros_like(labels, dtype=bool)
                selected_mask[residual_y, residual_x] = True
                selected_lab = np.median(fine_lab[selected_mask], axis=0)
                coherence = float(
                    np.median(
                        np.linalg.norm(
                            fine_lab[selected_mask] - selected_lab,
                            axis=1,
                        )
                    )
                )
                global_rarity = float(
                    np.mean(
                        np.linalg.norm(fine_lab - selected_lab, axis=2)
                        <= 0.035
                    )
                )
                role_contrast = float(
                    np.min(np.linalg.norm(role_labs - selected_lab, axis=1))
                )
                if (
                    coherence > 0.100
                    or global_rarity > 0.045
                    or role_contrast < 0.075
                ):
                    continue
                selected_color_array = np.median(
                    fine_array[selected_mask],
                    axis=0,
                )
                selected_color = tuple(
                    int(round(value)) for value in selected_color_array
                )
                score = (
                    role_contrast
                    * math.sqrt(residual_fraction)
                    * residual_compactness
                    * (0.50 + 0.50 * role_coverage)
                )
                junction_candidates.append(
                    (
                        score,
                        selected_mask,
                        selected_color,
                        residual_fraction,
                        "cross-field-contrast",
                    )
                )
        if junction_candidates:
            junction_candidates.sort(key=lambda item: item[0], reverse=True)
            junction_fallback = junction_candidates[0]

    # In a hue-restrained scene, one composition-defining focal cluster can
    # have weaker edges than surrounding texture. Preserve the relationship by
    # color rarity and geometry without testing a fixed hue or object class.
    if not candidates:
        chromatic = fine_lab[:, :, 1:]
        global_chromatic_median = np.median(chromatic, axis=(0, 1))
        chromatic_outlier = np.linalg.norm(
            chromatic - global_chromatic_median,
            axis=2,
        )
        raw_outlier_threshold = float(np.percentile(chromatic_outlier, 98.2))
        broad_chromatic_spread = float(np.percentile(chromatic_outlier, 90.0))
        if (
            0.030 <= raw_outlier_threshold <= 0.055
            and broad_chromatic_spread <= 0.035
        ):
            rare_mask = chromatic_outlier >= raw_outlier_threshold
            rare_mask[:2, :] = False
            rare_mask[-2:, :] = False
            rare_mask[:, :2] = False
            rare_mask[:, -2:] = False
            rare_image = Image.fromarray(
                np.where(rare_mask, 255, 0).astype(np.uint8),
                mode="L",
            )
            rare_image = rare_image.filter(ImageFilter.MaxFilter(7)).filter(
                ImageFilter.MinFilter(5)
            )
            rare_image = rare_image.filter(ImageFilter.ModeFilter(3))
            rare_mask = np.asarray(rare_image, dtype=np.uint8) >= 128
            rare_candidates: list[
                tuple[float, np.ndarray, tuple[int, int, int], float, str]
            ] = []
            rare_components = private_binary_components(rare_mask)
            for component in rare_components:
                area = len(component)
                area_fraction = area / total
                if not 0.001 <= area_fraction <= 0.025:
                    continue
                y_values = np.fromiter(
                    (point[0] for point in component),
                    dtype=np.int32,
                )
                x_values = np.fromiter(
                    (point[1] for point in component),
                    dtype=np.int32,
                )
                minimum_x = int(x_values.min())
                maximum_x = int(x_values.max())
                minimum_y = int(y_values.min())
                maximum_y = int(y_values.max())
                if (
                    minimum_x <= 2
                    or minimum_y <= 2
                    or maximum_x >= width - 3
                    or maximum_y >= height - 3
                ):
                    continue
                component_width = maximum_x - minimum_x + 1
                component_height = maximum_y - minimum_y + 1
                if component_width > width * 0.34 or component_height > height * 0.30:
                    continue
                compactness = area / (component_width * component_height)
                aspect = min(component_width, component_height) / max(
                    component_width,
                    component_height,
                )
                if compactness < 0.25 or aspect < 0.18:
                    continue
                component_mask = np.zeros_like(labels, dtype=bool)
                component_mask[y_values, x_values] = True
                _, existing_counts = np.unique(
                    labels[component_mask],
                    return_counts=True,
                )
                existing_role_purity = float(
                    existing_counts.max() / existing_counts.sum()
                )
                # Do not add an internal accent when one existing field already
                # represents the focal cluster coherently; that would fragment
                # a cabin, tree, or other already-legible subject.
                if existing_role_purity >= 0.80:
                    continue
                component_chromatic = np.median(chromatic[component_mask], axis=0)
                chromatic_contrast = float(
                    np.linalg.norm(component_chromatic - global_chromatic_median)
                )
                component_spread = float(
                    np.median(
                        np.linalg.norm(
                            chromatic[component_mask] - component_chromatic,
                            axis=1,
                        )
                    )
                )
                if (
                    chromatic_contrast < raw_outlier_threshold * 0.82
                    or component_spread > 0.035
                ):
                    continue
                inner_band = dilate_binary_mask(component_mask, 3)
                ring_mask = dilate_binary_mask(component_mask, ring_size) & (~inner_band)
                if not np.any(ring_mask):
                    continue
                ring_chromatic = np.median(chromatic[ring_mask], axis=0)
                local_chromatic_contrast = float(
                    np.linalg.norm(component_chromatic - ring_chromatic)
                )
                if local_chromatic_contrast < 0.016:
                    continue
                selected_mask = component_mask.copy()
                main_chromatic_vector = (
                    component_chromatic - global_chromatic_median
                )
                main_chromatic_length = float(
                    np.linalg.norm(main_chromatic_vector)
                )
                # Join only a small, hue-aligned cap immediately above the
                # focal cluster. A weak neutral interval can otherwise split a
                # tower, spire, mast, or roof cap from its main silhouette.
                for satellite in rare_components:
                    if satellite is component:
                        continue
                    satellite_area_fraction = len(satellite) / total
                    if not 0.00015 <= satellite_area_fraction <= 0.004:
                        continue
                    satellite_y = np.fromiter(
                        (point[0] for point in satellite),
                        dtype=np.int32,
                    )
                    satellite_x = np.fromiter(
                        (point[1] for point in satellite),
                        dtype=np.int32,
                    )
                    satellite_minimum_x = int(satellite_x.min())
                    satellite_maximum_x = int(satellite_x.max())
                    satellite_minimum_y = int(satellite_y.min())
                    satellite_maximum_y = int(satellite_y.max())
                    if satellite_maximum_y >= minimum_y:
                        continue
                    vertical_gap = minimum_y - satellite_maximum_y - 1
                    horizontal_overlap = min(
                        maximum_x,
                        satellite_maximum_x,
                    ) - max(minimum_x, satellite_minimum_x) + 1
                    if (
                        vertical_gap < 0
                        or vertical_gap > 0.045 * height
                        or horizontal_overlap <= 0
                    ):
                        continue
                    satellite_chromatic = np.median(
                        chromatic[satellite_y, satellite_x],
                        axis=0,
                    )
                    satellite_vector = (
                        satellite_chromatic - global_chromatic_median
                    )
                    satellite_length = float(np.linalg.norm(satellite_vector))
                    if main_chromatic_length <= 0.0 or satellite_length <= 0.0:
                        continue
                    direction_agreement = float(
                        np.dot(main_chromatic_vector, satellite_vector)
                        / (main_chromatic_length * satellite_length)
                    )
                    if direction_agreement < 0.82:
                        continue
                    selected_mask[satellite_y, satellite_x] = True
                    bridge_center = int(round(float(np.median(satellite_x))))
                    bridge_center = min(
                        maximum_x,
                        max(minimum_x, bridge_center),
                    )
                    satellite_width = (
                        satellite_maximum_x - satellite_minimum_x + 1
                    )
                    bridge_half_width = max(
                        1,
                        round(min(component_width, satellite_width) * 0.18),
                    )
                    selected_mask[
                        satellite_maximum_y + 1 : minimum_y,
                        max(0, bridge_center - bridge_half_width) : min(
                            width,
                            bridge_center + bridge_half_width + 1,
                        ),
                    ] = True
                selected_mask = fill_enclosed_holes(selected_mask)
                selected_mask = smooth_binary_boundary(
                    selected_mask,
                    radius=max(0.45, min(width, height) * 0.0018),
                )
                chromatic_direction = (
                    main_chromatic_vector / main_chromatic_length
                )
                chromatic_projection = np.sum(
                    (chromatic - global_chromatic_median)
                    * chromatic_direction,
                    axis=2,
                )
                projection_limit = float(
                    np.percentile(chromatic_projection[component_mask], 58.0)
                )
                color_domain = component_mask & (
                    chromatic_projection >= projection_limit
                )
                source_color_array = np.median(
                    np.asarray(image, dtype=np.uint8)[color_domain],
                    axis=0,
                )
                source_color = tuple(
                    int(round(value)) for value in source_color_array
                )
                selected_fraction = float(np.count_nonzero(selected_mask)) / total
                score = (
                    local_chromatic_contrast
                    * math.sqrt(area_fraction)
                    * compactness
                )
                rare_candidates.append(
                    (
                        score,
                        selected_mask,
                        source_color,
                        selected_fraction,
                        "rare-chromatic",
                    )
                )
            if rare_candidates:
                rare_candidates.sort(key=lambda item: item[0], reverse=True)
                candidates.append(rare_candidates[0])

    if not candidates and junction_fallback is not None:
        candidates.append(junction_fallback)

    if not candidates:
        return labels.copy(), [], [], []
    candidates.sort(key=lambda item: item[0], reverse=True)
    (
        _,
        selected_mask,
        selected_color,
        selected_fraction,
        selected_kind,
    ) = candidates[0]
    repaired = labels.copy()
    repaired[selected_mask] = first_new_label
    return (
        repaired,
        [selected_color],
        [round(selected_fraction, 6)],
        [selected_kind],
    )


def preserve_row_relative_luminous_support(
    image: Image.Image,
    focal_mask: np.ndarray,
) -> tuple[np.ndarray, tuple[int, int, int], float] | None:
    """Recover one coherent light support mass underneath a rare focal role.

    A broad snow-, sand-, foam-, or light-ground mass can have nearly the same
    absolute color as atmosphere while remaining clearly brighter than the
    open field beside it. Compare lightness row by row against both side bands,
    then keep only a large frame-connected component adjacent to the measured
    focal island. This avoids semantic scene labels and does not activate
    without the independent rare-chromatic focal evidence.
    """
    if not np.any(focal_mask):
        return None
    width, height = image.size
    total = width * height
    source = np.asarray(image, dtype=np.uint8)
    softened = image.filter(ImageFilter.GaussianBlur(radius=2.0))
    source_lab = srgb_array_to_oklab(np.asarray(softened, dtype=np.uint8))
    lightness = source_lab[:, :, 0]
    focal_y, focal_x = np.nonzero(focal_mask)
    minimum_y = int(focal_y.min())
    maximum_y = int(focal_y.max())
    vertical_start = max(2, minimum_y - round(0.20 * height))
    vertical_end = min(height - 2, maximum_y + round(0.42 * height))
    adjacency_size = max(7, round(min(width, height) * 0.040))
    if adjacency_size % 2 == 0:
        adjacency_size += 1
    focal_neighborhood = dilate_binary_mask(focal_mask, adjacency_size)
    candidates: list[
        tuple[float, np.ndarray, tuple[int, int, int], float]
    ] = []
    side_bands = (
        slice(0, max(3, round(0.22 * width))),
        slice(min(width - 3, round(0.78 * width)), width),
    )
    for side_band in side_bands:
        row_reference = np.median(lightness[:, side_band], axis=1)
        residual = lightness - row_reference[:, None]
        support_seed = residual >= 0.050
        support_seed[:vertical_start, :] = False
        support_seed[vertical_end:, :] = False
        support_image = Image.fromarray(
            np.where(support_seed, 255, 0).astype(np.uint8),
            mode="L",
        )
        support_image = support_image.filter(ImageFilter.MaxFilter(9)).filter(
            ImageFilter.MinFilter(7)
        )
        support_image = support_image.filter(ImageFilter.ModeFilter(5))
        support_seed = np.asarray(support_image, dtype=np.uint8) >= 128
        for component in private_binary_components(support_seed):
            area_fraction = len(component) / total
            if not 0.045 <= area_fraction <= 0.32:
                continue
            y_values = np.fromiter(
                (point[0] for point in component),
                dtype=np.int32,
            )
            x_values = np.fromiter(
                (point[1] for point in component),
                dtype=np.int32,
            )
            component_width = int(x_values.max() - x_values.min() + 1)
            component_height = int(y_values.max() - y_values.min() + 1)
            if (
                component_width < 0.35 * width
                or component_height < 0.12 * height
                or (
                    int(x_values.min()) > 2
                    and int(x_values.max()) < width - 3
                )
            ):
                continue
            component_mask = np.zeros_like(focal_mask, dtype=bool)
            component_mask[y_values, x_values] = True
            adjacency = int(
                np.count_nonzero(component_mask & focal_neighborhood)
            )
            if adjacency < max(8, round(0.001 * total)):
                continue
            component_mask, _, _ = close_narrow_negative_gaps(
                component_mask,
                0.022,
            )
            component_mask = fill_enclosed_holes(component_mask)
            component_mask = smooth_binary_boundary(
                component_mask,
                radius=max(1.0, min(width, height) * 0.0035),
            )
            color_domain = component_mask & (
                lightness >= np.percentile(lightness[component_mask], 42.0)
            )
            if not np.any(color_domain):
                color_domain = component_mask
            color_array = np.median(source[color_domain], axis=0)
            color = tuple(int(round(value)) for value in color_array)
            selected_fraction = float(np.count_nonzero(component_mask)) / total
            score = adjacency * math.sqrt(selected_fraction)
            candidates.append(
                (score, component_mask, color, selected_fraction)
            )
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    _, selected_mask, selected_color, selected_fraction = candidates[0]
    return selected_mask, selected_color, selected_fraction


def preserve_perspective_accent_line(
    image: Image.Image,
    labels: np.ndarray,
    first_new_label: int,
) -> tuple[np.ndarray, list[tuple[int, int, int]], list[float]]:
    """Retain one thin line only when it controls lower-frame perspective.

    The protected relationship is geometric rather than semantic: a
    chromatic, locally contrasted component must touch the bottom frame, stay
    narrow, span a substantial lower-frame distance, and aim toward the central
    image region. Aligned upper fragments may extend its measured vanishing
    direction, after which one tapered ribbon expresses the role minimally.
    """
    width, height = image.size
    total = width * height
    fine = image.filter(ImageFilter.GaussianBlur(radius=0.7))
    broad = image.filter(
        ImageFilter.GaussianBlur(radius=max(6.0, max(image.size) / 45.0))
    )
    source = np.asarray(image, dtype=np.uint8)
    fine_lab = srgb_array_to_oklab(np.asarray(fine, dtype=np.uint8))
    broad_lab = srgb_array_to_oklab(np.asarray(broad, dtype=np.uint8))
    local_delta = np.linalg.norm(fine_lab - broad_lab, axis=2)
    chroma = np.linalg.norm(fine_lab[:, :, 1:], axis=2)
    lightness_contrast = fine_lab[:, :, 0] - broad_lab[:, :, 0]
    zone = np.zeros((height, width), dtype=bool)
    zone[round(0.52 * height) :, round(0.30 * width) : round(0.70 * width)] = True
    evidence = (
        zone
        & (local_delta > 0.055)
        & (chroma > 0.035)
        & (lightness_contrast > 0.018)
    )
    evidence_image = Image.fromarray(
        np.where(evidence, 255, 0).astype(np.uint8),
        mode="L",
    )
    evidence_image = evidence_image.filter(ImageFilter.MaxFilter(3)).filter(
        ImageFilter.MinFilter(3)
    )
    evidence = np.asarray(evidence_image, dtype=np.uint8) >= 128

    candidates: list[
        tuple[
            float,
            list[tuple[int, int]],
            np.ndarray,
            np.ndarray,
            np.ndarray,
        ]
    ] = []
    for component in private_binary_components(evidence):
        y_values = np.fromiter((point[0] for point in component), dtype=np.int32)
        x_values = np.fromiter((point[1] for point in component), dtype=np.int32)
        component_width = int(x_values.max() - x_values.min() + 1)
        component_height = int(y_values.max() - y_values.min() + 1)
        if (
            int(y_values.max()) < height - 3
            or component_height < 0.18 * height
            or component_width > 0.07 * width
            or component_height / max(1, component_width) < 4.0
        ):
            continue
        bottom_values = x_values[y_values >= height - 12]
        if not len(bottom_values):
            continue
        bottom_center = float(np.median(bottom_values))
        if not 0.35 * width <= bottom_center <= 0.65 * width:
            continue
        rows = np.unique(y_values)
        row_centers = np.asarray(
            [float(np.median(x_values[y_values == row])) for row in rows],
            dtype=np.float64,
        )
        row_widths = np.asarray(
            [
                int(x_values[y_values == row].max() - x_values[y_values == row].min() + 1)
                for row in rows
            ],
            dtype=np.float64,
        )
        slope, intercept = np.polyfit(rows.astype(np.float64), row_centers, 1)
        fitted_centers = slope * rows + intercept
        fit_error = float(np.median(np.abs(row_centers - fitted_centers)))
        predicted_top = float(slope * round(0.48 * height) + intercept)
        if (
            abs(float(slope)) > 0.50
            or fit_error > max(1.6, 0.008 * width)
            or not 0.25 * width <= predicted_top <= 0.75 * width
        ):
            continue
        score = (
            component_height
            * float(np.mean(local_delta[y_values, x_values]))
            * float(np.mean(chroma[y_values, x_values]))
        )
        candidates.append(
            (score, component, rows, row_widths, np.asarray([slope, intercept]))
        )

    if not candidates:
        return labels.copy(), [], []
    candidates.sort(key=lambda item: item[0], reverse=True)
    _, component, rows, row_widths, line_fit = candidates[0]
    slope, intercept = (float(line_fit[0]), float(line_fit[1]))
    main_top = int(rows.min())
    weak_evidence = (
        (local_delta > 0.035)
        & (chroma > 0.025)
        & (lightness_contrast > 0.005)
    )
    search_start = round(0.48 * height)
    tube_radius = max(3, round(0.012 * width))
    aligned_rows: list[int] = []
    for y_value in range(search_start, main_top):
        center = round(slope * y_value + intercept)
        left = max(0, center - tube_radius)
        right = min(width, center + tube_radius + 1)
        if np.any(weak_evidence[y_value, left:right]):
            aligned_rows.append(y_value)
    upper_runs: list[tuple[int, int]] = []
    if aligned_rows:
        run_start = aligned_rows[0]
        previous = aligned_rows[0]
        for y_value in aligned_rows[1:]:
            if y_value != previous + 1:
                if previous - run_start + 1 >= 3:
                    upper_runs.append((run_start, previous))
                run_start = y_value
            previous = y_value
        if previous - run_start + 1 >= 3:
            upper_runs.append((run_start, previous))
    top_y = min((run[0] for run in upper_runs), default=main_top)
    bottom_rows = rows[rows >= height - 20]
    if len(bottom_rows):
        bottom_widths = row_widths[rows >= height - 20]
    else:
        bottom_widths = row_widths
    bottom_half_width = max(1.3, float(np.median(bottom_widths)) * 0.32)
    ribbon = np.zeros((height, width), dtype=bool)
    for y_value in range(top_y, height):
        progress = (y_value - top_y) / max(1, height - 1 - top_y)
        half_width = 0.55 + (bottom_half_width - 0.55) * (progress ** 1.25)
        center = slope * y_value + intercept
        left = max(0, int(math.floor(center - half_width)))
        right = min(width - 1, int(math.ceil(center + half_width)))
        ribbon[y_value, left : right + 1] = True

    component_y = np.fromiter((point[0] for point in component), dtype=np.int32)
    component_x = np.fromiter((point[1] for point in component), dtype=np.int32)
    component_pixels = source[component_y, component_x]
    component_lightness = fine_lab[component_y, component_x, 0]
    bright_limit = float(np.percentile(component_lightness, 60.0))
    color_pixels = component_pixels[component_lightness >= bright_limit]
    if not len(color_pixels):
        color_pixels = component_pixels
    color_array = np.median(color_pixels, axis=0)
    color = tuple(int(round(value)) for value in color_array)
    repaired = labels.copy()
    repaired[ribbon] = first_new_label
    area_fraction = round(float(np.count_nonzero(ribbon)) / total, 6)
    return repaired, [color], [area_fraction]


def choose_background(labels: np.ndarray) -> int:
    height, width = labels.shape
    edge_depth = max(1, round(min(width, height) * 0.035))
    samples = np.concatenate(
        (
            labels[:edge_depth, :].ravel(),
            labels[:, :edge_depth].ravel(),
            labels[:, -edge_depth:].ravel(),
        )
    )
    return int(Counter(int(value) for value in samples).most_common(1)[0][0])


def connected_regions(
    labels: np.ndarray,
    palette: list[tuple[int, int, int]],
    background: int,
    detail: float,
    max_shapes: int,
    protected_labels: set[int] | None = None,
    paint_last_labels: set[int] | None = None,
) -> list[Region]:
    height, width = labels.shape
    total = height * width
    visited = np.zeros_like(labels, dtype=bool)
    min_area = total * (0.014 - 0.010 * detail)
    regions: list[Region] = []
    background_color = palette[background]

    for y0 in range(height):
        for x0 in range(width):
            label = int(labels[y0, x0])
            if label == background or visited[y0, x0]:
                continue
            queue: deque[tuple[int, int]] = deque([(y0, x0)])
            visited[y0, x0] = True
            pixels: list[tuple[int, int]] = []
            sum_x = 0
            sum_y = 0
            while queue:
                y, x = queue.popleft()
                pixels.append((y, x))
                sum_x += x
                sum_y += y
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < height and 0 <= nx < width and not visited[ny, nx] and int(labels[ny, nx]) == label:
                        visited[ny, nx] = True
                        queue.append((ny, nx))
            area = len(pixels)
            region_minimum = (
                total * 0.0007
                if protected_labels and label in protected_labels
                else min_area
            )
            if area < region_minimum:
                continue
            cx = sum_x / area
            cy = sum_y / area
            contrast = color_distance(palette[label], background_color)
            score = (area / total) * (0.55 + 1.8 * contrast)
            regions.append(Region(label, pixels, area, cx, cy, score))

    # Retain the largest component of each surviving color, then spend the
    # remaining shape budget on the most structurally salient components.
    by_label: dict[int, list[Region]] = {}
    for region in regions:
        by_label.setdefault(region.label, []).append(region)
    mandatory = [max(group, key=lambda item: item.area) for group in by_label.values()]
    selected_ids = {id(region) for region in mandatory}
    optional = sorted((region for region in regions if id(region) not in selected_ids), key=lambda item: item.score, reverse=True)
    selected = mandatory + optional[: max(0, max_shapes - len(mandatory))]
    selected = sorted(
        selected[:max_shapes],
        key=lambda item: (
            bool(paint_last_labels and item.label in paint_last_labels),
            item.centroid_y,
            -item.area,
        ),
    )
    return selected


def boundary_loops(pixels: list[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    filled = set(pixels)
    edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    for y, x in filled:
        if (y - 1, x) not in filled:
            edges.add(((x, y), (x + 1, y)))
        if (y, x + 1) not in filled:
            edges.add(((x + 1, y), (x + 1, y + 1)))
        if (y + 1, x) not in filled:
            edges.add(((x + 1, y + 1), (x, y + 1)))
        if (y, x - 1) not in filled:
            edges.add(((x, y + 1), (x, y)))

    outgoing: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for start, end in edges:
        outgoing.setdefault(start, []).append(end)

    loops: list[list[tuple[int, int]]] = []
    remaining = set(edges)
    while remaining:
        start, current = min(remaining)
        remaining.remove((start, current))
        loop = [start, current]
        guard = 0
        while current != start and guard <= len(edges):
            candidates = [end for end in outgoing.get(current, []) if (current, end) in remaining]
            if not candidates:
                break
            nxt = min(candidates)
            remaining.remove((current, nxt))
            loop.append(nxt)
            current = nxt
            guard += 1
        if len(loop) >= 5 and loop[-1] == loop[0]:
            loops.append(loop[:-1])
    return loops


def perpendicular_distance(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> float:
    if start == end:
        return math.dist(point, start)
    x, y = point
    x1, y1 = start
    x2, y2 = end
    numerator = abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1)
    denominator = math.hypot(y2 - y1, x2 - x1)
    return numerator / denominator


def rdp(points: list[tuple[float, float]], epsilon: float) -> list[tuple[float, float]]:
    if len(points) < 3:
        return points
    distances = [perpendicular_distance(point, points[0], points[-1]) for point in points[1:-1]]
    if not distances:
        return [points[0], points[-1]]
    maximum = max(distances)
    index = distances.index(maximum) + 1
    if maximum > epsilon:
        left = rdp(points[: index + 1], epsilon)
        right = rdp(points[index:], epsilon)
        return left[:-1] + right
    return [points[0], points[-1]]


def simplify_closed(points: list[tuple[int, int]], epsilon: float) -> list[tuple[float, float]]:
    if len(points) <= 8:
        return [(float(x), float(y)) for x, y in points]
    # Rotate the seam to an extreme point so any simplification artifact falls
    # on a visually stable outer edge rather than inside the contour.
    cx = sum(x for x, _ in points) / len(points)
    cy = sum(y for _, y in points) / len(points)
    seam = max(range(len(points)), key=lambda index: (points[index][0] - cx) ** 2 + (points[index][1] - cy) ** 2)
    rotated = points[seam:] + points[:seam]
    open_curve = [(float(x), float(y)) for x, y in rotated] + [(float(rotated[0][0]), float(rotated[0][1]))]
    simplified = rdp(open_curve, epsilon)
    if simplified and simplified[-1] == simplified[0]:
        simplified.pop()
    return simplified


def resample_closed(points: list[tuple[float, float]], count: int) -> list[tuple[float, float]]:
    """Resample a closed polygon at uniform arc-length intervals."""
    if len(points) < 3 or count < 3:
        return points
    array = np.asarray(points, dtype=np.float64)
    ends = np.roll(array, -1, axis=0)
    lengths = np.linalg.norm(ends - array, axis=1)
    perimeter = float(np.sum(lengths))
    if perimeter <= 1e-6:
        return points
    cumulative = np.concatenate(([0.0], np.cumsum(lengths)))
    samples = np.linspace(0.0, perimeter, count, endpoint=False)
    result: list[tuple[float, float]] = []
    segment = 0
    for distance in samples:
        while segment + 1 < len(cumulative) - 1 and cumulative[segment + 1] <= distance:
            segment += 1
        local_length = lengths[segment]
        ratio = 0.0 if local_length <= 1e-9 else (distance - cumulative[segment]) / local_length
        point = array[segment] * (1.0 - ratio) + ends[segment] * ratio
        result.append((float(point[0]), float(point[1])))
    return result


def low_pass_closed(
    points: list[tuple[float, float]],
    curve_smoothing: float,
    passes: int = 2,
) -> list[tuple[float, float]]:
    """Remove small contour waves without increasing the control-point count."""
    array = np.asarray(points, dtype=np.float64)
    strength = 0.20 + 0.07 * curve_smoothing
    for _ in range(max(1, passes)):
        blurred = (
            np.roll(array, 2, axis=0)
            + 4.0 * np.roll(array, 1, axis=0)
            + 6.0 * array
            + 4.0 * np.roll(array, -1, axis=0)
            + np.roll(array, -2, axis=0)
        ) / 16.0
        array = array * (1.0 - strength) + blurred * strength
    return [(float(point[0]), float(point[1])) for point in array]


def suppress_micro_contour_roughness(
    points: list[tuple[float, float]],
    curve_smoothing: float,
    passes: int = 2,
) -> list[tuple[float, float]]:
    """Remove only short, shallow contour fluctuations.

    The segmentation mask lives on a much smaller pixel grid than the final
    SVG. A two- or three-pixel label fluctuation can therefore become a visible
    notch after scaling. Ordinary low-pass smoothing softens that notch but can
    also round a real peak. This filter compares narrow and broad closed-curve
    estimates: it moves a point only when the difference has micro-scale energy
    and the required displacement remains small. Large turns pass through
    unchanged.
    """
    if len(points) < 12:
        return points
    array = np.asarray(points, dtype=np.float64)
    narrow_weights = np.asarray((1.0, 4.0, 6.0, 4.0, 1.0)) / 16.0
    broad_weights = np.asarray(
        (1.0, 8.0, 28.0, 56.0, 70.0, 56.0, 28.0, 8.0, 1.0)
    ) / 256.0
    minimum_band_energy = 0.16
    maximum_displacement = 3.95 + 1.15 * curve_smoothing
    blend = 0.76 + 0.12 * curve_smoothing

    def closed_filter(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
        radius = len(weights) // 2
        filtered = np.zeros_like(values)
        for offset, weight in enumerate(weights):
            filtered += np.roll(values, radius - offset, axis=0) * weight
        return filtered

    for _ in range(max(1, passes)):
        narrow = closed_filter(array, narrow_weights)
        broad = closed_filter(array, broad_weights)
        band_energy = np.linalg.norm(narrow - broad, axis=1)
        displacement = np.linalg.norm(broad - array, axis=1)

        # The lower gate leaves straight runs and already-smooth curves alone.
        # The upper gate locks meaningful peaks whose removal would require a
        # larger move than a micro contour artifact.
        lower_gate = np.clip(
            (band_energy - minimum_band_energy) / 0.42,
            0.0,
            1.0,
        )
        upper_gate = np.clip(
            (maximum_displacement - displacement) / 0.85,
            0.0,
            1.0,
        )
        blend_weights = (blend * lower_gate * upper_gate)[:, None]
        array = array + (broad - array) * blend_weights
    return [(float(point[0]), float(point[1])) for point in array]


def smooth_path(
    points: list[tuple[float, float]],
    scale_x: float,
    scale_y: float,
    curve_smoothing: float,
    point_budget: int | None = None,
    curve_mode: str = "adaptive",
    smoothing_passes: int = 2,
    micro_contour_filter: bool = False,
) -> str:
    """Create a closed cubic Bézier contour with adaptive long handles."""
    if len(points) < 3:
        return ""
    array = np.asarray(points, dtype=np.float64)
    perimeter = float(np.sum(np.linalg.norm(np.roll(array, -1, axis=0) - array, axis=1)))
    spacing = 2.8 + 2.4 * curve_smoothing
    maximum_points = round(160 - 20 * curve_smoothing)
    if point_budget is not None:
        maximum_points = min(maximum_points, max(12, point_budget))
    point_count = max(12, min(maximum_points, round(perimeter / spacing)))
    uniform = resample_closed(points, point_count)
    if micro_contour_filter:
        uniform = suppress_micro_contour_roughness(
            uniform,
            curve_smoothing,
            passes=2,
        )
    rounded = low_pass_closed(uniform, curve_smoothing, passes=smoothing_passes)
    scaled = np.asarray([(x * scale_x, y * scale_y) for x, y in rounded], dtype=np.float64)

    if curve_mode == "bspline":
        # A periodic uniform cubic B-spline becomes a sequence of native cubic
        # Bézier segments. It approximates the sampled contour instead of
        # hitting every mask fluctuation, is C2 continuous, and remains exactly
        # straight wherever four consecutive guide points are collinear.
        commands: list[str] = []
        for index in range(len(scaled)):
            point_zero = scaled[index]
            point_one = scaled[(index + 1) % len(scaled)]
            point_two = scaled[(index + 2) % len(scaled)]
            point_three = scaled[(index + 3) % len(scaled)]
            anchor_start = (point_zero + 4.0 * point_one + point_two) / 6.0
            control_one = (4.0 * point_one + 2.0 * point_two) / 6.0
            control_two = (2.0 * point_one + 4.0 * point_two) / 6.0
            anchor_end = (point_one + 4.0 * point_two + point_three) / 6.0
            if index == 0:
                commands.append(f"M {anchor_start[0]:.2f} {anchor_start[1]:.2f}")
            commands.append(
                f"C {control_one[0]:.2f} {control_one[1]:.2f} "
                f"{control_two[0]:.2f} {control_two[1]:.2f} "
                f"{anchor_end[0]:.2f} {anchor_end[1]:.2f}"
            )
        commands.append("Z")
        return " ".join(commands)

    # Estimate each anchor's tangent from a wider arc-length neighborhood.
    # Immediate Catmull-Rom tangents round only the final few pixels of a turn,
    # which still reads as a polygon with softened corners. A wider secant
    # begins the turn earlier while remaining exactly straight on collinear runs.
    tangent_span = min(max(2, round(2 + 3 * curve_smoothing)), max(2, len(scaled) // 6))
    tangents = np.roll(scaled, -tangent_span, axis=0) - np.roll(scaled, tangent_span, axis=0)
    tangent_lengths = np.linalg.norm(tangents, axis=1)
    immediate = np.roll(scaled, -1, axis=0) - np.roll(scaled, 1, axis=0)
    immediate_lengths = np.linalg.norm(immediate, axis=1)
    for index in range(len(scaled)):
        if tangent_lengths[index] <= 1e-9:
            tangents[index] = immediate[index]
            tangent_lengths[index] = immediate_lengths[index]
    tangents /= np.maximum(tangent_lengths[:, None], 1e-9)

    outgoing = np.linalg.norm(np.roll(scaled, -1, axis=0) - scaled, axis=1)
    incoming = np.roll(outgoing, 1)
    local_length = 2.0 * incoming * outgoing / np.maximum(incoming + outgoing, 1e-9)
    incoming_direction = (scaled - np.roll(scaled, 1, axis=0)) / np.maximum(incoming[:, None], 1e-9)
    outgoing_direction = (np.roll(scaled, -1, axis=0) - scaled) / np.maximum(outgoing[:, None], 1e-9)
    alignment = np.clip(np.sum(incoming_direction * outgoing_direction, axis=1), -1.0, 1.0)
    turn_relief = 0.74 + 0.26 * ((alignment + 1.0) * 0.5)
    handle_scale = 0.34 + 0.12 * curve_smoothing
    handle_lengths = local_length * handle_scale * turn_relief
    handle_lengths = np.minimum(handle_lengths, 0.48 * np.minimum(incoming, outgoing))

    commands = [f"M {scaled[0, 0]:.2f} {scaled[0, 1]:.2f}"]
    for index, start in enumerate(scaled):
        next_index = (index + 1) % len(scaled)
        end = scaled[next_index]
        control_one = start + tangents[index] * handle_lengths[index]
        control_two = end - tangents[next_index] * handle_lengths[next_index]
        commands.append(
            f"C {control_one[0]:.2f} {control_one[1]:.2f} "
            f"{control_two[0]:.2f} {control_two[1]:.2f} {end[0]:.2f} {end[1]:.2f}"
        )
    commands.append("Z")
    return " ".join(commands)


def region_svg_path(
    region: Region,
    analysis_width: int,
    analysis_height: int,
    output_width: int,
    output_height: int,
    detail: float,
    curve_smoothing: float,
) -> str:
    scale_x = output_width / analysis_width
    scale_y = output_height / analysis_height
    epsilon = 3.3 - 2.1 * detail
    parts: list[str] = []
    for loop in boundary_loops(region.pixels):
        simplified = simplify_closed(loop, epsilon)
        path = smooth_path(simplified, scale_x, scale_y, curve_smoothing)
        if path:
            parts.append(path)
    return " ".join(parts)


def frame_bleed_margin(analysis_width: int, analysis_height: int) -> int:
    """Return enough analysis-space bleed to survive contour smoothing."""
    return max(3, round(min(analysis_width, analysis_height) * 0.012))


def touched_frame_edges(mask: np.ndarray) -> list[str]:
    edges: list[str] = []
    if bool(np.any(mask[:, 0])):
        edges.append("left")
    if bool(np.any(mask[:, -1])):
        edges.append("right")
    if bool(np.any(mask[0, :])):
        edges.append("top")
    if bool(np.any(mask[-1, :])):
        edges.append("bottom")
    return edges


def bleed_pixels_beyond_frame(
    pixels: list[tuple[int, int]],
    analysis_width: int,
    analysis_height: int,
    margin: int,
    spread_contacts: bool = True,
) -> list[tuple[int, int]]:
    """Extend only frame-touching pixels past the viewBox before fitting.

    Closed-loop smoothing otherwise rounds a contour away from x=0, y=0, or
    the opposite frame edges. A short clipped guard band keeps the rendered
    field flush to the canvas without changing any interior free contour.
    """
    if margin <= 0 or not pixels:
        return pixels
    filled = set(pixels)
    left_rows = [y_value for y_value, x_value in pixels if x_value == 0]
    right_rows = [y_value for y_value, x_value in pixels if x_value == analysis_width - 1]
    top_columns = [x_value for y_value, x_value in pixels if y_value == 0]
    bottom_columns = [x_value for y_value, x_value in pixels if y_value == analysis_height - 1]
    for y_value in left_rows:
        row_start = y_value - margin if spread_contacts else y_value
        row_end = y_value + margin if spread_contacts else y_value
        for nearby_y in range(row_start, row_end + 1):
            for x_value in range(-margin, 1):
                filled.add((nearby_y, x_value))
    for y_value in right_rows:
        row_start = y_value - margin if spread_contacts else y_value
        row_end = y_value + margin if spread_contacts else y_value
        for nearby_y in range(row_start, row_end + 1):
            for x_value in range(analysis_width - 1, analysis_width + margin + 1):
                filled.add((nearby_y, x_value))
    for x_value in top_columns:
        column_start = x_value - margin if spread_contacts else x_value
        column_end = x_value + margin if spread_contacts else x_value
        for nearby_x in range(column_start, column_end + 1):
            for y_value in range(-margin, 1):
                filled.add((y_value, nearby_x))
    for x_value in bottom_columns:
        column_start = x_value - margin if spread_contacts else x_value
        column_end = x_value + margin if spread_contacts else x_value
        for nearby_x in range(column_start, column_end + 1):
            for y_value in range(analysis_height - 1, analysis_height + margin + 1):
                filled.add((y_value, nearby_x))
    return sorted(filled)


def pixels_svg_path(
    pixels: list[tuple[int, int]],
    analysis_width: int,
    analysis_height: int,
    output_width: int,
    output_height: int,
    epsilon: float,
    curve_smoothing: float,
    point_budget: int | None = None,
    curve_mode: str = "adaptive",
    smoothing_passes: int = 2,
    frame_bleed: int | None = None,
    spread_frame_contacts: bool = True,
    micro_contour_filter: bool = False,
) -> str:
    scale_x = output_width / analysis_width
    scale_y = output_height / analysis_height
    bleed = (
        frame_bleed_margin(analysis_width, analysis_height)
        if frame_bleed is None
        else max(0, frame_bleed)
    )
    fitted_pixels = bleed_pixels_beyond_frame(
        pixels,
        analysis_width,
        analysis_height,
        bleed,
        spread_contacts=spread_frame_contacts,
    )
    parts: list[str] = []
    for loop in boundary_loops(fitted_pixels):
        simplified = simplify_closed(loop, epsilon)
        path = smooth_path(
            simplified,
            scale_x,
            scale_y,
            curve_smoothing,
            point_budget=point_budget,
            curve_mode=curve_mode,
            smoothing_passes=smoothing_passes,
            micro_contour_filter=micro_contour_filter,
        )
        if path:
            parts.append(path)
    return " ".join(parts)


def components_from_mask(mask: np.ndarray, min_fraction: float, limit: int) -> list[list[tuple[int, int]]]:
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    minimum = height * width * min_fraction
    components: list[list[tuple[int, int]]] = []
    for y0 in range(height):
        for x0 in range(width):
            if not mask[y0, x0] or visited[y0, x0]:
                continue
            queue: deque[tuple[int, int]] = deque([(y0, x0)])
            visited[y0, x0] = True
            pixels: list[tuple[int, int]] = []
            while queue:
                y, x = queue.popleft()
                pixels.append((y, x))
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        queue.append((ny, nx))
            if len(pixels) >= minimum:
                components.append(pixels)
    return sorted(components, key=len, reverse=True)[:limit]


def clean_binary_mask(mask: np.ndarray, closing_size: int = 9, mode_size: int = 7) -> np.ndarray:
    image = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), mode="L")
    if closing_size >= 3:
        if closing_size % 2 == 0:
            closing_size += 1
        image = image.filter(ImageFilter.MaxFilter(closing_size)).filter(ImageFilter.MinFilter(closing_size))
    if mode_size >= 3:
        if mode_size % 2 == 0:
            mode_size += 1
        image = image.filter(ImageFilter.ModeFilter(mode_size))
    return np.asarray(image, dtype=np.uint8) >= 128


def smooth_binary_boundary(mask: np.ndarray, radius: float) -> np.ndarray:
    """Round broad field boundaries without changing the silhouette detector."""
    if radius <= 0:
        return mask.copy()
    image = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), mode="L")
    image = image.filter(ImageFilter.GaussianBlur(radius=radius))
    return np.asarray(image, dtype=np.uint8) >= 128


def round_internal_positive_tips(
    mask: np.ndarray,
    rounding_fraction: float,
) -> tuple[np.ndarray, int, int]:
    """Remove narrow internal protrusions without touching an outer silhouette."""
    if rounding_fraction <= 0.0:
        return mask.copy(), 1, 0
    target_width = max(3, round(min(mask.shape) * rounding_fraction))
    if target_width % 2 == 0:
        target_width += 1
    image = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), mode="L")
    opened_image = image.filter(ImageFilter.MinFilter(target_width)).filter(
        ImageFilter.MaxFilter(target_width)
    )
    opened = (np.asarray(opened_image, dtype=np.uint8) >= 128) & mask
    original_count = int(np.count_nonzero(mask))
    opened_count = int(np.count_nonzero(opened))
    # Protect small but meaningful light islands from an over-large kernel.
    if opened_count < max(64, round(original_count * 0.72)):
        return mask.copy(), target_width, 0
    return opened, target_width, original_count - opened_count


def bottom_connected_mask(mask: np.ndarray, bottom_band: int = 4) -> np.ndarray:
    """Keep only candidate land connected to the bottom edge of the frame."""
    height, width = mask.shape
    candidate = mask.copy()
    candidate[-max(1, bottom_band) :, :] = True
    connected = np.zeros_like(candidate, dtype=bool)
    queue: deque[tuple[int, int]] = deque()
    for x_value in range(width):
        if candidate[height - 1, x_value]:
            connected[height - 1, x_value] = True
            queue.append((height - 1, x_value))
    while queue:
        y_value, x_value = queue.popleft()
        for delta_y, delta_x in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            next_y, next_x = y_value + delta_y, x_value + delta_x
            if (
                0 <= next_y < height
                and 0 <= next_x < width
                and candidate[next_y, next_x]
                and not connected[next_y, next_x]
            ):
                connected[next_y, next_x] = True
                queue.append((next_y, next_x))
    return connected


def dilate_binary_mask(mask: np.ndarray, size: int) -> np.ndarray:
    if size < 3:
        return mask.copy()
    if size % 2 == 0:
        size += 1
    image = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), mode="L")
    return np.asarray(image.filter(ImageFilter.MaxFilter(size)), dtype=np.uint8) >= 128


def close_narrow_negative_gaps(
    mask: np.ndarray,
    minimum_fraction: float,
) -> tuple[np.ndarray, int, int]:
    """Fill only negative-space channels narrower than a short-side fraction.

    Unioning the morphological close with the original mask makes the operation
    additive: thin positive subject features cannot be eroded, while needle-like
    sky bays and pinched crevices are bridged before the contour is fitted.
    """
    if minimum_fraction <= 0.0:
        return mask.copy(), 1, 0
    target_width = max(3, round(min(mask.shape) * minimum_fraction))
    if target_width % 2 == 0:
        target_width += 1
    image = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), mode="L")
    closed_image = image.filter(ImageFilter.MaxFilter(target_width)).filter(
        ImageFilter.MinFilter(target_width)
    )
    closed = np.asarray(closed_image, dtype=np.uint8) >= 128
    additions = closed & (~mask)
    return mask | additions, target_width, int(np.count_nonzero(additions))


def seam_underlap_geometry(
    mask_shape: tuple[int, int],
    minimum_fraction: float,
) -> tuple[int, int, int, int]:
    """Return clearance radius, fitting margin, overlap kernel, and proximity kernel."""
    if minimum_fraction <= 0.0:
        return 0, 0, 1, 1
    clearance_radius = max(1, round(min(mask_shape) * minimum_fraction))
    fitting_margin = max(3, clearance_radius + 3)
    overlap_radius = clearance_radius + fitting_margin
    return (
        clearance_radius,
        fitting_margin,
        overlap_radius * 2 + 1,
        clearance_radius * 2 + 1,
    )


def overlap_near_touching_fields(
    field_mask: np.ndarray,
    occluding_mask: np.ndarray,
    minimum_fraction: float,
) -> tuple[np.ndarray, int, int]:
    """Bridge a near-contact seam, then rely on render order to hide overlap.

    Independent spline fits can both pull inward from a shared pixel boundary
    and expose a hairline of background. Expansion is restricted to the local
    band where the field and the later-painted occluder nearly meet, so the
    field's free outer contour remains unchanged.
    """
    clearance_radius, _fitting_margin, overlap_kernel, proximity_kernel = (
        seam_underlap_geometry(field_mask.shape, minimum_fraction)
    )
    if clearance_radius == 0:
        return field_mask.copy(), overlap_kernel, 0
    # Pillow's MaxFilter argument is a *diameter*, so using the clearance value
    # directly only expands by half of the requested gap width. That leaves a
    # short wedge uncovered at tight joins after both contours are smoothed.
    # Treat the measured clearance as a radius and add a small fitting margin;
    # the later-painted field hides the extra underlap.
    expanded_field = dilate_binary_mask(field_mask, overlap_kernel)
    nearby_occluder = dilate_binary_mask(occluding_mask, proximity_kernel)
    additions = expanded_field & nearby_occluder & (~field_mask)
    return field_mask | additions, overlap_kernel, int(np.count_nonzero(additions))


def enclosed_hole_mask(mask: np.ndarray) -> np.ndarray:
    """Return background islands that cannot reach the canvas edge."""
    height, width = mask.shape
    outside = np.zeros_like(mask, dtype=bool)
    queue: deque[tuple[int, int]] = deque()
    for x_value in range(width):
        for y_value in (0, height - 1):
            if not mask[y_value, x_value] and not outside[y_value, x_value]:
                outside[y_value, x_value] = True
                queue.append((y_value, x_value))
    for y_value in range(height):
        for x_value in (0, width - 1):
            if not mask[y_value, x_value] and not outside[y_value, x_value]:
                outside[y_value, x_value] = True
                queue.append((y_value, x_value))
    while queue:
        y_value, x_value = queue.popleft()
        for delta_y, delta_x in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            next_y, next_x = y_value + delta_y, x_value + delta_x
            if (
                0 <= next_y < height
                and 0 <= next_x < width
                and not mask[next_y, next_x]
                and not outside[next_y, next_x]
            ):
                outside[next_y, next_x] = True
                queue.append((next_y, next_x))
    return (~mask) & (~outside)


def fill_enclosed_holes(mask: np.ndarray) -> np.ndarray:
    """Fill false islands enclosed by a subject while retaining open sky gaps."""
    return mask | enclosed_hole_mask(mask)


def fill_small_enclosed_holes(
    mask: np.ndarray,
    minimum_fraction: float,
) -> tuple[np.ndarray, int, int, int]:
    """Merge only micro-holes left by discarded color regions.

    Large enclosed openings remain visible. The area limit is derived from the
    same minimum-clearance width used for seam underlap, so the operation scales
    with analysis resolution and stays deterministic.
    """
    if minimum_fraction <= 0.0:
        return mask.copy(), 0, 0, 0
    clearance_width = max(1, round(min(mask.shape) * minimum_fraction))
    area_limit = clearance_width * clearance_width
    holes = enclosed_hole_mask(mask)
    visited = np.zeros_like(mask, dtype=bool)
    filled = mask.copy()
    filled_holes = 0
    filled_pixels = 0
    height, width = mask.shape
    for y_zero, x_zero in np.argwhere(holes):
        y_start = int(y_zero)
        x_start = int(x_zero)
        if visited[y_start, x_start]:
            continue
        queue: deque[tuple[int, int]] = deque([(y_start, x_start)])
        visited[y_start, x_start] = True
        component: list[tuple[int, int]] = []
        while queue:
            y_value, x_value = queue.popleft()
            component.append((y_value, x_value))
            for delta_y, delta_x in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                next_y, next_x = y_value + delta_y, x_value + delta_x
                if (
                    0 <= next_y < height
                    and 0 <= next_x < width
                    and holes[next_y, next_x]
                    and not visited[next_y, next_x]
                ):
                    visited[next_y, next_x] = True
                    queue.append((next_y, next_x))
        if len(component) <= area_limit:
            for y_value, x_value in component:
                filled[y_value, x_value] = True
            filled_holes += 1
            filled_pixels += len(component)
    return filled, area_limit, filled_holes, filled_pixels


def consolidate_subclearance_negative_space(
    region_masks: list[np.ndarray],
    minimum_fraction: float,
) -> tuple[
    list[np.ndarray],
    int,
    int,
    int,
    int,
    dict[str, int],
    dict[str, int],
]:
    """Absorb narrow background channels and micro-pockets into nearby fields.

    Repairing the union before individual curve fits prevents a small negative
    lobe from being pinched into a detached background island at a high-curvature
    or triple junction. Additions are assigned by direct boundary contact so no
    new structural color is invented.
    """
    layer_names = [
        f"color-region-{index + 1:02d}" for index in range(len(region_masks))
    ]
    component_counts = {name: 0 for name in layer_names}
    pixel_counts = {name: 0 for name in layer_names}
    if not region_masks or minimum_fraction <= 0.0:
        return (
            [mask.copy() for mask in region_masks],
            1,
            0,
            0,
            0,
            component_counts,
            pixel_counts,
        )

    merged_masks = [mask.copy() for mask in region_masks]
    retained_union = np.logical_or.reduce(merged_masks)
    closed_union, close_kernel, closed_pixels = close_narrow_negative_gaps(
        retained_union,
        minimum_fraction,
    )
    (
        repaired_union,
        hole_area_limit,
        filled_holes,
        _,
    ) = fill_small_enclosed_holes(closed_union, minimum_fraction)
    additions = repaired_union & (~retained_union)
    if not np.any(additions):
        return (
            merged_masks,
            close_kernel,
            hole_area_limit,
            closed_pixels,
            filled_holes,
            component_counts,
            pixel_counts,
        )

    height, width = additions.shape
    owner = np.full((height, width), -1, dtype=np.int16)
    for index, mask in enumerate(merged_masks):
        owner[mask] = index
    visited = np.zeros_like(additions, dtype=bool)

    for y_zero, x_zero in np.argwhere(additions):
        y_start = int(y_zero)
        x_start = int(x_zero)
        if visited[y_start, x_start]:
            continue
        queue: deque[tuple[int, int]] = deque([(y_start, x_start)])
        visited[y_start, x_start] = True
        component: list[tuple[int, int]] = []
        contacts: Counter[int] = Counter()
        while queue:
            y_value, x_value = queue.popleft()
            component.append((y_value, x_value))
            for delta_y, delta_x in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                next_y = y_value + delta_y
                next_x = x_value + delta_x
                if not (0 <= next_y < height and 0 <= next_x < width):
                    continue
                neighbor_owner = int(owner[next_y, next_x])
                if neighbor_owner >= 0:
                    contacts[neighbor_owner] += 1
                elif additions[next_y, next_x] and not visited[next_y, next_x]:
                    visited[next_y, next_x] = True
                    queue.append((next_y, next_x))

        if not contacts:
            component_mask = np.zeros_like(additions)
            y_values = np.fromiter(
                (point[0] for point in component),
                dtype=np.int32,
            )
            x_values = np.fromiter(
                (point[1] for point in component),
                dtype=np.int32,
            )
            component_mask[y_values, x_values] = True
            nearby_owner = owner[
                dilate_binary_mask(component_mask, 5) & (owner >= 0)
            ]
            contacts.update(int(value) for value in nearby_owner)
        if not contacts:
            continue

        target = max(contacts, key=lambda index: (contacts[index], -index))
        y_values = np.fromiter(
            (point[0] for point in component),
            dtype=np.int32,
        )
        x_values = np.fromiter(
            (point[1] for point in component),
            dtype=np.int32,
        )
        merged_masks[target][y_values, x_values] = True
        owner[y_values, x_values] = target
        layer_name = layer_names[target]
        component_counts[layer_name] += 1
        pixel_counts[layer_name] += len(component)

    return (
        merged_masks,
        close_kernel,
        hole_area_limit,
        closed_pixels,
        filled_holes,
        component_counts,
        pixel_counts,
    )


def fill_unrepresented_enclosed_holes(
    mask: np.ndarray,
    other_retained_masks: np.ndarray,
    background_mask: np.ndarray,
    source_array: np.ndarray,
    enclosing_color: tuple[int, int, int],
    background_color: tuple[int, int, int],
) -> tuple[np.ndarray, int, int, int, int]:
    """Merge discarded non-background islands into their enclosing field.

    A retained neighboring field or a true background opening remains
    protected. This prevents an omitted dark-green island, for example, from
    exposing a blue full-frame background inside a grass field. A compact
    enclosed component assigned to the background may also be merged when its
    measured source hue agrees with the enclosing field and strongly opposes
    the background hue. This catches dark same-material patches that a limited
    palette assigned by lightness while preserving real background openings.
    """
    holes = enclosed_hole_mask(mask)
    visited = np.zeros_like(mask, dtype=bool)
    filled = mask.copy()
    filled_holes = 0
    filled_pixels = 0
    chromatic_false_background_holes = 0
    chromatic_false_background_pixels = 0
    height, width = mask.shape
    for y_zero, x_zero in np.argwhere(holes):
        y_start = int(y_zero)
        x_start = int(x_zero)
        if visited[y_start, x_start]:
            continue
        queue: deque[tuple[int, int]] = deque([(y_start, x_start)])
        visited[y_start, x_start] = True
        component: list[tuple[int, int]] = []
        while queue:
            y_value, x_value = queue.popleft()
            component.append((y_value, x_value))
            for delta_y, delta_x in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                next_y, next_x = y_value + delta_y, x_value + delta_x
                if (
                    0 <= next_y < height
                    and 0 <= next_x < width
                    and holes[next_y, next_x]
                    and not visited[next_y, next_x]
                ):
                    visited[next_y, next_x] = True
                    queue.append((next_y, next_x))
        y_values = np.fromiter((point[0] for point in component), dtype=np.int32)
        x_values = np.fromiter((point[1] for point in component), dtype=np.int32)
        protected = bool(np.any(other_retained_masks[y_values, x_values]))
        background_fraction = float(np.mean(background_mask[y_values, x_values]))
        compact_area_limit = round(height * width * 0.002)
        compact_span_limit = max(3, round(min(height, width) * 0.07))
        component_width = int(x_values.max() - x_values.min() + 1)
        component_height = int(y_values.max() - y_values.min() + 1)
        source_color = tuple(
            int(round(value))
            for value in np.median(source_array[y_values, x_values], axis=0)
        )
        source_lab = np.asarray(srgb_to_oklab(source_color), dtype=np.float64)
        enclosing_lab = np.asarray(
            srgb_to_oklab(enclosing_color),
            dtype=np.float64,
        )
        background_lab = np.asarray(
            srgb_to_oklab(background_color),
            dtype=np.float64,
        )
        source_chroma = float(np.linalg.norm(source_lab[1:]))
        enclosing_chroma = float(np.linalg.norm(enclosing_lab[1:]))
        background_chroma = float(np.linalg.norm(background_lab[1:]))
        source_to_enclosing_hue = float(
            np.dot(source_lab[1:], enclosing_lab[1:])
            / max(1e-8, source_chroma * enclosing_chroma)
        )
        source_to_background_hue = float(
            np.dot(source_lab[1:], background_lab[1:])
            / max(1e-8, source_chroma * background_chroma)
        )
        chromatic_false_background = (
            background_fraction >= 0.80
            and len(component) <= compact_area_limit
            and component_width <= compact_span_limit
            and component_height <= compact_span_limit
            and source_chroma >= 0.055
            and enclosing_chroma >= 0.055
            and background_chroma >= 0.040
            and source_to_enclosing_hue >= 0.80
            and source_to_background_hue <= -0.45
        )
        if not protected and (
            background_fraction < 0.5 or chromatic_false_background
        ):
            filled[y_values, x_values] = True
            filled_holes += 1
            filled_pixels += len(component)
            if chromatic_false_background:
                chromatic_false_background_holes += 1
                chromatic_false_background_pixels += len(component)
    return (
        filled,
        filled_holes,
        filled_pixels,
        chromatic_false_background_holes,
        chromatic_false_background_pixels,
    )


def merge_discarded_nonbackground_regions(
    labels: np.ndarray,
    background: int,
    palette: list[tuple[int, int, int]],
    regions: list[Region],
    region_masks: list[np.ndarray],
    protected_labels: set[int] | None = None,
) -> tuple[list[np.ndarray], dict[str, int], dict[str, int]]:
    """Absorb omitted color components into a touching retained field.

    The full-frame SVG fill represents only the selected background label.
    Therefore a discarded non-background component must not become an opening
    to that unrelated fill. Components are merged by boundary contact, with
    source-palette distance breaking ambiguous contacts; isolated components
    farther than a small local band remain intentionally reduced away.
    """
    height, width = labels.shape
    owner = np.full((height, width), -1, dtype=np.int16)
    merged_masks = [mask.copy() for mask in region_masks]
    for index, mask in enumerate(merged_masks):
        owner[mask] = index
    visited = np.zeros_like(labels, dtype=bool)
    merged_components = {f"color-region-{index + 1:02d}": 0 for index in range(len(regions))}
    merged_pixels = {f"color-region-{index + 1:02d}": 0 for index in range(len(regions))}

    for y_zero in range(height):
        for x_zero in range(width):
            label = int(labels[y_zero, x_zero])
            if label == background or owner[y_zero, x_zero] >= 0 or visited[y_zero, x_zero]:
                continue
            queue: deque[tuple[int, int]] = deque([(y_zero, x_zero)])
            visited[y_zero, x_zero] = True
            component: list[tuple[int, int]] = []
            contacts: Counter[int] = Counter()
            while queue:
                y_value, x_value = queue.popleft()
                component.append((y_value, x_value))
                for delta_y, delta_x in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    next_y, next_x = y_value + delta_y, x_value + delta_x
                    if not (0 <= next_y < height and 0 <= next_x < width):
                        continue
                    neighbor_owner = int(owner[next_y, next_x])
                    if neighbor_owner >= 0:
                        contacts[neighbor_owner] += 1
                    elif (
                        not visited[next_y, next_x]
                        and int(labels[next_y, next_x]) == label
                    ):
                        visited[next_y, next_x] = True
                        queue.append((next_y, next_x))

            if not contacts:
                component_mask = np.zeros_like(labels, dtype=bool)
                y_values = np.fromiter((point[0] for point in component), dtype=np.int32)
                x_values = np.fromiter((point[1] for point in component), dtype=np.int32)
                component_mask[y_values, x_values] = True
                nearby_owner = owner[dilate_binary_mask(component_mask, 7) & (owner >= 0)]
                contacts.update(int(value) for value in nearby_owner)
            if not contacts:
                continue

            eligible_contacts = contacts
            if protected_labels:
                eligible_contacts = Counter(
                    {
                        index: count
                        for index, count in contacts.items()
                        if regions[index].label not in protected_labels
                        or regions[index].label == label
                    }
                )
            if not eligible_contacts:
                continue

            target = max(
                eligible_contacts,
                key=lambda index: (
                    eligible_contacts[index]
                    / (
                        1.0
                        + 2.0
                        * color_distance(palette[regions[index].label], palette[label])
                    ),
                    eligible_contacts[index],
                    -index,
                ),
            )
            y_values = np.fromiter((point[0] for point in component), dtype=np.int32)
            x_values = np.fromiter((point[1] for point in component), dtype=np.int32)
            merged_masks[target][y_values, x_values] = True
            owner[y_values, x_values] = target
            layer_name = f"color-region-{target + 1:02d}"
            merged_components[layer_name] += 1
            merged_pixels[layer_name] += len(component)
    return merged_masks, merged_components, merged_pixels


def fill_terrain_holes(mask: np.ndarray) -> np.ndarray:
    """Fill foreground shadows that touch side/bottom edges but not open sky."""
    height, width = mask.shape
    sky_connected = np.zeros_like(mask, dtype=bool)
    queue: deque[tuple[int, int]] = deque()
    for x_value in range(width):
        if not mask[0, x_value]:
            sky_connected[0, x_value] = True
            queue.append((0, x_value))
    while queue:
        y_value, x_value = queue.popleft()
        for delta_y, delta_x in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            next_y, next_x = y_value + delta_y, x_value + delta_x
            if (
                0 <= next_y < height
                and 0 <= next_x < width
                and not mask[next_y, next_x]
                and not sky_connected[next_y, next_x]
            ):
                sky_connected[next_y, next_x] = True
                queue.append((next_y, next_x))
    return mask | (~sky_connected)


def percentile_color(array: np.ndarray, mask: np.ndarray, percentile: float = 50.0) -> tuple[int, int, int]:
    pixels = array[mask]
    if not len(pixels):
        return (128, 128, 128)
    values = np.percentile(pixels, percentile, axis=0)
    return tuple(int(round(value)) for value in values)


def atmospheric_color(array: np.ndarray, mask: np.ndarray) -> tuple[int, int, int]:
    """Favor the source's subtle rose/blue atmospheric chroma over neutral haze."""
    pixels = array[mask].astype(np.float32)
    if not len(pixels):
        return (128, 128, 128)
    chroma_signal = (pixels[:, 0] + pixels[:, 2]) * 0.5 - pixels[:, 1]
    threshold = float(np.percentile(chroma_signal, 62.0))
    chromatic = pixels[chroma_signal >= threshold]
    if len(chromatic) < 16:
        chromatic = pixels
    values = np.median(chromatic, axis=0)
    return tuple(int(round(value)) for value in values)


def median_color(array: np.ndarray, mask: np.ndarray) -> tuple[int, int, int]:
    pixels = array[mask]
    if not len(pixels):
        return (128, 128, 128)
    values = np.median(pixels, axis=0)
    return tuple(int(round(value)) for value in values)


def is_night_landscape(image: Image.Image) -> bool:
    array = np.asarray(image, dtype=np.float32)
    luminance = 0.2126 * array[:, :, 0] + 0.7152 * array[:, :, 1] + 0.0722 * array[:, :, 2]
    height = luminance.shape[0]
    upper = luminance[: max(2, round(height * 0.58)), :]
    lower = array[round(height * 0.45) :, :, :]
    upper_rgb = array[: max(2, round(height * 0.58)), :, :]
    upper_warmth = float(np.median(upper_rgb[:, :, 0] - upper_rgb[:, :, 2]))
    lower_warmth = float(np.percentile(lower[:, :, 0] - lower[:, :, 2], 70))
    return float(np.mean(upper)) < 82.0 and lower_warmth > upper_warmth + 13.0


def night_landscape_layers(
    image: Image.Image,
    output_width: int,
    output_height: int,
    detail: float,
    color_mode: str,
    curve_smoothing: float,
    gradient_strength: float,
    min_negative_gap: float,
) -> tuple[
    tuple[int, int, int],
    list[SvgLayer],
    dict[str, str],
    np.ndarray,
    tuple[int, int, int],
    dict[str, object],
]:
    """Extract source-colored sky fields and a bottom-connected land silhouette."""
    array = np.asarray(image, dtype=np.uint8)
    height, width, _ = array.shape
    float_array = array.astype(np.float32)
    luminance = 0.2126 * float_array[:, :, 0] + 0.7152 * float_array[:, :, 1] + 0.0722 * float_array[:, :, 2]
    warm = float_array[:, :, 0] - float_array[:, :, 2]
    warm_image = Image.fromarray(np.clip(warm + 128.0, 0, 255).astype(np.uint8), mode="L")
    warm_smooth = np.asarray(
        warm_image.filter(ImageFilter.GaussianBlur(radius=max(1.15, width / 380.0))),
        dtype=np.float32,
    ) - 128.0
    smooth_luminance = np.asarray(
        Image.fromarray(np.clip(luminance, 0, 255).astype(np.uint8), mode="L").filter(
            ImageFilter.GaussianBlur(radius=max(1.0, width / 460.0))
        ),
        dtype=np.float32,
    )
    y_grid = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]

    # Warm rock is separated from the near-neutral sky, then required to remain
    # connected to the lower frame. This prevents a warm Milky Way from leaking
    # into the subject mask while preserving narrow hoodoos and overhangs.
    upper_luminance = luminance[: max(2, round(height * 0.28)), :]
    sky_floor = float(np.percentile(upper_luminance, 34.0))
    foreground_candidate = warm_smooth > (15.0 + 6.0 * (1.0 - y_grid))
    foreground_candidate &= smooth_luminance > max(20.0, sky_floor + 2.0)
    foreground_candidate &= y_grid > 0.245
    foreground_candidate[-max(2, round(height * 0.012)) :, :] = True
    foreground_candidate = clean_binary_mask(foreground_candidate, closing_size=5, mode_size=5)

    # Recover nearby rock shadows without allowing the permissive threshold to
    # propagate indefinitely into a warm Milky Way. The one-shot dilation is a
    # fixed shell around reliable warm seeds, not an iterative region grow.
    permissive_foreground = warm_smooth > (5.0 + 3.0 * (1.0 - y_grid))
    permissive_foreground &= smooth_luminance > 16.0
    permissive_foreground &= y_grid > 0.245
    recovery_shell = dilate_binary_mask(foreground_candidate, size=9)
    foreground_candidate |= recovery_shell & permissive_foreground
    foreground_candidate = clean_binary_mask(foreground_candidate, closing_size=5, mode_size=5)
    foreground_mask = bottom_connected_mask(foreground_candidate, bottom_band=max(3, round(height * 0.010)))
    foreground_mask = fill_terrain_holes(foreground_mask)
    foreground_mask, gap_closure_kernel, closed_gap_pixels = close_narrow_negative_gaps(
        foreground_mask,
        min_negative_gap,
    )
    foreground_components = components_from_mask(foreground_mask, min_fraction=0.0035, limit=2)
    if not foreground_components:
        raise ValueError("No stable foreground silhouette was found")
    foreground_path = " ".join(
        pixels_svg_path(
            component,
            width,
            height,
            output_width,
            output_height,
            epsilon=1.64 - 0.58 * detail,
            curve_smoothing=curve_smoothing,
            point_budget=132,
            curve_mode="bspline",
        )
        for component in foreground_components
    )

    sky_mask = ~foreground_mask
    base_source = percentile_color(array, sky_mask, 24.0)
    base_color = output_color(base_source, color_mode, role="sky")
    foreground_source = percentile_color(array, foreground_mask, 62.0)
    foreground_color = output_color(foreground_source, color_mode, role="foreground")

    layers: list[SvgLayer] = []
    gradient_axes: dict[str, str] = {}
    clips = {"foreground-clip": foreground_path}

    # One translucent field retains the Milky Way's broad direction without
    # creating nested bands that read as separate decorative blocks.
    broad = np.asarray(
        Image.fromarray(np.clip(luminance, 0, 255).astype(np.uint8), mode="L").filter(
            ImageFilter.GaussianBlur(radius=max(5.0, width / 31.0))
        ),
        dtype=np.float32,
    )
    sky_values = broad[sky_mask]
    luminous_counts: dict[str, int] = {}
    luminous_seam_pixels: dict[str, int] = {}
    luminous_seam_kernels: dict[str, int] = {}
    luminous_specs = (
        ("luminous-sky-field", 84.0, 0.16, "luminous-inner", 2.65, 86.0),
    )
    for name, percentile, opacity, role, epsilon_base, color_percentile in luminous_specs:
        threshold = float(np.percentile(sky_values, percentile))
        luminous_mask = sky_mask & (broad >= threshold) & (y_grid < 0.93)
        luminous_mask = clean_binary_mask(luminous_mask, closing_size=7, mode_size=7)
        luminous_mask = smooth_binary_boundary(luminous_mask, radius=max(2.5, width / 170.0))
        components = components_from_mask(luminous_mask, min_fraction=0.009, limit=2)
        filtered_components: list[list[tuple[int, int]]] = []
        for component in components:
            x_values = [point[1] for point in component]
            component_width = max(x_values) - min(x_values) + 1
            touches_side = min(x_values) <= 1 or max(x_values) >= width - 2
            if touches_side and component_width < width * 0.14:
                continue
            filtered_components.append(component)
        components = filtered_components
        luminous_counts[name] = len(components)
        if not components:
            continue
        stable_mask = np.zeros_like(luminous_mask)
        for component in components:
            for y_value, x_value in component:
                stable_mask[y_value, x_value] = True
        luminous_source = percentile_color(array, stable_mask & sky_mask, color_percentile)
        luminous_color = output_color(luminous_source, color_mode, role=role)
        luminous_gradient = source_gradient(
            array,
            stable_mask & sky_mask,
            luminous_color,
            gradient_strength,
            f"gradient-{name}",
        )
        if luminous_gradient:
            gradient_axes[name] = luminous_gradient.axis
        render_mask, seam_kernel, seam_pixels = overlap_near_touching_fields(
            stable_mask,
            foreground_mask,
            min_negative_gap,
        )
        render_components = components_from_mask(render_mask, min_fraction=0.009, limit=2)
        luminous_seam_pixels[name] = seam_pixels
        luminous_seam_kernels[name] = seam_kernel
        luminous_path = " ".join(
            pixels_svg_path(
                component,
                width,
                height,
                output_width,
                output_height,
                epsilon=epsilon_base - 0.42 * detail,
                curve_smoothing=min(1.0, curve_smoothing + 0.16),
                point_budget=48,
                curve_mode="bspline",
            )
            for component in render_components
        )
        layers.append(
            SvgLayer(name, luminous_path, luminous_color, opacity=opacity, gradient=luminous_gradient)
        )

    foreground_gradient = source_gradient(
        array,
        foreground_mask,
        foreground_color,
        gradient_strength,
        "gradient-foreground-silhouette",
    )
    if foreground_gradient:
        gradient_axes["foreground-silhouette"] = foreground_gradient.axis
    layers.append(
        SvgLayer(
            "foreground-silhouette",
            foreground_path,
            foreground_color,
            gradient=foreground_gradient,
        )
    )

    # Add one internal light role. The source-colored base carries the shadows;
    # omitting a separate shadow field prevents the foreground from fragmenting.
    # Internal value design operates at a much lower spatial frequency than
    # segmentation. This turns photographic ridges into one broad light field
    # instead of faithfully vectorizing every local tonal island.
    value_luminance = np.asarray(
        Image.fromarray(np.clip(luminance, 0, 255).astype(np.uint8), mode="L").filter(
            ImageFilter.GaussianBlur(radius=max(4.0, width / 54.0))
        ),
        dtype=np.float32,
    )
    fg_values = value_luminance[foreground_mask]
    light_floor = float(np.percentile(fg_values, 72.0))
    # Textured ground easily becomes a chain of decorative islands. Raise the
    # light threshold gradually only in the lowest third so the illuminated
    # hoodoos survive while minor ground variation falls back into the base.
    lower_ground_penalty = 22.0 * np.clip((y_grid - 0.68) / 0.32, 0.0, 1.0)
    value_specs = (
        ("foreground-light", value_luminance >= light_floor + lower_ground_penalty, "light"),
    )
    interior_counts: dict[str, int] = {}
    interior_rounding_kernels: dict[str, int] = {}
    interior_tip_pixels_removed: dict[str, int] = {}
    interior_edge_snap_kernels: dict[str, int] = {}
    interior_edge_snap_pixels: dict[str, int] = {}
    role_colors: dict[str, tuple[int, int, int]] = {}
    for name, value_mask, role in value_specs:
        mask = clean_binary_mask(foreground_mask & value_mask, closing_size=7, mode_size=7)
        mask = fill_enclosed_holes(mask)
        mask = smooth_binary_boundary(mask, radius=max(3.0, width / 120.0))
        internal_rounding_fraction = min(0.040, min_negative_gap * 1.35)
        mask, rounding_kernel, removed_tip_pixels = round_internal_positive_tips(
            mask,
            internal_rounding_fraction,
        )
        mask = smooth_binary_boundary(mask, radius=max(1.8, width / 260.0))
        interior_rounding_kernels[name] = rounding_kernel
        interior_tip_pixels_removed[name] = removed_tip_pixels
        components = components_from_mask(mask, min_fraction=0.0075, limit=2)
        interior_counts[name] = len(components)
        if not components:
            continue
        stable_mask = np.zeros_like(mask)
        for component in components:
            for y_value, x_value in component:
                stable_mask[y_value, x_value] = True
        source_color = median_color(array, stable_mask & foreground_mask)
        color = output_color(source_color, color_mode, role=role)
        role_colors[role] = color
        light_gradient = source_gradient(
            array,
            stable_mask & foreground_mask,
            color,
            gradient_strength,
            f"gradient-{name}",
        )
        if light_gradient:
            gradient_axes[name] = light_gradient.axis
        internal_edge_snap_fraction = min(0.060, min_negative_gap * 2.20)
        render_mask, edge_snap_kernel, edge_snap_pixels = overlap_near_touching_fields(
            stable_mask,
            ~foreground_mask,
            internal_edge_snap_fraction,
        )
        render_mask = fill_enclosed_holes(render_mask)
        render_components = components_from_mask(render_mask, min_fraction=0.0075, limit=2)
        interior_edge_snap_kernels[name] = edge_snap_kernel
        interior_edge_snap_pixels[name] = edge_snap_pixels
        path = " ".join(
            pixels_svg_path(
                component,
                width,
                height,
                output_width,
                output_height,
                epsilon=2.75 - 0.38 * detail,
                curve_smoothing=min(1.0, curve_smoothing + 0.14),
                point_budget=36,
                curve_mode="bspline",
                smoothing_passes=4,
            )
            for component in render_components
        )
        layers.append(
            SvgLayer(name, path, color, clip="foreground-clip", gradient=light_gradient)
        )

    bright_sky_threshold = float(np.percentile(luminance[sky_mask], 98.5))
    highlight_source = median_color(array, sky_mask & (luminance >= bright_sky_threshold))
    highlight_color = output_color(highlight_source, color_mode, role="star")

    metadata = {
        "archetype": "night-landscape",
        "foreground_component_count": len(foreground_components),
        "foreground_segmentation": "warm-seed + limited shadow recovery + top-connected sky fill + narrow-gap closure",
        "min_negative_gap_fraction": min_negative_gap,
        "negative_gap_closure_kernel": gap_closure_kernel,
        "negative_gap_pixels_closed": closed_gap_pixels,
        "curve_fitter": "periodic cubic B-spline to Bezier",
        "curve_segment_budgets": {
            "foreground-silhouette": 132,
            "luminous-sky-field": 48,
            "foreground-light-per-component": 36,
        },
        "gradient_axes": gradient_axes,
        "luminous_field_count": sum(luminous_counts.values()),
        "luminous_region_counts": luminous_counts,
        "luminous_seam_overlap_pixels": luminous_seam_pixels,
        "luminous_seam_overlap_kernels": luminous_seam_kernels,
        "interior_region_counts": interior_counts,
        "internal_contour_policy": "rounded positive tips + minimum-clearance edge snap inside foreground clip",
        "internal_rounding_kernels": interior_rounding_kernels,
        "internal_tip_pixels_removed": interior_tip_pixels_removed,
        "internal_edge_snap_kernels": interior_edge_snap_kernels,
        "internal_edge_snap_pixels": interior_edge_snap_pixels,
        "structural_palette": {
            "sky": rgb_hex(base_color),
            "foreground": rgb_hex(foreground_color),
            "light": rgb_hex(role_colors.get("light", foreground_color)),
            "star": rgb_hex(highlight_color),
        },
    }
    allowed_points = sky_mask & (y_grid < 0.79)
    return base_color, layers, clips, allowed_points, highlight_color, metadata


def detect_point_highlights(
    image: Image.Image,
    seed: int,
    limit: int = 32,
    allowed_mask: np.ndarray | None = None,
) -> list[tuple[float, float, float]]:
    gray_image = image.convert("L")
    gray = np.asarray(gray_image, dtype=np.float32)
    blurred = np.asarray(gray_image.filter(ImageFilter.GaussianBlur(radius=2.3)), dtype=np.float32)
    high_pass = gray - blurred
    height, width = gray.shape
    upper = gray[: max(2, round(height * 0.82)), :]
    if float(np.mean(upper)) > 105:
        return []
    high_threshold = float(np.percentile(high_pass[: upper.shape[0], :], 99.15))
    brightness_threshold = float(np.percentile(upper, 82.0))
    mask = (
        (high_pass >= max(9.0, high_threshold))
        & (gray >= max(80.0, brightness_threshold))
        & (blurred <= 145.0)
    )
    mask[upper.shape[0] :, :] = False
    if allowed_mask is not None:
        if allowed_mask.shape != mask.shape:
            raise ValueError("Highlight mask dimensions do not match the analysis image")
        mask &= allowed_mask
    ys, xs = np.where(mask)
    if len(xs) < 24:
        return []
    scores = high_pass[ys, xs] + 0.18 * gray[ys, xs]
    order = np.argsort(scores)[::-1]
    rng = np.random.default_rng(seed)
    chosen: list[tuple[float, float, float]] = []
    minimum_distance = max(4.0, min(width, height) * 0.022)
    for position in order:
        x = float(xs[position])
        y = float(ys[position])
        if any((x - px * width) ** 2 + (y - py * height) ** 2 < minimum_distance**2 for px, py, _ in chosen):
            continue
        normalized_score = clamp(float(scores[position]) / 170.0, 0.25, 1.0)
        radius = 0.70 + 1.20 * normalized_score + float(rng.uniform(-0.12, 0.12))
        chosen.append((x / width, y / height, radius))
        if len(chosen) >= limit:
            break
    return chosen


def svg_document(
    source_path: Path,
    output_width: int,
    output_height: int,
    background_color: tuple[int, int, int],
    layers: list[SvgLayer],
    clips: dict[str, str],
    highlight_color: tuple[int, int, int],
    highlights: list[tuple[float, float, float]],
    paper: float,
    paper_style: str,
    paper_density: float,
    grain_overlay: float,
    seed: int,
) -> str:
    background_hex = rgb_hex(background_color)
    star_color = tuple(round(channel * 0.72 + 255 * 0.28) for channel in highlight_color)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{output_width}" height="{output_height}" viewBox="0 0 {output_width} {output_height}" overflow="hidden">',
        f'  <title>Programmatic abstraction of {escape(source_path.name)}</title>',
        '  <desc>Deterministic source-derived shapes rendered as SVG; no Canvas and no generative image model.</desc>',
        '  <defs>',
    ]
    if paper > 0 and (paper_style == "grain" or grain_overlay > 0):
        lines.extend([
            '    <filter id="surface-noise" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB">',
            f'      <feTurbulence type="fractalNoise" baseFrequency="0.28" numOctaves="3" seed="{seed}" stitchTiles="stitch" result="noise"/>',
            '      <feColorMatrix in="noise" type="saturate" values="0" result="mono"/>',
            '      <feComponentTransfer in="mono">',
            '        <feFuncR type="linear" slope="1.32" intercept="-0.16"/>',
            '        <feFuncG type="linear" slope="1.32" intercept="-0.16"/>',
            '        <feFuncB type="linear" slope="1.32" intercept="-0.16"/>',
            '        <feFuncA type="linear" slope="0.72"/>',
            '      </feComponentTransfer>',
            '    </filter>',
        ])
    if paper > 0 and paper_style == "rough":
        lines.extend([
            '    <filter id="paper-undulation" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB">',
            f'      <feTurbulence type="fractalNoise" baseFrequency="0.010" numOctaves="1" seed="{seed}" stitchTiles="stitch" result="noise"/>',
            '      <feColorMatrix in="noise" type="saturate" values="0" result="mono"/>',
            '      <feComponentTransfer in="mono">',
            '        <feFuncR type="linear" slope="1.15" intercept="-0.075"/>',
            '        <feFuncG type="linear" slope="1.15" intercept="-0.075"/>',
            '        <feFuncB type="linear" slope="1.15" intercept="-0.075"/>',
            '        <feFuncA type="linear" slope="0.55"/>',
            '      </feComponentTransfer>',
            '    </filter>',
        ])

        texture_rng = np.random.default_rng(seed + 2048)
        canvas_area = output_width * output_height
        density = clamp(paper_density, 0.25, 4.0)
        particle_scale = clamp(density ** -0.28, 0.60, 1.30)
        fiber_count = max(72, round(canvas_area / 12000.0 * math.sqrt(density)))
        dark_pore_count = max(320, round(canvas_area / 2100.0 * density))
        light_pore_count = max(120, round(canvas_area / 6200.0 * density))

        lines.append(
            f'    <pattern id="paper-fiber-pattern" patternUnits="userSpaceOnUse" width="{output_width}" height="{output_height}">'
        )
        lines.append('      <g fill="none" stroke-linecap="round">')
        for _ in range(fiber_count):
            center_x = float(texture_rng.uniform(0.0, output_width))
            center_y = float(texture_rng.uniform(0.0, output_height))
            length = float(texture_rng.uniform(5.0, 20.0))
            angle = float(texture_rng.normal(-0.10, 0.38))
            half_dx = math.cos(angle) * length * 0.5
            half_dy = math.sin(angle) * length * 0.5
            normal_x = -math.sin(angle)
            normal_y = math.cos(angle)
            bend = float(texture_rng.uniform(-1.8, 1.8))
            start_x = center_x - half_dx
            start_y = center_y - half_dy
            end_x = center_x + half_dx
            end_y = center_y + half_dy
            control_x = center_x + normal_x * bend
            control_y = center_y + normal_y * bend
            stroke = "#F4E9DB" if texture_rng.random() < 0.32 else "#211713"
            width = float(texture_rng.uniform(0.38, 0.92) * particle_scale)
            opacity = float(texture_rng.uniform(0.28, 0.72))
            lines.append(
                f'        <path d="M {start_x:.2f} {start_y:.2f} Q {control_x:.2f} {control_y:.2f} {end_x:.2f} {end_y:.2f}" '
                f'stroke="{stroke}" stroke-width="{width:.2f}" opacity="{opacity:.3f}"/>'
            )
        lines.extend(['      </g>', '    </pattern>'])

        lines.append(
            f'    <pattern id="paper-pore-pattern" patternUnits="userSpaceOnUse" width="{output_width}" height="{output_height}">'
        )
        lines.append('      <g>')
        for index in range(dark_pore_count + light_pore_count):
            is_light = index >= dark_pore_count
            center_x = float(texture_rng.uniform(0.0, output_width))
            center_y = float(texture_rng.uniform(0.0, output_height))
            if is_light:
                radius_x = float(texture_rng.uniform(0.45, 1.45) * particle_scale)
                fill = "#F8EFE4"
                opacity = float(texture_rng.uniform(0.30, 0.68))
            else:
                radius_x = float(texture_rng.uniform(0.70, 2.65) * particle_scale)
                if texture_rng.random() < 0.055 / max(1.0, math.sqrt(density)):
                    radius_x *= float(
                        texture_rng.uniform(1.35, 1.85) * min(1.0, particle_scale)
                    )
                fill = "#17100D"
                opacity = float(texture_rng.uniform(0.34, 0.78))
            radius_y = radius_x * float(texture_rng.uniform(0.48, 1.05))
            angle = float(texture_rng.uniform(0.0, 180.0))
            lines.append(
                f'        <ellipse cx="{center_x:.2f}" cy="{center_y:.2f}" rx="{radius_x:.2f}" ry="{radius_y:.2f}" '
                f'fill="{fill}" opacity="{opacity:.3f}" transform="rotate({angle:.2f} {center_x:.2f} {center_y:.2f})"/>'
            )
        lines.extend(['      </g>', '    </pattern>'])
    for layer in layers:
        gradient = layer.gradient
        if gradient is None:
            continue
        lines.append(
            f'    <linearGradient id="{escape(gradient.name)}" '
            f'x1="{gradient.x1:.3f}" y1="{gradient.y1:.3f}" '
            f'x2="{gradient.x2:.3f}" y2="{gradient.y2:.3f}">'
        )
        for offset, color in gradient.stops:
            lines.append(f'      <stop offset="{offset:.3f}" stop-color="{rgb_hex(color)}"/>')
        lines.append('    </linearGradient>')
    for clip_id, clip_path in clips.items():
        lines.append(f'    <clipPath id="{escape(clip_id)}"><path d="{clip_path}" fill-rule="evenodd"/></clipPath>')
    lines.extend([
        '  </defs>',
        f'  <rect width="{output_width}" height="{output_height}" fill="{background_hex}"/>',
        '  <g id="source-derived-fields">',
    ])
    for layer in layers:
        if not layer.path:
            continue
        clip = f' clip-path="url(#{escape(layer.clip)})"' if layer.clip else ""
        opacity = f' opacity="{layer.opacity:.3f}"' if layer.opacity < 0.999 else ""
        fill = f"url(#{escape(layer.gradient.name)})" if layer.gradient else rgb_hex(layer.color)
        lines.append(
            f'    <path id="{escape(layer.name)}" d="{layer.path}" fill="{fill}" fill-rule="evenodd"{clip}{opacity}/>'
        )
    lines.append('  </g>')
    if highlights:
        lines.append(f'  <g id="point-highlights" fill="{rgb_hex(star_color)}" opacity="0.84">')
        for x, y, radius in highlights:
            lines.append(
                f'    <circle cx="{x * output_width:.2f}" cy="{y * output_height:.2f}" r="{radius * output_width / 900.0:.2f}"/>'
            )
        lines.append('  </g>')
    if paper > 0:
        lines.append(
            f'  <g id="surface-noise-layer" data-paper-style="{paper_style}" '
            f'data-paper-density="{paper_density:.3f}" data-grain-overlay="{grain_overlay:.3f}" '
            f'pointer-events="none">'
        )
        if paper_style == "grain":
            lines.append(
                f'    <rect width="{output_width}" height="{output_height}" fill="#8a8a8a" opacity="{paper:.3f}" filter="url(#surface-noise)" style="mix-blend-mode:soft-light"/>'
            )
        else:
            rough_layers = (
                ("paper-undulation-layer", "#8A8A8A", paper * 0.08, "url(#paper-undulation)", "soft-light"),
                ("paper-fiber-layer", "url(#paper-fiber-pattern)", paper * 0.62, None, None),
                ("paper-pore-layer", "url(#paper-pore-pattern)", paper * 0.82, None, None),
            )
            for layer_id, fill, opacity, filter_id, blend_mode in rough_layers:
                filter_attribute = f' filter="{filter_id}"' if filter_id else ""
                blend_attribute = f' style="mix-blend-mode:{blend_mode}"' if blend_mode else ""
                lines.append(
                    f'    <rect id="{layer_id}" width="{output_width}" height="{output_height}" fill="{fill}" opacity="{opacity:.3f}"{filter_attribute}{blend_attribute}/>'
                )
            if grain_overlay > 0:
                lines.append(
                    f'    <rect id="traditional-grain-overlay" width="{output_width}" height="{output_height}" '
                    f'fill="#8A8A8A" opacity="{grain_overlay:.3f}" filter="url(#surface-noise)" '
                    f'style="mix-blend-mode:soft-light"/>'
                )
        lines.append('  </g>')
    lines.append('</svg>')
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Source photograph")
    parser.add_argument("output", type=Path, help="Destination .svg")
    parser.add_argument("--width", type=int, default=1600, help="SVG width; aspect ratio follows the source")
    parser.add_argument("--palette-size", type=int, default=6, choices=range(4, 10), metavar="4..9")
    parser.add_argument("--detail", type=float, default=0.28, help="0 = most reduced, 1 = more source contours")
    parser.add_argument("--paper", type=float, default=0.34, help="Top surface-noise strength from 0 to 1")
    parser.add_argument(
        "--paper-style",
        choices=("grain", "rough"),
        default="grain",
        help="Use ordinary filtered grain or hybrid vector-particle rough paper",
    )
    parser.add_argument(
        "--paper-density",
        type=float,
        default=1.0,
        help="Vector particle coverage for rough paper from 0.25 to 4; higher values make finer, denser grain",
    )
    parser.add_argument(
        "--grain-overlay",
        type=float,
        default=0.0,
        help="Traditional fine fractal-noise layer added above rough paper from 0 to 1",
    )
    parser.add_argument(
        "--gradient-strength",
        type=float,
        default=0.30,
        help="Mix source-derived color variation into structural fills from 0 to 1",
    )
    parser.add_argument(
        "--min-negative-gap",
        type=float,
        default=0.018,
        help="Minimum retained negative-space width as a fraction of the short side; 0 disables closure",
    )
    parser.add_argument("--seed", type=int, default=17, help="Deterministic texture and highlight seed")
    parser.add_argument("--max-shapes", type=int, default=12, help="Maximum number of large color regions")
    parser.add_argument("--analysis-size", type=int, default=520, help="Longest side used for segmentation")
    parser.add_argument(
        "--color-mode",
        choices=("source", "balanced", "curated-night"),
        default="source",
        help="Keep sampled source colors, apply restrained OKLCH guardrails, or use the optional night preset",
    )
    parser.add_argument(
        "--curve-smoothing",
        type=float,
        default=0.82,
        help="Cubic contour smoothing from 0 to 1",
    )
    parser.add_argument(
        "--archetype",
        choices=("auto", "general", "night-landscape"),
        default="auto",
        help="Force a visual grammar or let measured image properties choose",
    )
    parser.add_argument("--no-points", action="store_true", help="Disable automatically detected point highlights")
    parser.add_argument("--analysis-json", type=Path, help="Optional path for the extracted visual plan")
    args = parser.parse_args()

    if not args.input.is_file():
        raise SystemExit(f"Input photograph not found: {args.input}")
    if args.output.suffix.lower() != ".svg":
        raise SystemExit("Output must use the .svg extension")
    if args.width < 320:
        raise SystemExit("--width must be at least 320")
    if (
        not 0.0 <= args.detail <= 1.0
        or not 0.0 <= args.paper <= 1.0
        or not 0.0 <= args.curve_smoothing <= 1.0
        or not 0.0 <= args.gradient_strength <= 1.0
        or not 0.0 <= args.min_negative_gap <= 0.08
        or not 0.25 <= args.paper_density <= 4.0
        or not 0.0 <= args.grain_overlay <= 1.0
    ):
        raise SystemExit(
            "--detail, --paper, --gradient-strength, and --curve-smoothing must be between 0 and 1; "
            "--min-negative-gap must be between 0 and 0.08; --paper-density must be between 0.25 and 4; "
            "--grain-overlay must be between 0 and 1"
        )
    if args.grain_overlay > 0 and (args.paper_style != "rough" or args.paper <= 0):
        raise SystemExit("--grain-overlay requires --paper-style rough and --paper above 0")
    if not 3 <= args.max_shapes <= 30:
        raise SystemExit("--max-shapes must be between 3 and 30")

    with Image.open(args.input) as opened:
        source = ImageOps.exif_transpose(opened).convert("RGB")
    analyzed = analysis_image(source, args.analysis_size)
    output_width = args.width
    output_height = round(output_width * source.height / source.width)
    analysis_width, analysis_height = analyzed.size
    archetype_metadata: dict[str, object]
    use_night_landscape = args.archetype == "night-landscape" or (
        args.archetype == "auto" and is_night_landscape(analyzed)
    )
    reflection_evidence = (
        horizontal_reflection_evidence(analyzed)
        if args.archetype == "auto" and not use_night_landscape
        else None
    )
    use_reflective_horizontal = reflection_evidence is not None
    labels, sampled_palette, palette_metadata = quantized_labels(
        analyzed,
        args.palette_size,
        smoothing=2,
        preserve_compact_islands=(
            not use_night_landscape and not use_reflective_horizontal
        ),
        preserve_perspective_lines=(
            not use_night_landscape and not use_reflective_horizontal
        ),
    )
    artistic_palette = [output_color(color, args.color_mode) for color in sampled_palette]
    if use_night_landscape:
        background_color, layers, clips, point_mask, highlight_color, archetype_metadata = night_landscape_layers(
            analyzed,
            output_width,
            output_height,
            args.detail,
            args.color_mode,
            args.curve_smoothing,
            args.gradient_strength,
            args.min_negative_gap,
        )
        background = None
    elif use_reflective_horizontal:
        assert reflection_evidence is not None
        (
            background_color,
            layers,
            clips,
            point_mask,
            highlight_color,
            sampled_palette,
            artistic_palette,
            reflection_population_fractions,
            archetype_metadata,
        ) = reflective_horizontal_layers(
            analyzed,
            output_width,
            output_height,
            reflection_evidence,
            args.color_mode,
            args.curve_smoothing,
            args.gradient_strength,
        )
        palette_metadata["palette_population_fractions"] = (
            reflection_population_fractions
        )
        background = None
    else:
        background = choose_background(labels)
        protected_source_role_labels = set(
            range(args.palette_size, len(sampled_palette))
        )
        compact_role_count = int(
            palette_metadata.get("compact_salient_island_count", 0)
        )
        perspective_line_role_count = int(
            palette_metadata.get("perspective_accent_line_count", 0)
        )
        overlay_role_count = compact_role_count + perspective_line_role_count
        overlay_source_role_labels = set(
            range(len(sampled_palette) - overlay_role_count, len(sampled_palette))
        )
        compact_role_labels = set(
            range(
                len(sampled_palette)
                - perspective_line_role_count
                - compact_role_count,
                len(sampled_palette) - perspective_line_role_count,
            )
        )
        perspective_line_role_labels = set(
            range(
                len(sampled_palette) - perspective_line_role_count,
                len(sampled_palette),
            )
        )
        regions = connected_regions(
            labels,
            sampled_palette,
            background,
            args.detail,
            args.max_shapes,
            protected_source_role_labels,
            overlay_source_role_labels,
        )
        region_masks: list[np.ndarray] = []
        for region in regions:
            region_mask = np.zeros((analysis_height, analysis_width), dtype=bool)
            for y_value, x_value in region.pixels:
                region_mask[y_value, x_value] = True
            region_masks.append(region_mask)
        gradient_masks = [mask.copy() for mask in region_masks]
        (
            region_masks,
            general_discarded_components_merged,
            general_discarded_pixels_merged,
        ) = merge_discarded_nonbackground_regions(
            labels,
            background,
            sampled_palette,
            regions,
            region_masks,
            protected_source_role_labels,
        )
        (
            region_masks,
            general_negative_space_close_kernel,
            general_negative_space_hole_area_limit,
            general_negative_space_closed_pixels,
            general_negative_space_holes_filled,
            general_negative_space_components_reassigned,
            general_negative_space_pixels_reassigned,
        ) = consolidate_subclearance_negative_space(
            region_masks,
            args.min_negative_gap,
        )

        render_masks: list[np.ndarray] = []
        general_seam_overlap_pixels: dict[str, int] = {}
        general_micro_holes_filled: dict[str, int] = {}
        general_micro_hole_pixels: dict[str, int] = {}
        general_unrepresented_holes_merged: dict[str, int] = {}
        general_unrepresented_hole_pixels: dict[str, int] = {}
        general_chromatic_false_background_holes_merged: dict[str, int] = {}
        general_chromatic_false_background_pixels_merged: dict[str, int] = {}
        general_frame_edges_touched: dict[str, list[str]] = {}
        general_seam_overlap_kernel = 1
        general_micro_hole_area_limit = 0
        general_frame_bleed_analysis_pixels = frame_bleed_margin(
            analysis_width,
            analysis_height,
        )
        (
            general_seam_clearance_radius,
            general_seam_fitting_margin,
            expected_general_seam_overlap_kernel,
            _,
        ) = seam_underlap_geometry(
            (analysis_height, analysis_width),
            args.min_negative_gap,
        )
        retained_union = np.logical_or.reduce(region_masks)
        background_mask = labels == background
        analyzed_array = np.asarray(analyzed, dtype=np.uint8)
        for index, region_mask in enumerate(region_masks):
            later_masks = region_masks[index + 1 :]
            if later_masks:
                later_union = np.logical_or.reduce(later_masks)
                render_mask, seam_kernel, seam_pixels = overlap_near_touching_fields(
                    region_mask,
                    later_union,
                    args.min_negative_gap,
                )
                general_seam_overlap_kernel = seam_kernel
            else:
                render_mask = region_mask.copy()
                seam_pixels = 0
            render_mask, hole_area_limit, holes_filled, hole_pixels = fill_small_enclosed_holes(
                render_mask,
                args.min_negative_gap,
            )
            other_retained_masks = retained_union & (~region_mask)
            (
                render_mask,
                unrepresented_holes,
                unrepresented_pixels,
                chromatic_false_background_holes,
                chromatic_false_background_pixels,
            ) = fill_unrepresented_enclosed_holes(
                render_mask,
                other_retained_masks,
                background_mask,
                analyzed_array,
                sampled_palette[regions[index].label],
                sampled_palette[background],
            )
            general_micro_hole_area_limit = hole_area_limit
            render_masks.append(render_mask)
            layer_name = f"color-region-{index + 1:02d}"
            general_seam_overlap_pixels[layer_name] = seam_pixels
            general_micro_holes_filled[layer_name] = holes_filled
            general_micro_hole_pixels[layer_name] = hole_pixels
            general_unrepresented_holes_merged[layer_name] = unrepresented_holes
            general_unrepresented_hole_pixels[layer_name] = unrepresented_pixels
            general_chromatic_false_background_holes_merged[layer_name] = (
                chromatic_false_background_holes
            )
            general_chromatic_false_background_pixels_merged[layer_name] = (
                chromatic_false_background_pixels
            )
            general_frame_edges_touched[layer_name] = touched_frame_edges(render_mask)

        paths = [
            pixels_svg_path(
                [(int(y_value), int(x_value)) for y_value, x_value in np.argwhere(render_mask)],
                analysis_width,
                analysis_height,
                output_width,
                output_height,
                epsilon=(
                    1.65
                    if region.label in compact_role_labels
                    else 3.3 - 2.1 * args.detail
                ),
                curve_smoothing=(
                    min(args.curve_smoothing, 0.70)
                    if region.label in compact_role_labels
                    else args.curve_smoothing
                ),
                smoothing_passes=(
                    2 if region.label in compact_role_labels else 4
                ),
                frame_bleed=(
                    1
                    if region.label in perspective_line_role_labels
                    else general_frame_bleed_analysis_pixels
                ),
                spread_frame_contacts=region.label not in perspective_line_role_labels,
                micro_contour_filter=region.label not in protected_source_role_labels,
            )
            for region, render_mask in zip(regions, render_masks)
        ]
        background_color = artistic_palette[background]
        layers = []
        for index, (region, gradient_mask, path) in enumerate(zip(regions, gradient_masks, paths)):
            if not path:
                continue
            layer_name = f"color-region-{index + 1:02d}"
            region_gradient = (
                None
                if region.label in perspective_line_role_labels
                else source_gradient(
                    analyzed_array,
                    gradient_mask,
                    artistic_palette[region.label],
                    args.gradient_strength,
                    f"gradient-{layer_name}",
                )
            )
            layers.append(
                SvgLayer(layer_name, path, artistic_palette[region.label], gradient=region_gradient)
            )
        clips = {}
        highlight_color = max(artistic_palette, key=lambda color: sum(color))
        point_mask = None
        archetype_metadata = {
            "archetype": "general-color-fields",
            "general_contour_policy": "four-pass closed-loop low-pass before cubic Bezier fitting",
            "general_contour_low_passes": 4,
            "general_micro_contour_policy": "scale-limited narrow-versus-broad contour filtering on ordinary fields only",
            "general_micro_contour_filter_passes": 2,
            "general_compact_contour_policy": "two-pass identity lock for protected compact roles",
            "general_compact_contour_low_passes": 2,
            "general_frame_boundary_policy": "extend touching paths beyond the clipped viewBox",
            "general_frame_bleed_analysis_pixels": general_frame_bleed_analysis_pixels,
            "general_frame_edges_touched": general_frame_edges_touched,
            "general_discarded_region_policy": "merge touching non-background components into retained fields",
            "general_discarded_components_merged": general_discarded_components_merged,
            "general_discarded_pixels_merged": general_discarded_pixels_merged,
            "general_negative_space_policy": "collapse sub-clearance background channels and micro-pockets before fitting",
            "general_negative_space_close_kernel": general_negative_space_close_kernel,
            "general_negative_space_hole_area_limit": general_negative_space_hole_area_limit,
            "general_negative_space_closed_pixels": general_negative_space_closed_pixels,
            "general_negative_space_holes_filled": general_negative_space_holes_filled,
            "general_negative_space_components_reassigned": general_negative_space_components_reassigned,
            "general_negative_space_pixels_reassigned": general_negative_space_pixels_reassigned,
            "general_boundary_policy": "curve-fit-safe render-order underlap between retained adjacent fields",
            "general_seam_clearance_radius_analysis_pixels": general_seam_clearance_radius,
            "general_seam_fitting_margin_analysis_pixels": general_seam_fitting_margin,
            "general_seam_overlap_kernel": general_seam_overlap_kernel,
            "general_seam_expected_overlap_kernel": expected_general_seam_overlap_kernel,
            "general_seam_overlap_pixels": general_seam_overlap_pixels,
            "general_micro_hole_policy": "fill enclosed holes up to the minimum-clearance area",
            "general_micro_hole_area_limit": general_micro_hole_area_limit,
            "general_micro_holes_filled": general_micro_holes_filled,
            "general_micro_hole_pixels": general_micro_hole_pixels,
            "general_unrepresented_hole_policy": "merge discarded non-background islands",
            "general_unrepresented_holes_merged": general_unrepresented_holes_merged,
            "general_unrepresented_hole_pixels": general_unrepresented_hole_pixels,
        }
        if any(general_chromatic_false_background_holes_merged.values()):
            archetype_metadata.update(
                {
                    "general_chromatic_false_background_policy": "merge compact enclosed background labels whose source hue aligns with the enclosing field and opposes the background",
                    "general_chromatic_false_background_holes_merged": general_chromatic_false_background_holes_merged,
                    "general_chromatic_false_background_pixels_merged": general_chromatic_false_background_pixels_merged,
                }
            )
    highlights = [] if args.no_points else detect_point_highlights(analyzed, args.seed, allowed_mask=point_mask)
    paper_vector_particle_count = 0
    if args.paper > 0 and args.paper_style == "rough":
        canvas_area = output_width * output_height
        paper_vector_particle_count = (
            max(72, round(canvas_area / 12000.0 * math.sqrt(args.paper_density)))
            + max(320, round(canvas_area / 2100.0 * args.paper_density))
            + max(120, round(canvas_area / 6200.0 * args.paper_density))
        )

    document = svg_document(
        args.input,
        output_width,
        output_height,
        background_color,
        layers,
        clips,
        highlight_color,
        highlights,
        args.paper,
        args.paper_style,
        args.paper_density,
        args.grain_overlay,
        args.seed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(document, encoding="utf-8")

    plan = {
        "input": str(args.input.resolve()),
        "source_dimensions": list(source.size),
        "output_dimensions": [output_width, output_height],
        "analysis_dimensions": [analysis_width, analysis_height],
        "renderer": "SVG (no Canvas, no image generation model)",
        "frame_bleed_policy": "extend frame-touching masks outside a clipped viewBox before fitting",
        "frame_bleed_analysis_pixels": frame_bleed_margin(analysis_width, analysis_height),
        "palette_sampled": [rgb_hex(color) for color in sampled_palette],
        "palette_output": [rgb_hex(color) for color in artistic_palette],
        **palette_metadata,
        "color_mode": args.color_mode,
        "curve_smoothing": args.curve_smoothing,
        "gradient_strength": args.gradient_strength,
        "min_negative_gap_fraction": args.min_negative_gap,
        "gradient_layer_count": sum(layer.gradient is not None for layer in layers),
        "background_label": background,
        "large_shape_count": len(layers),
        "point_highlight_count": len(highlights),
        "paper_strength": args.paper,
        "paper_style": args.paper_style,
        "paper_density": args.paper_density,
        "grain_overlay_strength": args.grain_overlay,
        "paper_vector_particle_count": paper_vector_particle_count,
        "paper_texture_model": "none"
        if args.paper <= 0
        else (
            "hybrid-vector-particles+traditional-grain"
            if args.paper_style == "rough" and args.grain_overlay > 0
            else ("hybrid-vector-particles" if args.paper_style == "rough" else "continuous-fractal-grain")
        ),
        "surface_noise_layer": args.paper > 0,
        "seed": args.seed,
        **archetype_metadata,
    }
    analysis_path = args.analysis_json or args.output.with_suffix(".json")
    analysis_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    print(f"PASS: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

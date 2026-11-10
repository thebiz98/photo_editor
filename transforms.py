"""
transforms.py - Pure Geometric Transforms, Homography Solver, and Perspective Quad Extraction.
Zero neural-network dependencies; operates directly with PIL and NumPy.
"""

import math
from typing import List, Optional, Tuple
import numpy as np
from PIL import Image


def calculate_perspective_coeffs(
    source_quad: List[Tuple[float, float]],
    target_w: int,
    target_h: int
) -> Tuple[float, ...]:
    """
    Computes the 8 coefficients (a, b, c, d, e, f, g, h) for PIL's Image.PERSPECTIVE transform.
    Maps target rectangle (0, 0, target_w, target_h) to source quadrilateral points:
    source_quad = [TL, TR, BR, BL].

    Transformation equations for mapping destination (X, Y) to source (x, y):
        x = (a*X + b*Y + c) / (g*X + h*Y + 1)
        y = (d*X + e*Y + f) / (g*X + h*Y + 1)
    """
    if len(source_quad) != 4:
        raise ValueError(f"source_quad must contain exactly 4 points (TL, TR, BR, BL), got {len(source_quad)}")

    if target_w <= 0 or target_h <= 0:
        raise ValueError(f"target dimensions must be positive, got ({target_w}, {target_h})")

    # Destination rectangle points: TL, TR, BR, BL
    dst_points = [
        (0.0, 0.0),
        (float(target_w), 0.0),
        (float(target_w), float(target_h)),
        (0.0, float(target_h)),
    ]

    matrix = []
    vector = []
    for (X, Y), (x, y) in zip(dst_points, source_quad):
        # Row for x mapping: a*X + b*Y + c - g*X*x - h*Y*x = x
        matrix.append([X, Y, 1.0, 0.0, 0.0, 0.0, -X * x, -Y * x])
        vector.append(float(x))

        # Row for y mapping: d*X + e*Y + f - g*X*y - h*Y*y = y
        matrix.append([0.0, 0.0, 0.0, X, Y, 1.0, -X * y, -Y * y])
        vector.append(float(y))

    a_mat = np.array(matrix, dtype=np.float64)
    b_vec = np.array(vector, dtype=np.float64)

    # Solve the 8x8 system of linear equations
    coeffs = np.linalg.solve(a_mat, b_vec)
    return tuple(coeffs.tolist())


def calculate_natural_quad_dimensions(source_quad: List[Tuple[float, float]]) -> Tuple[int, int]:
    """
    Calculates natural unconstrained width and height from source quadrilateral corner coordinates
    [TL, TR, BR, BL] using Euclidean distance. Preserves native image resolution.
    """
    if len(source_quad) != 4:
        raise ValueError("source_quad must have 4 points (TL, TR, BR, BL)")

    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = source_quad

    # Edge distances
    w_top = math.hypot(x1 - x0, y1 - y0)
    w_bottom = math.hypot(x2 - x3, y2 - y3)
    h_left = math.hypot(x3 - x0, y3 - y0)
    h_right = math.hypot(x2 - x1, y2 - y1)

    width = max(10, int(round(max(w_top, w_bottom))))
    height = max(10, int(round(max(h_left, h_right))))

    return (width, height)


def crop_and_resize(
    img: Image.Image,
    roi_box: Tuple[int, int, int, int],
    target_px: Optional[Tuple[int, int]] = None
) -> Image.Image:
    """
    Crops img to roi_box (x1, y1, x2, y2) and resizes to target_px (width_px, height_px).
    """
    x1, y1, x2, y2 = roi_box
    w, h = img.size
    x1 = max(0, min(int(round(min(x1, x2))), w - 1))
    y1 = max(0, min(int(round(min(y1, y2))), h - 1))
    x2 = max(x1 + 1, min(int(round(max(x1, x2))), w))
    y2 = max(y1 + 1, min(int(round(max(y1, y2))), h))

    cropped = img.crop((x1, y1, x2, y2))
    if target_px is not None and target_px[0] and target_px[1]:
        cropped = cropped.resize((int(target_px[0]), int(target_px[1])), Image.LANCZOS)
    return cropped


def extract_perspective_quad(
    img: Image.Image,
    source_quad: List[Tuple[float, float]],
    target_size: Optional[Tuple[int, int]] = None
) -> Image.Image:
    """
    Extracts and rectifies a 4-point quadrilateral [TL, TR, BR, BL] from img into a straightened rectangle.
    If target_size is None, natural unconstrained pixel dimensions are automatically calculated.
    """
    if target_size is None:
        target_w, target_h = calculate_natural_quad_dimensions(source_quad)
    else:
        target_w, target_h = int(round(target_size[0])), int(round(target_size[1]))

    coeffs = calculate_perspective_coeffs(source_quad, target_w, target_h)

    # Use BICUBIC resampling for sharp, smooth document/photo rectification
    rectified = img.transform(
        (target_w, target_h),
        Image.Transform.PERSPECTIVE,
        coeffs,
        Image.Resampling.BICUBIC
    )
    return rectified

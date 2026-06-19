"""Material 3 Expressive loading indicator — tkinter canvas port.

Shape geometry mirrors assets/blossom-m3-loading.js (Android M3 shape assets).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

SHAPE_COUNT = 7
SAMPLES_PER_CURVE = 14
POINTS_PER_SHAPE = 180
DURATION_PER_SHAPE_MS = 650.0
CONSTANT_ROTATION_DEG = 50.0
EXTRA_ROTATION_DEG = 90.0

SVG_DEFS: list[dict[str, object] | None] = [
    {
        "viewBox": 144,
        "d": (
            "M65.3162 3.5567C68.3922 -1.18556 75.6078 -1.18557 78.6837 3.55669L86.0569 14.9241"
            "C88.0791 18.0418 92.1588 19.3094 95.7112 17.9237L108.664 12.8715C114.067 10.7638"
            " 119.905 14.8195 119.478 20.3849L118.456 33.7255C118.175 37.3845 120.697 40.7029"
            " 124.422 41.5786L138.007 44.7714C143.674 46.1033 145.903 52.6655 142.137 56.9283"
            "L133.11 67.1465C130.634 69.9491 130.634 74.0509 133.11 76.8535L142.137 87.0716"
            "C145.903 91.3345 143.674 97.8967 138.007 99.2286L124.422 102.421C120.697 103.297"
            " 118.175 106.616 118.456 110.274L119.478 123.615C119.905 129.181 114.067 133.236"
            " 108.664 131.129L95.7112 126.076C92.1588 124.691 88.0791 125.958 86.0569 129.076"
            "L78.6838 140.443C75.6078 145.186 68.3922 145.186 65.3162 140.443L57.9431 129.076"
            "C55.9208 125.958 51.8412 124.691 48.2888 126.076L35.3365 131.129C29.933 133.236"
            " 24.0954 129.181 24.5219 123.615L25.5442 110.274C25.8246 106.616 23.3033 103.297"
            " 19.5775 102.421L5.99339 99.2286C0.326335 97.8967 -1.90342 91.3345 1.86259 87.0717"
            "L10.8899 76.8535C13.3658 74.0509 13.3658 69.9491 10.8899 67.1465L1.8626 56.9283"
            "C-1.90341 52.6655 0.326326 46.1033 5.99338 44.7714L19.5775 41.5786C23.3033 40.7029"
            " 25.8246 37.3845 25.5442 33.7255L24.5219 20.3849C24.0954 14.8195 29.933 10.7638"
            " 35.3364 12.8715L48.2888 17.9237C51.8412 19.3094 55.9208 18.0418 57.9431 14.9241"
            "L65.3162 3.5567Z"
        ),
    },
    {
        "viewBox": 144,
        "d": (
            "M56.3679 6.02002C57.1442 5.3783 57.5324 5.05744 57.8867 4.78656C66.2354 -1.59552"
            " 77.7646 -1.59552 86.1133 4.78656C86.4676 5.05744 86.8558 5.3783 87.6321 6.02002"
            "C87.9786 6.30648 88.1519 6.44971 88.3233 6.58606C92.2522 9.71203 97.0693 11.4835"
            " 102.068 11.6405C102.286 11.6473 102.51 11.6501 102.957 11.6558C103.96 11.6684"
            " 104.462 11.6747 104.906 11.6973C115.361 12.2303 124.193 19.7179 126.528 30.0289"
            "C126.627 30.4666 126.721 30.9644 126.907 31.9602C126.99 32.4047 127.032 32.627"
            " 127.076 32.8427C128.097 37.789 130.661 42.2744 134.39 45.6409C134.552 45.7878"
            " 134.722 45.9353 135.062 46.2304C135.822 46.8914 136.202 47.2219 136.528 47.5275"
            "C144.198 54.7262 146.2 66.1979 141.429 75.6132C141.227 76.0128 140.981 76.4547"
            " 140.49 77.3386C140.271 77.7332 140.162 77.9304 140.059 78.1246C137.694 82.5768"
            " 136.804 87.6775 137.519 92.6782C137.55 92.8964 137.586 93.1196 137.658 93.5661"
            "C137.82 94.5662 137.901 95.0663 137.956 95.5117C139.252 106.008 133.488 116.096"
            " 123.843 120.21C123.434 120.385 122.965 120.564 122.026 120.922C121.608 121.082"
            " 121.398 121.162 121.196 121.244C116.552 123.119 112.625 126.448 109.991 130.743"
            "C109.876 130.93 109.762 131.125 109.533 131.514C109.021 132.385 108.765 132.821"
            " 108.523 133.198C102.839 142.08 92.0048 146.064 81.9992 142.952C81.5745 142.82"
            " 81.1011 142.652 80.1544 142.318C79.7318 142.168 79.5205 142.094 79.3133 142.025"
            "C74.5631 140.445 69.4369 140.445 64.6867 142.025C64.4795 142.094 64.2682 142.168"
            " 63.8456 142.318C62.8989 142.652 62.4255 142.82 62.0008 142.952C51.9952 146.064"
            " 41.1613 142.08 35.4766 133.198C35.2353 132.821 34.9791 132.385 34.4669 131.514"
            "C34.2382 131.125 34.1239 130.93 34.009 130.743C31.3752 126.448 27.4482 123.119"
            " 22.8044 121.244C22.6018 121.162 22.3924 121.082 21.9736 120.922C21.0354 120.564"
            " 20.5663 120.385 20.1569 120.21C10.5122 116.096 4.74763 106.008 6.04367 95.5117"
            "C6.09868 95.0663 6.17963 94.5662 6.34151 93.5661C6.41377 93.1196 6.4499 92.8964"
            " 6.48109 92.6783C7.19603 87.6775 6.30587 82.5768 3.94121 78.1246C3.83807 77.9304"
            " 3.72855 77.7332 3.50951 77.3386C3.01883 76.4547 2.77349 76.0128 2.57099 75.6132"
            "C-2.19995 66.1979 -0.197931 54.7262 7.47248 47.5275C7.79804 47.2219 8.17819 46.8914"
            " 8.93848 46.2304C9.27787 45.9353 9.44757 45.7878 9.61023 45.6409C13.3394 42.2744"
            " 15.9025 37.789 16.9235 32.8427C16.9681 32.627 17.0097 32.4047 17.0929 31.9602"
            "C17.2793 30.9644 17.3725 30.4666 17.4717 30.0289C19.8069 19.7179 28.6387 12.2303"
            " 39.0944 11.6973C39.5382 11.6747 40.0397 11.6684 41.0426 11.6558C41.4903 11.6501"
            " 41.7142 11.6473 41.9322 11.6405C46.9307 11.4835 51.7478 9.71203 55.6767 6.58606"
            "C55.8481 6.44971 56.0214 6.30648 56.3679 6.02002Z"
        ),
    },
    {
        "viewBox": 144,
        "d": (
            "M49.3332 10.9681C56.3577 5.53061 59.8699 2.81189 63.6224 1.46315C69.0501 -0.487717"
            " 74.9499 -0.487717 80.3776 1.46315C84.1301 2.81189 87.6423 5.53062 94.6668 10.9681"
            "L110.03 22.8606L125.386 34.0038C132.67 39.2902 136.313 41.9334 138.747 45.2576"
            "C142.27 50.0661 144.119 55.9761 143.994 62.0207C143.907 66.1996 142.46 70.5678"
            " 139.564 79.3044L133.535 97.4958L127.969 116.136C125.358 124.884 124.052 129.258"
            " 121.769 132.66C118.466 137.581 113.667 141.201 108.144 142.936C104.327 144.135"
            " 99.9259 144.065 91.1241 143.926L72 143.623L52.8759 143.926C44.0741 144.065"
            " 39.6732 144.135 35.8555 142.936C30.3334 141.201 25.5338 137.581 22.2314 132.66"
            "C19.9483 129.258 18.6425 124.884 16.0307 116.136L10.4655 97.4958L4.43609 79.3044"
            "C1.54044 70.5678 0.0926215 66.1996 0.00597479 62.0207C-0.119358 55.9761 1.73035"
            " 50.0661 5.2525 45.2576C7.68747 41.9334 11.3298 39.2902 18.6143 34.0038L33.9696"
            " 22.8606L49.3332 10.9681Z"
        ),
    },
    {
        "viewBox": 144,
        "d": (
            "M40.4355 21.4968C63.0979 -1.16559 99.8408 -1.16559 122.503 21.4968C145.166 44.1592"
            " 145.166 80.9021 122.503 103.565L103.565 122.503C80.9021 145.166 44.1592 145.166"
            " 21.4968 122.503C-1.16559 99.8408 -1.1656 63.0979 21.4968 40.4355L40.4355 21.4968Z"
        ),
    },
    {
        "viewBox": 153,
        "d": (
            "M117.835 18.5569C122.594 18.8803 124.973 19.0419 126.896 19.883C129.679 21.0999"
            " 131.9 23.3213 133.117 26.1039C133.958 28.027 134.12 30.4062 134.443 35.1647"
            "L135.181 46.0237C135.312 47.9482 135.377 48.9105 135.586 49.8297C135.889 51.1579"
            " 136.414 52.4254 137.139 53.5784C137.641 54.3763 138.275 55.1029 139.544 56.5563"
            "L146.7 64.7565C149.837 68.3499 151.405 70.1466 152.17 72.1011C153.277 74.9292"
            " 153.277 78.0708 152.17 80.8989C151.405 82.8534 149.837 84.6501 146.7 88.2435"
            "L139.544 96.4437C138.275 97.8971 137.641 98.6237 137.139 99.4217C136.414 100.575"
            " 135.889 101.842 135.586 103.17C135.377 104.09 135.312 105.052 135.181 106.976"
            "L134.443 117.835C134.12 122.594 133.958 124.973 133.117 126.896C131.9 129.679"
            " 129.679 131.9 126.896 133.117C124.973 133.958 122.594 134.12 117.835 134.443"
            "L106.976 135.181C105.052 135.312 104.09 135.377 103.17 135.586C101.842 135.889"
            " 100.575 136.414 99.4217 137.139C98.6237 137.641 97.8971 138.275 96.4437 139.544"
            "L88.2435 146.7C84.6501 149.837 82.8534 151.405 80.8989 152.17C78.0708 153.277"
            " 74.9292 153.277 72.1011 152.17C70.1466 151.405 68.3499 149.837 64.7565 146.7"
            "L56.5563 139.544C55.1029 138.275 54.3763 137.641 53.5784 137.139C52.4254 136.414"
            " 51.1579 135.889 49.8297 135.586C48.9105 135.377 47.9482 135.312 46.0237 135.181"
            "L35.1647 134.443C30.4062 134.12 28.027 133.958 26.1039 133.117C23.3213 131.9"
            " 21.0999 129.679 19.883 126.896C19.0419 124.973 18.8803 122.594 18.5569 117.835"
            "L17.819 106.976C17.6882 105.052 17.6228 104.09 17.4136 103.17C17.1113 101.842"
            " 16.5863 100.575 15.8608 99.4217C15.3588 98.6237 14.7246 97.8971 13.4562 96.4437"
            "L6.29956 88.2435C3.16348 84.6501 1.59544 82.8534 0.830322 80.8989C-0.276774 78.0708"
            " -0.276774 74.9292 0.830323 72.1011C1.59544 70.1466 3.16348 68.3499 6.29956"
            " 64.7565L13.4562 56.5563C14.7246 55.1029 15.3588 54.3763 15.8608 53.5784"
            "C16.5863 52.4254 17.1113 51.1579 17.4136 49.8297C17.6228 48.9105 17.6882 47.9482"
            " 17.819 46.0237L18.5569 35.1647C18.8803 30.4062 19.0419 28.027 19.883 26.1039"
            "C21.0999 23.3213 23.3213 21.0999 26.1039 19.883C28.027 19.0419 30.4062 18.8803"
            " 35.1647 18.5569L46.0237 17.819C47.9482 17.6882 48.9105 17.6228 49.8297 17.4136"
            "C51.1579 17.1113 52.4254 16.5863 53.5784 15.8608C54.3763 15.3588 55.1029 14.7246"
            " 56.5563 13.4562L64.7565 6.29957C68.3499 3.16348 70.1466 1.59544 72.1011 0.830323"
            "C74.9292 -0.276774 78.0708 -0.276774 80.8989 0.830323C82.8534 1.59544 84.6501"
            " 3.16348 88.2435 6.29957L96.4437 13.4562C97.8971 14.7246 98.6237 15.3588 99.4216"
            " 15.8608C100.575 16.5863 101.842 17.1113 103.17 17.4136C104.09 17.6228 105.052"
            " 17.6882 106.976 17.819L117.835 18.5569Z"
        ),
    },
    {
        "viewBox": 144,
        "d": (
            "M89.4282 11.7931C116.492 0.0387955 143.961 27.5077 132.207 54.5718L130.263 59.0465"
            "C126.675 67.3094 126.675 76.6907 130.263 84.9535L132.207 89.4282C143.961 116.492"
            " 116.492 143.961 89.4282 132.207L84.9535 130.263C76.6907 126.675 67.3093 126.675"
            " 59.0465 130.263L54.5718 132.207C27.5077 143.961 0.0387983 116.492 11.7931 89.4282"
            "L13.7366 84.9535C17.3253 76.6907 17.3252 67.3093 13.7366 59.0465L11.7931 54.5718"
            "C0.0387955 27.5077 27.5077 0.0387993 54.5718 11.7931L59.0465 13.7366C67.3094"
            " 17.3252 76.6907 17.3252 84.9535 13.7366L89.4282 11.7931Z"
        ),
    },
    None,
]

_SHAPES: list[list[tuple[float, float]]] | None = None


def _parse_svg_path(d: str) -> list[tuple[str, list[float]]]:
    cmds: list[tuple[str, list[float]]] = []
    for m in re.finditer(r"([MCLZmclz])([^MCLZmclz]*)", d):
        nums = re.findall(r"-?\d+\.?\d*(?:e[+-]?\d+)?", m.group(2))
        cmds.append((m.group(1), [float(n) for n in nums]))
    return cmds


def _sample_cubic(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    steps: int,
) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for i in range(1, steps + 1):
        t = i / steps
        u = 1 - t
        out.append(
            (
                u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
                u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1],
            )
        )
    return out


def _svg_path_to_points(d: str) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    cx = 0.0
    cy = 0.0
    for cmd, args in _parse_svg_path(d):
        if cmd == "M":
            cx, cy = args[0], args[1]
            pts.append((cx, cy))
        elif cmd == "L":
            for i in range(0, len(args), 2):
                cx, cy = args[i], args[i + 1]
                pts.append((cx, cy))
        elif cmd == "C":
            for i in range(0, len(args), 6):
                p0 = (cx, cy)
                p1 = (args[i], args[i + 1])
                p2 = (args[i + 2], args[i + 3])
                p3 = (args[i + 4], args[i + 5])
                pts.extend(_sample_cubic(p0, p1, p2, p3, SAMPLES_PER_CURVE))
                cx, cy = p3
    return pts


def _normalize(pts: list[tuple[float, float]], view_box: float) -> list[tuple[float, float]]:
    h = view_box / 2
    c = [((x - h) / h, (y - h) / h) for x, y in pts]
    x0 = min(p[0] for p in c)
    x1 = max(p[0] for p in c)
    y0 = min(p[1] for p in c)
    y1 = max(p[1] for p in c)
    s = min(2 / (x1 - x0), 2 / (y1 - y0))
    ox = (x0 + x1) / 2
    oy = (y0 + y1) / 2
    return [((x - ox) * s, (y - oy) * s) for x, y in c]


def _resample(pts: list[tuple[float, float]], n: int) -> list[tuple[float, float]]:
    all_pts = [*pts, pts[0]]
    arc = [0.0]
    for i in range(1, len(all_pts)):
        dx = all_pts[i][0] - all_pts[i - 1][0]
        dy = all_pts[i][1] - all_pts[i - 1][1]
        arc.append(arc[-1] + math.hypot(dx, dy))
    total = arc[-1]
    out: list[tuple[float, float]] = []
    for i in range(n):
        target = (i / n) * total
        j = 1
        while j < len(arc) - 1 and arc[j] < target:
            j += 1
        t = (target - arc[j - 1]) / (arc[j] - arc[j - 1]) if arc[j] > arc[j - 1] else 0.0
        out.append(
            (
                all_pts[j - 1][0] + t * (all_pts[j][0] - all_pts[j - 1][0]),
                all_pts[j - 1][1] + t * (all_pts[j][1] - all_pts[j - 1][1]),
            )
        )
    return out


def _generate_oval(n: int) -> list[tuple[float, float]]:
    return [
        (math.cos(i / n * 2 * math.pi), 0.74 * math.sin(i / n * 2 * math.pi))
        for i in range(n)
    ]


def get_shapes() -> list[list[tuple[float, float]]]:
    global _SHAPES
    if _SHAPES is not None:
        return _SHAPES
    built: list[list[tuple[float, float]]] = []
    for defn in SVG_DEFS:
        if defn is None:
            built.append(_generate_oval(POINTS_PER_SHAPE))
            continue
        raw = _svg_path_to_points(str(defn["d"]))
        norm = _normalize(raw, float(defn["viewBox"]))
        built.append(_resample(norm, POINTS_PER_SHAPE))
    _SHAPES = built
    return _SHAPES


def lerp_shapes(
    a: list[tuple[float, float]], b: list[tuple[float, float]], t: float
) -> list[tuple[float, float]]:
    return [(a[i][0] + (b[i][0] - a[i][0]) * t, a[i][1] + (b[i][1] - a[i][1]) * t) for i in range(len(a))]


def get_morphed_shape(morph_fraction: float) -> list[tuple[float, float]]:
    shapes = get_shapes()
    idx = int(math.floor(morph_fraction))
    from_i = (idx % SHAPE_COUNT + SHAPE_COUNT) % SHAPE_COUNT
    to_i = (from_i + 1) % SHAPE_COUNT
    t = max(0.0, min(1.0, morph_fraction - idx))
    return lerp_shapes(shapes[from_i], shapes[to_i], t)


@dataclass
class Spring:
    k: float = 200.0
    damping_ratio: float = 0.6
    pos: float = 0.0
    vel: float = 0.0
    target: float = 0.0

    def __post_init__(self) -> None:
        self.c = self.damping_ratio * 2 * math.sqrt(self.k)

    def step(self, dt: float) -> None:
        sub = dt / 12.0
        for _ in range(12):
            accel = -self.k * (self.pos - self.target) - self.c * self.vel
            self.vel += accel * sub
            self.pos += self.vel * sub

    def reset(self) -> None:
        self.pos = 0.0
        self.vel = 0.0
        self.target = 0.0


@dataclass
class M3LoadingAnimator:
    morph_target: float = 1.0
    fraction: float = 0.0
    elapsed_ms: float = 0.0
    last_ts_ms: float = 0.0
    prev_cycle: int = 0
    speed: float = 1.0
    paused: bool = False
    rotation: float = 0.0
    morph: float = 0.0
    spring: Spring = field(default_factory=Spring)

    def __post_init__(self) -> None:
        self.spring.target = 1.0

    def update(self, ts_ms: float) -> None:
        if self.paused:
            self.last_ts_ms = ts_ms
            return
        if self.last_ts_ms == 0.0:
            self.last_ts_ms = ts_ms
        raw_dt = min((ts_ms - self.last_ts_ms) / 1000.0, 0.1)
        dt = raw_dt * self.speed
        self.last_ts_ms = ts_ms
        if dt <= 0:
            return
        self.elapsed_ms += dt * 1000.0
        cycle = int(self.elapsed_ms // DURATION_PER_SHAPE_MS)
        if cycle > self.prev_cycle:
            self.morph_target += cycle - self.prev_cycle
            self.spring.target = self.morph_target
            self.prev_cycle = cycle
        self.fraction = (self.elapsed_ms % DURATION_PER_SHAPE_MS) / DURATION_PER_SHAPE_MS
        self.spring.step(dt)
        base = self.morph_target - 1.0
        per_shape = self.spring.pos - base
        self.rotation = (
            (CONSTANT_ROTATION_DEG + EXTRA_ROTATION_DEG) * base
            + CONSTANT_ROTATION_DEG * self.fraction
            + EXTRA_ROTATION_DEG * per_shape
        ) % 360.0
        self.morph = self.spring.pos


def polygon_points(
    morph_fraction: float,
    rotation_deg: float,
    *,
    size: float = 48.0,
    size_ratio: float = 0.79,
) -> list[tuple[float, float]]:
    """Return canvas-ready polygon vertices for a centered indicator."""
    shape = get_morphed_shape(morph_fraction)
    indicator_size = size * size_ratio
    scale = indicator_size / 2.0
    cx = size / 2.0
    cy = size / 2.0
    rad = math.radians(rotation_deg)
    cos_r = math.cos(rad)
    sin_r = math.sin(rad)
    out: list[tuple[float, float]] = []
    for px, py in shape:
        rx = px * scale
        ry = py * scale
        out.append((cx + rx * cos_r - ry * sin_r, cy + rx * sin_r + ry * cos_r))
    return out


# M3 Expressive capsule progress geometry (mirrors assets/blossom-m3-progress.js).
PROGRESS_GEOM = {
    "fill_height": 12.0,
    "padding_min": 10.0,
    "padding_max": 14.0,
    "padding_ratio": 0.045,
    "indeterminate_span_ratio": 0.34,
}


def progress_layout(width: float, height: float) -> dict[str, float]:
    """Padded capsule track geometry (24px host, 12px fill)."""
    padding_x = min(
        PROGRESS_GEOM["padding_max"],
        max(PROGRESS_GEOM["padding_min"], width * PROGRESS_GEOM["padding_ratio"]),
    )
    usable = max(1.0, width - padding_x * 2.0)
    fill_h = PROGRESS_GEOM["fill_height"]
    track_y = (height - fill_h) / 2.0
    return {
        "padding_x": padding_x,
        "usable": usable,
        "fill_h": fill_h,
        "track_y": track_y,
        "track_x0": padding_x,
        "track_x1": padding_x + usable,
    }


def indeterminate_progress_window(
    width: float, phase: float, *, padding_x: float | None = None, usable: float | None = None
) -> tuple[float, float]:
    """Sliding [x0, x1] capsule window inside padded usable width (phase 0..1)."""
    pad = padding_x if padding_x is not None else min(12.0, max(10.0, width * 0.04))
    span_usable = usable if usable is not None else max(1.0, width - pad * 2.0)
    span = span_usable * PROGRESS_GEOM["indeterminate_span_ratio"]
    start = pad + (span_usable + span) * phase - span
    return max(pad, start), min(pad + span_usable, start + span)


def draw_capsule(
    canvas,
    x0: float,
    x1: float,
    y: float,
    height: float,
    fill: str,
    *,
    outline: str = "",
) -> None:
    """Rounded capsule (pill) on a tkinter canvas."""
    if x1 <= x0 + 0.5 or height <= 0:
        return
    w = x1 - x0
    r = min(height / 2.0, w / 2.0)
    edge = outline or fill
    if w <= height + 0.5:
        canvas.create_oval(x0, y, x1, y + height, fill=fill, outline=edge)
        return
    canvas.create_oval(x0, y, x0 + height, y + height, fill=fill, outline=edge)
    canvas.create_rectangle(x0 + r, y, x1 - r, y + height, fill=fill, outline=edge)
    canvas.create_oval(x1 - height, y, x1, y + height, fill=fill, outline=edge)

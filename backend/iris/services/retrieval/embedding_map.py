from __future__ import annotations

import math
import warnings
from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectedEmbedding:
    """A document embedding projected into viewer space."""

    x: float
    y: float
    z: float
    cluster_id: int | None


@dataclass(frozen=True)
class EmbeddingProjection:
    """Projection output plus the method used to generate it."""

    points: list[ProjectedEmbedding]
    method: str


def project_embeddings(vectors: list[list[float]], *, radius: float = 42.0) -> EmbeddingProjection:
    """Project high-dimensional embeddings into 3D coordinates with cluster ids."""
    if not vectors:
        return EmbeddingProjection(points=[], method="empty")
    if len(vectors) == 1:
        return EmbeddingProjection(points=[ProjectedEmbedding(0.0, 0.0, 0.0, None)], method="single-point")

    try:
        return _project_with_umap(vectors, radius=radius)
    except Exception:
        return _project_with_power_iteration(vectors, radius=radius)


def _project_with_umap(vectors: list[list[float]], *, radius: float) -> EmbeddingProjection:
    """Project embeddings with PCA denoising, UMAP layout, and KMeans cluster labels."""
    if len(vectors) < 8:
        raise ValueError("UMAP needs a larger sample")

    import numpy as np
    import umap
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import normalize

    matrix = normalize(np.asarray(vectors, dtype=np.float32), norm="l2")
    reduced_dimensions = min(50, matrix.shape[0] - 1, matrix.shape[1])
    if reduced_dimensions >= 2:
        reduced = PCA(n_components=reduced_dimensions, random_state=42).fit_transform(matrix)
    else:
        reduced = matrix

    neighbors = min(30, max(2, len(vectors) - 1))
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="n_jobs value .* overridden .*", category=UserWarning)
        coordinates = umap.UMAP(
            n_components=3,
            n_neighbors=neighbors,
            min_dist=0.08,
            metric="cosine",
            random_state=42,
            transform_seed=42,
        ).fit_transform(reduced)

    cluster_count = min(24, max(2, round(math.sqrt(len(vectors) / 5))))
    clusters = KMeans(n_clusters=cluster_count, n_init=10, random_state=42).fit_predict(reduced)
    scaled = _scale_numpy_points(coordinates, radius=radius)
    return EmbeddingProjection(
        points=[
            ProjectedEmbedding(
                x=round(float(point[0]), 4),
                y=round(float(point[1]), 4),
                z=round(float(point[2]), 4),
                cluster_id=int(cluster_id),
            )
            for point, cluster_id in zip(scaled, clusters)
        ],
        method=f"pca{reduced_dimensions}_umap3_kmeans{cluster_count}",
    )


def _scale_numpy_points(points, *, radius: float):
    import numpy as np

    centered = points - points.mean(axis=0, keepdims=True)
    distances = np.linalg.norm(centered, axis=1)
    scale_distance = float(np.percentile(distances, 95)) or 1.0
    scaled = centered * (radius / scale_distance)
    return np.clip(scaled, -radius * 1.35, radius * 1.35)


def _project_with_power_iteration(vectors: list[list[float]], *, radius: float) -> EmbeddingProjection:
    """Fallback projection using deterministic PCA-style power iteration."""
    dimensions = min(len(vector) for vector in vectors)
    trimmed = [vector[:dimensions] for vector in vectors if len(vector) >= dimensions]
    means = [sum(vector[index] for vector in trimmed) / len(trimmed) for index in range(dimensions)]
    centered = [[value - means[index] for index, value in enumerate(vector)] for vector in trimmed]

    components: list[list[float]] = []
    for seed in range(min(3, dimensions)):
        components.append(_principal_component(centered, components, seed))

    projected = [
        tuple(_dot(vector, component) for component in components) + (0.0,) * (3 - len(components))
        for vector in centered
    ]
    coordinates = _normalize(projected, radius)
    cluster_ids = _fallback_cluster_ids(coordinates)
    return EmbeddingProjection(
        points=[
            ProjectedEmbedding(x=x, y=y, z=z, cluster_id=cluster_id)
            for (x, y, z), cluster_id in zip(coordinates, cluster_ids)
        ],
        method="power_iteration_fallback",
    )


def _fallback_cluster_ids(points: list[tuple[float, float, float]]) -> list[int | None]:
    if len(points) < 4:
        return [None for _ in points]
    return [int((x >= 0)) + (2 * int(y >= 0)) + (4 * int(z >= 0)) for x, y, z in points]


def _principal_component(vectors: list[list[float]], previous: list[list[float]], seed: int) -> list[float]:
    dimensions = len(vectors[0])
    component = [0.0] * dimensions
    component[seed % dimensions] = 1.0

    for _ in range(24):
        next_component = [0.0] * dimensions
        for vector in vectors:
            scale = _dot(vector, component)
            for index, value in enumerate(vector):
                next_component[index] += scale * value
        for existing in previous:
            existing_scale = _dot(next_component, existing)
            for index, value in enumerate(existing):
                next_component[index] -= existing_scale * value
        component = _unit(next_component)
    return component


def _normalize(points: list[tuple[float, ...]], radius: float) -> list[tuple[float, float, float]]:
    max_distance = max(math.sqrt(sum(value * value for value in point)) for point in points) or 1.0
    scale = radius / max_distance
    return [
        (
            round(point[0] * scale, 4),
            round(point[1] * scale, 4),
            round(point[2] * scale, 4),
        )
        for point in points
    ]


def _dot(left: list[float] | tuple[float, ...], right: list[float]) -> float:
    return sum(left_value * right_value for left_value, right_value in zip(left, right))


def _unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]

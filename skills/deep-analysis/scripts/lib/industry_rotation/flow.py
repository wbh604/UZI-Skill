"""Conservation-constrained approximate flow solver ported from allw_lbw.

This is not the unpublished optimizer from the original research report.
"""
from __future__ import annotations

import math
import statistics
from typing import Sequence


def _zscore(values: Sequence[float]) -> list[float]:
    if not values:
        return []
    mean = statistics.fmean(values)
    variance = statistics.fmean((x - mean) ** 2 for x in values)
    std = math.sqrt(variance)
    if std <= 1e-15:
        return [0.0] * len(values)
    return [(x - mean) / std for x in values]


def _minimal_flow(net: Sequence[float]) -> list[list[float]]:
    """完整图上满足行和 net 的最小 Frobenius 范数反对称流。"""
    n = len(net)
    if abs(sum(net)) > 1e-10:
        raise ValueError("净流量必须加总为零")
    return [[(net[i] - net[j]) / n for j in range(n)] for i in range(n)]


def _row_sums(flow: Sequence[Sequence[float]]) -> list[float]:
    return [sum(row) for row in flow]


def _quadratic_divergence(
    flow: Sequence[Sequence[float]],
    coefficients: Sequence[float] | None = None,
) -> list[float]:
    raw = [sum(x * abs(x) for x in row) for row in flow]
    if coefficients is None:
        return raw
    if len(coefficients) != len(raw):
        raise ValueError("收益映射系数长度不一致")
    return [coefficient * value for coefficient, value in zip(coefficients, raw)]


def infer_flow_graph(
    industry_net: Sequence[float],
    excess_returns: Sequence[float],
    volume_share: Sequence[float] | None = None,
    size_share: Sequence[float] | None = None,
    iterations: int = 18,
    ridge: float = 0.03,
) -> list[list[float]]:
    """近似研报的资金流反演，同时严格保持边和节点的质量守恒。

    节点 0 为市场外部，行业从节点 1 开始。每轮梯度更新后，把解正交投影回
    指定行和的仿射空间。全局正系数代替研报未披露的逐行业 alpha/beta。
    """
    if len(industry_net) != len(excess_returns):
        raise ValueError("净流量和收益长度不一致")
    target_net = [0.0, *industry_net]
    target_return = [0.0, *excess_returns]
    n = len(target_net)
    if volume_share is None:
        volume_share = [1.0 / len(industry_net)] * len(industry_net)
    if size_share is None:
        size_share = [1.0 / len(industry_net)] * len(industry_net)
    if len(volume_share) != len(industry_net) or len(size_share) != len(industry_net):
        raise ValueError("成交额或规模占比长度不一致")
    # 曼宁式原始指数对应 H ~ S^(1/3) / V^(4/3) * Q|Q|。
    coefficients = [
        1.0,
        *[
            max(s, 1e-12) ** (1.0 / 3.0) / max(v, 1e-12) ** (4.0 / 3.0)
            for s, v in zip(size_share, volume_share)
        ],
    ]
    base = _minimal_flow(target_net)
    flow = [row[:] for row in base]
    q_scale = max(math.sqrt(statistics.fmean(x * x for x in industry_net)), 1e-8)

    for _ in range(max(iterations, 0)):
        divergence = _quadratic_divergence(flow, coefficients)
        denom = sum(x * x for x in divergence)
        if denom <= 1e-24:
            break
        scale = max(sum(h * d for h, d in zip(target_return, divergence)) / denom, 0.0)
        if scale <= 1e-12:
            rms_h = math.sqrt(statistics.fmean(h * h for h in target_return))
            rms_d = math.sqrt(statistics.fmean(d * d for d in divergence))
            scale = rms_h / max(rms_d, 1e-12)
        residual = [scale * d - h for d, h in zip(divergence, target_return)]

        gradients: list[tuple[int, int, float]] = []
        max_gradient = 0.0
        for i in range(n):
            for j in range(i + 1, n):
                x = flow[i][j]
                grad = 4.0 * scale * abs(x) * (
                    coefficients[i] * residual[i] - coefficients[j] * residual[j]
                )
                grad += 2.0 * ridge * (x - base[i][j])
                gradients.append((i, j, grad))
                max_gradient = max(max_gradient, abs(grad))
        if max_gradient <= 1e-18:
            break
        step = 0.12 * q_scale / max_gradient
        for i, j, grad in gradients:
            value = flow[i][j] - step * grad
            flow[i][j] = value
            flow[j][i] = -value

        residual_net = [target_net[i] - x for i, x in enumerate(_row_sums(flow))]
        for i in range(n):
            for j in range(i + 1, n):
                correction = (residual_net[i] - residual_net[j]) / n
                value = flow[i][j] + correction
                flow[i][j] = value
                flow[j][i] = -value

    return flow

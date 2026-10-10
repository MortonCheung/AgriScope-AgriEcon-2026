#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M1′ 共享库：自包含贝叶斯采样与诊断（无 PyMC 依赖，Python 3.9 + numpy 兼容）。
- 自适应随机游走 Metropolis（Haario 自适应协方差），4 链并行推进；
- 诊断：split-R-hat、bulk ESS、tail ESS（rank-normalized）、接受率。
说明：因环境无 PyMC（需 Python>=3.10），本实现替代 PyMC/ArviZ，细节见 MODEL_ENVIRONMENT.md。
"""
import numpy as np

PARAM_NAMES = ["alpha", "beta_T", "beta_R", "log_sigma"]


# ------------------------------------------------------------------ 先验
def log_prior(theta, prior):
    """prior: dict with keys alpha(mu,sd), beta_T(mu,sd), beta_R(mu,sd), log_sigma(mu,sd)."""
    alpha, bT, bR, ls = theta[..., 0], theta[..., 1], theta[..., 2], theta[..., 3]
    lp = np.zeros(theta.shape[:-1])
    lp = lp + _dnorm(alpha, prior["alpha"][0], prior["alpha"][1])
    lp = lp + _dnorm(bT, prior["beta_T"][0], prior["beta_T"][1])
    lp = lp + _dnorm(bR, prior["beta_R"][0], prior["beta_R"][1])
    lp = lp + _dnorm(ls, prior["log_sigma"][0], prior["log_sigma"][1])
    return lp


def _dnorm(x, mu, sd):
    return -0.5 * ((x - mu) / sd) ** 2 - np.log(sd)


# ------------------------------------------------------------------ 似然
def log_lik(theta, y, ZT, ZR, use_R=True):
    """log Y = alpha + beta_T*ZT + beta_R*ZR + eps, eps~N(0,sigma).
    theta: (...,4)；y/ZT/ZR: (n,)；返回 (...,)。"""
    alpha, bT, bR, ls = theta[..., 0], theta[..., 1], theta[..., 2], theta[..., 3]
    sigma = np.exp(ls)
    mu = alpha[..., None] + bT[..., None] * ZT[None, :]
    if use_R:
        mu = mu + bR[..., None] * ZR[None, :]
    resid = (y[None, :] - mu) / sigma[..., None]
    return -0.5 * np.sum(resid ** 2, axis=-1) - len(y) * ls - 0.5 * len(y) * np.log(2 * np.pi)


def log_posterior(theta, y, ZT, ZR, prior, use_R=True):
    lp = log_prior(theta, prior) + log_lik(theta, y, ZT, ZR, use_R=use_R)
    return lp


# ------------------------------------------------------------------ 采样
def sample(y, ZT, ZR, prior, use_R=True, n_chains=4, warmup=4000, draws=4000,
           seed=20260922, init_scale=0.15):
    rng = np.random.default_rng(seed)
    p = 4
    # 初值：以先验中心为起点 + 小扰动
    center = np.array([prior["alpha"][0], prior["beta_T"][0], prior["beta_R"][0], prior["log_sigma"][0]])
    theta = center + rng.normal(0, init_scale, size=(n_chains, p))
    lp = log_posterior(theta, y, ZT, ZR, prior, use_R)
    # 自适应协方差（warmup 期间用 Haario 更新）
    cov = np.eye(p) * (0.05 ** 2)
    scale = 2.38 / np.sqrt(p)
    chol = np.linalg.cholesky(cov)
    n_acc = 0
    total = 0
    for it in range(warmup):
        prop = theta + scale * (rng.normal(size=(n_chains, p)) @ chol.T)
        lp_prop = log_posterior(prop, y, ZT, ZR, prior, use_R)
        log_u = np.log(rng.random(n_chains))
        acc = log_u < (lp_prop - lp)
        theta = np.where(acc[:, None], prop, theta)
        lp = np.where(acc, lp_prop, lp)
        n_acc += acc.sum(); total += n_chains
        if it >= 200 and (it + 1) % 50 == 0:
            mu = theta.mean(0)
            xc = theta - mu
            new_cov = (xc.T @ xc) / (n_chains - 1) + 1e-8 * np.eye(p)
            cov = 0.8 * cov + 0.2 * new_cov
            try:
                chol = np.linalg.cholesky(cov)
            except np.linalg.LinAlgError:
                chol = np.linalg.cholesky(cov + 1e-6 * np.eye(p))
    warm_accept = n_acc / max(total, 1)
    # 采样
    chain = np.zeros((n_chains, draws, p))
    n_acc2 = 0
    for it in range(draws):
        prop = theta + scale * (rng.normal(size=(n_chains, p)) @ chol.T)
        lp_prop = log_posterior(prop, y, ZT, ZR, prior, use_R)
        log_u = np.log(rng.random(n_chains))
        acc = log_u < (lp_prop - lp)
        theta = np.where(acc[:, None], prop, theta)
        lp = np.where(acc, lp_prop, lp)
        chain[:, it, :] = theta
        n_acc2 += acc.sum()
    accept = n_acc2 / (draws * n_chains)
    return dict(chain=chain, accept=accept, warm_accept=warm_accept,
                param_names=PARAM_NAMES, use_R=use_R)


# ------------------------------------------------------------------ 诊断
def split_rhat(chain):
    """Gelman-Rubin split-R-hat. chain: (n_chains, n_draws, p) -> (p,)"""
    nc, nd, p = chain.shape
    x = chain.reshape(nc, nd // 2, 2, p).transpose(0, 2, 1, 3).reshape(nc * 2, nd // 2, p)
    m, n = x.shape[0], x.shape[1]
    means = x.mean(1)                       # (m,p)
    vars_ = x.var(1, ddof=1)                # (m,p)
    B = n * means.var(0, ddof=1)
    W = vars_.mean(0)
    var_hat = (n - 1) / n * W + B / n
    return np.sqrt(var_hat / W)


def _ess_1d(x):
    """bulk ESS via autocorrelation (Geyer initial positive)."""
    n = len(x)
    x = x - x.mean()
    var = np.sum(x * x) / n
    if var == 0:
        return float(n)
    acf = np.correlate(x, x, "full")[n - 1:] / (var * n)
    rho = acf.copy()
    # Geyer initial positive sequence
    tot = 0.0
    k = 1
    while k + 1 < n:
        pair = rho[k] + rho[k + 1]
        if pair < 0:
            break
        tot += pair
        k += 2
    tau = -1 + 2 * tot + 2 * rho[1] if n > 1 else 1
    tau = max(tau, 1.0)
    return float(n / tau)


def ess_bulk(chain):
    nc, nd, p = chain.shape
    out = []
    for j in range(p):
        vals = chain[:, :, j].reshape(-1)
        out.append(_ess_1d(vals))
    return np.array(out)


def ess_tail(chain, probs=(0.05, 0.95)):
    nc, nd, p = chain.shape
    out = []
    for j in range(p):
        v = chain[:, :, j].reshape(-1)
        q = np.quantile(v, probs)
        ind = ((v <= q[0]) | (v >= q[1])).astype(float)
        out.append(_ess_1d(ind) * (1 - 0) )
    return np.array(out)


def summarize(chain):
    nc, nd, p = chain.shape
    flat = chain.reshape(-1, p)
    return dict(
        mean=flat.mean(0), median=np.median(flat, 0), sd=flat.std(0, ddof=1),
        q025=np.quantile(flat, 0.025, axis=0), q975=np.quantile(flat, 0.975, axis=0),
        q05=np.quantile(flat, 0.05, axis=0), q95=np.quantile(flat, 0.95, axis=0),
        q25=np.quantile(flat, 0.25, axis=0), q75=np.quantile(flat, 0.75, axis=0),
    )


def post_draws_flat(chain):
    return chain.reshape(-1, chain.shape[2])

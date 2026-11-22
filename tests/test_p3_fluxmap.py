"""P3(엔진 쪽): FluxMapModel — 자속 맵 CSV를 읽어 보간하는 모델 (docs/ENGINE_SPEC.md 2장).

CSV는 전부 **테스트용 합성 데이터**다 (ConstantParamModel 또는 포화를 흉내 낸 식에서 생성).
핵심 검증: 상수 모델을 격자로 찍은 CSV는 선형 보간이 정확히 재현하므로, FluxMapModel을 쓴 결과가
ConstantParamModel 결과와 같아야 한다. 그러면 operating.py가 모델 종류와 무관하다는 것이 확인된다.
"""
import numpy as np
import pytest

from engine.model import FluxMapModel
from engine.operating import (
    base_speed,
    max_torque_curve,
    mtpa_point,
    optimal_current,
    optimal_current_map,
)

from conftest import IMAX, LD, LQ, P, PSI_M, RS

COMMENT = "# 출처: 합성 테스트 데이터 (ConstantParamModel 또는 포화 모사식에서 생성)\n# 단위: A, Wb, N·m\n"


def write_csv(path, flux_fn, step=5.0, torque_fn=None, comment=COMMENT, shuffle=True):
    axis = np.arange(-IMAX, IMAX + step / 2, step)
    gd, gq = np.meshgrid(axis, axis, indexing="ij")
    id_, iq = gd.ravel(), gq.ravel()
    psi_d, psi_q = flux_fn(id_, iq)
    cols, header = [id_, iq, psi_d, psi_q], "id_A,iq_A,psi_d_Wb,psi_q_Wb"
    if torque_fn is not None:
        cols.append(torque_fn(id_, iq))
        header += ",torque_Nm"
    rows = np.column_stack(cols)
    if shuffle:  # 행 순서에 의존하지 않아야 한다
        rows = rows[np.random.default_rng(0).permutation(len(rows))]
    with open(path, "w") as f:
        f.write(comment + header + "\n")
        np.savetxt(f, rows, delimiter=",", fmt="%.17g")
    return path


@pytest.fixture
def fm_rs(tmp_path, model_rs):
    return FluxMapModel.from_csv(write_csv(tmp_path / "rs.csv", model_rs.flux), p=P, Rs=RS)


def test_matches_constant_model(fm_rs, model_rs):
    rng = np.random.default_rng(3)
    id_, iq = rng.uniform(-IMAX, IMAX, 300), rng.uniform(-IMAX, IMAX, 300)
    we = rng.uniform(0, 6000, 300)
    for a, b in zip(fm_rs.flux(id_, iq), model_rs.flux(id_, iq)):
        np.testing.assert_allclose(a, b, rtol=1e-9, atol=1e-12)
    np.testing.assert_allclose(fm_rs.torque(id_, iq), model_rs.torque(id_, iq), rtol=1e-9, atol=1e-9)
    for a, b in zip(fm_rs.voltage(id_, iq, we), model_rs.voltage(id_, iq, we)):
        np.testing.assert_allclose(a, b, rtol=1e-9, atol=1e-9)


def test_scalar_input_returns_scalar_shape(fm_rs):
    psi_d, psi_q = fm_rs.flux(-100.0, 150.0)
    assert np.shape(psi_d) == () and np.shape(psi_q) == ()


def test_out_of_grid_is_an_error(fm_rs):
    with pytest.raises(ValueError, match="격자"):
        fm_rs.flux(-IMAX * 1.01, 0.0)
    with pytest.raises(ValueError, match="격자"):
        fm_rs.flux(0.0, IMAX + 1.0)
    fm_rs.flux(-IMAX * (1 + 1e-12), IMAX)  # 부동소수점 오차 수준은 허용


def test_csv_validation(tmp_path, model0):
    ok = write_csv(tmp_path / "ok.csv", model0.flux)
    FluxMapModel.from_csv(ok, p=P, Rs=0.0)

    no_comment = write_csv(tmp_path / "nc.csv", model0.flux, comment="")
    with pytest.raises(ValueError, match="출처"):
        FluxMapModel.from_csv(no_comment, p=P, Rs=0.0)

    lines = open(ok).read().splitlines()
    (tmp_path / "bad_col.csv").write_text("\n".join(l.replace("psi_q_Wb", "psi_x") for l in lines))
    with pytest.raises(ValueError, match="열"):
        FluxMapModel.from_csv(tmp_path / "bad_col.csv", p=P, Rs=0.0)

    (tmp_path / "gap.csv").write_text("\n".join(lines[:-1]) + "\n")  # 격자점 하나 빠짐
    with pytest.raises(ValueError, match="격자"):
        FluxMapModel.from_csv(tmp_path / "gap.csv", p=P, Rs=0.0)


def test_optional_fea_torque_column(tmp_path, model0):
    f = write_csv(tmp_path / "t.csv", model0.flux, torque_fn=model0.torque)
    m = FluxMapModel.from_csv(f, p=P, Rs=0.0)
    assert m.torque_fea is not None and m.torque_fea.shape == (m.id_axis.size, m.iq_axis.size)
    i, j = 60, 70
    assert m.torque_fea[i, j] == pytest.approx(float(model0.torque(m.id_axis[i], m.iq_axis[j])), rel=1e-12)
    assert FluxMapModel.from_csv(write_csv(tmp_path / "n.csv", model0.flux), p=P, Rs=0.0).torque_fea is None


# --- operating.py가 모델 종류와 무관하게 같은 답을 내는가 -------------------------------------
def test_operating_functions_agree_with_constant_model(fm_rs, model_rs, limits):
    Is = np.array([20.0, 100.0, 250.0])
    for a, b in zip(mtpa_point(fm_rs, Is), mtpa_point(model_rs, Is)):
        np.testing.assert_allclose(a, b, rtol=1e-6, atol=1e-6)
    assert base_speed(fm_rs, limits) == pytest.approx(base_speed(model_rs, limits), rel=1e-8)

    speeds = np.linspace(10.0, 1300.0, 30)
    a, b = max_torque_curve(fm_rs, limits, speeds), max_torque_curve(model_rs, limits, speeds)
    assert list(a.mode) == list(b.mode) and list(a.feasible) == list(b.feasible)
    f = b.feasible
    np.testing.assert_allclose(a.T_max[f], b.T_max[f], rtol=1e-5)

    T = np.array([20.0, 60.0, 100.0])
    sp = np.array([200.0, 900.0])
    ia, qa, fa = optimal_current_map(fm_rs, limits, T, sp)
    ib, qb, fb = optimal_current_map(model_rs, limits, T, sp)
    assert (fa == fb).all()
    np.testing.assert_allclose(ia[fa], ib[fb], rtol=1e-5, atol=1e-5)
    np.testing.assert_allclose(qa[fa], qb[fb], rtol=1e-5, atol=1e-5)


# --- 포화·교차결합이 있는 모델 (합성) ---------------------------------------------------------
def saturating_flux(id_, iq):
    """전류가 커질수록 인덕턴스가 줄고, d·q가 서로 영향을 주는 합성 모델 (실제 모터 아님)."""
    s = 1.0 / np.sqrt(1.0 + (np.hypot(id_, iq) / 400.0) ** 2)
    return PSI_M + LD * id_ * s, LQ * iq * s


@pytest.fixture
def fm_sat(tmp_path):
    return FluxMapModel.from_csv(write_csv(tmp_path / "sat.csv", saturating_flux), p=P, Rs=RS)


def test_saturating_map_power_balance(fm_sat):
    """P = Te·ωm + 1.5·Rs·I²는 자속이 어떤 함수여도 성립해야 한다 (derivations.md 2절)."""
    rng = np.random.default_rng(4)
    id_, iq, wm = rng.uniform(-250, 0, 100), rng.uniform(0, 250, 100), rng.uniform(0, 1500, 100)
    vd, vq = fm_sat.voltage(id_, iq, P * wm)
    lhs = 1.5 * (vd * id_ + vq * iq)
    rhs = fm_sat.torque(id_, iq) * wm + 1.5 * fm_sat.Rs * (id_**2 + iq**2)
    np.testing.assert_allclose(lhs, rhs, rtol=1e-9, atol=1e-6)


def test_saturating_map_torque_curve_is_feasible_and_lower(fm_sat, model_rs, limits):
    speeds = np.linspace(10.0, 1100.0, 40)
    tab = max_torque_curve(fm_sat, limits, speeds)
    ref = max_torque_curve(model_rs, limits, speeds)
    f = tab.feasible
    assert f.sum() > 30
    T = tab.T_max[f]
    assert np.all(np.diff(T) <= 1e-6 * T.max())
    assert np.all(np.hypot(tab.id[f], tab.iq[f]) <= IMAX * (1 + 1e-6))
    vd, vq = fm_sat.voltage(tab.id[f], tab.iq[f], P * tab.speed[f])
    assert np.all(np.hypot(vd, vq) <= limits.Vmax * (1 + 1e-6))
    # 포화로 릴럭턴스 토크가 줄어 일정 토크 구간 최대 토크가 상수 모델보다 작다
    assert tab.T_max[0] < ref.T_max[0]


def test_saturating_map_map_vs_scalar_optimal_current(fm_sat, limits):
    T = np.array([20.0, 60.0, 100.0])
    sp = np.array([200.0, 700.0])
    id_, iq, feas = optimal_current_map(fm_sat, limits, T, sp)
    for i, t in enumerate(T):
        for j, w in enumerate(sp):
            d, q, ok = optimal_current(fm_sat, limits, t, w)
            assert ok == feas[i, j]
            if ok:
                assert np.hypot(id_[i, j], iq[i, j]) == pytest.approx(np.hypot(d, q), rel=2e-3)
